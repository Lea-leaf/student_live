<script setup>
/**
 * 管理端 - 概览。
 * 需求：用户总数、帖子总数、今日新增、待审核数量。
 * 额外：7 日趋势（纯 CSS 柱状图，避免额外引入图表库）、模块分布、待审核快捷入口。
 */
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import adminApi from '@/api/admin'

const router = useRouter()

const loading = ref(false)
const stats = ref({})
const trend = ref({ labels: [], posts: [], users: [] })
const moduleStats = ref([])
const pending = ref([])

const cards = computed(() => [
  { label: '用户总数', value: stats.value.user_total || 0, sub: `今日新增 ${stats.value.user_today || 0}`, color: '#409eff' },
  { label: '帖子总数', value: stats.value.post_total || 0, sub: `今日新增 ${stats.value.post_today || 0}`, color: '#67c23a' },
  { label: '待审核', value: stats.value.post_pending || 0, sub: '点击进入审核工作台', color: '#e6a23c', route: 'admin-audit' },
  { label: '待处理举报', value: stats.value.report_pending || 0, sub: '点击查看举报', color: '#f56c6c', route: 'admin-reports' },
  { label: '回收站', value: stats.value.recycle_total || 0, sub: '软删除的帖子', color: '#909399', route: 'admin-trash' },
  { label: '封禁用户', value: stats.value.user_banned || 0, sub: `今日登录 ${stats.value.login_today || 0} 次`, color: '#b88230' }
])

/** 趋势柱状图高度（按最大值归一化） */
const trendMax = computed(() => {
  const values = [...(trend.value.posts || []), ...(trend.value.users || [])]
  return Math.max(1, ...values)
})

function barHeight(value) {
  return `${Math.round((value / trendMax.value) * 100)}%`
}

onMounted(loadAll)

async function loadAll() {
  loading.value = true
  try {
    const [overview, trendData, moduleData, pendingData] = await Promise.all([
      adminApi.dashboard.overview(),
      adminApi.dashboard.trend({ days: 7 }),
      adminApi.dashboard.moduleStats(),
      adminApi.dashboard.pending({ limit: 8 })
    ])
    stats.value = overview
    trend.value = trendData
    moduleStats.value = moduleData.list || []
    pending.value = pendingData.list || []
  } catch (error) {
    // 拦截器已提示
  } finally {
    loading.value = false
  }
}

function goCard(card) {
  if (card.route) router.push({ name: card.route })
}
</script>

<template>
  <div v-loading="loading">
    <!-- 统计卡片 -->
    <el-row :gutter="12">
      <el-col v-for="card in cards" :key="card.label" :xs="12" :sm="8" :md="4">
        <div
          class="slp-card stat-card"
          :style="{ borderTop: `3px solid ${card.color}`, cursor: card.route ? 'pointer' : 'default' }"
          @click="goCard(card)"
        >
          <div class="stat-card__label">{{ card.label }}</div>
          <div class="stat-card__value" :style="{ color: card.color }">{{ card.value }}</div>
          <div class="stat-card__label">{{ card.sub }}</div>
        </div>
      </el-col>
    </el-row>

    <el-row :gutter="12">
      <!-- 趋势 -->
      <el-col :xs="24" :md="14">
        <div class="slp-card">
          <h3 class="slp-mb-16">近 7 天新增趋势</h3>
          <div class="chart">
            <div v-for="(label, index) in trend.labels" :key="label" class="chart__col">
              <div class="chart__bars">
                <div
                  class="chart__bar chart__bar--post"
                  :style="{ height: barHeight(trend.posts[index] || 0) }"
                  :title="`发帖 ${trend.posts[index] || 0}`"
                />
                <div
                  class="chart__bar chart__bar--user"
                  :style="{ height: barHeight(trend.users[index] || 0) }"
                  :title="`注册 ${trend.users[index] || 0}`"
                />
              </div>
              <div class="chart__label">{{ label }}</div>
            </div>
          </div>
          <div class="chart__legend">
            <span><i class="dot dot--post" />发帖</span>
            <span><i class="dot dot--user" />注册</span>
          </div>
        </div>
      </el-col>

      <!-- 模块分布 -->
      <el-col :xs="24" :md="10">
        <div class="slp-card">
          <h3 class="slp-mb-16">模块帖子分布</h3>
          <el-table :data="moduleStats" size="small">
            <el-table-column prop="name" label="模块" />
            <el-table-column prop="code" label="标识" width="120" />
            <el-table-column prop="count" label="帖子数" width="90" align="right" />
          </el-table>
          <el-empty v-if="!moduleStats.length" description="暂无数据" :image-size="60" />
        </div>
      </el-col>
    </el-row>

    <!-- 待审核快捷处理 -->
    <div class="slp-card">
      <div class="slp-flex-between slp-mb-16">
        <h3>待审核信息（最近 8 条）</h3>
        <el-button text type="primary" @click="router.push({ name: 'admin-audit' })">进入审核工作台 →</el-button>
      </div>
      <el-table :data="pending" size="small" @row-click="() => router.push({ name: 'admin-audit' })">
        <el-table-column prop="id" label="ID" width="70" />
        <el-table-column prop="title" label="标题" show-overflow-tooltip />
        <el-table-column label="发布者" width="140">
          <template #default="{ row }">{{ row.author?.display_name || '-' }}</template>
        </el-table-column>
        <el-table-column prop="contact" label="联系方式" width="180" show-overflow-tooltip />
        <el-table-column prop="created_at" label="提交时间" width="160" />
      </el-table>
      <el-empty v-if="!pending.length" description="没有待审核的信息" :image-size="60" />
    </div>
  </div>
</template>

<style scoped>
.chart {
  display: flex;
  align-items: flex-end;
  gap: 8px;
  height: 180px;
}

.chart__col {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  height: 100%;
}

.chart__bars {
  flex: 1;
  width: 100%;
  display: flex;
  align-items: flex-end;
  justify-content: center;
  gap: 4px;
}

.chart__bar {
  width: 14px;
  min-height: 2px;
  border-radius: 3px 3px 0 0;
  transition: height 0.3s;
}

.chart__bar--post {
  background: #409eff;
}

.chart__bar--user {
  background: #67c23a;
}

.chart__label {
  font-size: 12px;
  color: #909399;
  margin-top: 6px;
}

.chart__legend {
  display: flex;
  gap: 16px;
  margin-top: 10px;
  font-size: 12px;
  color: #606266;
}

.chart__legend span {
  display: inline-flex;
  align-items: center;
  gap: 5px;
}

.dot {
  display: inline-block;
  width: 8px;
  height: 8px;
  border-radius: 50%;
}

.dot--post {
  background: #409eff;
}

.dot--user {
  background: #67c23a;
}
</style>
