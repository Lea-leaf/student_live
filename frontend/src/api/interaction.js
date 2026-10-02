/** 互动接口（收藏 / 举报 / 通知 / 评论占位） */
import request from './request'
import { API } from './index'

export const favoriteApi = {
  list: (params) => request.get(API.favorites.list, { params }),
  toggle: (postId) => request.post(API.favorites.toggle(postId)),
  check: (postId) => request.get(API.favorites.check(postId))
}

export const reportApi = {
  /** 提交举报：{ post_id | target_user_id, reason, detail } */
  create: (data) => request.post(API.reports.create, data),
  mine: (params) => request.get(API.reports.mine, { params })
}

export const notificationApi = {
  list: (params) => request.get(API.notifications.list, { params }),
  unreadCount: () => request.get(API.notifications.unreadCount),
  read: (id) => request.post(API.notifications.read(id)),
  readAll: () => request.post(API.notifications.readAll)
}

export default { favoriteApi, reportApi, notificationApi }
