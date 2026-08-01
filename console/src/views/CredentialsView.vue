<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { http } from '@/api/http'
import { ElMessage } from 'element-plus'

const items = ref<any[]>([])
const secretOnce = ref('')
const createOpen = ref(false)
const buckets = ref<{ name: string }[]>([])
const form = ref({
  label: 'console',
  role: 'readonly',
  buckets: [] as string[],
})

onMounted(async () => {
  const [creds, bucketList] = await Promise.all([
    http.get('/v1/credentials/'),
    http.get<{ name: string }[]>('/v1/buckets/', { params: { limit: 100 } }),
  ])
  items.value = creds.data
  buckets.value = bucketList.data
})

async function createKey() {
  const { data } = await http.post('/v1/credentials/', {
    label: form.value.label,
    role: form.value.role,
    buckets: form.value.buckets,
  })
  secretOnce.value = data.secret_key
  items.value.push(data)
  createOpen.value = false
  ElMessage.success('已创建，请保存 Secret')
}

async function removeKey(id: string) {
  await http.delete(`/v1/credentials/${id}`)
  items.value = items.value.filter((c) => c.access_key_id !== id)
}
</script>

<template>
  <div>
    <el-button type="primary" @click="createOpen = true">新建密钥</el-button>
    <el-alert
      v-if="secretOnce"
      type="warning"
      :title="`Secret（仅显示一次）: ${secretOnce}`"
      style="margin-top: 0.75rem"
    />
    <el-table :data="items" style="margin-top: 1rem">
      <el-table-column prop="access_key_id" label="Access Key" />
      <el-table-column prop="label" label="标签" />
      <el-table-column prop="role" label="权限" width="100" />
      <el-table-column label="桶范围">
        <template #default="{ row }">
          {{ row.buckets?.length ? row.buckets.join(', ') : '全部' }}
        </template>
      </el-table-column>
      <el-table-column label="操作" width="120">
        <template #default="{ row }">
          <el-button link type="danger" @click="removeKey(row.access_key_id)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="createOpen" title="新建子账号密钥" width="480px">
      <el-form label-width="100px">
        <el-form-item label="标签">
          <el-input v-model="form.label" />
        </el-form-item>
        <el-form-item label="权限">
          <el-select v-model="form.role">
            <el-option label="只读 readonly" value="readonly" />
            <el-option label="读写 readwrite" value="readwrite" />
          </el-select>
        </el-form-item>
        <el-form-item label="限定桶">
          <el-select v-model="form.buckets" multiple clearable placeholder="留空=全部可访问桶">
            <el-option v-for="b in buckets" :key="b.name" :label="b.name" :value="b.name" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="createOpen = false">取消</el-button>
        <el-button type="primary" @click="createKey">创建</el-button>
      </template>
    </el-dialog>
  </div>
</template>
