<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { http } from '@/api/http'
import { ElMessage } from 'element-plus'
import { zhCN } from '@/locales/zh-CN'

const props = defineProps<{
  modelValue: boolean
  bucket?: string
  objectKey?: string
}>()

const emit = defineEmits<{
  'update:modelValue': [boolean]
  created: []
}>()

const visible = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v),
})

const bucketLocal = ref('')
const keyLocal = ref('')
const password = ref('')
const expiresHours = ref(24)
const maxDownloads = ref<number | undefined>(undefined)
const lastLink = ref('')
const saving = ref(false)

const bucketLocked = computed(() => !!props.bucket)
const keyLocked = computed(() => !!props.objectKey)

watch(visible, (open) => {
  if (open) {
    bucketLocal.value = props.bucket || ''
    keyLocal.value = props.objectKey || ''
    password.value = ''
    expiresHours.value = 24
    maxDownloads.value = undefined
    lastLink.value = ''
  }
})

function shareLink(token: string) {
  return `${window.location.origin}/share/${token}`
}

async function submit() {
  if (!bucketLocal.value || !keyLocal.value) {
    ElMessage.warning('请填写桶与对象键')
    return
  }
  saving.value = true
  try {
    const { data } = await http.post('/v1/shares/', {
      bucket: bucketLocal.value,
      key: keyLocal.value,
      password: password.value || null,
      expires_in: Math.max(60, expiresHours.value * 3600),
      max_downloads:
        maxDownloads.value && maxDownloads.value > 0 ? maxDownloads.value : null,
    })
    lastLink.value = shareLink(data.token)
    ElMessage.success('分享已创建')
    emit('created')
  } catch {
    ElMessage.error('创建分享失败')
  } finally {
    saving.value = false
  }
}

async function copyLink() {
  if (!lastLink.value) {
    return
  }
  await navigator.clipboard.writeText(lastLink.value)
  ElMessage.success('链接已复制')
}
</script>

<template>
  <el-dialog v-model="visible" :title="zhCN.shareCreate" width="480px" destroy-on-close>
    <el-form label-width="110px">
      <el-form-item label="桶">
        <el-input v-model="bucketLocal" :disabled="bucketLocked" />
      </el-form-item>
      <el-form-item label="对象键">
        <el-input v-model="keyLocal" :disabled="keyLocked" />
      </el-form-item>
      <el-form-item :label="zhCN.sharePassword">
        <el-input v-model="password" type="password" show-password autocomplete="new-password" />
      </el-form-item>
      <el-form-item :label="zhCN.shareExpires">
        <el-input-number v-model="expiresHours" :min="1" :max="168" />
        <span class="unit">小时</span>
      </el-form-item>
      <el-form-item :label="zhCN.shareMaxDownloads">
        <el-input-number v-model="maxDownloads" :min="1" :max="10000" />
        <span class="unit">留空不限</span>
      </el-form-item>
    </el-form>
    <el-alert v-if="lastLink" type="success" :title="lastLink" class="link-alert" />
    <template #footer>
      <el-button v-if="lastLink" @click="copyLink">{{ zhCN.copyLink }}</el-button>
      <el-button @click="visible = false">关闭</el-button>
      <el-button type="primary" :loading="saving" @click="submit">创建</el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
.unit {
  margin-left: 0.5rem;
  color: var(--el-text-color-secondary);
  font-size: 0.85rem;
}
.link-alert {
  margin-top: 0.5rem;
  word-break: break-all;
}
</style>
