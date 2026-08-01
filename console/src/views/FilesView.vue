<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { http, getToken } from '@/api/http'
import { zhCN } from '@/locales/zh-CN'
import { presignGet, presignPut, contentUrl, createContentTicket } from '@/composables/usePresign'
import { uploadMultipart } from '@/composables/useMultipart'
import { formatBytes } from '@/utils/format'
import ShareCreateDialog from '@/components/ShareCreateDialog.vue'
import { ElMessage, ElMessageBox } from 'element-plus'

const props = defineProps<{ bucket?: string }>()
const route = useRoute()
const bucketName = computed(() => props.bucket || (route.query.bucket as string) || '')
const prefix = ref('')
const rows = ref<any[]>([])
const prefixes = ref<string[]>([])
const loading = ref(false)
const selected = ref<string[]>([])
const previewKey = ref('')
const previewKind = ref<'image' | 'video' | 'other'>('other')
const previewUrl = ref('')
const previewOpen = ref(false)
const previewMode = ref<'jwt' | 'presign'>('jwt')
const mpuOpen = ref(false)
const mpuPct = ref(0)
const shareOpen = ref(false)
const shareKey = ref('')

const breadcrumbs = computed(() => {
  const parts = prefix.value.split('/').filter(Boolean)
  const crumbs = [{ label: '/', path: '' }]
  let acc = ''
  for (const p of parts) {
    acc += p + '/'
    crumbs.push({ label: p, path: acc })
  }
  return crumbs
})

async function load() {
  if (!bucketName.value) {
    return
  }
  loading.value = true
  try {
    const { data } = await http.get(`/v1/buckets/${encodeURIComponent(bucketName.value)}/objects`, {
      params: { prefix: prefix.value, delimiter: '/' },
    })
    rows.value = data.contents || []
    prefixes.value = data.common_prefixes || []
  } finally {
    loading.value = false
  }
}

watch(bucketName, load, { immediate: true })
watch(prefix, load)

function enterFolder(p: string) {
  prefix.value = p
}

async function onUpload(file: File) {
  const key = prefix.value + file.name
  try {
    if (file.size > 80 * 1024 * 1024) {
      mpuOpen.value = true
      mpuPct.value = 0
      await uploadMultipart(bucketName.value, key, file, undefined, (p) => {
        mpuPct.value = p
      })
      mpuOpen.value = false
    } else {
      const url = await presignPut(bucketName.value, key)
      const res = await fetch(url, { method: 'PUT', body: file })
      if (!res.ok) {
        throw new Error('upload failed')
      }
    }
    ElMessage.success('上传成功')
    await load()
  } catch {
    ElMessage.error('上传失败')
    mpuOpen.value = false
  }
  return false
}

async function downloadKey(key: string) {
  const url = await presignGet(bucketName.value, key)
  window.open(url, '_blank')
}

async function removeSelected() {
  await ElMessageBox.confirm(zhCN.confirmDelete)
  await http.post(
    `/v1/buckets/${encodeURIComponent(bucketName.value)}/objects/batch-delete`,
    { keys: selected.value },
  )
  selected.value = []
  await load()
}

async function preview(key: string) {
  previewKey.value = key
  const lower = key.toLowerCase()
  if (/\.(mp4|webm)$/i.test(lower)) {
    previewKind.value = 'video'
  } else if (/\.(png|jpe?g|gif|webp)$/i.test(lower)) {
    previewKind.value = 'image'
  } else {
    previewKind.value = 'other'
  }
  if (previewMode.value === 'jwt') {
    if (previewKind.value === 'video') {
      const ticket = await createContentTicket(bucketName.value, key)
      previewUrl.value = contentUrl(bucketName.value, key, true, ticket)
    } else {
      const res = await fetch(contentUrl(bucketName.value, key, true), {
        headers: { Authorization: `Bearer ${getToken()}` },
      })
      if (!res.ok) {
        ElMessage.error('预览失败')
        return
      }
      previewUrl.value = URL.createObjectURL(await res.blob())
    }
  } else {
    previewUrl.value = await presignGet(bucketName.value, key)
  }
  previewOpen.value = true
}

