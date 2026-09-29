import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { ChatMessage, ToolCall, Session, AgentType, ApprovalRequest } from '@/types'
import { AgentWebSocket } from '@/api/agent'

export const useAgentStore = defineStore('agent', () => {
  // 状态
  const messages = ref<ChatMessage[]>([])
  const sessions = ref<Session[]>([])
  const currentSessionId = ref<string>('')
  const agentType = ref<AgentType>('react')
  const isConnected = ref(false)
  const isProcessing = ref(false)
  const approvalRequest = ref<ApprovalRequest | null>(null)
  const currentToolCall = ref<ToolCall | null>(null)

  // WebSocket实例
  let ws: AgentWebSocket | null = null

  // 计算属性
  const currentMessages = computed(() => messages.value)
  const currentSession = computed(() =>
    sessions.value.find(s => s.id === currentSessionId.value)
  )

  // 当前会话所有工具调用（供ECharts统计，技术栈2.2）
  const allToolCalls = computed<ToolCall[]>(() => {
    const calls: ToolCall[] = []
    for (const msg of messages.value) {
      if (msg.toolCalls?.length) {
        calls.push(...msg.toolCalls)
      }
    }
    return calls
  })

  // 生成ID
  function generateId(): string {
    return Date.now().toString(36) + Math.random().toString(36).substr(2)
  }

  // 初始化WebSocket
  function initWebSocket() {
    if (ws) return

    ws = new AgentWebSocket(
      (event) => handleWSEvent(event),
      () => { isConnected.value = true },
      () => { isConnected.value = false },
      () => { isConnected.value = false }
    )
    ws.connect()
  }

  // 断开WebSocket
  function disconnectWebSocket() {
    ws?.disconnect()
    ws = null
    isConnected.value = false
  }

  // 处理WebSocket事件
  function handleWSEvent(event: any) {
    const lastMsg = messages.value[messages.value.length - 1]
    if (!lastMsg || lastMsg.role !== 'assistant') return

    switch (event.type) {
      case 'plan':
        lastMsg.status = 'planning'
        break
      case 'status':
        if (event.content.includes('工具') || event.content.includes('执行')) {
          lastMsg.status = 'executing'
        } else if (event.content.includes('生成') || event.content.includes('回答')) {
          lastMsg.status = 'generating'
        }
        break
      case 'tool_start':
        const toolCall: ToolCall = {
          id: generateId(),
          toolName: event.data?.tool_name || event.content,
          toolInput: event.data?.tool_input || '',
          riskLevel: event.data?.risk_level || 'READ',
          status: 'running',
          startTime: Date.now()
        }
        lastMsg.toolCalls = lastMsg.toolCalls || []
        lastMsg.toolCalls.push(toolCall)
        currentToolCall.value = toolCall
        break
      case 'tool_end':
        const calls = lastMsg.toolCalls || []
        const runningCall = calls.find(c => c.status === 'running')
        if (runningCall) {
          runningCall.status = 'success'
          runningCall.toolOutput = event.data?.output || event.content
          runningCall.endTime = Date.now()
          runningCall.duration = event.data?.duration
            || ((runningCall.endTime || Date.now()) - (runningCall.startTime || Date.now())) / 1000
        }
        currentToolCall.value = null
        break
      case 'approval_required':
        approvalRequest.value = {
          toolName: event.data?.tool_name || event.content,
          toolInput: event.data?.tool_input || '',
          riskLevel: event.data?.risk_level || 'DANGEROUS'
        }
        const waitingCall = (lastMsg.toolCalls || []).find(c => c.status === 'running')
        if (waitingCall) {
          waitingCall.status = 'waiting_approval'
        }
        break
      case 'token':
        lastMsg.content += event.content
        break
      case 'error':
        lastMsg.status = 'error'
        lastMsg.content += `\n\n错误: ${event.content}`
        isProcessing.value = false
        break
      case 'done':
        lastMsg.status = 'done'
        lastMsg.streaming = false
        lastMsg.iterations = event.data?.iterations
        // 如果没有流式输出（token事件），则使用done事件中的完整答案
        if (!lastMsg.content && event.content) {
          lastMsg.content = event.content
        }
        isProcessing.value = false
        currentToolCall.value = null
        break
    }
  }

  // 发送消息
  function sendMessage(content: string) {
    if (!content.trim() || isProcessing.value) return

    // 添加用户消息
    const userMsg: ChatMessage = {
      id: generateId(),
      role: 'user',
      content,
      timestamp: Date.now()
    }
    messages.value.push(userMsg)

    // 添加AI消息（空内容，等待流式填充）
    const aiMsg: ChatMessage = {
      id: generateId(),
      role: 'assistant',
      content: '',
      timestamp: Date.now(),
      status: 'planning',
      streaming: true,
      toolCalls: []
    }
    messages.value.push(aiMsg)

    isProcessing.value = true

    // 发送WebSocket消息
    ws?.sendMessage(content, agentType.value)
  }

  // 批准高风险操作
  function approveAction() {
    ws?.sendApprove()
    approvalRequest.value = null
    const lastMsg = messages.value[messages.value.length - 1]
    const waitingCall = (lastMsg?.toolCalls || []).find(c => c.status === 'waiting_approval')
    if (waitingCall) {
      waitingCall.status = 'running'
    }
  }

  // 拒绝高风险操作
  function rejectAction() {
    ws?.sendReject()
    approvalRequest.value = null
    const lastMsg = messages.value[messages.value.length - 1]
    const waitingCall = (lastMsg?.toolCalls || []).find(c => c.status === 'waiting_approval')
    if (waitingCall) {
      waitingCall.status = 'failed'
      waitingCall.toolOutput = '用户拒绝执行'
    }
  }

  // 停止生成
  function stopGeneration() {
    ws?.sendStop()
    isProcessing.value = false
    const lastMsg = messages.value[messages.value.length - 1]
    if (lastMsg) {
      lastMsg.status = 'done'
      lastMsg.streaming = false
    }
  }

  // 新建会话
  function newSession() {
    const session: Session = {
      id: generateId(),
      title: '新会话',
      createdAt: Date.now(),
      updatedAt: Date.now(),
      messageCount: 0
    }
    sessions.value.unshift(session)
    currentSessionId.value = session.id
    messages.value = []
  }

  // 切换会话
  function switchSession(sessionId: string) {
    currentSessionId.value = sessionId
    // 实际项目中应从后端加载历史消息
    messages.value = []
  }

  // 清空消息
  function clearMessages() {
    messages.value = []
  }

  return {
    // 状态
    messages,
    sessions,
    currentSessionId,
    agentType,
    isConnected,
    isProcessing,
    approvalRequest,
    currentToolCall,
    // 计算属性
    currentMessages,
    currentSession,
    allToolCalls,
    // 方法
    initWebSocket,
    disconnectWebSocket,
    sendMessage,
    approveAction,
    rejectAction,
    stopGeneration,
    newSession,
    switchSession,
    clearMessages
  }
})
