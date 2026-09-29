<template>
  <div class="tool-stats">
    <el-card shadow="never" class="stats-card">
      <template #header>
        <div class="stats-header">
          <el-icon><DataAnalysis /></el-icon>
          <span>工具调用统计（ECharts）</span>
        </div>
      </template>
      <div ref="chartRef" class="chart-container"></div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, onMounted, onBeforeUnmount } from 'vue'
import * as echarts from 'echarts'
import { DataAnalysis } from '@element-plus/icons-vue'
import type { ToolCall } from '@/types'

const props = defineProps<{
  toolCalls: ToolCall[]
}>()

const chartRef = ref<HTMLDivElement>()
let chart: echarts.ECharts | null = null

function renderChart(): void {
  if (!chartRef.value) return
  if (!chart) {
    chart = echarts.init(chartRef.value)
  }

  // 按工具名统计调用次数
  const counts: Record<string, number> = {}
  for (const tc of props.toolCalls || []) {
    counts[tc.toolName] = (counts[tc.toolName] || 0) + 1
  }
  const names = Object.keys(counts)
  const values = Object.values(counts)

  chart.setOption({
    tooltip: { trigger: 'axis' },
    grid: { left: 48, right: 20, top: 20, bottom: 32 },
    xAxis: {
      type: 'category',
      data: names,
      axisLabel: { interval: 0, rotate: 30, fontSize: 11 }
    },
    yAxis: {
      type: 'value',
      minInterval: 1,
      name: '调用次数'
    },
    series: [{
      type: 'bar',
      data: values,
      barWidth: 28,
      itemStyle: {
        borderRadius: [4, 4, 0, 0],
        color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
          { offset: 0, color: '#667eea' },
          { offset: 1, color: '#764ba2' }
        ])
      },
      label: { show: true, position: 'top', fontSize: 11 }
    }]
  })
}

function handleResize(): void {
  chart?.resize()
}

watch(() => props.toolCalls, () => renderChart(), { deep: true })

onMounted(() => {
  renderChart()
  window.addEventListener('resize', handleResize)
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', handleResize)
  chart?.dispose()
  chart = null
})
</script>

<style scoped>
.stats-card {
  margin-bottom: 16px;
}

.stats-header {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  font-weight: 600;
  color: #606266;
}

.chart-container {
  height: 220px;
  width: 100%;
}
</style>
