/**
 * 通用工具函数。
 */

/** 时间格式化：后端返回 'YYYY-MM-DD HH:mm:ss' */
export function formatTime(value, withTime = true) {
  if (!value) return '-'
  const text = String(value).replace('T', ' ')
  return withTime ? text.slice(0, 16) : text.slice(0, 10)
}

/** 相对时间：刚刚 / 3 分钟前 / 2 天前 */
export function fromNow(value) {
  if (!value) return '-'
  const target = new Date(String(value).replace(/-/g, '/'))
  const diff = (Date.now() - target.getTime()) / 1000
  if (Number.isNaN(diff)) return formatTime(value)
  if (diff < 60) return '刚刚'
  if (diff < 3600) return `${Math.floor(diff / 60)} 分钟前`
  if (diff < 86400) return `${Math.floor(diff / 3600)} 小时前`
  if (diff < 86400 * 7) return `${Math.floor(diff / 86400)} 天前`
  return formatTime(value, false)
}

/** 文件大小 */
export function formatSize(bytes) {
  const size = Number(bytes) || 0
  if (size < 1024) return `${size} B`
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`
  return `${(size / 1024 / 1024).toFixed(2)} MB`
}

/** 状态 → Element Plus tag 类型 */
export function statusTagType(status) {
  const map = {
    ongoing: 'success',
    claimed: 'warning',
    expired: 'info',
    closed: 'danger',
    pending: 'warning',
    approved: 'success',
    rejected: 'danger',
    active: 'success',
    banned: 'danger',
    handled: 'success'
  }
  return map[status] || 'info'
}

/** 安全公告是否已确认（按用户维度记录，避免每次刷新都弹） */
const NOTICE_KEY = 'slp_security_notice_ack'

export function isNoticeAcknowledged(identity) {
  try {
    const raw = localStorage.getItem(NOTICE_KEY)
    if (!raw) return false
    const data = JSON.parse(raw)
    return data.identity === identity
  } catch (error) {
    return false
  }
}

export function acknowledgeNotice(identity) {
  localStorage.setItem(NOTICE_KEY, JSON.stringify({ identity, at: Date.now() }))
}

/** 复制文本到剪贴板 */
export async function copyText(text) {
  try {
    await navigator.clipboard.writeText(text)
    return true
  } catch (error) {
    // 兼容非 https / 旧浏览器
    const input = document.createElement('textarea')
    input.value = text
    document.body.appendChild(input)
    input.select()
    document.execCommand('copy')
    document.body.removeChild(input)
    return true
  }
}

/** 下载文本文件（用于导出日志等） */
export function downloadText(filename, content) {
  const blob = new Blob([content], { type: 'text/plain;charset=utf-8' })
  const link = document.createElement('a')
  link.href = URL.createObjectURL(blob)
  link.download = filename
  link.click()
  URL.revokeObjectURL(link.href)
}

export default {
  formatTime,
  fromNow,
  formatSize,
  statusTagType,
  isNoticeAcknowledged,
  acknowledgeNotice,
  copyText,
  downloadText
}
