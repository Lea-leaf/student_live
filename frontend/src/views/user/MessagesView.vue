<script setup>
/**
 * 我的私信：左侧会话列表 + 右侧聊天窗口。
 *
 * - 未读红点：message store 轮询 /messages/unread-count；
 * - 拉取某会话时后端自动把对方发来的消息标记已读，发送方刷新后看到「已读」；
 * - 支持从帖子详情点击「私信TA」带 query.user 进入，直接打开与作者的会话；
 * - 文字 / 图片 / 语音复用 CommentComposer（上传链路与评论完全一致）。
 */
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { ChatDotRound, Refresh } from '@element-plus/icons-vue'

import CommentComposer from '@/components/CommentComposer.vue'
import { messageApi } from '@/api/interaction'
import { useMessageStore } from '@/stores/message'
import { useUserStore } from '@/stores/user'
import { formatTime, fromNow } from '@/utils'

const route = useRoute()
const router = useRouter()
const userStore = useUserStore()
const messageStore = useMessageStore()

const conversations = ref([])
const messages = ref([])
const partner = ref(null)
const activeUserId = ref(null)
const loadingConversations = ref(false)
const loadingMessages = ref(false)
const sending = ref(false)
const composerRef = ref(null)
const messageBodyRef = ref(null)
let pollTimer = null

//: 撤回窗口与后端保持一致：5 分钟
const RECALL_WINDOW_MS = 5 * 60 * 1000

const myId = computed(() => userStore.user?.id)

watch(
  () => route.query.user,
  (value) => {
    const userId = Number(value)
    if (!userId) {
      activeUserId.value = null
      partner.value = null
      messages.value = []
      // 无 query 时默认选中第一个会话（桌面端体验更顺）
      if (conversations.value.length) {
        selectConversation(conversations.value[0], true)
      }
      return
    }
    activeUserId.value = userId
    loadMessages(userId)
  }
)

onMounted(async () => {
  await loadConversations()
  if (!route.query.user && conversations.value.length) {
    selectConversation(conversations.value[0], true)
  } else if (route.query.user) {
    activeUserId.value = Number(route.query.user)
    loadMessages(activeUserId.value)
  }
  startPolling()
})

onUnmounted(stopPolling)

async function loadConversations() {
  loadingConversations.value = true
  try {
    const data = await messageApi.conversations({ page: 1, size: 50 })
    conversations.value = data.list || []
    messageStore.unread = data.unread || 0
    messageStore.unreadConversations = data.unread_conversations || 0
  } catch (error) {
    // 拦截器已提示
  } finally {
    loadingConversations.value = false
  }
}

async function loadMessages(userId, silent = false) {
  if (!userId) return
  if (!silent) loadingMessages.value = true
  try {
    const data = await messageApi.withUser(userId, { page: 1, size: 50 })
    messages.value = data.list || []
    partner.value = data.user || partner.value
    if (data.read_count) {
      messageStore.refreshUnread()
      loadConversations()
    }
    scrollToBottom()
  } catch (error) {
    // 拦截器已提示
  } finally {
    if (!silent) loadingMessages.value = false
  }
}

function selectConversation(row, replace = false) {
  const userId = row?.user_id || row?.user?.id
  if (!userId) return
  const location = { name: 'messages', query: { user: userId } }
  if (replace) router.replace(location)
  else router.push(location)
}

async function sendMessage(payload) {
  if (!activeUserId.value || sending.value) return
  // 纯文字时也保持和评论一致的校验
  if (!payload.content && !payload.media.length) {
    ElMessage.warning('请输入内容')
    return
  }
  sending.value = true
  try {
    await messageApi.send(activeUserId.value, {
      content: payload.content,
      media: payload.media
    })
    composerRef.value?.reset()
    await loadMessages(activeUserId.value, true)
    await loadConversations()
    messageStore.refreshUnread()
  } catch (error) {
    // 拦截器已提示
  } finally {
    sending.value = false
  }
}

function scrollToBottom() {
  nextTick(() => {
    if (messageBodyRef.value) {
      messageBodyRef.value.scrollTop = messageBodyRef.value.scrollHeight
    }
  })
}

function isMine(message) {
  return message.sender_id === myId.value
}

/** 是否还在 5 分钟撤回窗口内（后端还会再校验一次） */
function canRecall(message) {
  if (!isMine(message) || !message.created_at) return false
  const target = new Date(String(message.created_at).replace(/-/g, '/')).getTime()
  if (Number.isNaN(target)) return false
  const diff = Date.now() - target
  return diff >= 0 && diff <= RECALL_WINDOW_MS
}

