<script setup>
/**
 * 信息详情页。
 *
 * 规则（需求 6.2）：仅「进行中」的信息可查看详情，
 * 已认领 / 已过期 / 已关闭 由后端拦截（错误码 4002），前端给出友好提示。
 *
 * 联系方式公开可见（需求要求），页面显著提示「请自行判断风险」。
 */
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { ChatDotRound, Location, Star, StarFilled, Timer, View, Warning } from '@element-plus/icons-vue'

import { favoriteApi, likeApi, reportApi } from '@/api/interaction'
import CommentSection from '@/components/CommentSection.vue'
import lostFoundApi from '@/api/lostFound'
import { useAppStore } from '@/stores/app'
import { useUserStore } from '@/stores/user'
import { copyText, formatTime, statusTagType } from '@/utils'

const route = useRoute()
const router = useRouter()
const appStore = useAppStore()
const userStore = useUserStore()

const loading = ref(true)
const post = ref(null)
const favorited = ref(false)
const liked = ref(false)
const loadError = ref('')
const submitting = ref(false)
const liking = ref(false)

const postId = computed(() => Number(route.params.id))

const title = computed(() => {
  if (!post.value) return ''
  return post.value.title || post.value.content?.slice(0, 24) || '信息详情'
})

/**
 * 是否是作者本人（或真正的管理员），可执行状态流转 / 编辑 / 删除。
 *
 * ⚠️ 用 `isTrueAdmin` 而不是 `isAdmin`：后者表示"能进后台"（含审核员），
 * 而审核员在前台**不能**替用户改状态 / 改正文（后端 `can_edit` 同样只放行作者与管理员）。
 * 审核员的内容处置请走后台「内容管理 / 审核工作台」。
 */
const canManage = computed(() => {
  if (!post.value || !userStore.user) return false
  return post.value.user_id === userStore.user.id || userStore.isTrueAdmin
})

const canClaim = computed(() => post.value && post.value.status === 'ongoing' && canManage.value)

/** 模块差异化状态文案：二手交易在售中 / 已售出 / 已过期 / 已下架 */
const statusText = computed(() => {
  if (post.value?.type === 'second_hand') {
    return { ongoing: '在售中', claimed: '已售出', expired: '已过期', closed: '已下架' }
  }
  return { ongoing: '进行中', claimed: '已认领', expired: '已过期', closed: '已关闭' }
})
const claimActionText = computed(() => (post.value?.type === 'second_hand' ? '标记已售出' : '标记已认领'))
const closeActionText = computed(() => (post.value?.type === 'second_hand' ? '下架该商品' : '关闭该信息'))

onMounted(load)

async function load() {
  loading.value = true
  loadError.value = ''
  try {
    post.value = await lostFoundApi.detail(postId.value)
    // 详情接口已带 liked / favorited（v1.2 起），省掉两个单独的 check 请求
    favorited.value = !!post.value.favorited
    liked.value = !!post.value.liked
    if (userStore.isLogin && typeof post.value.liked === 'undefined') {
      try {
        const check = await favoriteApi.check(postId.value)
        favorited.value = !!check.favorited
      } catch (error) {
        favorited.value = false
      }
    }
  } catch (error) {
    post.value = null
    loadError.value = error?.msg || '该信息当前不可查看'
  } finally {
    loading.value = false
  }
}

/** 标记状态：claimed / expired / closed / ongoing */
async function changeStatus(status, label) {
  try {
    await ElMessageBox.confirm(`确认把这条信息标记为「${label}」吗？`, '操作确认', {
      type: 'warning'
    })
  } catch (error) {
    return
  }
  submitting.value = true
  try {
    post.value = await lostFoundApi.updateStatus(postId.value, { status })
    ElMessage.success(`已标记为「${label}」`)
  } catch (error) {
    // 拦截器已提示
  } finally {
    submitting.value = false
  }
}

async function toggleFavorite() {
  if (!userStore.isLogin) {
    ElMessage.warning('登录后才能收藏')
    return
  }
  try {
    const data = await favoriteApi.toggle(postId.value)
    favorited.value = data.favorited
    if (post.value) post.value.favorite_count = data.favorite_count
    ElMessage.success(data.favorited ? '已收藏' : '已取消收藏')
  } catch (error) {
    // 拦截器已提示
  }
}

async function toggleLike() {
  if (!userStore.isLogin) {
    ElMessage.warning('登录后才能点赞')
    return
  }
  liking.value = true
  try {
    const data = await likeApi.togglePost(postId.value)
    liked.value = data.liked
    if (post.value) post.value.like_count = data.like_count
  } catch (error) {
    // 拦截器已提示
  } finally {
    liking.value = false
  }
}

