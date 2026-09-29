<template>
  <div class="app-container">
    <!-- 顶部导航 -->
    <header class="app-header">
      <div class="header-left">
        <el-icon class="logo-icon"><MagicStick /></el-icon>
        <h1 class="app-title">多工具 AI Agent 助手</h1>
      </div>
      <div class="header-center">
        <el-radio-group v-model="agentStore.agentType" size="small" @change="handleAgentTypeChange">
          <el-radio-button value="react">ReAct</el-radio-button>
          <el-radio-button value="langgraph">LangGraph</el-radio-button>
          <el-radio-button value="planner">Plan-and-Execute</el-radio-button>
        </el-radio-group>
      </div>
      <div class="header-right">
        <el-tag :type="agentStore.isConnected ? 'success' : 'danger'" size="small" effect="plain">
          <el-icon><Connection /></el-icon>
          {{ agentStore.isConnected ? '已连接' : '未连接' }}
        </el-tag>
        <el-dropdown trigger="click" @command="handleUserCommand">
          <span class="user-menu">
            <el-avatar :size="26" class="user-avatar">{{ avatarText }}</el-avatar>
            <span class="username">{{ authStore.user?.username || '用户' }}</span>
            <el-icon><ArrowDown /></el-icon>
          </span>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="logout" divided>
                <el-icon><SwitchButton /></el-icon>退出登录
              </el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </div>
    </header>

    <!-- 主内容区 -->
    <div class="main-content">
      <!-- 左侧会话列表 -->
      <aside class="sidebar">
        <SessionSidebar
          :sessions="agentStore.sessions"
          :current-session-id="agentStore.currentSessionId"
          @new-session="handleNewSession"
          @switch-session="handleSwitchSession"
        />
      </aside>

      <!-- 中间聊天区 -->
      <main class="chat-area">
        <el-scrollbar ref="scrollRef" class="message-list">
          <div v-if="agentStore.messages.length === 0" class="welcome">
            <el-icon class="welcome-icon"><Cpu /></el-icon>
            <h2>AI Agent 助手</h2>
            <p>我可以调用搜索、数据库、Python代码、RAG知识库等工具帮您完成任务</p>
            <div class="example-questions">
              <el-button
                v-for="q in exampleQuestions"
                :key="q"
                class="example-btn"
                @click="sendQuestion(q)"
              >{{ q }}</el-button>
            </div>
          </div>
          <ChatMessage
            v-for="msg in agentStore.messages"
            :key="msg.id"
            :message="msg"
          />
        </el-scrollbar>

        <!-- 工具统计图表（技术栈2.2：ECharts） -->
        <ToolStatsChart :tool-calls="agentStore.allToolCalls" />

        <!-- 输入区 -->
        <div class="input-area">
          <div class="input-box">
            <el-input
              v-model="inputText"
              type="textarea"
              :rows="2"
              placeholder="输入您的任务，按 Enter 发送，Shift+Enter 换行"
              @keydown.enter.exact.prevent="handleSend"
              :disabled="agentStore.isProcessing"
              resize="none"
            />
            <div class="input-actions">
              <el-button
                v-if="agentStore.isProcessing"
                type="danger"
                :icon="SwitchButton"
                @click="handleStop"
                circle
              />
              <el-button
                v-else
                type="primary"
                :icon="Promotion"
                class="send-btn"
                @click="handleSend"
                :disabled="!inputText.trim()"
                circle
              />
            </div>
          </div>
          <div class="input-hint">
            <el-icon><InfoFilled /></el-icon>
            <span>当前模式: {{ agentTypeLabel }} | 支持工具调用、代码执行、数据库查询、RAG检索</span>
          </div>
        </div>
      </main>
    </div>

    <!-- 高风险操作审批弹窗 -->
    <ApprovalDialog
      :approval="agentStore.approvalRequest"
      @approve="handleApprove"
      @reject="handleReject"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, nextTick, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { MagicStick, Cpu, Promotion, SwitchButton, Connection, InfoFilled, ArrowDown } from '@element-plus/icons-vue'
import { useAgentStore } from '@/stores/agent'
import { useAuthStore } from '@/stores/auth'
import ChatMessage from '@/components/ChatMessage.vue'
import SessionSidebar from '@/components/SessionSidebar.vue'
import ApprovalDialog from '@/components/ApprovalDialog.vue'
import ToolStatsChart from '@/components/ToolStatsChart.vue'

