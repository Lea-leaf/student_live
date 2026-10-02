<script setup>
/**
 * 消息通知：审核结果、系统公告等。
 * 未读数由 notification store 统一维护（顶部小红点共用）。
 */
import { onMounted, reactive } from 'vue'

import { useNotificationStore } from '@/stores/notification'
import { useRouter } from 'vue-router'
import { fromNow } from '@/utils'

const notificationStore = useNotificationStore()
const router = useRouter()

const query = reactive({ page: 1, size: 20, is_read: '' })

onMounted(load)

async function load() {
  const params = { page: query.page, size: query.size }
  if (query.is_read !== '') params.is_read = query.is_read
  await notificationStore.fetchList(params)
}

function markRead(item) {
  if (item.is_read) return
  notificationStore.markRead(item.id)
}

function markAll() {
  notificationStore.markAllRead()
}

function openLink(item) {
  markRead(item)
  const link = item.link
  if (link && link.route === 'post-detail' && link.post_id) {
    router.push({ name: 'post-detail', params: { id: link.post_id } })
  }
}

const typeLabels = {
  audit: '审核',
  comment: '评论',
  message: '私信',
  system: '系统'
}
</script>

<template>
  <div class="slp-container slp-page">
    <div class="slp-card">
      <div class="slp-flex-between">
        <h2>消息通知</h2>
        <div class="slp-toolbar">
          <el-select v-model="query.is_read" placeholder="全部" style="width: 120px" @change="load">
            <el-option label="全部" value="" />
            <el-option label="未读" value="0" />
            <el-option label="已读" value="1" />
          </el-select>
          <el-button :disabled="!notificationStore.unread" @click="markAll">
            全部已读（{{ notificationStore.unread }}）
          </el-button>
        </div>
      </div>
    </div>

    <div v-loading="notificationStore.loading">
      <div
        v-for="item in notificationStore.list"
        :key="item.id"
        class="slp-card notice-item"
        :class="{ 'is-unread': !item.is_read }"
        @click="openLink(item)"
      >
        <div class="slp-flex-between slp-mb-8">
          <div class="notice-item__title">
            <el-tag size="small" effect="plain">{{ typeLabels[item.type] || item.type }}</el-tag>
            <span>{{ item.title }}</span>
          </div>
          <span class="slp-text-sub">{{ fromNow(item.created_at) }}</span>
        </div>
        <p class="slp-text-sub" style="margin: 0">{{ item.content }}</p>
        <div class="notice-item__actions">
          <el-button v-if="!item.is_read" text type="primary" size="small" @click.stop="markRead(item)">
            标为已读
          </el-button>
        </div>
      </div>

      <el-empty v-if="!notificationStore.loading && !notificationStore.list.length" description="暂无通知" />
    </div>
  </div>
</template>

<style scoped>
.notice-item {
  cursor: pointer;
}

.notice-item.is-unread {
  border-left: 3px solid var(--slp-primary);
}

.notice-item__title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 600;
}

.notice-item__actions {
  margin-top: 6px;
}
</style>