/** 撤回：数据库物理删除，双方都看不到 */
async function recallMessage(message) {
  try {
    await ElMessageBox.confirm('撤回后双方都将看不到这条消息，确认撤回吗？', '撤回消息', {
      type: 'warning',
      confirmButtonText: '撤回'
    })
  } catch (error) {
    return
  }
  try {
    await messageApi.recall(message.id)
    ElMessage.success('已撤回')
    await refreshAfterDelete()
  } catch (error) {
    // 拦截器已提示
  }
}

/** 普通删除：只让自己的客户端不再显示，对方仍然可见 */
async function deleteMessage(message) {
  try {
    await ElMessageBox.confirm('删除后仅你的客户端不再显示，对方仍然可见。确认删除吗？', '删除消息', {
      type: 'warning',
      confirmButtonText: '删除'
    })
  } catch (error) {
    return
  }
  try {
    const data = await messageApi.remove(message.id)
    ElMessage.success(data.purged ? '消息已删除' : '已从你的列表移除')
    await refreshAfterDelete()
  } catch (error) {
    // 拦截器已提示
  }
}

async function refreshAfterDelete() {
  await loadMessages(activeUserId.value, true)
  await loadConversations()
  messageStore.refreshUnread()
}

function previewOf(message) {
  if (!message) return ''
  if (message.content) return message.content
  const type = message.media?.[0]?.type
  return { image: '[图片]', audio: '[语音]', video: '[视频]' }[type] || '[消息]'
}

function startPolling(interval = 10000) {
  stopPolling()
  pollTimer = setInterval(() => {
    if (document.hidden) return
    if (activeUserId.value) loadMessages(activeUserId.value, true)
    else loadConversations()
    messageStore.refreshUnread()
  }, interval)
}

function stopPolling() {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}
</script>

<template>
  <div class="slp-container slp-page">
    <div class="message-layout">
      <!-- 会话列表 -->
      <aside class="conversation-panel">
        <div class="conversation-panel__head">
          <span class="conversation-panel__title">
            <el-icon><ChatDotRound /></el-icon> 私信
          </span>
          <el-button text size="small" :icon="Refresh" :loading="loadingConversations" @click="loadConversations" />
        </div>

        <div v-loading="loadingConversations" class="conversation-panel__body">
          <div
            v-for="row in conversations"
            :key="row.user_id"
            class="conversation-item"
            :class="{ 'is-active': row.user_id === activeUserId }"
            @click="selectConversation(row)"
          >
            <el-avatar :size="40" :src="row.user?.avatar">
              {{ (row.user?.display_name || '?').slice(0, 1) }}
            </el-avatar>
            <div class="conversation-item__body">
              <div class="conversation-item__top">
                <span class="conversation-item__name">{{ row.user?.display_name || '同学' }}</span>
                <span class="slp-text-sub">{{ fromNow(row.last_message?.created_at) }}</span>
              </div>
              <div class="conversation-item__preview">
                {{ previewOf(row.last_message) }}
              </div>
            </div>
            <el-badge v-if="row.unread" :value="row.unread" />
          </div>

          <el-empty
            v-if="!loadingConversations && !conversations.length"
            description="还没有私信，去帖子详情页私信发布者吧"
          />
        </div>
      </aside>

      <!-- 聊天窗口 -->
      <section class="chat-panel">
        <template v-if="activeUserId && partner">
          <div class="chat-panel__head">
            <el-avatar :size="32" :src="partner.avatar">
              {{ (partner.display_name || '?').slice(0, 1) }}
            </el-avatar>
            <div>
              <div class="chat-panel__name">{{ partner.display_name || '同学' }}</div>
              <div class="slp-text-sub">学号 {{ partner.student_id || '-' }}</div>
            </div>
          </div>

          <div ref="messageBodyRef" v-loading="loadingMessages" class="chat-panel__body">
            <div v-if="!messages.length && !loadingMessages" class="chat-panel__empty">
              还没有聊天记录，打个招呼吧
            </div>

            <div
              v-for="message in messages"
              :key="message.id"
              class="message-row"
              :class="{ 'is-mine': isMine(message) }"
            >
              <el-avatar :size="32" :src="isMine(message) ? userStore.avatar : partner.avatar">
                {{ (isMine(message) ? userStore.displayName : partner.display_name || '?').slice(0, 1) }}
              </el-avatar>
              <div class="message-row__body">
                <div class="message-bubble">
                  <p v-if="message.content" class="message-bubble__text">{{ message.content }}</p>
                  <div v-if="message.media?.length" class="message-bubble__media">
                    <template v-for="item in message.media" :key="item.id || item.url">
                      <audio v-if="item.type === 'audio'" :src="item.url" controls preload="none" />
                      <video v-else-if="item.type === 'video'" :src="item.url" controls />
                      <el-image
                        v-else
                        :src="item.url"
                        :preview-src-list="message.media.filter(m => m.type === 'image').map(m => m.url)"
                        fit="cover"
                        class="message-bubble__image"
                      />
                    </template>
                  </div>
                </div>
                <div class="message-row__meta">
                  <span>{{ formatTime(message.created_at) }}</span>
                  <span v-if="isMine(message)" :class="{ 'is-read': message.is_read }">
                    {{ message.is_read ? '已读' : '未读' }}
                  </span>
                  <span class="message-row__actions">
                    <el-button v-if="canRecall(message)" text size="small" @click.stop="recallMessage(message)">
                      撤回
                    </el-button>
                    <el-button text size="small" @click.stop="deleteMessage(message)">
                      删除
                    </el-button>
                  </span>
                </div>
              </div>
            </div>
          </div>

          <div class="chat-panel__composer">
            <CommentComposer
              ref="composerRef"
              compact
              placeholder="输入私信内容"
              button-text="发送"
              :loading="sending"
              :max-length="2000"
              @submit="sendMessage"
            />
          </div>
        </template>

        <el-empty
          v-else
          class="chat-panel__placeholder"
          description="选择左侧会话，或从帖子详情点击「私信TA」开始聊天"
        />
      </section>
    </div>
  </div>
