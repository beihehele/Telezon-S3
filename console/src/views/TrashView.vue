<script setup lang="ts">
import { ref, watch, computed } from 'vue'
import { http } from '@/api/http'
import { zhCN } from '@/locales/zh-CN'
import { ElMessage } from 'element-plus'

const props = defineProps<{ bucket?: string }>()
const items = ref<any[]>([])
const bucketName = computed(() => props.bucket || '')

async function load() {
  if (!bucketName.value) return
  const { data } = await http.get('/v1/trash/', { params: { bucket: bucketName.value } })
  items.value = data
}

watch(bucketName, load, { immediate: true })

async function restore(row: any) {
  await http.post('/v1/trash/restore', { trash_id: row.trash_id })
  ElMessage.success('已恢复')
  await load()
}

async function purge(row: any) {
  await http.delete(`/v1/trash/${row.trash_id}`)
  ElMessage.success('已永久删除')
  await load()
}
</script>

<template>
  <el-table :data="items" v-if="items.length">
    <el-table-column prop="key" label="对象" />
    <el-table-column prop="size" label="大小" width="100" />
    <el-table-column label="操作" width="200">
      <template #default="{ row }">
        <el-button link @click="restore(row)">{{ zhCN.restore }}</el-button>
        <el-button link type="danger" @click="purge(row)">{{ zhCN.purge }}</el-button>
      </template>
    </el-table-column>
  </el-table>
  <el-empty v-else :description="zhCN.empty" />
</template>
