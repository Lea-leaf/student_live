/**
 * 通知状态：未读数量轮询 + 列表。
 * 原型阶段用轮询（30s），后续接 WebSocket 时只需替换 startPolling 的实现。
 */
import { defineStore } from 'pinia'

import { notificationApi } from '@/api/interaction'

let timer = null

export const useNotificationStore = defineStore('notification', {
  state: () => ({
    unread: 0,
    list: [],
    total: 0,
    loading: false
  }),

  actions: {
    /** 刷新未读数 */
    async refreshUnread() {
      try {
        const data = await notificationApi.unreadCount()
        this.unread = data.unread || 0
      } catch (error) {
        // 未登录或后端不可用时静默处理
      }
    },

    /** 拉取通知列表 */
    async fetchList(params = {}) {
      this.loading = true
      try {
        const data = await notificationApi.list({ page: 1, size: 20, ...params })
        this.list = data.list || []
        this.total = data.total || 0
        if (typeof data.unread === 'number') {
          this.unread = data.unread
        }
      } finally {
        this.loading = false
      }
    },

    /** 标记单条已读 */
    async markRead(id) {
      await notificationApi.read(id)
      const hit = this.list.find((item) => item.id === id)
      if (hit && !hit.is_read) {
        hit.is_read = true
        this.unread = Math.max(this.unread - 1, 0)
      }
    },

    /** 全部已读 */
    async markAllRead() {
      await notificationApi.readAll()
      this.list.forEach((item) => { item.is_read = true })
      this.unread = 0
    },

    /** 开始轮询未读数 */
    startPolling(interval = 30000) {
      this.stopPolling()
      this.refreshUnread()
      timer = setInterval(() => this.refreshUnread(), interval)
    },

    /** 停止轮询 */
    stopPolling() {
      if (timer) {
        clearInterval(timer)
        timer = null
      }
    }
  }
})

export default useNotificationStore
