<template>
  <div class="tool-timeline">
    <div v-if="toolCalls.length === 0" class="empty">
      <el-icon><MagicStick /></el-icon>
      <span>等待工具调用...</span>
    </div>
    <el-timeline v-else>
      <el-timeline-item
        v-for="call in toolCalls"
        :key="call.id"
        :type="getTimelineType(call.status)"
        :icon="getTimelineIcon(call.status)"
        :hollow="call.status === 'pending'"
      >
        <div class="tool-call-card" :class="call.status">
          <div class="tool-header">
            <div class="tool-name">
              <el-icon><Cpu /></el-icon>
              <span>{{ call.toolName }}</span>
              <el-tag :type="getRiskTagType(call.riskLevel)" size="small" class="risk-tag">
                {{ call.riskLevel }}
              </el-tag>
            </div>
            <div class="tool-status">
              <el-tag v-if="call.status === 'running'" type="primary" size="small" effect="plain">
                <el-icon class="is-loading"><Loading /></el-icon>
                执行中
              </el-tag>
              <el-tag v-else-if="call.status === 'success'" type="success" size="small" effect="plain">
                成功
              </el-tag>
              <el-tag v-else-if="call.status === 'failed'" type="danger" size="small" effect="plain">
                失败
              </el-tag>
              <el-tag v-else-if="call.status === 'waiting_approval'" type="warning" size="small" effect="plain">
                等待审批
              </el-tag>
              <span v-if="call.duration" class="duration">{{ call.duration.toFixed(2) }}s</span>
            </div>
          </div>
          <div class="tool-body">
            <div v-if="call.toolInput" class="tool-section">
              <div class="section-label">输入</div>
              <pre class="section-content input">{{ call.toolInput }}</pre>
            </div>
            <div v-if="call.toolOutput && call.status !== 'running'" class="tool-section">
              <div class="section-label">输出</div>
              <pre class="section-content output">{{ truncateOutput(call.toolOutput) }}</pre>
            </div>
          </div>
        </div>
      </el-timeline-item>
    </el-timeline>
  </div>
</template>

<script setup lang="ts">
import type { ToolCall } from '@/types'

defineProps<{
  toolCalls: ToolCall[]
}>()

function getTimelineType(status: string): string {
  switch (status) {
    case 'success': return 'success'
    case 'failed': return 'danger'
    case 'running': return 'primary'
    case 'waiting_approval': return 'warning'
    default: return 'info'
  }
}

function getTimelineIcon(status: string): any {
  // 返回图标组件名，由el-timeline-item的icon属性处理
  return null
}

function getRiskTagType(riskLevel: string): string {
  switch (riskLevel) {
    case 'READ': return 'success'
    case 'SANDBOX': return 'warning'
    case 'DANGEROUS': return 'danger'
    default: return 'info'
  }
}

function truncateOutput(output: string): string {
  if (output.length > 500) {
    return output.substring(0, 500) + '\n... (输出已截断)'
  }
  return output
}
</script>

<style scoped>
.tool-timeline {
  padding: 8px 0;
}

.empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 30px;
  color: #c0c4cc;
  font-size: 13px;
  gap: 8px;
}

.tool-call-card {
  background: #fff;
  border: 1px solid #ebeef5;
  border-radius: 8px;
  overflow: hidden;
  transition: all 0.2s;
}

.tool-call-card.running {
  border-color: #409eff;
  box-shadow: 0 0 0 2px rgba(64, 158, 255, 0.1);
}

.tool-call-card.success {
  border-color: #67c23a;
}

.tool-call-card.failed {
  border-color: #f56c6c;
}

.tool-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px 14px;
  background: #fafafa;
  border-bottom: 1px solid #ebeef5;
}

.tool-name {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  font-weight: 600;
  color: #303133;
}

.risk-tag {
  margin-left: 6px;
}

.tool-status {
  display: flex;
  align-items: center;
  gap: 8px;
}

.duration {
  font-size: 12px;
  color: #909399;
}

.tool-body {
  padding: 10px 14px;
}

.tool-section {
  margin-bottom: 8px;
}

.tool-section:last-child {
  margin-bottom: 0;
}

.section-label {
  font-size: 11px;
  color: #909399;
  margin-bottom: 4px;
  font-weight: 600;
  text-transform: uppercase;
}

.section-content {
  margin: 0;
  padding: 8px 10px;
  border-radius: 4px;
  font-size: 12px;
  line-height: 1.5;
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 200px;
  overflow-y: auto;
  font-family: 'Consolas', 'Monaco', monospace;
}

.section-content.input {
  background: #ecf5ff;
  color: #409eff;
}

.section-content.output {
  background: #f0f9eb;
  color: #67c23a;
}
</style>
