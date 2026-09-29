import { createRouter, createWebHistory } from 'vue-router'
import { tokenStorage } from '@/api/agent'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/login',
      name: 'login',
      component: () => import('@/views/LoginView.vue'),
      meta: { title: '登录' }
    },
    {
      path: '/',
      name: 'home',
      component: () => import('@/views/HomeView.vue'),
      meta: { title: 'AI Agent 助手', requiresAuth: true }
    },
    {
      path: '/:pathMatch(.*)*',
      redirect: '/'
    }
  ]
})

// 路由守卫（技术栈2.2：未登录跳转登录页）
router.beforeEach((to) => {
  if (to.meta.requiresAuth && !tokenStorage.getAccess()) {
    return { name: 'login', query: { redirect: to.fullPath } }
  }
  if (to.name === 'login' && tokenStorage.getAccess()) {
    return { name: 'home' }
  }
  return true
})

export default router
