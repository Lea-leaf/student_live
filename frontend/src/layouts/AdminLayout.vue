<script setup>
/**
 * 管理端布局：左侧菜单 + 顶部面包屑 + 内容区。
 *
 * 菜单项与后端 `app/admin/*` 蓝图一一对应；
 * 后续做管理员分级（RBAC）时，只需在这里按角色过滤 menuItems 即可。
 */
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import {
  Bell,
  ChatDotSquare,
  Coin,
  DataLine,
  Delete,
  Document,
  Expand,
  Fold,
  Grid,
  HomeFilled,
  List,
  Setting,
  SwitchButton,
  User
} from '@element-plus/icons-vue'

import { useAppStore } from '@/stores/app'
import { useUserStore } from '@/stores/user'

const appStore = useAppStore()
const userStore = useUserStore()
const router = useRouter()
const route = useRoute()

const collapsed = ref(false)

/** 菜单结构（后续 RBAC 分级时按角色过滤） */
const menuItems = [
  { index: '/admin/dashboard', title: '概览', icon: HomeFilled },
  { index: '/admin/audit', title: '审核工作台', icon: Document },
  { index: '/admin/posts', title: '内容管理', icon: List },
  { index: '/admin/users', title: '用户管理', icon: User },
  { index: '/admin/modules', title: '模块管理', icon: Grid },
  { index: '/admin/reports', title: '举报处理', icon: ChatDotSquare },
  { index: '/admin/trash', title: '回收站', icon: Delete },
  { index: '/admin/logs', title: '日志管理', icon: DataLine },
  { index: '/admin/configs', title: '系统配置', icon: Setting }
]

const activeMenu = computed(() => {
  // 详情页高亮父级菜单
  if (route.path.startsWith('/admin/users/')) return '/admin/users'
  return route.path
})

const currentTitle = computed(() => route.meta.title || '管理后台')

function handleSelect(index) {
  router.push(index)
}

function goFront() {
  router.push({ name: 'home' })
}

async function logout() {
  await userStore.logout()
  ElMessage.success('已退出登录')
  router.push({ name: 'login' })
}
</script>

<template>
  <el-container class="admin-layout">
    <!-- 左侧菜单 -->
    <el-aside :width="collapsed ? '64px' : '210px'" class="admin-sidebar">
      <div class="admin-logo">
        <el-icon :size="20" color="#409eff"><Coin /></el-icon>
        <span v-show="!collapsed">{{ appStore.siteName }} · 后台</span>
      </div>
      <el-menu
        :default-active="activeMenu"
        :collapse="collapsed"
        :collapse-transition="false"
        background-color="#1f2d3d"
        text-color="#c0c4cc"
        active-text-color="#ffffff"
        @select="handleSelect"
      >
        <el-menu-item v-for="item in menuItems" :key="item.index" :index="item.index">
          <el-icon><component :is="item.icon" /></el-icon>
          <template #title>{{ item.title }}</template>
        </el-menu-item>
      </el-menu>
    </el-aside>

    <el-container>
      <!-- 顶栏 -->
      <el-header class="admin-header">
        <div class="admin-header__left">
          <el-button text :icon="collapsed ? Expand : Fold" @click="collapsed = !collapsed" />
          <el-breadcrumb separator="/">
            <el-breadcrumb-item>管理后台</el-breadcrumb-item>
            <el-breadcrumb-item>{{ currentTitle }}</el-breadcrumb-item>
          </el-breadcrumb>
        </div>
        <div class="admin-header__right">
          <el-button text :icon="Bell" @click="router.push({ name: 'notifications' })">
            通知
          </el-button>
          <el-button text @click="goFront">返回前台</el-button>
          <el-dropdown>
            <span class="admin-header__user">
              <el-avatar :size="26" :src="userStore.avatar">
                {{ userStore.displayName.slice(0, 1) }}
              </el-avatar>
              <span>{{ userStore.displayName }}</span>
            </span>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item @click="router.push({ name: 'profile' })">个人中心</el-dropdown-item>
                <el-dropdown-item divided @click="logout">
                  <el-icon><SwitchButton /></el-icon> 退出登录
                </el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
      </el-header>

      <!-- 内容 -->
      <el-main class="admin-main">
        <router-view />
      </el-main>
    </el-container>
  </el-container>
</template>

<style scoped>
.admin-layout {
  height: 100vh;
}

.admin-sidebar {
  transition: width 0.2s;
  overflow-x: hidden;
}

.admin-logo {
  height: 60px;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 0 18px;
  color: #fff;
  font-weight: 600;
  border-bottom: 1px solid #2c3e50;
  white-space: nowrap;
}

.admin-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: #fff;
  border-bottom: 1px solid #ebeef5;
  height: 60px;
}

.admin-header__left,
.admin-header__right {
  display: flex;
  align-items: center;
  gap: 10px;
}

.admin-header__user {
  display: flex;
  align-items: center;
  gap: 6px;
  cursor: pointer;
  outline: none;
}

.admin-main {
  background: var(--slp-bg);
  padding: 16px;
}
</style>
