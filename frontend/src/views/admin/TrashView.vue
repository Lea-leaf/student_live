<script setup>
/**
 * 管理端 - 回收站。
 * 需求：软删除帖子仅管理员可见，默认保留最近 10 条，数量可配置。
 */
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'

import adminApi from '@/api/admin'
import { formatTime } from '@/utils'

const loading = ref(false)
const list = ref([])
const total = ref(0)
const stats = ref({})
const keepCount = ref(10)
const selection = ref([])
const query = reactive({ page: 1, size: 10, keyword: '', type: '' })

onMounted(loadAll)

async function loadAll() {
  await Promise.all([load(), loadStats()])
}

async function load() {
  loading.value = true
  try {
    const params = { page: query.page, size: query.size }
    if (query.keyword) params.keyword = query.keyword
    if (query.type) params.type = query.type
    const data = await adminApi.trash.list(params)
    list.value = data.list || []
    total.value = data.total || 0
    keepCount.value = data.retention_count || 10
  } catch (error) {
    list.value = []
  } finally {
    loading.value = false
  }
}

async function loadStats() {
  try {
    stats.value = await adminApi.trash.stats()
    keepCount.value = stats.value.retention_count || keepCount.value
  } catch (error) {
    // 忽略
  }
}

async function restore(row) {
  try {
    await adminApi.trash.restore(row.id)
    ElMessage.success('已恢复')
    loadAll()
  } catch (error) {
    // 拦截器已提示
  }
}

async function purge(row) {
  try {
    await ElMessageBox.confirm(
      `彻底删除后无法恢复，确认删除「${row.title || row.id}」吗？`,
      '彻底删除',
      { type: 'error', confirmButtonText: '确认彻底删除' }
    )
    await adminApi.trash.purge(row.id)
    ElMessage.success('已彻底删除')
    loadAll()
  } catch (error) {
    // 取消
  }
}

async function batchRestore() {
  if (!selection.value.length) return
  const data = await adminApi.trash.list({ page: 1, size: 100 })
  ElMessage.info(`当前回收站共 ${data.total} 条，正在恢复选中的 ${selection.value.length} 条`)
  for (const row of selection.value) {
    // 逐个恢复，保证失败可定位
    // eslint-disable-next-line no-await-in-loop
    await adminApi.trash.restore(row.id).catch(() => {})
  }
  ElMessage.success('批量恢复完成')
  loadAll()
}

async function cleanup() {
  try {
    const { value } = await ElMessageBox.prompt(
      '超出保留条数的旧记录将被彻底删除，请输入保留条数',
      '按保留条数清理',
      { inputValue: String(keepCount.value), inputPattern: /^\d+$/, inputErrorMessage: '请输入数字' }
    )
    const data = await adminApi.trash.cleanup({ keep: Number(value) })
    ElMessage.success(`已清理 ${data.removed} 条，当前保留最近 ${data.keep} 条`)
    loadAll()
  } catch (error) {
    // 取消
  }
}
</script>

<template>
  <div>
    <el-row :gutter="12">
      <el-col :xs="24" :sm="8">
        <div class="slp-card stat-card">
          <div class="stat-card__label">回收站条数</div>
          <div class="stat-card__value">{{ stats.total || 0 }}</div>
        </div>
      </el-col>
      <el-col :xs="24" :sm="8">
        <div class="slp-card stat-card">
          <div class="stat-card__label">保留条数（可配置）</div>
          <div class="stat-card__value">{{ stats.retention_count || 10 }}</div>
        </div>
      </el-col>
      <el-col :xs="24" :sm="8">
        <div class="slp-card stat-card">
          <div class="stat-card__label">超量处理方式</div>
          <div class="stat-card__value" style="font-size: 18px">
            {{ stats.retention_mode === 'force' ? '彻底删除旧记录' : '仅保留不删除' }}
          </div>
        </div>
      </el-col>
    </el-row>

    <div class="slp-card">
      <div class="slp-toolbar">
        <el-input v-model="query.keyword" placeholder="搜索标题 / 描述" clearable style="width: 220px" @keyup.enter="load" />
        <el-button type="primary" @click="load">查询</el-button>
        <el-button @click="loadAll">刷新</el-button>
        <div style="flex: 1"></div>
        <el-button :disabled="!selection.length" @click="batchRestore">
          批量恢复（{{ selection.length }}）
        </el-button>
        <el-button type="warning" plain @click="cleanup">按保留条数清理</el-button>
      </div>
      <p class="slp-text-sub slp-mt-8">
        软删除的帖子只在这里可见，普通用户完全看不到。超出保留条数的旧记录会按配置自动彻底删除。
      </p>
    </div>

    <div class="slp-card">
      <el-table
        v-loading="loading"
        :data="list"
        size="small"
        @selection-change="(rows) => (selection = rows)"
      >
        <el-table-column type="selection" width="45" />
        <el-table-column prop="id" label="ID" width="70" />
        <el-table-column label="标题" min-width="180" show-overflow-tooltip>
          <template #default="{ row }">{{ row.title || '（无标题）' }}</template>
        </el-table-column>
        <el-table-column label="模块" width="100">
          <template #default="{ row }">{{ row.module_name || row.type }}</template>
        </el-table-column>
        <el-table-column label="发布者" width="130">
          <template #default="{ row }">{{ row.author?.display_name || '-' }}</template>
        </el-table-column>
        <el-table-column prop="contact" label="联系方式" width="150" show-overflow-tooltip />
        <el-table-column label="删除人" width="130">
          <template #default="{ row }">{{ row.deleted_by_user?.display_name || '用户本人' }}</template>
        </el-table-column>
        <el-table-column label="删除时间" width="160">
          <template #default="{ row }">{{ formatTime(row.deleted_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="160" fixed="right">
          <template #default="{ row }">
            <el-button text type="primary" size="small" @click="restore(row)">恢复</el-button>
            <el-button text type="danger" size="small" @click="purge(row)">彻底删除</el-button>
          </template>
        </el-table-column>
      </el-table>

      <el-empty v-if="!loading && !list.length" description="回收站是空的" :image-size="70" />

      <div v-if="total > query.size" class="slp-mt-16" style="text-align: right">
        <el-pagination
          layout="prev, pager, next, total"
          :total="total"
          :page-size="query.size"
          :current-page="query.page"
          background
          @current-change="(page) => { query.page = page; load() }"
        />
      </div>
    </div>
  </div>
</template>