/** 评论区数量变化时同步帖子详情与列表卡片上的计数 */
function onCommentsChanged(count) {
  if (post.value) post.value.comment_count = count
}

/** 从详情页发起私信（自己不能给自己发） */
function goMessageAuthor() {
  if (!userStore.isLogin) {
    ElMessage.warning('登录后才能私信')
    return
  }
  if (!post.value?.author?.id || post.value.author.id === userStore.user?.id) return
  router.push({ name: 'messages', query: { user: post.value.author.id } })
}

async function removePost() {
  try {
    await ElMessageBox.confirm('删除后信息会进入管理员回收站，确认删除吗？', '删除确认', {
      type: 'warning',
      confirmButtonText: '确认删除'
    })
  } catch (error) {
    return
  }
  try {
    await lostFoundApi.remove(postId.value)
    ElMessage.success('已删除')
    router.replace({ name: 'my-posts' })
  } catch (error) {
    // 拦截器已提示
  }
}

async function reportPost() {
  if (!userStore.isLogin) {
    ElMessage.warning('登录后才能举报')
    return
  }
  try {
    const { value } = await ElMessageBox.prompt('请填写举报原因（例如：虚假信息 / 广告）', '举报信息', {
      inputPlaceholder: '举报原因',
      inputValidator: (text) => (text && text.trim().length >= 2 ? true : '请填写至少 2 个字'),
      confirmButtonText: '提交举报'
    })
    await reportApi.create({ post_id: postId.value, reason: value })
    ElMessage.success('举报已提交，管理员会尽快处理')
  } catch (error) {
    // 取消或接口报错
  }
}

async function copyContact() {
  if (!post.value?.contact) return
  await copyText(post.value.contact)
  ElMessage.success('联系方式已复制')
}

function handleCommand(command) {
  if (statusText.value[command]) {
    changeStatus(command, statusText.value[command])
  }
}
</script>

