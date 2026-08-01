<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { http } from '@/api/http'
import { ElMessage } from 'element-plus'
import { zhCN } from '@/locales/zh-CN'
import { formatDateTime } from '@/utils/format'
import ShareCreateDialog from '@/components/ShareCreateDialog.vue'

const items = ref<any[]>([])
const createOpen = ref(false)

async function load() {
  const { data } = await http.get('/v1/shares/')
  items.value = data
}

onMounted(load)

function shareLink(token: string) {
  return `${window.location.origin}/share/${token}`
}

async function copyToken(token: string) {
  await navigator.clipboard.writeText(shareLink(token))
  ElMessage.success('链接已复制')
}

async function revoke(token: string) {
  await http.delete(`/v1/shares/${token}`)
  ElMessage.success('已撤销')
  await load()
}
</script>

<template>
  <div>
    <el-button type="primary" @click="createOpen = true">{{ zhCN.shareCreate }}</el-button>
    <el-table :data="items" style="margin-top: 1rem">
      <el-table-column prop="bucket" label="桶" width="120" />
      <el-table-column prop="key" label="对象" />
      <el-table-column label="过期时间" width="170">
        <template #default="{ row }">
          {{ formatDateTime(row.expires_at) }}
        </template>
      </el-table-column>
      <el-table-column prop="download_count" label="下载次数" width="100" />
      <el-table-column label="链接" width="100">
        <template #default="{ row }">
          <el-button link @click="copyToken(row.token)">{{ zhCN.copyLink }}</el-button>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="100">
        <template #default="{ row }">
          <el-button link type="danger" @click="revoke(row.token)">撤销</el-button>
        </template>
      </el-table-column>
    </el-table>
    <ShareCreateDialog v-model="createOpen" @created="load" />
  </div>
</template>
