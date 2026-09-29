// Agent类型定义

// 聊天消息
export interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  timestamp: number
  toolCalls?: ToolCall[]
  status?: 'planning' | 'executing' | 'generating' | 'done' | 'error'
  streaming?: boolean
  iterations?: number
}

// 工具调用记录
export interface ToolCall {
  id: string
  toolName: string
  toolInput: string
  toolOutput?: string
  riskLevel: 'READ' | 'SANDBOX' | 'DANGEROUS'
  status: 'pending' | 'running' | 'success' | 'failed' | 'waiting_approval'
  startTime?: number
  endTime?: number
  duration?: number
}

// 会话
export interface Session {
  id: string
  title: string
  createdAt: number
  updatedAt: number
  messageCount: number
}

// 工具信息
export interface ToolInfo {
  name: string
  description: string
  risk_level: string
}

// 健康检查
export interface HealthResponse {
  status: string
  agent_types: string[]
  tools_count: number
}

// WebSocket事件
export type WSEventType =
  | 'plan'
  | 'status'
  | 'tool_start'
  | 'tool_end'
  | 'approval_required'
  | 'token'
  | 'error'
  | 'done'

export interface WSEvent {
  type: WSEventType
  content: string
  data?: any
}

// 审批请求
export interface ApprovalRequest {
  toolName: string
  toolInput: string
  riskLevel: string
}

// Agent模式
export type AgentType = 'react' | 'langgraph' | 'planner'

// ============================================================
// 认证类型（技术栈2.2：JWT Token自动刷新）
// ============================================================

export interface UserInfo {
  id: number
  username: string
  email: string
}

export interface TokenResponse {
  access_token: string
  refresh_token: string
  token_type: string
  expires_in: number
  user: UserInfo
}
