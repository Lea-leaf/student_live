/** 认证相关接口 */
import request from './request'
import { API } from './index'

export const authApi = {
  /** 获取图形验证码：返回 { captcha_id, image, svg, expires_in } */
  captcha: () => request.get(API.auth.captcha),

  /** 注册：{ student_id, password, confirm_password, nickname, captcha_id, captcha } */
  register: (data) => request.post(API.auth.register, data),

  /** 登录：{ student_id, password } → { user, access_token, refresh_token } */
  login: (data) => request.post(API.auth.login, data),

  /** 当前用户信息 */
  me: () => request.get(API.auth.me),

  /** 修改资料：{ nickname, avatar } */
  updateMe: (data) => request.put(API.auth.me, data),

  /** 修改密码：{ old_password, new_password } */
  changePassword: (data) => request.put(API.auth.password, data),

  /** 登出 */
  logout: () => request.post(API.auth.logout),

  /** 安全公告文案 */
  securityNotice: () => request.get(API.auth.securityNotice)
}

export default authApi
