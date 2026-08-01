import { ref } from 'vue'
import { http } from '@/api/http'

const allowSignup = ref(true)
let loaded = false

export function useAuthPublicConfig() {
  async function load() {
    if (loaded) {
      return allowSignup.value
    }
    try {
      const { data } = await http.get<{ allow_signup: boolean }>('/auth/config')
      allowSignup.value = data.allow_signup
    } catch {
      allowSignup.value = false
    }
    loaded = true
    return allowSignup.value
  }

  return { allowSignup, load }
}
