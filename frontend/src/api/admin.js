/** 管理端接口 */
import request from './request'
import { API } from './index'

export const adminApi = {
  // ---------------- 首页统计 ----------------
  dashboard: {
    overview: () => request.get(API.admin.overview),
    trend: (params) => request.get(API.admin.trend, { params }),
    moduleStats: () => request.get(API.admin.moduleStats),
    pending: (params) => request.get(API.admin.pending, { params }),
    /** 媒体存储用量 / 未提交上传 / 孤儿文件 */
    media: () => request.get(API.admin.media),
    /** 清理未引用媒体（未提交上传 + 孤儿文件，默认保留 24 小时） */
    mediaClean: (data) => request.post(API.admin.mediaClean, data || {})
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
    /** 彻底删除用户（需传 confirm_student_id 二次确认） */
    remove: (id, data) => request.delete(API.admin.userDetail(id), { data })
  },

  // ---------------- 管理员移交（系统只允许一个管理员）----------------
  handover: {
    /** 当前移交状态（发起人 / 接班人视角）+ 可选接任者名单 + 服务器北京时间 */
    status: () => request.get(API.admin.handoverStatus),
    /** 发起移交：{ user_id, reason } */
    start: (data) => request.post(API.admin.handover, data),
    /** 撤销移交（反悔期 24 小时内） */
    cancel: (data) => request.post(API.admin.handoverCancel, data || {}),
    /** 立即结算已到期的移交（演示 / 排障用） */
    finalize: () => request.post(API.admin.handoverFinalize)
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
    summary: () => request.get(API.admin.postSummary),

    // ---- 审核指派 / 认领 ----
    /** 可指派的审核员名单 + 各自待审数量（仅管理员有内容） */
    assignees: () => request.get(API.admin.auditAssignees),
    /** 指派 / 改派 / 收回公共池（assignee_id 传 null 即收回） */
    assign: (id, data) => request.post(API.admin.postAssign(id), data),
    /** 审核员自助认领（先到先得，被抢走时后端返回 4005） */
    claim: (id) => request.post(API.admin.postClaim(id)),
    /** 放弃认领，退回公共池 */
    release: (id, data) => request.post(API.admin.postRelease(id), data || {}),
    /** 该帖子的审核流水（指派 / 认领 / 退回 / 通过 / 拒绝） */
    auditLogs: (id) => request.get(API.admin.postAuditLogs(id))
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
