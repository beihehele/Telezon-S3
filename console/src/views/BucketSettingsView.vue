<script setup lang="ts">
import { ref, watch, computed } from 'vue'
import { http } from '@/api/http'
import { ElMessage } from 'element-plus'

const props = defineProps<{ bucket?: string }>()
const bucketName = computed(() => props.bucket || '')
const form = ref({ is_public: false, telegram_chat_id: '', telegram_topic_id: '' })

async function load() {
  if (!bucketName.value) return
  const { data } = await http.get(`/v1/buckets/${encodeURIComponent(bucketName.value)}`)
  form.value.is_public = !!data.is_public
  form.value.telegram_chat_id = data.telegram_chat_id || ''
  form.value.telegram_topic_id = data.telegram_topic_id ? String(data.telegram_topic_id) : ''
}

watch(bucketName, load, { immediate: true })

async function save() {
  await http.put(`/v1/buckets/${encodeURIComponent(bucketName.value)}`, {
    is_public: form.value.is_public,
    telegram_chat_id: form.value.telegram_chat_id || null,
    telegram_topic_id: form.value.telegram_topic_id
      ? Number(form.value.telegram_topic_id)
      : null,
  })
  ElMessage.success('已保存')
}
</script>

<template>
  <el-form label-width="140px" style="max-width: 480px">
    <el-form-item label="公开读">
      <el-switch v-model="form.is_public" />
    </el-form-item>
    <el-form-item label="Telegram Chat ID">
      <el-input v-model="form.telegram_chat_id" />
    </el-form-item>
    <el-form-item label="Topic ID">
      <el-input v-model="form.telegram_topic_id" />
    </el-form-item>
    <el-button type="primary" @click="save">保存</el-button>
  </el-form>
</template>
