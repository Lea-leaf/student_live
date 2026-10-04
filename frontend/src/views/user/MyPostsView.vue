<script setup>
/**
 * 我的发布：含待审核 / 未通过 / 已关闭等全部状态。
 * 支持状态筛选、编辑、删除、快速标记「已认领」。
 */
import { onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'

import lostFoundApi from '@/api/lostFound'
import { formatTime, statusTagType } from '@/utils'

const router = useRouter()

const loading = ref(false)
const list = ref([])
const total = ref(0)
const query = reactive({ page: 1, size: 10, status: '', audit_status: '' })

// 模块状态字典：我的发布是跨模块列表，按每条帖子的 type 懒加载 /meta
const metaMap = reactive({})
const countVisible = ref(false)
const countSaving = ref(false)
const countForm = reactive({
  postId: null,
  target_count: 1,
  current_count: 0,
  like_count: 0
})

onMounted(load)

async function load() {
  loading.value = true
  try {
    const params = { page: query.page, size: query.size }
    if (query.status) params.status = query.status
    if (query.audit_status) params.audit_status = query.audit_status
    const data = await lostFoundApi.myPosts(params)
    list.value = data.list || []
    total.value = data.total || 0
    await ensureMetas(list.value)
  } catch (error) {
    list.value = []
  } finally {
    loading.value = false
  }
}

async function ensureMetas(rows) {
  const types = [...new Set(rows.map((item) => item.type).filter(Boolean))]
  await Promise.all(types.map((type) => ensureMeta(type)))
}

async function ensureMeta(type) {
  if (!type || metaMap[type]) return metaMap[type] || []
  try {
    const data = await lostFoundApi.meta({ type })
    metaMap[type] = data.statuses || []
  } catch (error) {
    metaMap[type] = []
  }
  return metaMap[type]
}

const FALLBACK_STATUS_LABELS = {
  ongoing: '进行中',
  claimed: '已认领',
  expired: '已过期',
  closed: '已关闭'
}

function statusLabel(item, status) {
  const hit = (metaMap[item.type] || []).find((option) => option.value === status)
  return hit?.label || FALLBACK_STATUS_LABELS[status] || status
}

function canClaim(item) {
  return item.status === 'ongoing' && (metaMap[item.type] || []).some((option) => option.value === 'claimed')
}

function canClose(item) {
  return item.status !== 'closed' && (metaMap[item.type] || []).some((option) => option.value === 'closed')
}

function openCountDialog(item) {
  countForm.postId = item.id
  countForm.target_count = Number(item.ext?.target_count ?? 1)
  countForm.current_count = Number(item.ext?.current_count ?? 0)
  countForm.like_count = Number(item.like_count || 0)
  countVisible.value = true
}

async function saveCount() {
  if (!countForm.postId) return
  countSaving.value = true
  try {
    await lostFoundApi.updateCount(countForm.postId, {
      target_count: countForm.target_count,
      current_count: countForm.current_count
    })
    ElMessage.success('人数已更新')
    countVisible.value = false
    load()
  } catch (error) {
    // 拦截器已提示
  } finally {
    countSaving.value = false
  }
}

async function syncIntent(item) {
  try {
    await ElMessageBox.confirm(
      `把当前人数同步为「意向 ${item.like_count} 人」？目标人数不变。`,
      '按意向同步',
      { type: 'warning', confirmButtonText: '同步' }
    )
  } catch (error) {
    return
  }
  try {
    await lostFoundApi.updateCount(item.id, { current_count: Number(item.like_count || 0) })
    ElMessage.success('已按意向人数同步')
    load()
  } catch (error) {
    // 拦截器已提示
  }
}

function onFilterChange() {
  query.page = 1
  load()
}

async function markClaimed(item) {
  const label = statusLabel(item, 'claimed')
  try {
    await ElMessageBox.confirm(`标记为「${label}」后，该信息将不再提供详情查看，确认吗？`, '操作确认', {
      type: 'warning'
    })
  } catch (error) {
    return
  }
  try {
    await lostFoundApi.updateStatus(item.id, { status: 'claimed' })
    ElMessage.success(`已标记为「${label}」`)
    load()
  } catch (error) {
    // 拦截器已提示
  }
}

async function closePost(item) {
  const label = statusLabel(item, 'closed')
  try {
    await ElMessageBox.confirm(`确认标记为「${label}」吗？`, '操作确认', {
      type: 'warning'
    })
  } catch (error) {
    return
  }
  try {
    await lostFoundApi.updateStatus(item.id, { status: 'closed' })
    ElMessage.success(`已标记为「${label}」`)
    load()
  } catch (error) {
    // 拦截器已提示
  }
}

async function removePost(item) {
  try {
    await ElMessageBox.confirm('删除后可在管理员回收站恢复，确认删除吗？', '删除确认', {
      type: 'warning',
      confirmButtonText: '确认删除'
    })
  } catch (error) {
    return
  }
  try {
    await lostFoundApi.remove(item.id)
    ElMessage.success('已删除')
    load()
  } catch (error) {
    // 拦截器已提示
  }
}

const statusOptions = [
  { value: 'ongoing', label: '进行中' },
  { value: 'claimed', label: '已认领' },
  { value: 'expired', label: '已过期' },
  { value: 'closed', label: '已关闭' }
]

const auditOptions = [
  { value: 'pending', label: '待审核' },
  { value: 'approved', label: '已通过' },
  { value: 'rejected', label: '未通过' }
]
</script>

<template>
  <div class="slp-container slp-page">
    <div class="slp-card">
      <div class="slp-flex-between">
        <h2>我的发布</h2>
        <el-button type="primary" @click="router.push({ name: 'post-create' })">发布新信息</el-button>
      </div>
      <div class="slp-toolbar slp-mt-16">
        <el-select v-model="query.status" placeholder="业务状态" clearable style="width: 140px" @change="onFilterChange">
          <el-option v-for="item in statusOptions" :key="item.value" :label="item.label" :value="item.value" />
        </el-select>
        <el-select
          v-model="query.audit_status"
          placeholder="审核状态"
          clearable
          style="width: 140px"
          @change="onFilterChange"
        >
          <el-option v-for="item in auditOptions" :key="item.value" :label="item.label" :value="item.value" />
        </el-select>
        <el-button @click="load">刷新</el-button>
      </div>
    </div>

    <div v-loading="loading">
      <div v-for="item in list" :key="item.id" class="slp-card">
        <div class="slp-flex-between slp-mb-8">
          <h3 class="item-title">{{ item.title || '（无标题）' }}</h3>
          <div class="item-tags">
            <el-tag :type="statusTagType(item.audit_status)" size="small" effect="plain">
              {{ item.audit_status_label }}
            </el-tag>
            <el-tag :type="statusTagType(item.status)" size="small">{{ item.status_label }}</el-tag>
          </div>
        </div>

        <p class="slp-text-sub slp-mb-8">{{ item.content || '（无描述）' }}</p>

        <div class="post-card__meta slp-mb-8">
          <span>地点：{{ item.location || '-' }}</span>
          <span v-if="item.contact">联系方式：{{ item.contact }}</span>
          <span>浏览 {{ item.view_count }}</span>
          <span>{{ formatTime(item.created_at) }}</span>
        </div>

        <div v-if="item.type === 'group_buy' && item.ext" class="slp-text-sub slp-mb-8">
          当前人数 {{ item.ext.current_count }} / {{ item.ext.target_count }}
           开始日期 {{ item.ext.start_date }}
           意向 {{ item.like_count }} 人
        </div>

        <el-alert
          v-if="item.audit_status === 'rejected'"
          class="slp-mb-8"
          type="error"
          :closable="false"
          :title="`未通过审核：${item.audit_remark || '内容不符合平台规范'}`"
        />

        <div class="slp-toolbar">
          <el-button
            v-if="item.status === 'ongoing'"
            size="small"
            type="primary"
            plain
            @click="router.push({ name: 'post-detail', params: { id: item.id } })"
          >
            查看详情
          </el-button>
          <el-button size="small" @click="router.push({ name: 'post-edit', params: { id: item.id } })">
            编辑
          </el-button>
          <el-button v-if="item.type === 'group_buy'" size="small" plain @click="openCountDialog(item)">
            修改人数
          </el-button>
          <el-button v-if="item.type === 'group_buy'" size="small" plain @click="syncIntent(item)">
            按意向同步（{{ item.like_count }}）
          </el-button>
          <el-button v-if="canClaim(item)" size="small" type="success" plain @click="markClaimed(item)">
            标记{{ statusLabel(item, 'claimed') }}
          </el-button>
          <el-button v-if="canClose(item)" size="small" type="warning" plain @click="closePost(item)">
            {{ statusLabel(item, 'closed') }}
          </el-button>
          <el-button size="small" type="danger" plain @click="removePost(item)">删除</el-button>
        </div>
      </div>

      <el-empty v-if="!loading && !list.length" description="你还没有发布过信息">
        <el-button type="primary" @click="router.push({ name: 'post-create' })">去发布</el-button>
      </el-empty>
    </div>

    <el-dialog v-model="countVisible" title="修改拼单人数" width="420px">
      <el-form label-width="90px">
        <el-form-item label="目标人数">
          <el-input-number v-model="countForm.target_count" :min="1" :max="999" :step="1" />
        </el-form-item>
        <el-form-item label="当前人数">
          <el-input-number v-model="countForm.current_count" :min="0" :max="999" :step="1" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="countVisible = false">取消</el-button>
        <el-button type="primary" :loading="countSaving" @click="saveCount">保存</el-button>
      </template>
    </el-dialog>

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
.item-title {
  margin: 0;
  font-size: 16px;
}

.item-tags {
  display: flex;
  gap: 6px;
}
</style>
