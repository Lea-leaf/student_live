/**
 * 接口地址集中管理。
 *
 * ⚠️ 重要约定：这里的所有路径都**不含** `/api/v1` 前缀！
 * 前缀由 `request.js` 里的 axios `baseURL` 统一加上（默认 `/api/v1`，
 * 可用环境变量 `VITE_API_BASE` 覆盖）。
 *
 * 踩过的坑：早期这里每个地址都写成 `/auth/login`，
 * 而 baseURL 也是 `/api/v1`，两者叠加成 `/api/v1/api/v1/auth/login`，
 * 后端返回 404 —— 页面能打开但点登录报
 * "The requested URL was not found on the server"。
 *
 * 与后端 `app/modules` 和 `app/admin` 的蓝图前缀一一对应，
 * 新增模块时在这里加一段即可，页面里不出现裸字符串地址。
 */

export const API = {
  // ---- 认证 ----
  auth: {
    captcha: '/auth/captcha',
    register: '/auth/register',
    login: '/auth/login',
    logout: '/auth/logout',
    refresh: '/auth/refresh',
    me: '/auth/me',
    password: '/auth/password',
    securityNotice: '/auth/security-notice'
  },
  // ---- 公共 ----
  common: {
    enums: '/common/enums',
    modules: '/common/modules',
    configs: '/common/configs',
    health: '/common/health',
    upload: '/common/upload'
  },
  // ---- 失物招领 ----
  lostFound: {
    list: '/lost_found/posts',
    detail: (id) => `/lost_found/posts/${id}`,
    create: '/lost_found/posts',
    update: (id) => `/lost_found/posts/${id}`,
    remove: (id) => `/lost_found/posts/${id}`,
    upload: '/lost_found/posts/upload',
    myPosts: '/lost_found/my/posts',
    status: (id) => `/lost_found/posts/${id}/status`,
    claim: (id) => `/lost_found/posts/${id}/claim`,
    meta: '/lost_found/meta'
  },
  // ---- 互动（v1.0 部分可用） ----
  favorites: {
    list: `/favorites`,
    toggle: (postId) => `/favorites/posts/${postId}`,
    check: (postId) => `/favorites/check/${postId}`
  },
  reports: {
    create: `/reports`,
    mine: `/reports/my`
  },
  notifications: {
    list: `/notifications`,
    unreadCount: `/notifications/unread-count`,
    read: (id) => `/notifications/read/${id}`,
    readAll: `/notifications/read-all`
  },
  comments: {
    list: (postId) => `/comments/posts/${postId}/comments`,
    create: (postId) => `/comments/posts/${postId}/comments`,
    remove: (id) => `/comments/${id}`
  },
  likes: {
    post: (postId) => `/likes/posts/${postId}`,
    postState: (postId) => `/likes/posts/${postId}`,
    comment: (commentId) => `/likes/comments/${commentId}`,
    commentState: (commentId) => `/likes/comments/${commentId}`
  },
  messages: {
    conversations: `/messages/conversations`,
    withUser: (userId) => `/messages/with/${userId}`,
    send: (userId) => `/messages/with/${userId}`,
    recall: (messageId) => `/messages/${messageId}/recall`,
    remove: (messageId) => `/messages/${messageId}`,
    read: (messageId) => `/messages/read/${messageId}`,
    readAll: `/messages/read-all`,
    unreadCount: `/messages/unread-count`
  },
  // ---- 管理端 ----
  admin: {
    overview: `/admin/dashboard/overview`,
    trend: `/admin/dashboard/trend`,
    moduleStats: `/admin/dashboard/module-stats`,
    pending: `/admin/dashboard/pending`,

    users: `/admin/users`,
    userDetail: (id) => `/admin/users/${id}`,
    userPosts: (id) => `/admin/users/${id}/posts`,
    userLogs: (id) => `/admin/users/${id}/logs`,
    userBan: (id) => `/admin/users/${id}/ban`,
    userUnban: (id) => `/admin/users/${id}/unban`,
    userResetPassword: (id) => `/admin/users/${id}/reset-password`,
    userRole: (id) => `/admin/users/${id}/role`,
    userMedia: (id) => `/admin/users/${id}/media`,
    batchBan: `/admin/users/batch/ban`,

    comments: '/admin/comments',
    commentStats: '/admin/comments/stats',
    commentDelete: (id) => `/admin/comments/${id}`,

    posts: `/admin/posts`,
    postDetail: (id) => `/admin/posts/${id}`,
    postAudit: (id) => `/admin/posts/${id}/audit`,
    postStatus: (id) => `/admin/posts/${id}/status`,
    postTop: (id) => `/admin/posts/${id}/top`,
    postDelete: (id) => `/admin/posts/${id}`,
    postPending: `/admin/posts/pending`,
    postBatchAudit: `/admin/posts/batch/audit`,
    postSummary: `/admin/posts/stats/summary`,

    modules: `/admin/modules`,
    moduleUpdate: (id) => `/admin/modules/${id}`,
    moduleToggle: (id) => `/admin/modules/${id}/toggle`,
    moduleReorder: `/admin/modules/reorder`,
    moduleDelete: (id) => `/admin/modules/${id}`,

    trash: `/admin/trash`,
    trashRestore: (id) => `/admin/trash/${id}/restore`,
    trashPurge: (id) => `/admin/trash/${id}`,
    trashCleanup: `/admin/trash/cleanup`,
    trashStats: `/admin/trash/stats`,

    reports: `/admin/reports`,
    reportHandle: (id) => `/admin/reports/${id}/handle`,

    operationLogs: `/admin/logs/operations`,
    loginLogs: `/admin/logs/logins`,
    errorLogs: `/admin/logs/errors`,
    logsSummary: `/admin/logs/summary`,

    configs: `/admin/configs`,
    configsReset: `/admin/configs/reset`,
    configsInit: `/admin/configs/init`
  }
}

export default API
