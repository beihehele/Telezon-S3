<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { useAuthPublicConfig } from '@/composables/useAuthConfig'
import { zhCN } from '@/locales/zh-CN'
import { ElMessage } from 'element-plus'

const auth = useAuthStore()
const router = useRouter()
const { allowSignup, load } = useAuthPublicConfig()
const username = ref('')
const password = ref('')

onMounted(() => load())

async function onSubmit() {
  try {
    await auth.login(username.value, password.value)
    await router.push('/files')
  } catch {
    ElMessage.error('登录失败')
  }
}
</script>

<template>
  <div class="login-wrap">
    <el-card class="login-card">
      <h1>{{ zhCN.appTitle }}</h1>
      <el-form @submit.prevent="onSubmit">
        <el-form-item :label="zhCN.username">
          <el-input id="login-username" v-model="username" autocomplete="username" />
        </el-form-item>
        <el-form-item :label="zhCN.password">
          <el-input
            id="login-password"
            v-model="password"
            type="password"
            autocomplete="current-password"
          />
        </el-form-item>
        <el-button type="primary" native-type="submit" :loading="auth.loading" block>
          {{ zhCN.login }}
        </el-button>
        <router-link v-if="allowSignup" class="link" to="/register">{{ zhCN.hasAccount }}</router-link>
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
