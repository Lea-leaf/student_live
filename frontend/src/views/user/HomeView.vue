<script setup>
/**
 * 首页：模块入口 + 最新信息 + 平台数据概览。
 * 综合浏览：默认展示全部模块的帖子（这里以启用中的失物招领为主）。
 */
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import lostFoundApi from '@/api/lostFound'
import PostCard from '@/components/PostCard.vue'
import { useAppStore } from '@/stores/app'
import { useUserStore } from '@/stores/user'

const router = useRouter()
const appStore = useAppStore()
const userStore = useUserStore()

const loading = ref(false)
const posts = ref([])
const total = ref(0)

const modules = computed(() => appStore.modules)

onMounted(loadPosts)

async function loadPosts() {
  loading.value = true
  try {
    const data = await lostFoundApi.list({ page: 1, size: 6, sort: 'latest' })
    posts.value = data.list || []
    total.value = data.total || 0
  } catch (error) {
    // 拦截器已提示
  } finally {
    loading.value = false
  }
}

function goList(query = {}) {
  router.push({ name: 'post-list', query })
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
</script>

<template>
  <div class="slp-container slp-page">
    <!-- Hero -->
    <section class="hero slp-card">
      <div class="hero__text">
        <h1>{{ appStore.siteName }}</h1>
        <p>同学之间的校园生活互助平台：丢了东西、捡到东西，一句话发出来。</p>
        <div class="hero__actions">
          <el-button type="primary" size="large" @click="goPublish">我要发布</el-button>
          <el-button size="large" @click="goList()">浏览全部信息</el-button>
        </div>
      </div>
      <div class="hero__stats">
        <div>
          <div class="stat-card__value">{{ total }}</div>
          <div class="stat-card__label">条进行中的信息</div>
        </div>
        <div>
          <div class="stat-card__value">{{ modules.length }}</div>
          <div class="stat-card__label">个生活模块</div>
        </div>
      </div>
    </section>

    <!-- 模块入口 -->
    <section class="slp-card">
      <div class="slp-flex-between slp-mb-16">
        <h3>生活模块</h3>
        <span class="slp-text-sub">模块可在后台启停与排序</span>
      </div>
      <div class="module-grid">
        <div
          v-for="item in modules"
          :key="item.code"
          class="module-item"
          @click="goList({ type: item.code })"
        >
          <el-icon :size="22" color="#409eff"><Grid /></el-icon>
          <div>
            <div class="module-item__name">{{ item.name }}</div>
            <div class="slp-text-sub">{{ item.description || '暂无简介' }}</div>
          </div>
        </div>
        <el-empty v-if="!modules.length" description="暂无启用中的模块" :image-size="60" />
      </div>
    </section>

    <!-- 最新信息 -->
    <section>
      <div class="slp-flex-between slp-mb-8">
        <h3>最新信息</h3>
        <el-button text type="primary" @click="goList()">查看全部 →</el-button>
      </div>

      <div v-loading="loading">
        <PostCard v-for="post in posts" :key="post.id" :post="post" @click="goDetail" />
        <el-empty v-if="!loading && !posts.length" description="还没有信息，来发第一条吧" />
      </div>
    </section>
  </div>
</template>

<style scoped>
.hero {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 24px;
  padding: 28px;
  background: linear-gradient(120deg, #ffffff 0%, #f0f7ff 100%);
}

.hero__text h1 {
  margin: 0 0 10px;
  font-size: 26px;
}

.hero__text p {
  color: #5a6b7f;
  margin: 0 0 18px;
}

.hero__actions {
  display: flex;
  gap: 10px;
}

.hero__stats {
  display: flex;
  gap: 32px;
  text-align: center;
}

.module-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  gap: 12px;
}

.module-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 14px;
  border: 1px solid #ebeef5;
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.2s;
}

.module-item:hover {
  border-color: var(--slp-primary);
  background: #f5faff;
}

.module-item__name {
  font-weight: 600;
  margin-bottom: 2px;
}

@media (max-width: 768px) {
  .hero {
    flex-direction: column;
    align-items: flex-start;
  }

  .hero__stats {
    width: 100%;
    justify-content: space-around;
  }
}
</style>
