/**
 * 用户状态：登录信息、token、权限判断。
 * token 存 localStorage，刷新页面后通过 fetchMe() 恢复用户信息。
 */
import { defineStore } from 'pinia'

import authApi from '@/api/auth'
import { clearToken, getToken, setToken } from '@/api/request'

export const useUserStore = defineStore('user', {
  state: () => ({
    /** 当前用户信息（未登录为 null） */
    user: null,
    /** 是否已尝试恢复登录态 */
    initialized: false,
    /** 登录中标记（防止重复提交） */
    logging: false
  }),

  getters: {
    /** 是否已登录 */
    isLogin: (state) => !!state.user && !!getToken(),
    /** 是否管理员 */
    isAdmin: (state) => !!(state.user && state.user.is_admin),
    /** 展示名 */
    displayName: (state) => (state.user ? state.user.display_name || state.user.nickname || state.user.student_id : '游客'),
    /** 头像 */
    avatar: (state) => (state.user ? state.user.avatar : ''),
    /** 学号 */
    studentId: (state) => (state.user ? state.user.student_id : '')
  },

  actions: {
    /** 登录 */
    async login(payload) {
      this.logging = true
      try {
        const data = await authApi.login(payload)
        setToken(data.access_token, data.refresh_token)
        this.user = data.user
        this.initialized = true
        return data.user
      } finally {
        this.logging = false
      }
    },

    /** 注册并自动登录 */
    async register(payload) {
      const data = await authApi.register(payload)
      setToken(data.access_token, data.refresh_token)
      this.user = data.user
      this.initialized = true
      return data.user
    },

    /** 拉取当前用户（页面刷新后恢复登录态） */
    async fetchMe() {
      if (!getToken()) {
        this.user = null
        this.initialized = true
        return null
      }
      try {
        this.user = await authApi.me()
      } catch (error) {
        // token 失效：已在拦截器里清理，这里保持未登录状态
        this.user = null
        clearToken()
      } finally {
        this.initialized = true
      }
      return this.user
    },

    /** 更新资料 */
    async updateProfile(payload) {
      this.user = await authApi.updateMe(payload)
      return this.user
    },

    /** 登出 */
    async logout() {
      try {
        if (getToken()) {
          await authApi.logout()
        }
      } catch (error) {
        // 忽略登出接口异常，本地状态必须清干净
      } finally {
        clearToken()
        this.user = null
        this.initialized = true
      }
    }
  }
})

export default useUserStore
