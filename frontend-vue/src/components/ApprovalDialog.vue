<template>
  <el-dialog
    v-model="visible"
    title="高风险操作确认"
    width="500px"
    :close-on-click-modal="false"
    :close-on-press-escape="false"
    :show-close="false"
  >
    <div class="approval-content">
      <el-alert
        title="检测到高风险操作，需要您的确认"
        type="warning"
        :closable="false"
        show-icon
        class="alert"
      />
      <div class="info-section">
        <div class="info-row">
          <span class="label">工具名称</span>
          <el-tag type="danger" size="small">{{ approval?.toolName }}</el-tag>
        </div>
        <div class="info-row">
          <span class="label">风险等级</span>
          <el-tag type="danger" size="small">{{ approval?.riskLevel }}</el-tag>
        </div>
        <div class="info-row">
          <span class="label">操作内容</span>
        </div>
        <pre class="tool-input">{{ approval?.toolInput }}</pre>
      </div>
      <div class="warning-text">
        <el-icon><Warning /></el-icon>
        <span>此操作可能修改或删除数据，请确认操作内容无误后再执行。</span>
      </div>
    </div>
    <template #footer>
      <el-button @click="handleReject">拒绝执行</el-button>
      <el-button type="primary" @click="handleApprove">确认执行</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { ApprovalRequest } from '@/types'

const props = defineProps<{
  approval: ApprovalRequest | null
}>()

const emit = defineEmits<{
  (e: 'approve'): void
  (e: 'reject'): void
}>()

const visible = computed({
  get: () => !!props.approval,
  set: () => {}
})

function handleApprove() {
  emit('approve')
}

function handleReject() {
  emit('reject')
}
</script>

<style scoped>
.approval-content {
  padding: 0;
}

.alert {
  margin-bottom: 16px;
}

.info-section {
  background: #fafafa;
  border-radius: 8px;
  padding: 16px;
  margin-bottom: 16px;
}

.info-row {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 10px;
}

.label {
  font-size: 13px;
  color: #909399;
  min-width: 70px;
}

.tool-input {
  margin: 0;
  padding: 10px 12px;
  background: #fff;
  border: 1px solid #ebeef5;
  border-radius: 4px;
  font-size: 12px;
  line-height: 1.5;
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 150px;
  overflow-y: auto;
  font-family: 'Consolas', 'Monaco', monospace;
  color: #606266;
}

.warning-text {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: #e6a23c;
}
</style>
