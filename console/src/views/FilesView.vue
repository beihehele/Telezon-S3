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
const previewLoading = ref(false)
const previewMode = ref<'jwt' | 'presign'>('jwt')
const mpuOpen = ref(false)
const mpuPct = ref(0)
const shareOpen = ref(false)
const shareKey = ref('')
const tableRef = ref<{ clearSelection: () => void } | null>(null)

const tableData = computed(() => [
  ...prefixes.value.map((p) => ({ key: p, folder: true, size: 0, last_modified: '' })),
  ...rows.value.map((r) => ({ ...r, folder: false })),
])

function rowSelectable(row: { folder?: boolean }) {
  return !row.folder
}

function onSelectionChange(rowsSelected: { key: string; folder?: boolean }[]) {
  selected.value = rowsSelected.filter((x) => !x.folder).map((x) => x.key)
}

const CONTENT_PROXY_HINT_BYTES = 8 * 1024 * 1024

function selectedLabel(n: number) {
  return zhCN.selectedCount.replace('{n}', String(n))
}

function displayName(row: { key: string; folder: boolean }) {
  if (row.folder) {
    const parts = row.key.replace(/\/$/, '').split('/')
    return parts[parts.length - 1] ? `${parts[parts.length - 1]}/` : row.key
  }
  const parts = row.key.split('/')
  return parts[parts.length - 1] || row.key
}

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
    selected.value = []
    tableRef.value?.clearSelection()
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
  tableRef.value?.clearSelection()
  await load()
}

function revokePreviewUrl() {
  if (previewUrl.value.startsWith('blob:')) {
    URL.revokeObjectURL(previewUrl.value)
  }
  previewUrl.value = ''
}

function onPreviewDialogClosed() {
  revokePreviewUrl()
  previewLoading.value = false
}

function applyOtherPresignUrl(url: string) {
  previewUrl.value = url
  previewLoading.value = false
  const opened = window.open(url, '_blank', 'noopener,noreferrer')
  if (opened) {
    previewOpen.value = false
    ElMessage.success(zhCN.previewOpenedNewTab)
  } else {
    ElMessage.warning(zhCN.previewOpenBlocked)
  }
}

async function preview(key: string, size = 0) {
  revokePreviewUrl()
  previewKey.value = key
  const lower = key.toLowerCase()
  if (/\.(mp4|webm)$/i.test(lower)) {
    previewKind.value = 'video'
  } else if (/\.(png|jpe?g|gif|webp)$/i.test(lower)) {
    previewKind.value = 'image'
  } else {
    previewKind.value = 'other'
  }
  previewOpen.value = true
  previewLoading.value = true
  const large = size > 80 * 1024 * 1024
  const mode =
    large && previewMode.value === 'jwt' ? 'presign' : previewMode.value
  if (large && mode === 'presign') {
    ElMessage.info('大文件已改用预签名链接预览，便于 Range 从存储拉流')
  }
  try {
    if (mode === 'jwt') {
      if (previewKind.value === 'video' || previewKind.value === 'image') {
        const ticket = await createContentTicket(bucketName.value, key)
        previewUrl.value = contentUrl(bucketName.value, key, true, ticket)
      } else {
        if (size > CONTENT_PROXY_HINT_BYTES) {
          applyOtherPresignUrl(await presignGet(bucketName.value, key))
        } else {
          const res = await fetch(contentUrl(bucketName.value, key, true), {
            headers: { Authorization: `Bearer ${getToken()}` },
          })
          if (!res.ok) {
            throw new Error('preview failed')
          }
          previewUrl.value = URL.createObjectURL(await res.blob())
          previewLoading.value = false
        }
      }
    } else {
      const url = await presignGet(bucketName.value, key)
      if (previewKind.value === 'other') {
        applyOtherPresignUrl(url)
      } else {
        previewUrl.value = url
        previewLoading.value = false
      }
    }
  } catch {
    ElMessage.error('预览失败')
    previewOpen.value = false
    previewLoading.value = false
  }
}

function onPreviewMediaReady() {
  previewLoading.value = false
}

function onPreviewMediaError() {
  previewLoading.value = false
  ElMessage.error('媒体加载失败，可尝试「预签名预览」或下载后本地播放')
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
        {{ zhCN.delete }}<template v-if="selected.length"> ({{ selected.length }})</template>
      </el-button>
      <span v-if="selected.length" class="selected-hint">{{ selectedLabel(selected.length) }}</span>
      <el-button @click="load">{{ zhCN.refresh }}</el-button>
      <el-radio-group v-model="previewMode" size="small">
        <el-radio-button value="jwt">{{ zhCN.previewJwt }}</el-radio-button>
        <el-radio-button value="presign">{{ zhCN.previewPresign }}</el-radio-button>
      </el-radio-group>
    </div>
    <p class="hint">{{ zhCN.previewTip }}</p>
    <div class="files-table-wrap">
    <el-table
      ref="tableRef"
      v-loading="loading"
      row-key="key"
      :data="tableData"
      @selection-change="onSelectionChange"
    >
      <el-table-column type="selection" width="48" :selectable="rowSelectable" />
      <el-table-column label="名称" min-width="200" show-overflow-tooltip>
        <template #default="{ row }">
          <a v-if="row.folder" href="#" @click.prevent="enterFolder(row.key)">{{ displayName(row) }}</a>
          <span v-else>{{ displayName(row) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="大小" width="100">
        <template #default="{ row }">
          <span v-if="!row.folder">{{ formatBytes(row.size) }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="last_modified" label="修改时间" width="180" />
      <el-table-column label="操作" width="280" fixed="right">
        <template #default="{ row }">
          <template v-if="!row.folder">
            <el-button v-if="isPreviewable(row.key)" link @click="preview(row.key, row.size)">
              {{ zhCN.preview }}
            </el-button>
            <el-button link @click="downloadKey(row.key)">{{ zhCN.download }}</el-button>
            <el-button link @click="openShare(row.key)">{{ zhCN.share }}</el-button>
            <el-button link @click="renameKey(row.key)">{{ zhCN.rename }}</el-button>
          </template>
        </template>
      </el-table-column>
    </el-table>
    </div>
    <el-dialog v-model="previewOpen" width="80%" destroy-on-close @closed="onPreviewDialogClosed">
      <div v-loading="previewLoading" style="min-height: 120px">
        <video
          v-if="previewKind === 'video' && previewUrl"
          :src="previewUrl"
          controls
          preload="metadata"
          playsinline
          style="width: 100%; max-height: 70vh"
          @loadeddata="onPreviewMediaReady"
          @canplay="onPreviewMediaReady"
          @error="onPreviewMediaError"
        />
        <img
          v-else-if="previewKind === 'image' && previewUrl"
          :src="previewUrl"
          style="max-width: 100%; max-height: 70vh"
          @load="onPreviewMediaReady"
          @error="onPreviewMediaError"
        />
        <p v-else-if="previewKind === 'other'">
          <template
            v-if="previewUrl && (previewUrl.startsWith('http://') || previewUrl.startsWith('https://'))"
          >
            {{ zhCN.previewOpenBlocked }}
            <el-link :href="previewUrl" target="_blank" rel="noopener noreferrer">
              {{ zhCN.openPreviewLink }}
            </el-link>
          </template>
          <template v-else>{{ zhCN.previewUnsupported }}</template>
        </p>
      </div>
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
.selected-hint {
  color: var(--el-text-color-secondary);
  font-size: 0.85rem;
  align-self: center;
}
.files-table-wrap {
  width: 100%;
  overflow-x: auto;
}
</style>
