<template>
  <div class="chat-message" :class="message.role">
    <div class="avatar">
      <el-icon v-if="message.role === 'user'" size="18"><User /></el-icon>
      <el-icon v-else size="18"><Cpu /></el-icon>
    </div>
    <div class="message-body">
      <div class="message-header">
        <span class="role-name">{{ message.role === 'user' ? '我' : 'AI Agent' }}</span>
        <el-tag v-if="message.status === 'planning'" size="small" type="info" effect="plain">
          <el-icon class="is-loading"><Loading /></el-icon>规划中
        </el-tag>
        <el-tag v-else-if="message.status === 'executing'" size="small" type="primary" effect="plain">
          执行工具中
        </el-tag>
        <el-tag v-else-if="message.status === 'generating'" size="small" type="warning" effect="plain">
          生成回答中
        </el-tag>
        <el-tag v-else-if="message.status === 'error'" size="small" type="danger" effect="plain">
          出错
        </el-tag>
        <span v-if="message.iterations" class="iterations">迭代 {{ message.iterations }} 次</span>
      </div>
      <div class="message-content">
        <p v-if="!message.content && message.streaming" class="waiting-text">
          <el-icon class="is-loading"><Loading /></el-icon>
          正在思考...
        </p>
        <!-- 用户消息：纯文本；AI消息：Markdown渲染 + 代码高亮（技术栈2.2） -->
        <MarkdownContent v-else-if="message.role === 'assistant'" :content="message.content" class="answer-text"
          :class="{ 'streaming-cursor': message.streaming }" />
        <p v-else class="answer-text">{{ message.content }}</p>
        <!-- 工具调用详情已移入右侧"工具调用"面板，不再内嵌，避免拉长会话 -->
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { ChatMessage } from '@/types'
import MarkdownContent from './MarkdownContent.vue'

defineProps<{
  message: ChatMessage
}>()
</script>

<style scoped>
.chat-message {
  display: flex;
  padding: 16px 20px;
  gap: 12px;
}

.chat-message.user {
  flex-direction: row-reverse;
}

.avatar {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.chat-message.user .avatar {
  background: #409eff;
  color: #fff;
}

.chat-message.assistant .avatar {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: #fff;
}

.message-body {
  max-width: 80%;
  min-width: 0;
}

.chat-message.user .message-body {
  text-align: right;
}

.message-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
  flex-wrap: wrap;
}

.chat-message.user .message-header {
  justify-content: flex-end;
}

.role-name {
  font-size: 13px;
  font-weight: 600;
  color: #303133;
}

.iterations {
  font-size: 12px;
  color: #909399;
}

.message-content {
  background: #fff;
  border-radius: 12px;
  padding: 12px 16px;
  text-align: left;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.05);
}

.chat-message.user .message-content {
  background: #ecf5ff;
}

.waiting-text {
  margin: 0;
  font-size: 14px;
  color: #909399;
  display: flex;
  align-items: center;
  gap: 6px;
}

.answer-text {
  margin: 0;
  font-size: 14px;
  line-height: 1.7;
  color: #303133;
  white-space: pre-wrap;
  word-break: break-word;
}
</style>