<template>
  <div class="slp-container slp-page">
    <div class="slp-mb-16">
      <el-button text @click="router.back()">← 返回</el-button>
    </div>

    <el-skeleton v-if="loading" :rows="6" animated />

    <el-result
      v-else-if="loadError"
      icon="warning"
      title="该信息当前不可查看"
      :sub-title="loadError"
    >
      <template #extra>
        <el-button type="primary" @click="router.push({ name: 'post-list' })">返回列表</el-button>
      </template>
    </el-result>

    <template v-else-if="post">
      <!-- 头部信息 -->
      <div class="slp-card">
        <div class="slp-flex-between slp-mb-16">
          <h1 class="detail-title">{{ title }}</h1>
          <div class="detail-tags">
            <el-tag v-if="post.is_top" type="danger" effect="dark">置顶</el-tag>
            <el-tag :type="statusTagType(post.status)">{{ post.status_label }}</el-tag>
            <el-tag v-if="post.audit_status !== 'approved'" type="warning" effect="plain">
              {{ post.audit_status_label }}
            </el-tag>
          </div>
        </div>

        <div class="post-card__meta slp-mb-16">
          <span><el-icon><Location /></el-icon> {{ post.location || '未填写地点' }}</span>
          <span><el-icon><Timer /></el-icon> {{ post.happened_at ? formatTime(post.happened_at) : '未填写时间' }}</span>
          <span><el-icon><View /></el-icon> {{ post.view_count || 0 }} 次浏览</span>
          <span><el-icon><ChatDotRound /></el-icon> {{ post.comment_count || 0 }} 条评论</span>
          <span>发布于 {{ formatTime(post.created_at) }}</span>
        </div>

        <!-- 二手交易扩展字段 -->
        <div v-if="post.type === 'second_hand'" class="detail-ext">
          <span class="detail-ext__price">￥{{ post.ext?.price }}</span>
          <el-tag v-if="post.ext?.condition" type="success" effect="plain">
            {{ post.ext.condition }}
          </el-tag>
          <el-tag v-if="post.ext?.trade_type" type="info" effect="plain">
            {{ post.ext.trade_type }}
          </el-tag>
          <span v-if="post.ext?.original_price" class="slp-text-sub">
            原价 ￥{{ post.ext.original_price }}
          </span>
        </div>

        <p v-if="post.content" class="detail-content">{{ post.content }}</p>
        <p v-else class="slp-text-sub">发布者未填写描述</p>

        <!-- 媒体 -->
        <div v-if="post.media && post.media.length" class="detail-media">
          <template v-for="item in post.media" :key="item.url">
            <video v-if="item.type === 'video'" :src="item.url" controls />
            <el-image v-else :src="item.url" :preview-src-list="post.media.filter(m => m.type !== 'video').map(m => m.url)" fit="cover" />
          </template>
        </div>
      </div>

      <!-- 联系方式 -->
      <div class="slp-card">
        <h3 class="slp-mb-8">联系方式</h3>
        <div class="detail-contact">
          {{ post.contact }}
          <el-button text type="primary" size="small" @click="copyContact">复制</el-button>
        </div>
        <el-alert
          class="slp-mt-16"
          type="warning"
          :closable="false"
          show-icon
          title="联系方式由发布者填写并公开显示，请自行判断风险，谨防诈骗"
        />
      </div>

      <!-- 发布者信息 -->
      <div class="slp-card">
        <h3 class="slp-mb-8">发布者</h3>
        <div class="author-row">
          <el-avatar :size="40" :src="post.author?.avatar">
            {{ (post.author?.display_name || '?').slice(0, 1) }}
          </el-avatar>
          <div>
            <div>{{ post.author?.display_name || '匿名同学' }}</div>
            <div class="slp-text-sub">学号 {{ post.author?.student_id || '-' }}</div>
          </div>
          <div style="flex: 1"></div>
          <el-button
            v-if="userStore.isLogin && post.author?.id !== userStore.user?.id"
            type="primary"
            plain
            :icon="ChatDotRound"
            @click="goMessageAuthor"
          >
            私信TA
          </el-button>
        </div>
        <el-alert
          v-if="post.audit_status === 'rejected'"
          class="slp-mt-16"
          type="error"
          :closable="false"
          :title="`未通过审核：${post.audit_remark || '内容不符合平台规范'}`"
        />
      </div>

      <!-- 操作区 -->
      <div class="slp-card">
        <div class="slp-toolbar">
          <el-button
            :type="liked ? 'primary' : ''"
            :icon="liked ? StarFilled : Star"
            :loading="liking"
            @click="toggleLike"
          >
            {{ liked ? '已点赞' : '点赞' }} {{ post.like_count || 0 }}
          </el-button>
          <el-button :icon="favorited ? StarFilled : Star" @click="toggleFavorite">
            {{ favorited ? '已收藏' : '收藏' }} {{ post.favorite_count || 0 }}
          </el-button>
          <el-button :icon="Warning" @click="reportPost">举报</el-button>

          <template v-if="canManage">
            <el-button
              v-if="canClaim"
              type="success"
              :loading="submitting"
              @click="changeStatus('claimed', statusText.claimed)"
            >
              {{ claimActionText }}
            </el-button>

            <el-dropdown v-if="post.status !== 'closed'" @command="handleCommand">
              <el-button :loading="submitting">
                修改状态<el-icon class="el-icon--right"><ChatDotRound /></el-icon>
              </el-button>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item command="ongoing">标记为{{ statusText.ongoing }}</el-dropdown-item>
                  <el-dropdown-item command="claimed">标记为{{ statusText.claimed }}</el-dropdown-item>
                  <el-dropdown-item command="expired">标记为{{ statusText.expired }}</el-dropdown-item>
                  <el-dropdown-item command="closed" divided>{{ closeActionText }}</el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>

            <el-button type="primary" plain @click="router.push({ name: 'post-edit', params: { id: post.id } })">
              编辑
            </el-button>
            <el-button type="danger" plain @click="removePost">删除</el-button>
          </template>

          <el-button text @click="router.push({ name: 'post-list' })">返回列表</el-button>
        </div>
      </div>

      <!-- 评论区：发表 / 楼中楼 / 图片语音 / 点赞 -->
      <CommentSection
        :post-id="postId"
        :author-id="post.user_id"
        @count-change="onCommentsChanged"
      />
    </template>
  </div>
</template>

<style scoped>
.detail-title {
  font-size: 22px;
  margin: 0;
}

.detail-tags {
  display: flex;
  gap: 8px;
  flex-shrink: 0;
}

.detail-content {
  line-height: 1.9;
  color: #303133;
  white-space: pre-line;
  margin: 0;
}

.author-row {
  display: flex;
  align-items: center;
  gap: 12px;
}

.detail-ext {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 12px;
}

.detail-ext__price {
  font-size: 24px;
  font-weight: 700;
  color: #f56c6c;
}
</style>
