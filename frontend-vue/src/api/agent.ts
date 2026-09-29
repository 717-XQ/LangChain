import axios from 'axios'
import type { HealthResponse, ToolInfo, TokenResponse, UserInfo } from '@/types'

const API_BASE = '/api'

// ============================================================
// Token 存取（localStorage，供拦截器与WebSocket使用）
// ============================================================

export const tokenStorage = {
  getAccess(): string | null {
    return localStorage.getItem('agent_access_token')
  },
  getRefresh(): string | null {
    return localStorage.getItem('agent_refresh_token')
  },
  getUsername(): string | null {
    return localStorage.getItem('agent_username')
  },
  set(tokens: TokenResponse): void {
    localStorage.setItem('agent_access_token', tokens.access_token)
    localStorage.setItem('agent_refresh_token', tokens.refresh_token)
    localStorage.setItem('agent_username', tokens.user.username)
  },
  clear(): void {
    localStorage.removeItem('agent_access_token')
    localStorage.removeItem('agent_refresh_token')
    localStorage.removeItem('agent_username')
  }
}

// ============================================================
// Axios 实例（技术栈2.2：Token自动注入 + 401自动刷新）
// ============================================================

const http = axios.create({
  baseURL: API_BASE,
  timeout: 30000
})

// 请求拦截器：注入 Bearer Token
http.interceptors.request.use((config) => {
  const token = tokenStorage.getAccess()
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// 响应拦截器：401 时用刷新Token续期并重试原请求
let refreshing = false
http.interceptors.response.use(
  (response) => response,
  async (error) => {
    const original = error.config
    const status = error.response?.status

    // 非401或已重试过 → 直接抛出
    if (status !== 401 || original._retried || !tokenStorage.getRefresh()) {
      // 认证相关接口401（登录密码错误等）不触发跳转
      if (status === 401 && original.url?.includes('/auth/')) {
        return Promise.reject(error)
      }
      if (status === 401 && !original.url?.includes('/auth/')) {
        tokenStorage.clear()
        window.location.href = '/login'
      }
      return Promise.reject(error)
    }

    // 并发401只刷新一次
    if (refreshing) {
      return Promise.reject(error)
    }
    refreshing = true
    original._retried = true

    try {
      const { data } = await axios.post<TokenResponse>('/api/auth/refresh', {
        refresh_token: tokenStorage.getRefresh()
      })
      tokenStorage.set(data)
      original.headers.Authorization = `Bearer ${data.access_token}`
      return http(original)
    } catch (refreshError) {
      tokenStorage.clear()
      window.location.href = '/login'
      return Promise.reject(refreshError)
    } finally {
      refreshing = false
    }
  }
)

// ============================================================
// 认证 API（技术栈2.1：JWT）
// ============================================================

export async function login(username: string, password: string): Promise<TokenResponse> {
  const { data } = await axios.post<TokenResponse>('/api/auth/login', { username, password })
  tokenStorage.set(data)
  return data
}

export async function register(username: string, email: string, password: string): Promise<TokenResponse> {
  const { data } = await axios.post<TokenResponse>('/api/auth/register', { username, email, password })
  tokenStorage.set(data)
  return data
}

export async function getMe(): Promise<UserInfo> {
  const { data } = await http.get<UserInfo>('/auth/me')
  return data
}

export function logout(): void {
  tokenStorage.clear()
  window.location.href = '/login'
}

// ============================================================
// 业务 API
// ============================================================

// 健康检查（公开）
export async function healthCheck(): Promise<HealthResponse> {
  const { data } = await http.get<HealthResponse>('/health')
  return data
}

// 获取工具列表
export async function listTools(): Promise<ToolInfo[]> {
  const { data } = await http.get<ToolInfo[]>('/tools')
  return data
}

// 非流式聊天
export async function chat(message: string, agentType: string = 'react'): Promise<any> {
  const { data } = await http.post('/chat', { message, agent_type: agentType })
  return data
}

// ============================================================
// WebSocket连接管理（技术栈2.2：携带Token）
// ============================================================

export class AgentWebSocket {
  private ws: WebSocket | null = null
  private reconnectAttempts = 0
  private maxReconnectAttempts = 3

  constructor(
    private onMessage: (event: any) => void,
    private onOpen?: () => void,
    private onClose?: () => void,
    private onError?: (error: Event) => void
  ) {}

  connect(): void {
    // 开发环境直接连接后端WebSocket（携带JWT Token），生产环境通过Nginx反向代理
    const token = tokenStorage.getAccess() || ''
    const wsUrl = import.meta.env.DEV
      ? `ws://localhost:8000/ws?token=${encodeURIComponent(token)}`
      : `${window.location.protocol === 'https:' ? 'wss:' : 'ws:'}//${window.location.host}/ws?token=${encodeURIComponent(token)}`
    console.log('[WebSocket] 连接到:', wsUrl)
    this.ws = new WebSocket(wsUrl)

    this.ws.onopen = () => {
      console.log('[WebSocket] 连接成功！')
      this.reconnectAttempts = 0
      this.onOpen?.()
    }

    this.ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data)
        this.onMessage(data)
      } catch (e) {
        console.error('WebSocket消息解析失败:', e)
      }
    }

    this.ws.onclose = () => {
      this.onClose?.()
      this.tryReconnect()
    }

    this.ws.onerror = (error) => {
      console.error('[WebSocket] 连接错误:', error)
      this.onError?.(error)
    }
  }

  private tryReconnect(): void {
    if (this.reconnectAttempts < this.maxReconnectAttempts) {
      this.reconnectAttempts++
      setTimeout(() => this.connect(), 2000 * this.reconnectAttempts)
    }
  }

  sendMessage(message: string, agentType: string = 'react', sessionId: string = 'default'): void {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({
        type: 'message',
        content: message,
        agent_type: agentType,
        session_id: sessionId
      }))
    }
  }

  sendApprove(): void {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({ type: 'approve' }))
    }
  }

  sendReject(): void {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({ type: 'reject' }))
    }
  }

  sendStop(): void {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({ type: 'stop' }))
    }
  }

  disconnect(): void {
    this.ws?.close()
    this.ws = null
  }

  isConnected(): boolean {
    return this.ws?.readyState === WebSocket.OPEN
  }
}
