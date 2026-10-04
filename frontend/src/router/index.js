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

/**
 * 管理端落地页优先级：按角色实际拥有的能力挑第一个可进的页面。
 * 管理员 → 概览；只有审核能力的角色 → 审核工作台。
 * 顺序与 AdminLayout 的菜单保持一致，也是 `/admin` 重定向的依据。
 */
const ADMIN_LANDING = [
  { name: 'admin-dashboard', capability: 'dashboard.view' },
  { name: 'admin-audit', capability: 'post.audit' },
  { name: 'admin-posts', capability: 'post.view' },
  { name: 'admin-reports', capability: 'report.handle' },
  { name: 'admin-users', capability: 'user.view' },
  { name: 'admin-trash', capability: 'trash.view' },
  { name: 'admin-logs', capability: 'log.view' },
  { name: 'admin-modules', capability: 'module.manage' },
  { name: 'admin-configs', capability: 'config.manage' }
]

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
  //
  // `meta.capability` 决定「谁能进这个页面」：后端下发的能力清单是唯一依据，
  // 审核员只拿到内容相关的几项，因此自然看不到系统配置 / 模块 / 日志 / 回收站。
  // 注意：这只是**体验层**过滤，真正的门禁在后端装饰器上。
  // ------------------------------------------------------------------
  {
    path: '/admin',
    component: () => import('@/layouts/AdminLayout.vue'),
    // 不再硬编码跳概览：审核员没有 dashboard.view 时会被守卫再弹一次，
    // 这里直接交给他能进的第一个页面。
    redirect: () => {
      const userStore = useUserStore()
      const landing = ADMIN_LANDING.find((item) => userStore.can(item.capability))
      return landing ? { name: landing.name } : { name: 'home', query: { denied: 'admin' } }
    },
    meta: { requiresAuth: true, requiresAdmin: true },
    children: [
      {
        path: 'dashboard',
        name: 'admin-dashboard',
        component: () => import('@/views/admin/DashboardView.vue'),
        meta: { title: '概览', requiresAdmin: true, capability: 'dashboard.view' }
      },
      {
        path: 'users',
        name: 'admin-users',
        component: () => import('@/views/admin/UserManageView.vue'),
        meta: { title: '用户管理', requiresAdmin: true, capability: 'user.view' }
      },
      {
        path: 'users/:id',
        name: 'admin-user-detail',
        component: () => import('@/views/admin/UserDetailView.vue'),
        meta: { title: '用户详情', requiresAdmin: true, capability: 'user.detail' }
      },
      {
        path: 'posts',
        name: 'admin-posts',
        component: () => import('@/views/admin/PostManageView.vue'),
        meta: { title: '内容管理', requiresAdmin: true, capability: 'post.view' }
      },
      {
        path: 'audit',
        name: 'admin-audit',
        component: () => import('@/views/admin/AuditView.vue'),
        meta: { title: '审核工作台', requiresAdmin: true, capability: 'post.audit' }
      },
      {
        path: 'modules',
        name: 'admin-modules',
        component: () => import('@/views/admin/ModuleManageView.vue'),
        meta: { title: '模块管理', requiresAdmin: true, capability: 'module.manage' }
      },
      {
        path: 'trash',
        name: 'admin-trash',
        component: () => import('@/views/admin/TrashView.vue'),
        meta: { title: '回收站', requiresAdmin: true, capability: 'trash.view' }
      },
      {
        path: 'reports',
        name: 'admin-reports',
        component: () => import('@/views/admin/ReportView.vue'),
        meta: { title: '举报处理', requiresAdmin: true, capability: 'report.handle' }
      },
      {
        path: 'logs',
        name: 'admin-logs',
        component: () => import('@/views/admin/LogView.vue'),
        meta: { title: '日志管理', requiresAdmin: true, capability: 'log.view' }
      },
      {
        path: 'configs',
        name: 'admin-configs',
        component: () => import('@/views/admin/ConfigView.vue'),
        meta: { title: '系统配置', requiresAdmin: true, capability: 'config.manage' }
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

  // 管理端页面的能力校验：审核员没有 config.manage，所以进不了系统配置
  if (to.meta.capability && !userStore.can(to.meta.capability)) {
    // 已经被挡在某个管理页外时，退回到他确实能进的第一个管理页，
    // 避免出现"点进去又被弹回前台"的来回跳。
    const fallback = ADMIN_LANDING.find((item) => userStore.can(item.capability))
    if (fallback && to.name !== fallback.name) {
      return { name: fallback.name, query: { denied: 'capability' } }
    }
    return { name: 'home', query: { denied: 'capability' } }
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
