<template>
  <div class="session-sidebar">
    <div class="sidebar-header">
      <el-button type="primary" :icon="Plus" class="new-session-btn" @click="handleNewSession">
        新建会话
      </el-button>
    </div>
    <el-scrollbar class="session-list">
      <div v-if="sessions.length === 0" class="empty">
        <el-icon><ChatDotRound /></el-icon>
        <span>暂无会话</span>
      </div>
      <div
        v-for="session in sessions"
        :key="session.id"
        class="session-item"
        :class="{ active: session.id === currentSessionId }"
        @click="handleSwitch(session.id)"
      >
        <el-icon class="session-icon"><ChatDotRound /></el-icon>
        <div class="session-info">
          <span class="session-title">{{ session.title }}</span>
          <span class="session-time">{{ formatTime(session.updatedAt) }}</span>
        </div>
      </div>
    </el-scrollbar>
  </div>
</template>

<script setup lang="ts">
import { Plus, ChatDotRound } from '@element-plus/icons-vue'
import type { Session } from '@/types'

defineProps<{
  sessions: Session[]
  currentSessionId: string
}>()

const emit = defineEmits<{
  (e: 'new-session'): void
  (e: 'switch-session', id: string): void
}>()

function handleNewSession() {
  emit('new-session')
}

function handleSwitch(id: string) {
  emit('switch-session', id)
}

function formatTime(timestamp: number): string {
  const date = new Date(timestamp)
  const now = new Date()
  if (date.toDateString() === now.toDateString()) {
    return date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
  }
  return date.toLocaleDateString('zh-CN', { month: '2-digit', day: '2-digit' })
}
</script>

<style scoped>
.session-sidebar {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: #fff;
  border-right: 1px solid #ebeef5;
}

.sidebar-header {
  padding: 16px;
  border-bottom: 1px solid #ebeef5;
}

.new-session-btn {
  width: 100%;
}

.session-list {
  flex: 1;
  overflow: hidden;
}

.empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 40px 20px;
  color: #c0c4cc;
  font-size: 13px;
  gap: 8px;
}

.session-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 16px;
  cursor: pointer;
  transition: background 0.2s;
  border-bottom: 1px solid #f5f7fa;
}

.session-item:hover {
  background: #f5f7fa;
}

.session-item.active {
  background: #ecf5ff;
  border-right: 3px solid #409eff;
}

.session-icon {
  color: #909399;
  font-size: 16px;
  flex-shrink: 0;
}

.session-item.active .session-icon {
  color: #409eff;
}

.session-info {
  display: flex;
  flex-direction: column;
  min-width: 0;
  flex: 1;
}

.session-title {
  font-size: 13px;
  color: #303133;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.session-time {
  font-size: 11px;
  color: #c0c4cc;
  margin-top: 2px;
}
</style>
