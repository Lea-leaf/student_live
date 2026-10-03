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

/**
 * 接口前缀：全局唯一来源。
 *
 * ⚠️ `src/api/index.js` 里的所有路径都**不含**这个前缀，由 axios 的 baseURL 统一加上。
 * 早期两处各写了一份 `/api/v1`，结果拼成 `/api/v1/api/v1/auth/login`，登录直接 404。
 * 需要在前缀之外发请求（例如健康检查、静态资源判断）时，从这里取，不要再写一份。
 */
export const API_BASE = import.meta.env.VITE_API_BASE || '/api/v1'

/**
 * 文件上传专用超时（毫秒）。
 * 普通接口用 20 秒足够，但视频最大 50MB，慢网络下 20 秒传不完，
 * 会被 axios 判为超时而中断。上传单独放宽到 5 分钟。
 */
export const UPLOAD_TIMEOUT = Number(import.meta.env.VITE_UPLOAD_TIMEOUT || 5 * 60 * 1000)

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
  baseURL: API_BASE,
  timeout: 20000
})

// ---------------------------------------------------------------------------
// 运行时自检：请求地址若出现重复前缀，说明有人又硬编码了前缀，立即报错而不是静默 404
// ---------------------------------------------------------------------------
function assertNoDoubledPrefix(config) {
  const url = config.url || ''
  if (url.startsWith(API_BASE)) {
    const message = `[api] 接口地址重复了前缀：baseURL="${API_BASE}" + url="${url}"。
请把 src/api/index.js 里的路径写成相对形式（例如 '/auth/login'），前缀由 baseURL 统一提供。`
    console.error(message)
    ElMessage.error('接口配置错误：请求地址重复了 /api/v1 前缀，请查看控制台')
    throw new Error(message)
  }
  return config
}

// ---------------------------------------------------------------------------
// 请求拦截：前缀自检 + 注入 token
// ---------------------------------------------------------------------------
service.interceptors.request.use(
  (config) => {
    assertNoDoubledPrefix(config)
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

/**
 * 跳转登录页。
 * 优先用 SPA 路由（不刷新页面、保留当前路径作为 redirect），
 * 拿不到 router 时才退回改 hash —— 直接改 hash 会整页刷新，登录态与 Pinia 状态都会丢。
 */
async function goLogin(redirectPath) {
  const target = `/auth/login?redirect=${encodeURIComponent(redirectPath || '/')}`
  try {
    const { default: router } = await import('@/router')
    await router.replace(target)
    return
  } catch (error) {
    console.warn('[api] 路由跳转失败，退回 hash 方式：', error?.message)
  }
  window.location.hash = `#${target}`
}

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
        const current = window.location.hash.replace(/^#/, '') || '/'
        setTimeout(async () => {
          await goLogin(current)
          redirecting = false
        }, 300)
      }
      return Promise.reject(body)
    }
    // 2004 账号被封禁：给出明确弹窗
    if (code === 2004) {
      // .catch 必须加：用户点 × / ESC 关闭弹窗时 ElMessageBox 会 reject，
      // 不接住控制台就报 Uncaught (in promise) cancel
      ElMessageBox.alert(msg || '账号已被封禁', '访问受限', { type: 'error' }).catch(() => {})
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
 *
 * ⚠️ 必须单独覆盖 timeout：全局 axios 实例是 20 秒，
 * 图片几秒能传完没问题，但**视频（最大 50MB）在 20 秒内很可能传不完**，
 * 会直接报「请求超时」而不是显示上传进度 —— 这是实际踩过的坑。
 * 这里给上传单独放宽到 5 分钟；进度条照常工作，不会一直干等。
 *
 * @param {string} url 接口地址
 * @param {File[]} files 文件列表
 * @param {object} extra 额外表单字段
 * @param {Function} onProgress 进度回调（0-100）
 * @param {number} timeout 可选：自定义超时（毫秒）
 */
export function upload(url, files, extra = {}, onProgress, timeout = UPLOAD_TIMEOUT) {
  const formData = new FormData()
  files.forEach((file) => formData.append('files', file))
  Object.entries(extra).forEach(([key, value]) => formData.append(key, value))
  return service.post(url, formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
    // 上传不跟全局 20s 超时走，否则大视频必然超时
    timeout,
    onUploadProgress: (event) => {
      if (onProgress && event.total) {
        onProgress(Math.round((event.loaded * 100) / event.total))
      }
    }
  })
}

export default service
