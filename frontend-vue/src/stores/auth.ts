import { defineStore } from 'pinia'
import { ref } from 'vue'
import { login as apiLogin, register as apiRegister, tokenStorage, logout as apiLogout } from '@/api/agent'
import type { UserInfo } from '@/types'

export const useAuthStore = defineStore('auth', () => {
  // 状态（初始化时从localStorage恢复）
  const user = ref<UserInfo | null>(null)
  const isAuthenticated = ref<boolean>(!!tokenStorage.getAccess())
  const loading = ref(false)

  // 登录
  async function login(username: string, password: string): Promise<UserInfo> {
    loading.value = true
    try {
      const tokens = await apiLogin(username, password)
      user.value = tokens.user
      isAuthenticated.value = true
      return tokens.user
    } finally {
      loading.value = false
    }
  }

  // 注册（自动登录）
  async function register(username: string, email: string, password: string): Promise<UserInfo> {
    loading.value = true
    try {
      const tokens = await apiRegister(username, email, password)
      user.value = tokens.user
      isAuthenticated.value = true
      return tokens.user
    } finally {
      loading.value = false
    }
  }

  // 退出登录
  function logout(): void {
    user.value = null
    isAuthenticated.value = false
    apiLogout()
  }

  return {
    user,
    isAuthenticated,
    loading,
    login,
    register,
    logout
  }
})
