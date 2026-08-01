<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter, RouterView } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { useThemeStore } from '@/stores/theme'
import { zhCN } from '@/locales/zh-CN'
import { http } from '@/api/http'
import {
  FolderOpened,
  Delete,
  Share,
  Key,
  Setting,
  User,
  Moon,
  Sunny,
} from '@element-plus/icons-vue'

const auth = useAuthStore()
const theme = useThemeStore()
const router = useRouter()
const route = useRoute()
const healthOk = ref(true)
const buckets = ref<{ name: string }[]>([])
const bucket = ref('')

const active = computed(() => route.name as string)

onMounted(async () => {
  try {
    const h = await http.get('/health')
    healthOk.value = h.status === 200 && h.data?.status !== 'degraded'
  } catch {
    healthOk.value = false
  }
  const { data } = await http.get<{ name: string }[]>('/v1/buckets/', { params: { limit: 100 } })
  buckets.value = data
  if (data.length && !bucket.value) {
    bucket.value = (route.query.bucket as string) || data[0].name
  }
})

watch(bucket, (name) => {
  if (name && route.query.bucket !== name) {
    router.replace({ query: { ...route.query, bucket: name } })
  }
})

function nav(index: string) {
  router.push({ name: index, query: { bucket: bucket.value } })
}

function logout() {
  auth.logout()
  router.push('/login')
}
</script>

<template>
  <el-container class="layout">
    <el-aside width="220px" class="aside">
      <div class="brand">{{ zhCN.appTitle }}</div>
      <el-select v-model="bucket" class="bucket-select" :placeholder="zhCN.bucket">
        <el-option v-for="b in buckets" :key="b.name" :label="b.name" :value="b.name" />
      </el-select>
      <el-menu :default-active="active" @select="nav">
        <el-menu-item index="files">
          <el-icon><FolderOpened /></el-icon>
          <span>{{ zhCN.files }}</span>
        </el-menu-item>
        <el-menu-item index="trash">
          <el-icon><Delete /></el-icon>
          <span>{{ zhCN.trash }}</span>
        </el-menu-item>
        <el-menu-item index="shares">
          <el-icon><Share /></el-icon>
          <span>{{ zhCN.shares }}</span>
        </el-menu-item>
        <el-menu-item index="credentials">
          <el-icon><Key /></el-icon>
          <span>{{ zhCN.credentials }}</span>
        </el-menu-item>
        <el-menu-item index="settings">
          <el-icon><Setting /></el-icon>
          <span>{{ zhCN.settings }}</span>
        </el-menu-item>
        <el-menu-item v-if="auth.isAdmin" index="users">
          <el-icon><User /></el-icon>
          <span>{{ zhCN.users }}</span>
        </el-menu-item>
      </el-menu>
    </el-aside>
    <el-container>
      <el-header class="header">
        <span :class="healthOk ? 'ok' : 'bad'">
          {{ healthOk ? zhCN.healthOk : zhCN.healthBad }}
        </span>
        <span class="spacer" />
        <el-button text @click="theme.toggle()">
          <el-icon><Moon v-if="!theme.dark" /><Sunny v-else /></el-icon>
          {{ zhCN.darkMode }}
        </el-button>
        <span class="user">{{ auth.user?.username }}</span>
        <el-button text @click="logout">{{ zhCN.logout }}</el-button>
      </el-header>
      <el-main class="main">
        <RouterView :bucket="bucket" />
      </el-main>
    </el-container>
  </el-container>
</template>

<style scoped>
.layout {
  min-height: 100vh;
}
.aside {
  border-right: 1px solid var(--el-border-color);
  padding: 0.75rem;
}
.brand {
  font-weight: 600;
  margin-bottom: 0.75rem;
}
.bucket-select {
  width: 100%;
  margin-bottom: 0.5rem;
}
.header {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  border-bottom: 1px solid var(--el-border-color);
}
.spacer {
  flex: 1;
}
.ok {
  color: var(--el-color-success);
}
.bad {
  color: var(--el-color-danger);
}
.main {
  padding: 1rem;
}
@media (max-width: 768px) {
  .layout {
    flex-direction: column;
  }
  .aside {
    width: 100% !important;
  }
}
</style>
