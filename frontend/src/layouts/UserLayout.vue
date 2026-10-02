<script setup>
/**
 * 用户端布局：顶部导航 + 内容区 + 页脚。
 *
 * 安全公告（需求 4.3）：
 *   首次使用（登录后）弹出一次；用户确认后记录到 localStorage，
 *   发布信息前若未确认，PostEditView 会再次调用 ensureNotice() 拦截。
 */
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Bell, Plus, School } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'

import { useAppStore } from '@/stores/app'
import { useNotificationStore } from '@/stores/notification'
import { useUserStore } from '@/stores/user'
import { acknowledgeNotice, isNoticeAcknowledged } from '@/utils'

const appStore = useAppStore()
const userStore = useUserStore()
const notificationStore = useNotificationStore()
const router = useRouter()
const route = useRoute()

const noticeVisible = ref(false)

const siteName = computed(() => appStore.siteName)
const modules = computed(() => appStore.modules)

/** 是否在「发布/列表」等着重显示模块导航的页面 */
const activeModule = computed(() => (route.query.type ? String(route.query.type) : ''))

onMounted(async () => {
  // 登录用户：轮询未读通知 + 首次弹出安全公告
  if (userStore.isLogin) {
    notificationStore.startPolling()
    maybeShowNotice()
  }
})

onUnmounted(() => {
  notificationStore.stopPolling()
})

/** 未确认过安全公告则弹出 */
function maybeShowNotice() {
  const identity = userStore.studentId || 'guest'
  if (isNoticeAcknowledged(identity)) return
  noticeVisible.value = true
}

/** 供子页面调用（发布前拦截） */
async function ensureNotice() {
  const identity = userStore.studentId || 'guest'
  if (isNoticeAcknowledged(identity)) return true
  return new Promise((resolve) => {
    ElMessageBox.confirm(
      '发布前请确认：不要上传身份证、银行卡、家庭住址等敏感隐私信息；' +
        '平台管理员可查看所有用户发布的信息；联系方式公开可见，请自行判断风险。',
      '安全公告',
      { confirmButtonText: '我已了解', showCancelButton: false, type: 'warning' }
    )
      .then(() => {
        acknowledgeNotice(identity)
        resolve(true)
      })
      .catch(() => resolve(false))
  })
}

defineExpose({ ensureNotice })

function onNoticeConfirm() {
  acknowledgeNotice(userStore.studentId || 'guest')
  noticeVisible.value = false
}

function goModule(code) {
  router.push({ name: 'post-list', query: { type: code } })
}

function goPublish() {
  router.push({ name: 'post-create' })
}

async function handleCommand(command) {
  if (command === 'logout') {
    await userStore.logout()
    notificationStore.stopPolling()
    ElMessage.success('已退出登录')
    router.push({ name: 'home' })
    return
  }
  router.push({ name: command })
}

const noticeText = computed(() => appStore.config.security_notice_text || '')
</script>

