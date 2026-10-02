<script setup>
/**
 * 管理端 - 日志管理。
 * 需求：登录日志、操作日志、异常日志（可选）。
 * 异常日志直接读取后端 app/logs/error.log 的尾部，便于排障。
 */
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'

import adminApi from '@/api/admin'
import { downloadText } from '@/utils'

const activeTab = ref('operation')
const loading = ref(false)

const operations = reactive({ list: [], total: 0, page: 1, size: 15 })
const logins = reactive({ list: [], total: 0, page: 1, size: 15 })
const errors = reactive({ lines: [], path: '', exists: false })
const summary = ref({})

const opQuery = reactive({ keyword: '', module: '', action: '', log_type: '' })
const loginQuery = reactive({ keyword: '', success: '' })

const modules = ['auth', 'lost_found', 'users', 'posts', 'modules', 'trash', 'reports', 'configs']
const actions = ['login', 'logout', 'register', 'create', 'update', 'delete', 'audit', 'claim',
  'update_status', 'ban', 'unban', 'reset_password', 'change_role', 'toggle_top', 'restore',
  'purge', 'handle_report', 'cleanup_trash', 'update_configs']

onMounted(() => {
  loadSummary()
  loadOperations()
  loadLogins()
})

async function loadSummary() {
  try {
    summary.value = await adminApi.logs.summary()
  } catch (error) {
    // 忽略
  }
}

async function loadOperations(page = operations.page) {
  operations.page = page
  loading.value = true
  try {
    const params = { page, size: operations.size }
    Object.entries(opQuery).forEach(([key, value]) => { if (value) params[key] = value })
    const data = await adminApi.logs.operations(params)
    operations.list = data.list || []
    operations.total = data.total || 0
  } catch (error) {
    operations.list = []
  } finally {
    loading.value = false
  }
}

async function loadLogins(page = logins.page) {
  logins.page = page
  loading.value = true
  try {
    const params = { page, size: logins.size }
    Object.entries(loginQuery).forEach(([key, value]) => { if (value !== '') params[key] = value })
    const data = await adminApi.logs.logins(params)
    logins.list = data.list || []
    logins.total = data.total || 0
  } catch (error) {
    logins.list = []
  } finally {
    loading.value = false
  }
}

async function loadErrors() {
  loading.value = true
  try {
    const data = await adminApi.logs.errors({ lines: 300 })
    errors.lines = data.lines || []
    errors.path = data.path
    errors.exists = data.exists
  } catch (error) {
    errors.lines = []
  } finally {
    loading.value = false
  }
}

function onTabChange(name) {
  if (name === 'error' && !errors.lines.length) loadErrors()
}

function exportLogs() {
  if (activeTab.value === 'error') {
    if (!errors.lines.length) {
      ElMessage.warning('没有可导出的异常日志')
      return
    }
    downloadText('error.log', errors.lines.join('\n'))
    return
  }
  const rows = activeTab.value === 'operation' ? operations.list : logins.list
  if (!rows.length) {
    ElMessage.warning('没有可导出的日志')
    return
  }
  const headers = Object.keys(rows[0])
  const csv = [headers.join(',')].concat(
    rows.map((row) => headers.map((key) => `"${String(row[key] ?? '').replace(/"/g, '""')}"`).join(','))
  ).join('\n')
  downloadText(`${activeTab.value}-logs.csv`, `\ufeff${csv}`)
  ElMessage.success('已导出当前页日志')
}
</script>

