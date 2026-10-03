/**
 * 私信未读状态：顶部小红点轮询 + 会话未读数。
 * 私信页打开某会话时后端会返回 read_count，页面再调用 refreshUnread() 同步。
 */
import { defineStore } from 'pinia'

import { messageApi } from '@/api/interaction'

let timer = null

export const useMessageStore = defineStore('message', {
  state: () => ({
    /** 未读私信总数 */
    unread: 0,
    /** 有未读私信的会话数 */
    unreadConversations: 0,
    loading: false
  }),

  actions: {
    /** 刷新未读红点 */
    async refreshUnread() {
      try {
        const data = await messageApi.unreadCount()
        this.unread = data.unread || 0
        this.unreadConversations = data.unread_conversations || 0
      } catch (error) {
        // 未登录或后端不可用时静默处理
      }
    },

    /** 开始轮询（默认 30 秒，与通知中心保持一致） */
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

export default useMessageStore