function isPreviewable(key: string) {
  const lower = key.toLowerCase()
  return /\.(png|jpe?g|gif|webp|mp4|webm|mp3|wav|txt|md|json)$/.test(lower)
}

function openShare(key: string) {
  shareKey.value = key
  shareOpen.value = true
}

async function renameKey(key: string) {
  const base = key.includes('/') ? key.replace(/\/[^/]+$/, '/') : ''
  const name = key.slice(base.length)
  const { value } = await ElMessageBox.prompt(zhCN.renameTo, zhCN.rename, {
    inputValue: name,
    inputValidator: (v) => (v && v.trim() ? true : '名称不能为空'),
  })
  const toKey = base + String(value).trim()
  if (toKey === key) {
    return
  }
  await http.post(`/v1/buckets/${encodeURIComponent(bucketName.value)}/objects/rename`, {
    from: key,
    to: toKey,
  })
  ElMessage.success('已重命名')
  await load()
}
</script>

<template>
  <div>
    <el-breadcrumb separator="/">
      <el-breadcrumb-item
        v-for="c in breadcrumbs"
        :key="c.path"
        @click="prefix = c.path"
        style="cursor: pointer"
      >
        {{ c.label }}
      </el-breadcrumb-item>
    </el-breadcrumb>
    <div class="toolbar">
      <el-upload :show-file-list="false" :before-upload="onUpload">
        <el-button type="primary">{{ zhCN.upload }}</el-button>
      </el-upload>
      <el-button :disabled="!selected.length" type="danger" @click="removeSelected">
        {{ zhCN.delete }}
      </el-button>
      <el-button @click="load">{{ zhCN.refresh }}</el-button>
      <el-radio-group v-model="previewMode" size="small">
        <el-radio-button value="jwt">{{ zhCN.previewJwt }}</el-radio-button>
        <el-radio-button value="presign">{{ zhCN.previewPresign }}</el-radio-button>
      </el-radio-group>
    </div>
    <p class="hint">{{ zhCN.previewTip }}</p>
    <el-table
      v-loading="loading"
      :data="[
        ...prefixes.map((p) => ({ key: p, folder: true, size: 0 })),
        ...rows.map((r) => ({ ...r, folder: false })),
      ]"
      @selection-change="(s: any[]) => (selected = s.filter((x) => !x.folder).map((x) => x.key))"
    >
      <el-table-column type="selection" width="48" />
      <el-table-column label="名称">
        <template #default="{ row }">
          <a v-if="row.folder" href="#" @click.prevent="enterFolder(row.key)">{{ row.key }}</a>
          <span v-else>{{ row.key }}</span>
        </template>
      </el-table-column>
      <el-table-column label="大小" width="100">
        <template #default="{ row }">
          <span v-if="!row.folder">{{ formatBytes(row.size) }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="last_modified" label="修改时间" width="180" />
      <el-table-column label="操作" width="280">
        <template #default="{ row }">
          <template v-if="!row.folder">
            <el-button v-if="isPreviewable(row.key)" link @click="preview(row.key)">
              {{ zhCN.preview }}
            </el-button>
            <el-button link @click="downloadKey(row.key)">{{ zhCN.download }}</el-button>
            <el-button link @click="openShare(row.key)">{{ zhCN.share }}</el-button>
            <el-button link @click="renameKey(row.key)">{{ zhCN.rename }}</el-button>
          </template>
        </template>
      </el-table-column>
    </el-table>
    <el-dialog v-model="previewOpen" width="80%" destroy-on-close>
      <video v-if="previewKind === 'video'" :src="previewUrl" controls style="width: 100%" />
      <img v-else-if="previewKind === 'image'" :src="previewUrl" style="max-width: 100%" />
    </el-dialog>
    <el-dialog v-model="mpuOpen" :title="zhCN.uploadMpu" :close-on-click-modal="false">
      <el-progress :percentage="mpuPct" />
    </el-dialog>
    <ShareCreateDialog
      v-model="shareOpen"
      :bucket="bucketName"
      :object-key="shareKey"
    />
  </div>
</template>

<style scoped>
.toolbar {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  margin: 0.75rem 0;
}
.hint {
  color: var(--el-text-color-secondary);
  font-size: 0.85rem;
}
</style>