</template>

<style scoped>
.message-layout {
  display: flex;
  gap: 16px;
  height: calc(100vh - 160px);
  min-height: 520px;
}

.conversation-panel {
  width: 300px;
  flex-shrink: 0;
  background: #fff;
  border: 1px solid #ebeef5;
  border-radius: 10px;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.conversation-panel__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 14px;
  border-bottom: 1px solid #ebeef5;
}

.conversation-panel__title {
  display: flex;
  align-items: center;
  gap: 6px;
  font-weight: 600;
}

.conversation-panel__body {
  flex: 1;
  overflow-y: auto;
  padding: 6px;
}

.conversation-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px;
  border-radius: 8px;
  cursor: pointer;
}

.conversation-item:hover,
.conversation-item.is-active {
  background: #ecf5ff;
}

.conversation-item__body {
  flex: 1;
  min-width: 0;
}

.conversation-item__top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.conversation-item__name {
  font-weight: 600;
  font-size: 14px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.conversation-item__preview {
  margin-top: 2px;
  color: #909399;
  font-size: 12px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.chat-panel {
  flex: 1;
  min-width: 0;
  background: #fff;
  border: 1px solid #ebeef5;
  border-radius: 10px;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.chat-panel__head {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 16px;
  border-bottom: 1px solid #ebeef5;
}

.chat-panel__name {
  font-weight: 600;
}

.chat-panel__body {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
  background: #f7f8fa;
}

.chat-panel__empty {
  text-align: center;
  color: #909399;
  padding-top: 40px;
  font-size: 13px;
}

.message-row {
  display: flex;
  gap: 8px;
  margin-bottom: 14px;
}

.message-row.is-mine {
  flex-direction: row-reverse;
}

.message-row__body {
  max-width: 70%;
}

.message-bubble {
  background: #fff;
  border-radius: 8px;
  padding: 8px 10px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.06);
}

.message-row.is-mine .message-bubble {
  background: #d9ecff;
}

.message-bubble__text {
  margin: 0;
  line-height: 1.6;
  white-space: pre-line;
  word-break: break-word;
}

.message-bubble__media {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 6px;
}

.message-bubble__media audio {
  height: 36px;
  max-width: 220px;
}

.message-bubble__media video {
  max-width: 220px;
  max-height: 150px;
  border-radius: 6px;
}

.message-bubble__image {
  width: 120px;
  height: 120px;
  border-radius: 6px;
  cursor: zoom-in;
}

.message-row__meta {
  display: flex;
  gap: 8px;
  margin-top: 3px;
  font-size: 11px;
  color: #c0c4cc;
}

.message-row.is-mine .message-row__meta {
  justify-content: flex-end;
}

.message-row__meta .is-read {
  color: #67c23a;
}

.message-row__actions {
  display: inline-flex;
  align-items: center;
  gap: 2px;
}

.message-row__actions .el-button {
  padding: 0;
  height: auto;
  font-size: 11px;
}

.chat-panel__composer {
  padding: 12px 16px;
  border-top: 1px solid #ebeef5;
  background: #fff;
}

.chat-panel__placeholder {
  margin: auto;
}

@media (max-width: 768px) {
  .message-layout {
    flex-direction: column;
    height: auto;
  }

  .conversation-panel {
    width: 100%;
    max-height: 320px;
  }

  .chat-panel {
    min-height: 480px;
  }
}
</style>