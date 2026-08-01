import { defineStore } from 'pinia'
import { ref, watch } from 'vue'

const KEY = 'telezon_theme'

export const useThemeStore = defineStore('theme', () => {
  const dark = ref(localStorage.getItem(KEY) === 'dark')

  function apply() {
    document.documentElement.classList.toggle('dark', dark.value)
  }

  function toggle() {
    dark.value = !dark.value
  }

  watch(
    dark,
    (v) => {
      localStorage.setItem(KEY, v ? 'dark' : 'light')
      apply()
    },
    { immediate: true },
  )

  return { dark, toggle, apply }
})