<template>
  <div class="user-layout">
    <!-- 顶部导航 -->
    <header class="user-header">
      <div class="slp-container user-header__inner">
        <div class="user-header__left" @click="router.push({ name: 'home' })">
          <el-icon :size="22" color="#409eff"><School /></el-icon>
          <span class="user-header__title">{{ siteName }}</span>
        </div>

        <nav class="user-header__nav hide-on-mobile">
          <router-link
            class="user-header__nav-item"
            :class="{ active: route.name === 'home' }"
            :to="{ name: 'home' }"
          >
            首页
          </router-link>
          <a
            v-for="item in modules"
            :key="item.code"
            class="user-header__nav-item"
            :class="{ active: activeModule === item.code }"
            @click="goModule(item.code)"
          >
            {{ item.name }}
          </a>
        </nav>

        <div class="user-header__right">
          <el-button type="primary" :icon="Plus" @click="goPublish">发布信息</el-button>

          <template v-if="userStore.isLogin">
            <el-badge
              :value="notificationStore.unread"
              :hidden="!notificationStore.unread"
              class="user-header__badge"
            >
              <el-button :icon="Bell" circle @click="router.push({ name: 'notifications' })" />
            </el-badge>

            <el-dropdown @command="handleCommand">
              <span class="user-header__user">
                <el-avatar :size="28" :src="userStore.avatar">
                  {{ userStore.displayName.slice(0, 1) }}
                </el-avatar>
                <span class="hide-on-mobile">{{ userStore.displayName }}</span>
              </span>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item command="profile">个人中心</el-dropdown-item>
                  <el-dropdown-item command="my-posts">我的发布</el-dropdown-item>
                  <el-dropdown-item command="my-favorites">我的收藏</el-dropdown-item>
                  <el-dropdown-item v-if="userStore.isAdmin" command="admin-dashboard" divided>
                    管理后台
                  </el-dropdown-item>
                  <el-dropdown-item command="logout" divided>退出登录</el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
          </template>

          <template v-else>
            <el-button text @click="router.push({ name: 'login' })">登录</el-button>
            <el-button text @click="router.push({ name: 'register' })">注册</el-button>
          </template>
        </div>
      </div>
    </header>

    <!-- 站点公告 -->
    <div v-if="appStore.config.site_notice" class="slp-container">
      <el-alert
        class="slp-mt-16"
        :title="appStore.config.site_notice"
        type="info"
        :closable="false"
        show-icon
      />
    </div>

    <!-- 内容区 -->
    <main class="user-main">
      <router-view />
    </main>

    <!-- 页脚 -->
    <footer class="user-footer">
      <div class="slp-container">
        <p>{{ siteName }} · 毕业设计原型 · 仅用于课程与答辩演示</p>
        <p class="slp-text-sub">
          请勿在平台上传身份证、银行卡、家庭住址等敏感信息
        </p>
      </div>
    </footer>

    <!-- 安全公告弹窗 -->
    <el-dialog
      v-model="noticeVisible"
      title="安全公告"
      width="520px"
      :close-on-click-modal="false"
      @closed="() => {}"
    >
      <p style="white-space: pre-line; line-height: 1.8">
        {{ noticeText || '请勿上传敏感隐私信息；管理员可查看所有发布内容；联系方式公开可见。' }}
      </p>
      <template #footer>
        <el-button type="primary" @click="onNoticeConfirm">我已了解</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.user-layout {
  display: flex;
  flex-direction: column;
  min-height: 100vh;
}

.user-header {
  background: #fff;
  border-bottom: 1px solid #ebeef5;
  position: sticky;
  top: 0;
  z-index: 100;
}

.user-header__inner {
  display: flex;
  align-items: center;
  justify-content: space-between;
  height: 60px;
  gap: 16px;
}

.user-header__left {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
}

.user-header__title {
  font-size: 17px;
  font-weight: 700;
}

.user-header__nav {
  display: flex;
  align-items: center;
  gap: 4px;
  flex: 1;
  margin-left: 20px;
}

.user-header__nav-item {
  padding: 6px 12px;
  border-radius: 6px;
  color: #606266;
  cursor: pointer;
  font-size: 14px;
}

.user-header__nav-item:hover,
.user-header__nav-item.active {
  color: var(--slp-primary);
  background: #ecf5ff;
}

.user-header__right {
  display: flex;
  align-items: center;
  gap: 10px;
}

.user-header__user {
  display: flex;
  align-items: center;
  gap: 6px;
  cursor: pointer;
  outline: none;
}

.user-header__badge {
  margin-right: 4px;
}

.user-main {
  flex: 1;
}

.user-footer {
  background: #fff;
  border-top: 1px solid #ebeef5;
  padding: 18px 0;
  text-align: center;
  color: #909399;
  font-size: 13px;
}

.user-footer p {
  margin: 4px 0;
}
</style>
