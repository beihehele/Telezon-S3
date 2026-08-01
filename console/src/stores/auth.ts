import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { http, setToken, getToken } from '@/api/http'

export interface CurrentUser {
  username: string
  email: string
  role: string
  access_key_id: string
}

export const useAuthStore = defineStore('auth', () => {
  const user = ref<CurrentUser | null>(null)
  const loading = ref(false)

  const isAdmin = computed(() => user.value?.role === 'admin')
  const isLoggedIn = computed(() => !!getToken() && !!user.value)

  async function login(username: string, password: string) {
    loading.value = true
    try {
      const body = new URLSearchParams()
      body.set('username', username)
      body.set('password', password)
      const { data } = await http.post<{ access_token: string }>('/auth/login', body, {
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      })
      setToken(data.access_token)
      await fetchMe()
    } finally {
      loading.value = false
    }
  }

  async function fetchMe() {
    if (!getToken()) {
      user.value = null
      return
    }
    const { data } = await http.get<CurrentUser>('/auth/current_user')
    user.value = data
  }

  function logout() {
    setToken(null)
    user.value = null
  }

  return { user, loading, isAdmin, isLoggedIn, login, fetchMe, logout }
})
