<script setup>
/**
 * 信息列表页（失物招领等模块通用）。
 * 查询参数与后端 `GET /api/v1/lost_found/posts` 完全对应，
 * 因此 URL 可以直接分享（?type=lost_found&status=ongoing&keyword=伞）。
 */
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Search } from '@element-plus/icons-vue'

import lostFoundApi from '@/api/lostFound'
import PostCard from '@/components/PostCard.vue'
import { useAppStore } from '@/stores/app'
import { useUserStore } from '@/stores/user'

const route = useRoute()
const router = useRouter()
const appStore = useAppStore()
const userStore = useUserStore()

const loading = ref(false)
const posts = ref([])
const total = ref(0)

const query = reactive({
  page: 1,
  size: 10,
  keyword: '',
  status: '',
  sort: 'latest'
})

/** 模块：目前只有失物招领有完整业务，其他模块按启用状态显示 */
const activeModule = computed(() => String(route.query.type || 'lost_found'))

const metaStatuses = ref([])

/** 状态下拉优先走后端 /meta（按模块过滤 + 模块专属文案） */
const statusOptions = computed(() => {
  if (metaStatuses.value.length) return metaStatuses.value
  return appStore.enums.post_status || [
    { value: 'ongoing', label: '进行中' },
    { value: 'claimed', label: '已认领' },
    { value: 'expired', label: '已过期' },
    { value: 'closed', label: '已关闭' }
  ]
})

async function loadMeta() {
  try {
    const data = await lostFoundApi.meta({ type: activeModule.value })
    metaStatuses.value = data.statuses || []
    // 模块切换后，当前筛选值可能不属于新模块，自动清掉
    if (query.status && !metaStatuses.value.some((item) => item.value === query.status)) {
      query.status = ''
    }
  } catch (error) {
    metaStatuses.value = []
  }
}

onMounted(async () => {
  query.keyword = String(route.query.keyword || '')
  query.status = String(route.query.status || '')
  query.page = Number(route.query.page || 1)
  await loadMeta()
  load()
})

// 路由参数变化时重新加载（模块切换）
watch(() => route.query.type, async () => {
  query.page = 1
  query.status = ''
  await loadMeta()
  load()
})

async function load() {
  loading.value = true
  try {
    const params = {
      page: query.page,
      size: query.size,
      sort: query.sort,
      type: activeModule.value
    }
    if (query.keyword) params.keyword = query.keyword
    if (query.status) params.status = query.status
    const data = await lostFoundApi.list(params)
    posts.value = data.list || []
    total.value = data.total || 0
  } catch (error) {
    posts.value = []
    total.value = 0
  } finally {
    loading.value = false
  }
}

/** 把当前查询写回 URL，方便分享与刷新 */
function syncUrl() {
  router.replace({
    name: 'post-list',
    query: {
      type: activeModule.value,
      ...(query.keyword ? { keyword: query.keyword } : {}),
      ...(query.status ? { status: query.status } : {}),
      ...(query.page > 1 ? { page: query.page } : {})
    }
  })
}

function onSearch() {
  query.page = 1
  syncUrl()
  load()
}

function onReset() {
  query.keyword = ''
  query.status = ''
  query.sort = 'latest'
  query.page = 1
  syncUrl()
  load()
}

function onPageChange(page) {
  query.page = page
  syncUrl()
  load()
}

function goDetail(post) {
  router.push({ name: 'post-detail', params: { id: post.id } })
}

function goPublish() {
  if (!userStore.isLogin) {
    router.push({ name: 'login', query: { redirect: '/publish' } })
    return
  }
  router.push({ name: 'post-create' })
}

function switchModule(code) {
  router.push({ name: 'post-list', query: { type: code } })
}
</script>

<template>
  <div class="slp-container slp-page">
    <!-- 模块切换 -->
    <el-tabs :model-value="activeModule" class="slp-mb-8" @tab-change="switchModule">
      <el-tab-pane
        v-for="item in appStore.modules"
        :key="item.code"
        :label="item.name"
        :name="item.code"
      />
    </el-tabs>

    <!-- 搜索与筛选 -->
    <div class="slp-card">
      <div class="slp-toolbar">
        <el-input
          v-model="query.keyword"
          placeholder="搜索标题 / 描述 / 地点"
          :prefix-icon="Search"
          clearable
          style="width: 260px"
          @keyup.enter="onSearch"
        />
        <el-select v-model="query.status" placeholder="全部状态" clearable style="width: 140px">
          <el-option
            v-for="item in statusOptions"
            :key="item.value"
            :label="item.label"
            :value="item.value"
          />
        </el-select>
        <el-select v-model="query.sort" style="width: 140px">
          <el-option label="最新发布" value="latest" />
          <el-option label="最热（综合互动）" value="hot" />
          <el-option label="最早发布" value="oldest" />
        </el-select>
        <el-button type="primary" @click="onSearch">搜索</el-button>
        <el-button @click="onReset">重置</el-button>
        <div style="flex: 1"></div>
        <el-button type="primary" plain @click="goPublish">发布信息</el-button>
      </div>
      <p class="slp-text-sub slp-mt-8">
        共 {{ total }} 条信息。
        按平台规则：「已认领 / 已过期」仍会显示在列表中，但不再提供详情查看；
        「已关闭」的信息不进入公开列表。
      </p>
    </div>

    <!-- 列表 -->
    <div v-loading="loading">
      <PostCard v-for="post in posts" :key="post.id" :post="post" @click="goDetail" />
      <el-empty v-if="!loading && !posts.length" description="没有找到符合条件的信息" />
    </div>

    <!-- 分页 -->
    <div v-if="total > query.size" class="slp-flex-between slp-mt-16" style="justify-content: center">
      <el-pagination
        layout="prev, pager, next, total"
        :total="total"
        :page-size="query.size"
        :current-page="query.page"
        background
        @current-change="onPageChange"
      />
    </div>
  </div>
</template>
