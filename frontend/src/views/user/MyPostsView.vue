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
  } catch (error) {
    list.value = []
  } finally {
    loading.value = false
  }
}

function onFilterChange() {
  query.page = 1
  load()
}

async function markClaimed(item) {
  try {
    await ElMessageBox.confirm('标记为「已认领」后，该信息将不再提供详情查看，确认吗？', '操作确认', {
      type: 'warning'
    })
  } catch (error) {
    return
  }
  try {
    await lostFoundApi.claim(item.id)
    ElMessage.success('已标记为已认领')
    load()
  } catch (error) {
    // 拦截器已提示
  }
}

async function closePost(item) {
  try {
    await ElMessageBox.confirm('关闭后该信息不再出现在公开列表中，确认关闭吗？', '操作确认', {
      type: 'warning'
    })
  } catch (error) {
    return
  }
  try {
    await lostFoundApi.updateStatus(item.id, { status: 'closed' })
    ElMessage.success('已关闭')
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
          <span>联系方式：{{ item.contact }}</span>
          <span>浏览 {{ item.view_count }}</span>
          <span>{{ formatTime(item.created_at) }}</span>
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
          <el-button v-if="item.status === 'ongoing'" size="small" type="success" plain @click="markClaimed(item)">
            标记已认领
          </el-button>
          <el-button v-if="item.status !== 'closed'" size="small" type="warning" plain @click="closePost(item)">
            关闭
          </el-button>
          <el-button size="small" type="danger" plain @click="removePost(item)">删除</el-button>
        </div>
      </div>

      <el-empty v-if="!loading && !list.length" description="你还没有发布过信息">
        <el-button type="primary" @click="router.push({ name: 'post-create' })">去发布</el-button>
      </el-empty>
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
.item-title {
  margin: 0;
  font-size: 16px;
}

.item-tags {
  display: flex;
  gap: 6px;
}
</style>
