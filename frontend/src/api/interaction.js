/** 互动接口（收藏 / 举报 / 通知 / 评论 / 点赞 / 私信） */
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

export const commentApi = {
  /** 评论列表：顶级评论分页，每条自带楼中楼 replies */
  list: (postId, params) => request.get(API.comments.list(postId), { params }),
  /** 发表评论 / 回复：{ content, media, parent_id, reply_to_user_id } */
  create: (postId, data) => request.post(API.comments.create(postId), data),
  /** 删除评论（本人或管理员） */
  remove: (id) => request.delete(API.comments.remove(id))
}

export const likeApi = {
  /** 帖子点赞 / 取消（幂等切换） */
  togglePost: (postId) => request.post(API.likes.post(postId)),
  /** 查询帖子点赞状态 */
  checkPost: (postId) => request.get(API.likes.postState(postId)),
  /** 评论点赞 / 取消（幂等切换） */
  toggleComment: (commentId) => request.post(API.likes.comment(commentId))
}

export const messageApi = {
  /** 会话列表 */
  conversations: (params) => request.get(API.messages.conversations, { params }),
  /** 与某人的私信记录（拉取即已读） */
  withUser: (userId, params) => request.get(API.messages.withUser(userId), { params }),
  /** 发送私信：{ content, media, msg_type, post_id } */
  send: (userId, data) => request.post(API.messages.send(userId), data),
  /** 撤回自己 5 分钟内发送的消息（数据库物理删除） */
  recall: (messageId) => request.post(API.messages.recall(messageId)),
  /** 删除自己私信里的某条消息（单侧隐藏，对方仍可见） */
  remove: (messageId) => request.delete(API.messages.remove(messageId)),
  /** 单条已读回执 */
  read: (messageId) => request.post(API.messages.read(messageId)),
  /** 全部已读 */
  readAll: () => request.post(API.messages.readAll),
  /** 未读红点 */
  unreadCount: () => request.get(API.messages.unreadCount)
}

export default { favoriteApi, reportApi, notificationApi, commentApi, likeApi, messageApi }