<template>
  <div>
    <el-row :gutter="12">
      <el-col :xs="12" :sm="6">
        <div class="slp-card stat-card">
          <div class="stat-card__label">操作日志总数</div>
          <div class="stat-card__value">{{ summary.operation_total || 0 }}</div>
          <div class="stat-card__label">今日 {{ summary.operation_today || 0 }}</div>
        </div>
      </el-col>
      <el-col :xs="12" :sm="6">
        <div class="slp-card stat-card">
          <div class="stat-card__label">登录日志总数</div>
          <div class="stat-card__value">{{ summary.login_total || 0 }}</div>
          <div class="stat-card__label">今日 {{ summary.login_today || 0 }}</div>
        </div>
      </el-col>
      <el-col :xs="12" :sm="6">
        <div class="slp-card stat-card">
          <div class="stat-card__label">今日登录失败</div>
          <div class="stat-card__value" style="color: #f56c6c">{{ summary.login_failed_today || 0 }}</div>
        </div>
      </el-col>
      <el-col :xs="12" :sm="6">
        <div class="slp-card stat-card">
          <div class="stat-card__label">异常日志文件</div>
          <div class="stat-card__value" style="font-size: 16px">
            {{ errors.exists ? '可读取' : '未生成' }}
          </div>
        </div>
      </el-col>
    </el-row>

    <div class="slp-card">
      <el-tabs v-model="activeTab" @tab-change="onTabChange">
        <!-- 操作日志 -->
        <el-tab-pane label="操作日志" name="operation">
          <div class="slp-toolbar slp-mb-16">
            <el-input v-model="opQuery.keyword" placeholder="搜索账号 / 动作 / 详情" clearable style="width: 220px" @keyup.enter="loadOperations(1)" />
            <el-select v-model="opQuery.module" placeholder="全部模块" clearable style="width: 150px">
              <el-option v-for="item in modules" :key="item" :label="item" :value="item" />
            </el-select>
            <el-select v-model="opQuery.action" placeholder="全部动作" clearable style="width: 160px">
              <el-option v-for="item in actions" :key="item" :label="item" :value="item" />
            </el-select>
            <el-button type="primary" @click="loadOperations(1)">查询</el-button>
            <div style="flex: 1"></div>
            <el-button @click="exportLogs">导出 CSV</el-button>
          </div>

          <el-table v-loading="loading" :data="operations.list" size="small">
            <el-table-column prop="id" label="ID" width="70" />
            <el-table-column prop="username" label="操作人" width="120" />
            <el-table-column prop="module" label="模块" width="110" />
            <el-table-column prop="action" label="动作" width="130" />
            <el-table-column label="对象" width="130">
              <template #default="{ row }">
                {{ row.target_type || '-' }}<span v-if="row.target_id">#{{ row.target_id }}</span>
              </template>
            </el-table-column>
            <el-table-column prop="ip" label="IP" width="140" />
            <el-table-column prop="detail" label="详情" min-width="200" show-overflow-tooltip>
              <template #default="{ row }">
                {{ typeof row.detail === 'object' ? JSON.stringify(row.detail) : (row.detail || '-') }}
              </template>
            </el-table-column>
            <el-table-column prop="created_at" label="时间" width="160" />
          </el-table>

          <div v-if="operations.total > operations.size" class="slp-mt-16" style="text-align: right">
            <el-pagination
              layout="prev, pager, next, total"
              :total="operations.total"
              :page-size="operations.size"
              :current-page="operations.page"
              background
              @current-change="loadOperations"
            />
          </div>
        </el-tab-pane>

        <!-- 登录日志 -->
        <el-tab-pane label="登录日志" name="login">
          <div class="slp-toolbar slp-mb-16">
            <el-input v-model="loginQuery.keyword" placeholder="搜索学号 / IP / 说明" clearable style="width: 220px" @keyup.enter="loadLogins(1)" />
            <el-select v-model="loginQuery.success" placeholder="全部结果" clearable style="width: 140px">
              <el-option label="成功" value="1" />
              <el-option label="失败" value="0" />
            </el-select>
            <el-button type="primary" @click="loadLogins(1)">查询</el-button>
            <div style="flex: 1"></div>
            <el-button @click="exportLogs">导出 CSV</el-button>
          </div>

          <el-table v-loading="loading" :data="logins.list" size="small">
            <el-table-column prop="id" label="ID" width="70" />
            <el-table-column prop="student_id" label="尝试登录账号" width="140" />
            <el-table-column label="结果" width="90">
              <template #default="{ row }">
                <el-tag :type="row.success ? 'success' : 'danger'" size="small">
                  {{ row.success ? '成功' : '失败' }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="message" label="说明" min-width="180" show-overflow-tooltip />
            <el-table-column prop="ip" label="IP" width="150" />
            <el-table-column prop="user_agent" label="User-Agent" min-width="200" show-overflow-tooltip />
            <el-table-column prop="created_at" label="时间" width="160" />
          </el-table>

          <div v-if="logins.total > logins.size" class="slp-mt-16" style="text-align: right">
            <el-pagination
              layout="prev, pager, next, total"
              :total="logins.total"
              :page-size="logins.size"
              :current-page="logins.page"
              background
              @current-change="loadLogins"
            />
          </div>
        </el-tab-pane>

        <!-- 异常日志 -->
        <el-tab-pane label="异常日志" name="error">
          <div class="slp-toolbar slp-mb-16">
            <span class="slp-text-sub">日志文件：{{ errors.path || 'app/logs/error.log' }}</span>
            <div style="flex: 1"></div>
            <el-button @click="loadErrors">刷新</el-button>
            <el-button @click="exportLogs">导出</el-button>
          </div>
          <pre v-if="errors.lines.length" class="error-log">{{ errors.lines.join('\n') }}</pre>
          <el-empty v-else description="暂时没有异常日志（这是好事）" :image-size="70" />
        </el-tab-pane>
      </el-tabs>
    </div>
  </div>
</template>

<style scoped>
.error-log {
  max-height: 460px;
  overflow: auto;
  background: #1f2d3d;
  color: #f0f2f5;
  padding: 14px;
  border-radius: 8px;
  font-size: 12px;
  line-height: 1.7;
  white-space: pre-wrap;
  word-break: break-all;
}
</style>
