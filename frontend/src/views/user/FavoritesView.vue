<script setup>
/**
 * 我的收藏。
 */
import { onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'

import { favoriteApi } from '@/api/interaction'
import PostCard from '@/components/PostCard.vue'

const router = useRouter()

const loading = ref(false)
const list = ref([])
const total = ref(0)
const query = reactive({ page: 1, size: 10 })

onMounted(load)

async function load() {
  loading.value = true
  try {
    const data = await favoriteApi.list({ page: query.page, size: query.size })
    list.value = data.list || []
    total.value = data.total || 0
  } catch (error) {
    list.value = []
  } finally {
    loading.value = false
  }
}

function goDetail(post) {
  if (post.status !== 'ongoing') return
  router.push({ name: 'post-detail', params: { id: post.id } })
}
</script>

<template>
  <div class="slp-container slp-page">
    <div class="slp-card">
      <h2>我的收藏</h2>
      <p class="slp-text-sub">共 {{ total }} 条</p>
    </div>

    <div v-loading="loading">
      <PostCard v-for="post in list" :key="post.id" :post="post" @click="goDetail" />
      <el-empty v-if="!loading && !list.length" description="还没有收藏任何信息" />
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
