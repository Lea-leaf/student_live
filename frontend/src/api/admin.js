/** 管理端接口 */
import request from './request'
import { API } from './index'

export const adminApi = {
  // ---------------- 首页统计 ----------------
  dashboard: {
    overview: () => request.get(API.admin.overview),
    trend: (params) => request.get(API.admin.trend, { params }),
    moduleStats: () => request.get(API.admin.moduleStats),
    pending: (params) => request.get(API.admin.pending, { params })
  },

  // ---------------- 用户管理 ----------------
  users: {
    list: (params) => request.get(API.admin.users, { params }),
    detail: (id) => request.get(API.admin.userDetail(id)),
    posts: (id, params) => request.get(API.admin.userPosts(id), { params }),
    logs: (id, params) => request.get(API.admin.userLogs(id), { params }),
    /** 媒体文件清单与磁盘占用（删除用户前确认用） */
    media: (id) => request.get(API.admin.userMedia(id)),
    ban: (id, data) => request.post(API.admin.userBan(id), data),
    unban: (id) => request.post(API.admin.userUnban(id)),
    resetPassword: (id, data) => request.post(API.admin.userResetPassword(id), data || {}),
    changeRole: (id, data) => request.post(API.admin.userRole(id), data),
    create: (data) => request.post(API.admin.users, data),
    batchBan: (data) => request.post(API.admin.batchBan, data),
    /** 彻底删除用户（需传 confirm_student_id 二次确认；仅超级管理员） */
    remove: (id, data) => request.delete(API.admin.userDetail(id), { data })
  },

  // ---------------- 评论管理 ----------------
  comments: {
    list: (params) => request.get(API.admin.comments, { params }),
    stats: () => request.get(API.admin.commentStats),
    /** purge=1 时彻底删除（含子回复） */
    remove: (id, purge) => request.delete(API.admin.commentDelete(id), {
      params: purge ? { purge: 1 } : {}
    })
  },

  // ---------------- 内容管理 ----------------
  posts: {
    list: (params) => request.get(API.admin.posts, { params }),
    pending: (params) => request.get(API.admin.postPending, { params }),
    detail: (id) => request.get(API.admin.postDetail(id)),
    audit: (id, data) => request.post(API.admin.postAudit(id), data),
    batchAudit: (data) => request.post(API.admin.postBatchAudit, data),
    changeStatus: (id, data) => request.post(API.admin.postStatus(id), data),
    toggleTop: (id, data) => request.post(API.admin.postTop(id), data || {}),
    update: (id, data) => request.put(API.admin.postDetail(id), data),
    remove: (id) => request.delete(API.admin.postDelete(id)),
    summary: () => request.get(API.admin.postSummary)
  },

  // ---------------- 模块管理 ----------------
  modules: {
    list: () => request.get(API.admin.modules),
    create: (data) => request.post(API.admin.modules, data),
    update: (id, data) => request.put(API.admin.moduleUpdate(id), data),
    toggle: (id, data) => request.post(API.admin.moduleToggle(id), data || {}),
    reorder: (items) => request.post(API.admin.moduleReorder, { items }),
    remove: (id) => request.delete(API.admin.moduleDelete(id))
  },

  // ---------------- 回收站 ----------------
  trash: {
    list: (params) => request.get(API.admin.trash, { params }),
    restore: (id) => request.post(API.admin.trashRestore(id)),
    purge: (id) => request.delete(API.admin.trashPurge(id)),
    cleanup: (data) => request.post(API.admin.trashCleanup, data || {}),
    stats: () => request.get(API.admin.trashStats)
  },

  // ---------------- 举报 ----------------
  reports: {
    list: (params) => request.get(API.admin.reports, { params }),
    handle: (id, data) => request.post(API.admin.reportHandle(id), data)
  },

  // ---------------- 日志 ----------------
  logs: {
    operations: (params) => request.get(API.admin.operationLogs, { params }),
    logins: (params) => request.get(API.admin.loginLogs, { params }),
    errors: (params) => request.get(API.admin.errorLogs, { params }),
    summary: () => request.get(API.admin.logsSummary)
  },

  // ---------------- 系统配置 ----------------
  configs: {
    list: (params) => request.get(API.admin.configs, { params }),
    update: (items) => request.put(API.admin.configs, { items }),
    reset: (keys) => request.post(API.admin.configsReset, { keys }),
    init: () => request.post(API.admin.configsInit)
  }
}

export default adminApi
