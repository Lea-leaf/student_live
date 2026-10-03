/**
 * 路由表 + 全局守卫。
 *
 * 三种布局：
 *   PublicLayout  登录/注册（居中卡片）
 *   UserLayout    用户端（顶部导航 + 内容区）
 *   AdminLayout   管理端（左侧菜单 + 顶栏）
 *
 * 使用 hash 模式：部署到任意静态服务器（甚至直接丢到 Flask 的 static）都能用，
 * 不需要额外的 history fallback 配置。
 */
import { createRouter, createWebHashHistory } from 'vue-router'

import { useUserStore } from '@/stores/user'
import { useAppStore } from '@/stores/app'

const routes = [
  // ------------------------------------------------------------------
  // 公开页面（登录 / 注册）
  // ------------------------------------------------------------------
  {
    path: '/auth',
    component: () => import('@/layouts/PublicLayout.vue'),
    children: [
      {
        path: 'login',
        name: 'login',
        component: () => import('@/views/user/LoginView.vue'),
        meta: { title: '登录', public: true }
      },
      {
        path: 'register',
        name: 'register',
        component: () => import('@/views/user/RegisterView.vue'),
        meta: { title: '注册', public: true }
      }
    ]
  },

  // ------------------------------------------------------------------
  // 用户端
  // ------------------------------------------------------------------
  {
    path: '/',
    component: () => import('@/layouts/UserLayout.vue'),
    children: [
      {
        path: '',
        name: 'home',
        component: () => import('@/views/user/HomeView.vue'),
        meta: { title: '首页', public: true }
      },
      {
        path: 'posts',
        name: 'post-list',
        component: () => import('@/views/user/PostListView.vue'),
        meta: { title: '失物招领', public: true }
      },
      {
        path: 'posts/:id',
        name: 'post-detail',
        component: () => import('@/views/user/PostDetailView.vue'),
        // 详情页默认要求登录（游客看详情由后端配置控制，前端先按默认收紧）
        meta: { title: '信息详情' }
      },
      {
        path: 'publish',
        name: 'post-create',
        component: () => import('@/views/user/PostEditView.vue'),
        meta: { title: '发布信息', requiresAuth: true }
      },
      {
        path: 'posts/:id/edit',
        name: 'post-edit',
        component: () => import('@/views/user/PostEditView.vue'),
        meta: { title: '编辑信息', requiresAuth: true }
      },
      {
        path: 'my/posts',
        name: 'my-posts',
        component: () => import('@/views/user/MyPostsView.vue'),
        meta: { title: '我的发布', requiresAuth: true }
      },
      {
        path: 'my/favorites',
        name: 'my-favorites',
        component: () => import('@/views/user/FavoritesView.vue'),
        meta: { title: '我的收藏', requiresAuth: true }
      },
      {
        path: 'notifications',
        name: 'notifications',
        component: () => import('@/views/user/NotificationView.vue'),
        meta: { title: '消息通知', requiresAuth: true }
      },
      {
        path: 'messages',
        name: 'messages',
        component: () => import('@/views/user/MessagesView.vue'),
        meta: { title: '我的私信', requiresAuth: true }
      },
      {
        path: 'profile',
        name: 'profile',
        component: () => import('@/views/user/ProfileView.vue'),
        meta: { title: '个人中心', requiresAuth: true }
      }
    ]
  },

  // ------------------------------------------------------------------
  // 管理端
  // ------------------------------------------------------------------
  {
    path: '/admin',
    component: () => import('@/layouts/AdminLayout.vue'),
    redirect: '/admin/dashboard',
    meta: { requiresAuth: true, requiresAdmin: true },
    children: [
      {
        path: 'dashboard',
        name: 'admin-dashboard',
        component: () => import('@/views/admin/DashboardView.vue'),
        meta: { title: '概览', requiresAdmin: true }
      },
      {
        path: 'users',
        name: 'admin-users',
        component: () => import('@/views/admin/UserManageView.vue'),
        meta: { title: '用户管理', requiresAdmin: true }
      },
      {
        path: 'users/:id',
        name: 'admin-user-detail',
        component: () => import('@/views/admin/UserDetailView.vue'),
        meta: { title: '用户详情', requiresAdmin: true }
      },
      {
        path: 'posts',
        name: 'admin-posts',
        component: () => import('@/views/admin/PostManageView.vue'),
        meta: { title: '内容管理', requiresAdmin: true }
      },
      {
        path: 'audit',
        name: 'admin-audit',
        component: () => import('@/views/admin/AuditView.vue'),
        meta: { title: '审核工作台', requiresAdmin: true }
      },
      {
        path: 'modules',
        name: 'admin-modules',
        component: () => import('@/views/admin/ModuleManageView.vue'),
        meta: { title: '模块管理', requiresAdmin: true }
      },
      {
        path: 'trash',
        name: 'admin-trash',
        component: () => import('@/views/admin/TrashView.vue'),
        meta: { title: '回收站', requiresAdmin: true }
      },
      {
        path: 'reports',
        name: 'admin-reports',
        component: () => import('@/views/admin/ReportView.vue'),
        meta: { title: '举报处理', requiresAdmin: true }
      },
      {
        path: 'logs',
        name: 'admin-logs',
        component: () => import('@/views/admin/LogView.vue'),
        meta: { title: '日志管理', requiresAdmin: true }
      },
      {
        path: 'configs',
        name: 'admin-configs',
        component: () => import('@/views/admin/ConfigView.vue'),
        meta: { title: '系统配置', requiresAdmin: true }
      }
    ]
  },

  // 404
  {
    path: '/:pathMatch(.*)*',
    name: 'not-found',
    component: () => import('@/views/NotFoundView.vue'),
    meta: { title: '页面不存在', public: true }
  }
]

const router = createRouter({
  history: createWebHashHistory(),
  routes,
  scrollBehavior: () => ({ top: 0 })
})

// ---------------------------------------------------------------------------
// 全局守卫
// ---------------------------------------------------------------------------
router.beforeEach(async (to) => {
  const userStore = useUserStore()
  const appStore = useAppStore()

  // 首次进入：恢复登录态 + 加载模块字典
  if (!userStore.initialized) {
    await userStore.fetchMe()
  }
  if (!appStore.loaded) {
    appStore.loadModulesAndEnums()
  }

  // 管理端权限
  if (to.meta.requiresAdmin && !userStore.isAdmin) {
    return { name: 'home', query: { denied: 'admin' } }
  }

  // 登录校验
  if ((to.meta.requiresAuth || to.meta.requiresAdmin) && !userStore.isLogin) {
    return { name: 'login', query: { redirect: to.fullPath } }
  }

  return true
})

router.afterEach((to) => {
  const appStore = useAppStore()
  const base = appStore.siteName
  document.title = to.meta.title ? `${to.meta.title} - ${base}` : base
})

export default router
