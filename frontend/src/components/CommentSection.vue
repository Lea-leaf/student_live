<script setup>
/**
 * 帖子评论区：发表 + 楼中楼回复 + 图片/语音 + 评论点赞。
 *
 * 后端列表接口一次返回顶级评论及整棵子树（root_id 设计），
 * 这里只负责渲染两层视觉：顶级评论 + 其下所有回复（回复里带「回复 @某人」）。
 */
import { computed, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { ChatDotRound, Delete, Star, StarFilled } from '@element-plus/icons-vue'

import CommentComposer from '@/components/CommentComposer.vue'
import { commentApi, likeApi } from '@/api/interaction'
import { useUserStore } from '@/stores/user'
import { fromNow } from '@/utils'

const props = defineProps({
  postId: { type: Number, required: true },
  authorId: { type: Number, default: 0 }
})

const emit = defineEmits(['count-change'])

const router = useRouter()
const userStore = useUserStore()

const loading = ref(false)
const comments = ref([])
const total = ref(0)
const totalAll = ref(0)
const page = ref(1)
const size = ref(10)
const submitting = ref(false)
const replyTarget = ref(null)
const replySubmitting = ref(false)
const topComposer = ref(null)
const replyComposer = ref(null)

/** replyComposer 位于 v-for 内，用函数 ref 保证拿到单个实例而不是数组 */
function setReplyComposer(el) {
  if (el) replyComposer.value = el
}

const isLogin = computed(() => userStore.isLogin)

//: 与后端保持一致：用户只能撤回 5 分钟内自己的评论
const RECALL_WINDOW_MS = 5 * 60 * 1000

onMounted(load)
watch(() => props.postId, () => { page.value = 1; load() })

async function load() {
  loading.value = true
  try {
    const data = await commentApi.list(props.postId, { page: page.value, size: size.value })
    comments.value = data.list || []
    total.value = data.total || 0
    totalAll.value = data.total_all || 0
    emit('count-change', totalAll.value)
  } catch (error) {
    // 拦截器已提示
  } finally {
    loading.value = false
  }
}

function goLogin() {
  router.push({ name: 'login', query: { redirect: router.currentRoute.value.fullPath } })
}

/** 是否是自己的评论，且还在 5 分钟撤回窗口内 */
function canRecall(comment) {
  if (!userStore.user || comment.user_id !== userStore.user.id || !comment.created_at) {
    return false
  }
  const target = new Date(String(comment.created_at).replace(/-/g, '/')).getTime()
  if (Number.isNaN(target)) return false
  const diff = Date.now() - target
  return diff >= 0 && diff <= RECALL_WINDOW_MS
}

/**
 * 谁能在这里直接物理删除任意评论：**只有真正的管理员**。
 *
 * 审核员也有删评论的权限，但必须走管理端（`DELETE /admin/comments/<id>`），
 * 那里有权限校验与操作日志留痕；用户端接口对非管理员仍按
 * 「只能撤回自己 5 分钟内的评论」处理。
 * 早期这里用 `isAdmin`（= is_staff），会把删除按钮错误地显示给审核员。
 */
const isAdmin = computed(() => userStore.isTrueAdmin)

async function submitTop(payload) {
  submitting.value = true
  try {
    await commentApi.create(props.postId, payload)
    topComposer.value?.reset()
    ElMessage.success('评论成功')
    page.value = 1
    await load()
  } catch (error) {
    // 拦截器已提示
  } finally {
    submitting.value = false
  }
}

function startReply(comment) {
  replyTarget.value = comment
}

function cancelReply() {
  replyTarget.value = null
}

async function submitReply(payload) {
  if (!replyTarget.value) return
  replySubmitting.value = true
  try {
    await commentApi.create(props.postId, {
      ...payload,
      parent_id: replyTarget.value.id,
      reply_to_user_id: replyTarget.value.user_id
    })
    replyComposer.value?.reset()
    ElMessage.success('回复成功')
    replyTarget.value = null
    await load()
  } catch (error) {
    // 拦截器已提示
  } finally {
    replySubmitting.value = false
  }
}

async function toggleLike(comment) {
  if (!isLogin.value) {
    ElMessage.warning('登录后才能点赞')
    return
  }
  try {
    const data = await likeApi.toggleComment(comment.id)
    comment.liked = data.liked
    comment.like_count = data.like_count
  } catch (error) {
    // 拦截器已提示
  }
}

/** 用户撤回自己的评论：5 分钟内，数据库物理删除 */
async function recallComment(comment) {
  try {
    await ElMessageBox.confirm('撤回后该评论会从数据库删除（含子回复与媒体），确认撤回吗？', '撤回评论', {
      type: 'warning',
      confirmButtonText: '确认撤回'
    })
  } catch (error) {
    return
  }
  try {
    await commentApi.remove(comment.id)
    ElMessage.success('评论已撤回')
    if (replyTarget.value?.id === comment.id) replyTarget.value = null
    await load()
  } catch (error) {
    // 拦截器已提示
  }
}

/** 管理员删除评论：同样是数据库物理删除，会保留操作日志 */
async function adminDeleteComment(comment) {
  try {
    await ElMessageBox.confirm('管理员删除会从数据库物理清除该评论及其子回复，确认删除吗？', '管理员删除评论', {
      type: 'warning',
      confirmButtonText: '确认删除'
    })
  } catch (error) {
    return
  }
  try {
    await commentApi.remove(comment.id)
    ElMessage.success('评论已删除')
    if (replyTarget.value?.id === comment.id) replyTarget.value = null
    await load()
  } catch (error) {
    // 拦截器已提示
  }
}

function imageList(comment) {
  return (comment.media || []).filter((item) => item.type === 'image').map((item) => item.url)
}

function mediaTypeLabel(comment) {
  const item = (comment.media || [])[0]
  if (!item) return ''
  return { image: '图片', audio: '语音', video: '视频' }[item.type] || '媒体'
}

function onPageChange(value) {
  page.value = value
  load()
}
</script>

<template>
  <div class="slp-card comment-section">
    <div class="comment-section__head">
      <h3 class="comment-section__title">
        <el-icon><ChatDotRound /></el-icon>
        评论区
        <span class="slp-text-sub">（{{ totalAll }} 条）</span>
      </h3>
    </div>

    <!-- 登录提示 -->
    <el-alert
      v-if="!isLogin"
      class="slp-mb-16"
      type="info"
      :closable="false"
      show-icon
      title="登录后即可发表评论、回复和点赞"
    >
      <template #default>
        <el-button text type="primary" size="small" @click="goLogin">去登录</el-button>
      </template>
    </el-alert>

    <!-- 发表评论 -->
    <CommentComposer
      v-else
      ref="topComposer"
      class="slp-mb-16"
      placeholder="友善评论，理性交流"
      button-text="发表评论"
      :loading="submitting"
      :max-length="1000"
      @submit="submitTop"
    />

    <!-- 评论列表 -->
    <div v-loading="loading">
      <el-empty v-if="!loading && !comments.length" description="还没有评论，来抢沙发吧" />

      <div v-for="(root, rootIndex) in comments" :key="root.id" class="comment-item">
        <div class="comment-item__main">
          <el-avatar :size="36" :src="root.author?.avatar">
            {{ (root.author?.display_name || '?').slice(0, 1) }}
          </el-avatar>
          <div class="comment-item__body">
            <div class="comment-item__meta">
              <span class="comment-item__name">{{ root.author?.display_name || '匿名同学' }}</span>
              <el-tag v-if="root.user_id === authorId" size="small" type="success" effect="plain">
                作者
              </el-tag>
              <span class="slp-text-sub">{{ fromNow(root.created_at) }}</span>
            </div>

            <p v-if="root.content" class="comment-item__content">{{ root.content }}</p>

            <!-- 媒体 -->
            <div v-if="root.media?.length" class="comment-item__media">
              <template v-for="item in root.media" :key="item.id || item.url">
                <audio v-if="item.type === 'audio'" :src="item.url" controls preload="none" />
                <video v-else-if="item.type === 'video'" :src="item.url" controls />
                <el-image
                  v-else
                  :src="item.url"
                  :preview-src-list="imageList(root)"
                  fit="cover"
                  class="comment-item__image"
                />
              </template>
            </div>

            <div class="comment-item__actions">
              <el-button
                text
                size="small"
                :type="root.liked ? 'primary' : ''"
                :icon="root.liked ? StarFilled : Star"
                @click="toggleLike(root)"
              >
                {{ root.like_count || 0 }}
              </el-button>
              <el-button text size="small" @click="startReply(root)">回复</el-button>
              <el-button v-if="canRecall(root)" text size="small" type="warning" @click="recallComment(root)">
                撤回
              </el-button>
              <el-button v-if="isAdmin" text size="small" type="danger" :icon="Delete" @click="adminDeleteComment(root)">
                删除
              </el-button>
            </div>
          </div>
        </div>

        <!-- 顶级评论的回复框 -->
        <div v-if="replyTarget?.id === root.id" class="comment-item__reply-box">
          <CommentComposer
            :ref="setReplyComposer"
            compact
            :placeholder="`回复 ${root.author?.display_name || '对方'}`"
            button-text="回复"
            :loading="replySubmitting"
            @submit="submitReply"
          />
          <el-button text size="small" @click="cancelReply">取消</el-button>
        </div>

        <!-- 楼中楼子树 -->
        <div v-if="root.replies?.length" class="comment-item__replies">
          <div v-for="reply in root.replies" :key="reply.id" class="reply-item">
            <el-avatar :size="28" :src="reply.author?.avatar">
              {{ (reply.author?.display_name || '?').slice(0, 1) }}
            </el-avatar>
            <div class="reply-item__body">
              <div class="comment-item__meta">
                <span class="comment-item__name">{{ reply.author?.display_name || '匿名同学' }}</span>
                <span v-if="reply.reply_to" class="slp-text-sub">
                  回复 @{{ reply.reply_to.display_name }}
                </span>
                <span class="slp-text-sub">{{ fromNow(reply.created_at) }}</span>
              </div>
              <p v-if="reply.content" class="comment-item__content">{{ reply.content }}</p>
              <div v-if="reply.media?.length" class="comment-item__media">
                <template v-for="item in reply.media" :key="item.id || item.url">
                  <audio v-if="item.type === 'audio'" :src="item.url" controls preload="none" />
                  <video v-else-if="item.type === 'video'" :src="item.url" controls />
                  <el-image
                    v-else
                    :src="item.url"
                    :preview-src-list="imageList(reply)"
                    fit="cover"
                    class="comment-item__image"
                  />
                </template>
              </div>
              <div class="comment-item__actions">
                <el-button
                  text
                  size="small"
                  :type="reply.liked ? 'primary' : ''"
                  :icon="reply.liked ? StarFilled : Star"
                  @click="toggleLike(reply)"
                >
                  {{ reply.like_count || 0 }}
                </el-button>
                <el-button text size="small" @click="startReply(reply)">回复</el-button>
                <el-button v-if="canRecall(reply)" text size="small" type="warning" @click="recallComment(reply)">
                  撤回
                </el-button>
                <el-button v-if="isAdmin" text size="small" type="danger" :icon="Delete" @click="adminDeleteComment(reply)">
                  删除
                </el-button>
              </div>

              <!-- 回复某条楼中楼的输入框 -->
              <div v-if="replyTarget?.id === reply.id" class="comment-item__reply-box">
                <CommentComposer
                  :ref="setReplyComposer"
                  compact
                  :placeholder="`回复 ${reply.author?.display_name || '对方'}`"
                  button-text="回复"
                  :loading="replySubmitting"
                  @submit="submitReply"
                />
                <el-button text size="small" @click="cancelReply">取消</el-button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 分页 -->
    <div v-if="total > size" class="comment-section__pager">
      <el-pagination
        layout="prev, pager, next"
        :current-page="page"
        :page-size="size"
        :total="total"
        @current-change="onPageChange"
      />
    </div>
  </div>
</template>

<style scoped>
.comment-section__head {
  margin-bottom: 14px;
}

.comment-section__title {
  display: flex;
  align-items: center;
  gap: 6px;
  margin: 0;
  font-size: 16px;
}

.comment-item {
  padding: 14px 0;
  border-top: 1px solid #f2f3f5;
}

.comment-item__main {
  display: flex;
  gap: 10px;
}

.comment-item__body {
  flex: 1;
  min-width: 0;
}

.comment-item__meta {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  font-size: 13px;
  margin-bottom: 4px;
}

.comment-item__name {
  font-weight: 600;
  color: #303133;
}

.comment-item__content {
  margin: 4px 0;
  line-height: 1.7;
  white-space: pre-line;
  word-break: break-word;
}

.comment-item__media {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  margin: 8px 0;
}

.comment-item__media audio {
  height: 40px;
  max-width: 240px;
}

.comment-item__media video {
  max-width: 240px;
  max-height: 160px;
  border-radius: 6px;
}

.comment-item__image {
  width: 100px;
  height: 100px;
  border-radius: 6px;
  cursor: zoom-in;
}

.comment-item__actions {
  display: flex;
  align-items: center;
  gap: 4px;
  margin-top: 4px;
}

.comment-item__reply-box {
  margin: 10px 0 4px 46px;
  display: flex;
  align-items: flex-end;
  gap: 8px;
}

.comment-item__replies {
  margin: 10px 0 0 46px;
  padding-left: 12px;
  border-left: 2px solid #f2f3f5;
}

.reply-item {
  display: flex;
  gap: 8px;
  padding: 8px 0;
}

.reply-item__body {
  flex: 1;
  min-width: 0;
}

.comment-section__pager {
  display: flex;
  justify-content: center;
  margin-top: 14px;
}
</style>