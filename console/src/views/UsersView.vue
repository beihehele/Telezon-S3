<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { http } from '@/api/http'
import { ElMessage, ElMessageBox } from 'element-plus'
import { zhCN } from '@/locales/zh-CN'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
const users = ref<any[]>([])
const createOpen = ref(false)
const editOpen = ref(false)
const editUsername = ref('')
const formCreate = ref({ username: '', email: '', password: '' })
const formEdit = ref({ email: '', password: '', role: 'user' })

async function load() {
  const { data } = await http.get('/v1/users/', { params: { limit: 200 } })
  users.value = data
}

onMounted(load)

async function createUser() {
  await http.post('/v1/users/', formCreate.value)
  ElMessage.success('用户已创建')
  createOpen.value = false
  formCreate.value = { username: '', email: '', password: '' }
  await load()
}

function openEdit(row: any) {
  editUsername.value = row.username
  formEdit.value = { email: row.email, password: '', role: row.role || 'user' }
  editOpen.value = true
}

async function saveEdit() {
  const body: Record<string, string> = {
    email: formEdit.value.email,
    role: formEdit.value.role,
  }
  if (formEdit.value.password) {
    body.password = formEdit.value.password
  }
  await http.put(`/v1/users/${encodeURIComponent(editUsername.value)}`, body)
  ElMessage.success('已保存')
  editOpen.value = false
  await load()
}

async function removeUser(row: any) {
  if (row.username === auth.user?.username) {
    ElMessage.warning('不能删除当前登录用户')
    return
  }
  await ElMessageBox.confirm(zhCN.confirmDeleteUser)
  await http.delete(`/v1/users/${encodeURIComponent(row.username)}`)
  ElMessage.success('已删除')
  await load()
}
</script>

<template>
  <div>
    <el-button type="primary" @click="createOpen = true">{{ zhCN.createUser }}</el-button>
    <el-table :data="users" style="margin-top: 1rem">
      <el-table-column prop="username" :label="zhCN.username" />
      <el-table-column prop="email" :label="zhCN.email" />
      <el-table-column prop="role" :label="zhCN.role" width="100" />
      <el-table-column label="操作" width="160">
        <template #default="{ row }">
          <el-button link @click="openEdit(row)">编辑</el-button>
          <el-button link type="danger" @click="removeUser(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="createOpen" :title="zhCN.createUser" width="420px">
      <el-form label-width="80px">
        <el-form-item :label="zhCN.username">
          <el-input v-model="formCreate.username" />
        </el-form-item>
        <el-form-item :label="zhCN.email">
          <el-input v-model="formCreate.email" />
        </el-form-item>
        <el-form-item :label="zhCN.password">
          <el-input v-model="formCreate.password" type="password" show-password />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="createOpen = false">取消</el-button>
        <el-button type="primary" @click="createUser">创建</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="editOpen" :title="zhCN.editUser" width="420px">
      <el-form label-width="80px">
        <el-form-item :label="zhCN.username">
          <el-input :model-value="editUsername" disabled />
        </el-form-item>
        <el-form-item :label="zhCN.email">
          <el-input v-model="formEdit.email" />
        </el-form-item>
        <el-form-item :label="zhCN.password">
          <el-input
            v-model="formEdit.password"
            type="password"
            show-password
            placeholder="留空不修改"
          />
        </el-form-item>
        <el-form-item :label="zhCN.role">
          <el-select v-model="formEdit.role">
            <el-option label="user" value="user" />
            <el-option label="admin" value="admin" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="editOpen = false">取消</el-button>
        <el-button type="primary" @click="saveEdit">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>
