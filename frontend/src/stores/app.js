/**
 * 应用级状态：公开配置、模块列表、字典。
 * 这些数据全局复用，进页面时拉一次即可。
 */
import { defineStore } from 'pinia'

import commonApi from '@/api/common'

export const useAppStore = defineStore('app', {
  state: () => ({
    /** 站点与业务开关配置 */
    config: {
      site_name: '校园生活平台',
      site_notice: '',
      security_notice_enabled: true,
      security_notice_text: '',
      post_audit_enabled: true,
      register_captcha_enabled: true,
      guest_can_list: true,
      guest_can_detail: false,
      upload_max_mb_image: '10',
      upload_max_mb_video: '50',
      upload_max_mb_audio: '5'
    },
    /** 启用中的模块 */
    modules: [],
    /** 字典 */
    enums: {
      post_status: [],
      audit_status: [],
      report_status: [],
      user_status: [],
      role: []
    },
    loaded: false
  }),

  getters: {
    siteName: (state) => state.config.site_name || '校园生活平台',
    auditEnabled: (state) => String(state.config.post_audit_enabled) === '1'
      || state.config.post_audit_enabled === true
  },

  actions: {
    /** 拉取公开配置 */
    async loadPublicConfig() {
      try {
        const data = await commonApi.configs()
        this.config = { ...this.config, ...data }
      } catch (error) {
        // 后端未启动时静默降级，页面仍可渲染
        console.warn('[app] 加载公开配置失败：', error?.msg || error?.message)
      }
    },

    /** 拉取模块与字典 */
    async loadModulesAndEnums() {
      try {
        const [modules, enums] = await Promise.all([
          commonApi.modules(),
          commonApi.enums()
        ])
        this.modules = modules.list || []
        this.enums = { ...this.enums, ...enums }
      } catch (error) {
        console.warn('[app] 加载模块/字典失败：', error?.msg || error?.message)
      } finally {
        this.loaded = true
      }
    },

    /** 按 code 取模块名 */
    moduleName(code) {
      const hit = this.modules.find((item) => item.code === code)
      return hit ? hit.name : code
    },

    /** 按字典取值对应的中文标签 */
    labelOf(dictKey, value) {
      const list = this.enums[dictKey] || []
      const hit = list.find((item) => item.value === value)
      return hit ? hit.label : value
    }
  }
})

export default useAppStore
