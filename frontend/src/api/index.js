/**
 * 接口地址集中管理。
 *
 * 约定：与后端 `app/modules` 和 `app/admin` 的蓝图前缀一一对应，
 * 新增模块时在这里加一段即可，页面里不出现裸字符串地址。
 */
const API_PREFIX = '/api/v1'

export const API = {
  // ---- 认证 ----
  auth: {
    captcha: `${API_PREFIX}/auth/captcha`,
    register: `${API_PREFIX}/auth/register`,
    login: `${API_PREFIX}/auth/login`,
    logout: `${API_PREFIX}/auth/logout`,
    refresh: `${API_PREFIX}/auth/refresh`,
    me: `${API_PREFIX}/auth/me`,
    password: `${API_PREFIX}/auth/password`,
    securityNotice: `${API_PREFIX}/auth/security-notice`
  },
  // ---- 公共 ----
  common: {
    enums: `${API_PREFIX}/common/enums`,
    modules: `${API_PREFIX}/common/modules`,
    configs: `${API_PREFIX}/common/configs`,
    health: `${API_PREFIX}/common/health`,
    upload: `${API_PREFIX}/common/upload`
  },
  // ---- 失物招领 ----
  lostFound: {
    list: `${API_PREFIX}/lost_found/posts`,
    detail: (id) => `${API_PREFIX}/lost_found/posts/${id}`,
    create: `${API_PREFIX}/lost_found/posts`,
    update: (id) => `${API_PREFIX}/lost_found/posts/${id}`,
    remove: (id) => `${API_PREFIX}/lost_found/posts/${id}`,
    upload: `${API_PREFIX}/lost_found/posts/upload`,
    myPosts: `${API_PREFIX}/lost_found/my/posts`,
    status: (id) => `${API_PREFIX}/lost_found/posts/${id}/status`,
    claim: (id) => `${API_PREFIX}/lost_found/posts/${id}/claim`,
    meta: `${API_PREFIX}/lost_found/meta`
  },
  // ---- 互动（v1.0 部分可用） ----
  favorites: {
    list: `${API_PREFIX}/favorites`,
    toggle: (postId) => `${API_PREFIX}/favorites/posts/${postId}`,
    check: (postId) => `${API_PREFIX}/favorites/check/${postId}`
  },
  reports: {
    create: `${API_PREFIX}/reports`,
    mine: `${API_PREFIX}/reports/my`
  },
  notifications: {
    list: `${API_PREFIX}/notifications`,
    unreadCount: `${API_PREFIX}/notifications/unread-count`,
    read: (id) => `${API_PREFIX}/notifications/read/${id}`,
    readAll: `${API_PREFIX}/notifications/read-all`
  },
  comments: {
    list: (postId) => `${API_PREFIX}/comments/posts/${postId}/comments`,
    create: (postId) => `${API_PREFIX}/comments/posts/${postId}/comments`
  },
  messages: {
    conversations: `${API_PREFIX}/messages/conversations`
  },
  // ---- 管理端 ----
  admin: {
    overview: `${API_PREFIX}/admin/dashboard/overview`,
    trend: `${API_PREFIX}/admin/dashboard/trend`,
    moduleStats: `${API_PREFIX}/admin/dashboard/module-stats`,
    pending: `${API_PREFIX}/admin/dashboard/pending`,

    users: `${API_PREFIX}/admin/users`,
    userDetail: (id) => `${API_PREFIX}/admin/users/${id}`,
    userPosts: (id) => `${API_PREFIX}/admin/users/${id}/posts`,
    userLogs: (id) => `${API_PREFIX}/admin/users/${id}/logs`,
    userBan: (id) => `${API_PREFIX}/admin/users/${id}/ban`,
    userUnban: (id) => `${API_PREFIX}/admin/users/${id}/unban`,
    userResetPassword: (id) => `${API_PREFIX}/admin/users/${id}/reset-password`,
    userRole: (id) => `${API_PREFIX}/admin/users/${id}/role`,
    batchBan: `${API_PREFIX}/admin/users/batch/ban`,

    posts: `${API_PREFIX}/admin/posts`,
    postDetail: (id) => `${API_PREFIX}/admin/posts/${id}`,
    postAudit: (id) => `${API_PREFIX}/admin/posts/${id}/audit`,
    postStatus: (id) => `${API_PREFIX}/admin/posts/${id}/status`,
    postTop: (id) => `${API_PREFIX}/admin/posts/${id}/top`,
    postDelete: (id) => `${API_PREFIX}/admin/posts/${id}`,
    postPending: `${API_PREFIX}/admin/posts/pending`,
    postBatchAudit: `${API_PREFIX}/admin/posts/batch/audit`,
    postSummary: `${API_PREFIX}/admin/posts/stats/summary`,

    modules: `${API_PREFIX}/admin/modules`,
    moduleUpdate: (id) => `${API_PREFIX}/admin/modules/${id}`,
    moduleToggle: (id) => `${API_PREFIX}/admin/modules/${id}/toggle`,
    moduleReorder: `${API_PREFIX}/admin/modules/reorder`,
    moduleDelete: (id) => `${API_PREFIX}/admin/modules/${id}`,

    trash: `${API_PREFIX}/admin/trash`,
    trashRestore: (id) => `${API_PREFIX}/admin/trash/${id}/restore`,
    trashPurge: (id) => `${API_PREFIX}/admin/trash/${id}`,
    trashCleanup: `${API_PREFIX}/admin/trash/cleanup`,
    trashStats: `${API_PREFIX}/admin/trash/stats`,

    reports: `${API_PREFIX}/admin/reports`,
    reportHandle: (id) => `${API_PREFIX}/admin/reports/${id}/handle`,

    operationLogs: `${API_PREFIX}/admin/logs/operations`,
    loginLogs: `${API_PREFIX}/admin/logs/logins`,
    errorLogs: `${API_PREFIX}/admin/logs/errors`,
    logsSummary: `${API_PREFIX}/admin/logs/summary`,

    configs: `${API_PREFIX}/admin/configs`,
    configsReset: `${API_PREFIX}/admin/configs/reset`,
    configsInit: `${API_PREFIX}/admin/configs/init`
  }
}

export default API
