<script setup>
/**
 * 帖子卡片：列表页复用组件。
 * 需求 6.2 的状态可见性规则由后端判定，这里只负责展示与「详情可点」的视觉反馈。
 */
import { computed } from 'vue'
import { ChatDotRound, Location, Star, Timer, View } from '@element-plus/icons-vue'

import { fromNow, statusTagType } from '@/utils'

const props = defineProps({
  post: { type: Object, required: true }
})

const emit = defineEmits(['click', 'favorite'])

/** 详情是否可点：已认领 / 已过期 / 已关闭 都不可点 */
const clickable = computed(() => props.post.status === 'ongoing')

const thumb = computed(() => {
  const media = props.post.media || []
  const image = media.find((item) => item.type !== 'video')
  return image ? image.url : ''
})

const title = computed(() => props.post.title || props.post.content?.slice(0, 24) || '（无标题）')

function onClick() {
  if (!clickable.value) return
  emit('click', props.post)
}
</script>

<template>
  <div class="slp-card post-card" :class="{ 'is-disabled': !clickable }" @click="onClick">
    <div class="post-card__row">
      <div class="post-card__body">
        <div class="slp-flex-between slp-mb-8">
          <h3 class="post-card__title">{{ title }}</h3>
          <div class="post-card__tags">
            <el-tag v-if="post.is_top" type="danger" size="small" effect="dark">置顶</el-tag>
            <el-tag :type="statusTagType(post.status)" size="small">{{ post.status_label }}</el-tag>
            <el-tag v-if="post.audit_status === 'pending'" type="warning" size="small" effect="plain">
              待审核
            </el-tag>
            <el-tag v-if="post.audit_status === 'rejected'" type="danger" size="small" effect="plain">
              未通过
            </el-tag>
          </div>
        </div>

        <p v-if="post.content" class="post-card__content">{{ post.content }}</p>

        <div class="post-card__meta">
          <span v-if="post.location">
            <el-icon><Location /></el-icon> {{ post.location }}
          </span>
          <span v-if="post.happened_at">
            <el-icon><Timer /></el-icon> {{ post.happened_at?.slice(0, 16) }}
          </span>
          <span>
            <el-icon><View /></el-icon> {{ post.view_count || 0 }}
          </span>
          <span>
            <el-icon><ChatDotRound /></el-icon> {{ post.comment_count || 0 }}
          </span>
          <span>
            <el-icon><Star /></el-icon> {{ post.like_count || 0 }}
          </span>
          <span v-if="post.author">{{ post.author.display_name }}</span>
          <span>{{ fromNow(post.created_at) }}</span>
        </div>

        <p v-if="!clickable" class="post-card__hint">
          该信息已「{{ post.status_label }}」，按平台规则不再提供详情查看
        </p>
      </div>

      <img v-if="thumb" class="post-card__thumb" :src="thumb" alt="配图" loading="lazy" />
    </div>
  </div>
</template>

<style scoped>
.post-card__row {
  display: flex;
  gap: 14px;
  align-items: flex-start;
}

.post-card__body {
  flex: 1;
  min-width: 0;
}

.post-card__tags {
  display: flex;
  gap: 6px;
  flex-shrink: 0;
}

.post-card__meta span {
  display: inline-flex;
  align-items: center;
  gap: 3px;
}

.post-card__hint {
  margin: 10px 0 0;
  font-size: 12px;
  color: #e6a23c;
}

.post-card.is-disabled {
  cursor: default;
  opacity: 0.82;
}

.post-card.is-disabled:hover {
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.04);
  transform: none;
}
</style>
