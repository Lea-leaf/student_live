<script setup>
/**
 * 管理端 - 审核工作台。
 * 需求 6.4：默认管理员审核通过后才显示；审核状态：待审核 / 已通过 / 已拒绝。
 * 支持单条审核与批量审核，审核结果自动给发布者发通知。
 */
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'

import adminApi from '@/api/admin'
import { statusTagType } from '@/utils'

const loading = ref(false)
const list = ref([])
const total = ref(0)
const selection = ref([])
const moduleOptions = ref([])
const batchRemark = ref('')
const query = reactive({ page: 1, size: 10, type: '' })

onMounted(load)

async function load() {
  loading.value = true
  try {
    const params = { page: query.page, size: query.size }
    if (query.type) params.type = query.type
    const data = await adminApi.posts.pending(params)
    list.value = data.list || []
    total.value = data.total || 0
    if (!moduleOptions.value.length) {
      const all = await adminApi.posts.list({ page: 1, size: 1 })
      moduleOptions.value = all.modules || []
    }
  } catch (error) {
    list.value = []
  } finally {
    loading.value = false
  }
}

async function auditOne(row, auditStatus) {
  const label = auditStatus === 'approved' ? '通过' : '拒绝'
  try {
    const { value } = await ElMessageBox.prompt(
      auditStatus === 'approved' ? '审核备注（选填）' : '请填写拒绝原因（会通知发布者）',
      `${label}「${row.title || row.id}」`,
      {
        inputPlaceholder: '审核意见',
        confirmButtonText: `确认${label}`,
        inputValidator: auditStatus === 'rejected'
          ? (text) => (text && text.trim() ? true : '拒绝时必须填写原因')
          : undefined,
        type: 'warning'
      }
    )
    await adminApi.posts.audit(row.id, { audit_status: auditStatus, remark: value || null })
    ElMessage.success(`已${label}`)
    load()
  } catch (error) {
    // 取消或接口报错
  }
}

async function batchAudit(auditStatus) {
  if (!selection.value.length) {
    ElMessage.warning('请先勾选要审核的信息')
    return
  }
  const label = auditStatus === 'approved' ? '通过' : '拒绝'
  try {
    await ElMessageBox.confirm(
      `确认批量${label} ${selection.value.length} 条信息吗？`,
      '批量审核',
      { type: 'warning' }
    )
    const data = await adminApi.posts.batchAudit({
      post_ids: selection.value.map((item) => item.id),
      audit_status: auditStatus,
      remark: batchRemark.value || null
    })
    ElMessage.success(`已处理 ${data.affected} 条`)
    batchRemark.value = ''
    load()
  } catch (error) {
    // 取消
  }
}

function preview(row) {
  const media = (row.media || [])
    .map((item) => (item.type === 'video'
      ? `<video src="${item.url}" controls style="width:160px;height:120px;object-fit:cover"></video>`
      : `<img src="${item.url}" style="width:120px;height:120px;object-fit:cover;border-radius:6px"/>`))
    .join('')
  ElMessageBox.alert(
    `<div style="line-height:1.9">
       <b>标题：</b>${row.title || '（无标题）'}<br/>
       <b>描述：</b>${(row.content || '（无描述）').replace(/\n/g, '<br/>')}<br/>
       <b>地点：</b>${row.location || '-'}　<b>时间：</b>${row.happened_at || '-'}<br/>
       <b>联系方式：</b>${row.contact}<br/>
       <b>发布者：</b>${row.author?.display_name || '-'}（${row.author?.student_id || '-'}）<br/>
       <div style="display:flex;gap:8px;flex-wrap:wrap;margin-top:8px">${media}</div>
     </div>`,
    `待审核 #${row.id}`,
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
        <el-select v-model="query.type" placeholder="全部模块" clearable style="width: 160px" @change="load">
          <el-option v-for="item in moduleOptions" :key="item.code" :label="item.name" :value="item.code" />
        </el-select>
        <el-button @click="load">刷新</el-button>
        <div style="flex: 1"></div>
        <el-input v-model="batchRemark" placeholder="批量审核备注（选填）" style="width: 220px" />
        <el-button type="success" :disabled="!selection.length" @click="batchAudit('approved')">
          批量通过（{{ selection.length }}）
        </el-button>
        <el-button type="danger" plain :disabled="!selection.length" @click="batchAudit('rejected')">
          批量拒绝
        </el-button>
      </div>
      <p class="slp-text-sub slp-mt-8">
        待审核 {{ total }} 条。审核通过后信息才会在公开列表中显示；拒绝时请填写原因，系统会自动通知发布者。
      </p>
    </div>

    <div v-loading="loading">
      <div v-for="row in list" :key="row.id" class="slp-card">
        <div class="audit-row">
          <el-checkbox
            :model-value="selection.some((item) => item.id === row.id)"
            @change="(checked) => {
              if (checked) selection = selection.concat([row])
              else selection = selection.filter((item) => item.id !== row.id)
            }"
          />
          <div class="audit-row__body">
            <div class="slp-flex-between slp-mb-8">
              <h3 class="audit-row__title">#{{ row.id }} {{ row.title || '（无标题）' }}</h3>
              <div class="audit-row__tags">
                <el-tag type="warning" size="small">待审核</el-tag>
                <el-tag size="small" effect="plain">{{ row.module_name || row.type }}</el-tag>
              </div>
            </div>
            <p class="slp-text-sub slp-mb-8" style="white-space: pre-line">{{ row.content || '（无描述）' }}</p>
            <div class="post-card__meta slp-mb-8">
              <span>地点：{{ row.location || '-' }}</span>
              <span>时间：{{ row.happened_at || '-' }}</span>
              <span>联系方式：{{ row.contact }}</span>
              <span>发布者：{{ row.author?.display_name }}（{{ row.author?.student_id }}）</span>
              <span>{{ row.created_at }}</span>
            </div>
            <div v-if="(row.media || []).length" class="audit-row__media">
              <template v-for="item in row.media" :key="item.url">
                <video v-if="item.type === 'video'" :src="item.url" />
                <img v-else :src="item.url" alt="配图" />
              </template>
            </div>
            <div class="slp-toolbar slp-mt-8">
              <el-button size="small" @click="preview(row)">查看完整内容</el-button>
              <el-button size="small" type="success" @click="auditOne(row, 'approved')">通过</el-button>
              <el-button size="small" type="danger" plain @click="auditOne(row, 'rejected')">拒绝</el-button>
            </div>
          </div>
        </div>
      </div>

      <el-empty v-if="!loading && !list.length" description="暂无待审核信息 🎉" />
    </div>

    <div v-if="total > query.size" class="slp-mt-16" style="text-align: center">
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
</template>

<style scoped>
.audit-row {
  display: flex;
  gap: 12px;
  align-items: flex-start;
}

.audit-row__body {
  flex: 1;
  min-width: 0;
}

.audit-row__title {
  margin: 0;
  font-size: 16px;
}

.audit-row__tags {
  display: flex;
  gap: 6px;
}

.audit-row__media {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.audit-row__media img,
.audit-row__media video {
  width: 90px;
  height: 90px;
  object-fit: cover;
  border-radius: 6px;
  border: 1px solid #ebeef5;
}
</style>
