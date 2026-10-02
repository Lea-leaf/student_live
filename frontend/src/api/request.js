/**
 * Axios 封装：统一 baseURL、JWT 注入、统一响应拆包、错误提示。
 *
 * 后端统一响应格式：{ code, msg, data }
 * 约定：code === 0 视为成功，此时 resolve 的是 data 本身（业务代码少写一层 .data）；
 *      其他情况统一 ElMessage 报错并 reject，特殊错误码（401/2004）做跳转与提示。
 */
import axios from 'axios'
import { ElMessage, ElMessageBox } from 'element-plus'

export const TOKEN_KEY = 'slp_access_token'
export const REFRESH_KEY = 'slp_refresh_token'

export function getToken() {
  return localStorage.getItem(TOKEN_KEY) || ''
}

export function setToken(accessToken, refreshToken) {
  if (accessToken) localStorage.setItem(TOKEN_KEY, accessToken)
  if (refreshToken) localStorage.setItem(REFRESH_KEY, refreshToken)
}

export function clearToken() {
  localStorage.removeItem(TOKEN_KEY)
  localStorage.removeItem(REFRESH_KEY)
}

const service = axios.create({
  // 开发环境走 Vite 代理；生产环境同域部署时也无需改
  baseURL: import.meta.env.VITE_API_BASE || '/api/v1',
  timeout: 20000
})

// ---------------------------------------------------------------------------
// 请求拦截：注入 token
// ---------------------------------------------------------------------------
service.interceptors.request.use(
  (config) => {
    const token = getToken()
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }
    return config
  },
  (error) => Promise.reject(error)
)

// 未登录跳转只弹一次，避免并发请求刷屏
let redirecting = false

// ---------------------------------------------------------------------------
// 响应拦截：拆包 + 错误处理
// ---------------------------------------------------------------------------
service.interceptors.response.use(
  (response) => {
    const body = response.data
    // 非 JSON（例如文件下载）直接返回
    if (body === null || typeof body !== 'object' || !('code' in body)) {
      return body
    }
    if (body.code === 0) {
      return body.data
    }

    const { code, msg } = body
    // 2001 未登录 / 2002 token 过期 → 清理登录态并跳登录页
    if (code === 2001 || code === 2002) {
      clearToken()
      if (!redirecting) {
        redirecting = true
        ElMessage.warning(msg || '登录已过期，请重新登录')
        const redirect = encodeURIComponent(window.location.hash.replace(/^#/, '') || '/')
        setTimeout(() => {
          window.location.hash = `#/login?redirect=${redirect}`
          redirecting = false
        }, 300)
      }
      return Promise.reject(body)
    }
    // 2004 账号被封禁：给出明确弹窗
    if (code === 2004) {
      ElMessageBox.alert(msg || '账号已被封禁', '访问受限', { type: 'error' })
      return Promise.reject(body)
    }

    ElMessage.error(msg || '请求失败')
    return Promise.reject(body)
  },
  (error) => {
    // 网络层错误（后端未启动、超时等）
    let message = '网络异常，请稍后重试'
    if (error.code === 'ECONNABORTED') {
      message = '请求超时，请检查后端服务是否已启动'
    } else if (error.response) {
      const { status } = error.response
      const data = error.response.data
      if (data && data.msg) {
        message = data.msg
      } else if (status === 404) {
        message = '接口不存在（请确认后端已启动并注册了该路由）'
      } else if (status === 500) {
        message = '服务器内部错误'
      }
      if (status === 401) {
        clearToken()
      }
    }
    ElMessage.error(message)
    return Promise.reject(error)
  }
)

/**
 * 上传文件（multipart/form-data）
 * @param {string} url 接口地址
 * @param {File[]} files 文件列表
 * @param {object} extra 额外表单字段
 * @param {Function} onProgress 进度回调（0-100）
 */
export function upload(url, files, extra = {}, onProgress) {
  const formData = new FormData()
  files.forEach((file) => formData.append('files', file))
  Object.entries(extra).forEach(([key, value]) => formData.append(key, value))
  return service.post(url, formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
    onUploadProgress: (event) => {
      if (onProgress && event.total) {
        onProgress(Math.round((event.loaded * 100) / event.total))
      }
    }
  })
}

export default service
