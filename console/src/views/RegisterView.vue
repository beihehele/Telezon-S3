<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { http } from '@/api/http'
import { useAuthPublicConfig } from '@/composables/useAuthConfig'
import { zhCN } from '@/locales/zh-CN'
import { ElMessage } from 'element-plus'

const router = useRouter()
const { load } = useAuthPublicConfig()
const username = ref('')
const email = ref('')
const password = ref('')
const loading = ref(false)

onMounted(async () => {
  const ok = await load()
  if (!ok) {
    ElMessage.warning('未开放自助注册')
    await router.replace('/login')
  }
})

async function onSubmit() {
  loading.value = true
  try {
    await http.post('/auth/signup', {
      username: username.value,
      email: email.value,
      password: password.value,
    })
    ElMessage.success('注册成功，请登录')
    await router.push('/login')
  } catch {
    ElMessage.error('注册失败（用户名或邮箱可能已存在）')
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="login-wrap">
    <el-card class="login-card">
      <h1>{{ zhCN.signupTitle }}</h1>
      <el-form @submit.prevent="onSubmit">
        <el-form-item :label="zhCN.username">
          <el-input v-model="username" autocomplete="username" />
        </el-form-item>
        <el-form-item :label="zhCN.email">
          <el-input v-model="email" type="email" autocomplete="email" />
        </el-form-item>
        <el-form-item :label="zhCN.password">
          <el-input v-model="password" type="password" autocomplete="new-password" show-password />
        </el-form-item>
        <el-button type="primary" native-type="submit" :loading="loading" block>
          {{ zhCN.signup }}
        </el-button>
        <router-link class="link" to="/login">{{ zhCN.backToLogin }}</router-link>
      </el-form>
    </el-card>
  </div>
</template>

<style scoped>
.login-wrap {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 1rem;
  background: var(--el-bg-color-page);
}
.login-card {
  width: 100%;
  max-width: 400px;
}
.link {
  display: block;
  margin-top: 1rem;
  text-align: center;
  font-size: 0.9rem;
}
</style>