const router = useRouter()
const agentStore = useAgentStore()
const authStore = useAuthStore()
const inputText = ref('')
const scrollRef = ref()

const exampleQuestions = [
  '帮我查询技术部有多少名员工',
  '计算1到100所有质数的和',
  '什么是RAG检索增强生成',
  '查询薪资最高的员工姓名和薪资'
]

const avatarText = computed(() => {
  const name = authStore.user?.username || ''
  return name.slice(0, 1).toUpperCase()
})

const agentTypeLabel = computed(() => {
  const map: Record<string, string> = {
    react: 'ReAct (推理+行动)',
    langgraph: 'LangGraph (状态图编排)',
    planner: 'Plan-and-Execute (规划执行)'
  }
  return map[agentStore.agentType] || agentStore.agentType
})

async function scrollToBottom() {
  await nextTick()
  if (scrollRef.value) {
    const scrollbar = scrollRef.value
    scrollbar.scrollTo({ top: scrollbar.scrollHeight, behavior: 'smooth' })
  }
}

function handleSend() {
  const content = inputText.value.trim()
  if (!content) return
  agentStore.sendMessage(content)
  inputText.value = ''
  scrollToBottom()
}

function sendQuestion(question: string) {
  agentStore.sendMessage(question)
  scrollToBottom()
}

function handleStop() {
  agentStore.stopGeneration()
  ElMessage.info('已停止生成')
}

function handleApprove() {
  agentStore.approveAction()
  ElMessage.success('已批准执行')
}

function handleReject() {
  agentStore.rejectAction()
  ElMessage.warning('已拒绝执行')
}

function handleNewSession() {
  agentStore.newSession()
  ElMessage.success('已创建新会话')
}

function handleSwitchSession(id: string) {
  agentStore.switchSession(id)
}

function handleAgentTypeChange() {
  ElMessage.success(`已切换到 ${agentTypeLabel.value} 模式`)
}

function handleUserCommand(command: string) {
  if (command === 'logout') {
    agentStore.disconnectWebSocket()
    authStore.logout()
    router.replace('/login')
    ElMessage.success('已退出登录')
  }
}

onMounted(() => {
  agentStore.initWebSocket()
  agentStore.newSession()
})

onUnmounted(() => {
  agentStore.disconnectWebSocket()
})
</script>

<style scoped>
.app-container {
  height: 100vh;
  display: flex;
  flex-direction: column;
  background: #f0f2f5;
}

.app-header {
  height: 56px;
  background: #fff;
  border-bottom: 1px solid #ebeef5;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 24px;
  flex-shrink: 0;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 200px;
}

.logo-icon {
  font-size: 24px;
  color: #667eea;
}

.app-title {
  font-size: 16px;
  font-weight: 600;
  color: #303133;
  margin: 0;
}

.header-center {
  flex: 1;
  display: flex;
  justify-content: center;
}

.header-right {
  width: 220px;
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 14px;
}

.user-menu {
  display: flex;
  align-items: center;
  gap: 6px;
  cursor: pointer;
  color: #606266;
  font-size: 13px;
}

.user-avatar {
  background: #667eea;
  color: #fff;
  font-weight: 600;
}

.username {
  max-width: 72px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.main-content {
  flex: 1;
  display: flex;
  overflow: hidden;
}

.sidebar {
  width: 240px;
  flex-shrink: 0;
}

.chat-area {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: #fff;
}

.message-list {
  flex: 1;
  overflow: hidden;
}

.welcome {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  padding: 40px;
  text-align: center;
}

.welcome-icon {
  font-size: 64px;
  color: #667eea;
  margin-bottom: 16px;
}

.welcome h2 {
  font-size: 22px;
  color: #303133;
  margin: 0 0 8px 0;
}

.welcome p {
  font-size: 14px;
  color: #909399;
  margin: 0 0 24px 0;
  max-width: 500px;
}

.example-questions {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  justify-content: center;
  max-width: 600px;
}

.example-btn {
  margin: 0;
}

.input-area {
  border-top: 1px solid #ebeef5;
  padding: 16px 24px;
  flex-shrink: 0;
  background: #fafafa;
}

.input-box {
  display: flex;
  gap: 12px;
  align-items: flex-end;
}

.input-actions {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.send-btn {
  width: 40px;
  height: 40px;
  padding: 0;
}

.input-hint {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 8px;
  font-size: 12px;
  color: #c0c4cc;
}
</style>
