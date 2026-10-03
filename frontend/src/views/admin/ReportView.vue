<script setup>
/**
 * 管理端 - 举报处理。
 * 支持「驳回」与「举报成立」，成立时可联动删除帖子或封禁用户。
 */
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'

import adminApi from '@/api/admin'
import { statusTagType } from '@/utils'

const loading = ref(false)
const list = ref([])
const total = ref(0)
const query = reactive({ page: 1, size: 10, status: '', keyword: '' })

onMounted(load)

async function load() {
  loading.value = true
  try {
    const params = { page: query.page, size: query.size }
    if (query.status) params.status = query.status
    if (query.keyword) params.keyword = query.keyword
    const data = await adminApi.reports.list(params)
    list.value = data.list || []
    total.value = data.total || 0
  } catch (error) {
    list.value = []
  } finally {
    loading.value = false
  }
}

async function handle(row, status) {
  const isHandled = status === 'handled'
  try {
    const { value } = await ElMessageBox.prompt(
      isHandled ? '请填写处理说明（可选联动动作将在下一步选择）' : '请填写驳回理由',
      isHandled ? '举报成立' : '驳回举报',
      { inputPlaceholder: '处理说明', confirmButtonText: '下一步' }
    )

    let action = 'none'
    if (isHandled) {
      const chosen = await ElMessageBox.confirm(
        '是否需要联动处理？选择「删除帖子」将把被举报内容移入回收站。',
        '联动动作',
        {
          distinguishCancelAndClose: true,
          confirmButtonText: '删除帖子',
          cancelButtonText: '仅记录，不联动'
        }
      ).then(() => 'delete_post').catch((e) => (e === 'cancel' ? 'none' : null))

      if (chosen === null) return
      action = chosen
    }

    const data = await adminApi.reports.handle(row.id, { status, remark: value, action })
    ElMessage.success(data.action_result ? `处理完成：${data.action_result}` : '处理完成')
    load()
  } catch (error) {
    // 取消或接口报错
  }
}

function viewTarget(row) {
  const post = row.post || {}
  ElMessageBox.alert(
    `<div style="line-height:1.9">
       <b>举报原因：</b>${row.reason}<br/>
       <b>补充说明：</b>${row.detail || '-'}<br/>
       <b>举报人：</b>${row.reporter?.display_name || '-'}<br/>
       <b>被举报帖子：</b>#${post.id || '-'} ${post.title || '-'}<br/>
       <b>帖子内容：</b>${post.content || '-'}<br/>
       <b>被举报用户：</b>${row.target_user?.display_name || post.author?.display_name || '-'}
     </div>`,
    `举报 #${row.id}`,
    { dangerouslyUseHTMLString: true, confirmButtonText: '关闭' }
  ).catch(() => {
    // 用户点 × / ESC 关闭时会 reject，必须吞掉，否则报 Uncaught (in promise) cancel
  })
}
</script>

<template>
  <div>
    <div class="slp-card">
      <div class="slp-toolbar">
        <el-input v-model="query.keyword" placeholder="搜索举报原因 / 说明" clearable style="width: 220px" @keyup.enter="load" />
        <el-select v-model="query.status" placeholder="全部状态" clearable style="width: 140px" @change="load">
          <el-option label="待处理" value="pending" />
          <el-option label="已处理" value="handled" />
          <el-option label="已驳回" value="rejected" />
        </el-select>
        <el-button type="primary" @click="load">查询</el-button>
      </div>
    </div>

    <div class="slp-card">
      <el-table v-loading="loading" :data="list" size="small">
        <el-table-column prop="id" label="ID" width="70" />
        <el-table-column prop="reason" label="举报原因" width="160" show-overflow-tooltip />
        <el-table-column prop="detail" label="补充说明" min-width="160" show-overflow-tooltip />
        <el-table-column label="被举报帖子" min-width="180" show-overflow-tooltip>
          <template #default="{ row }">
            <span v-if="row.post">#{{ row.post.id }} {{ row.post.title }}</span>
            <span v-else class="slp-text-sub">-</span>
          </template>
        </el-table-column>
        <el-table-column label="举报人" width="120">
          <template #default="{ row }">{{ row.reporter?.display_name || '-' }}</template>
        </el-table-column>
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="statusTagType(row.status)" size="small">{{ row.status_label }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="created_at" label="举报时间" width="160" />
        <el-table-column label="处理说明" width="160" show-overflow-tooltip>
          <template #default="{ row }">{{ row.handle_remark || '-' }}</template>
        </el-table-column>
        <el-table-column label="操作" width="200" fixed="right">
          <template #default="{ row }">
            <el-button text type="primary" size="small" @click="viewTarget(row)">查看</el-button>
            <template v-if="row.status === 'pending'">
              <el-button text type="success" size="small" @click="handle(row, 'handled')">举报成立</el-button>
              <el-button text type="danger" size="small" @click="handle(row, 'rejected')">驳回</el-button>
            </template>
          </template>
        </el-table-column>
      </el-table>

      <el-empty v-if="!loading && !list.length" description="没有举报记录" :image-size="70" />

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
