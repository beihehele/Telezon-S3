import { createRouter, createWebHashHistory } from 'vue-router'
import { getToken } from '@/api/http'
import { useAuthStore } from '@/stores/auth'

const router = createRouter({
  history: createWebHashHistory(),
  routes: [
    { path: '/login', name: 'login', component: () => import('@/views/LoginView.vue') },
    { path: '/register', name: 'register', component: () => import('@/views/RegisterView.vue') },
    {
      path: '/',
      component: () => import('@/layouts/MainLayout.vue'),
      children: [
        { path: '', redirect: '/files' },
        { path: 'files', name: 'files', component: () => import('@/views/FilesView.vue') },
        { path: 'trash', name: 'trash', component: () => import('@/views/TrashView.vue') },
        { path: 'shares', name: 'shares', component: () => import('@/views/SharesView.vue') },
        {
          path: 'credentials',
          name: 'credentials',
          component: () => import('@/views/CredentialsView.vue'),
        },
        {
          path: 'settings',
          name: 'settings',
          component: () => import('@/views/BucketSettingsView.vue'),
        },
        { path: 'users', name: 'users', component: () => import('@/views/UsersView.vue') },
      ],
    },
  ],
})

router.beforeEach(async (to) => {
  if (to.name === 'login' || to.name === 'register') {
    return true
  }
  if (!getToken()) {
    return { name: 'login' }
  }
  const auth = useAuthStore()
  if (!auth.user) {
    try {
      await auth.fetchMe()
    } catch {
      return { name: 'login' }
    }
  }
  if (to.name === 'users' && !auth.isAdmin) {
    return { name: 'files' }
  }
  return true
})

export default router
