/** 公共接口（字典、模块、配置、上传、健康检查） */
import request, { upload } from './request'
import { API } from './index'

export const commonApi = {
  /** 枚举字典（状态/角色等） */
  enums: () => request.get(API.common.enums),

  /** 启用中的模块列表 */
  modules: () => request.get(API.common.modules),

  /** 公开配置 */
  configs: () => request.get(API.common.configs),

  /** 健康检查 */
  health: () => request.get(API.common.health),

  /** 通用上传 */
  upload: (files, onProgress) => upload(API.common.upload, files, {}, onProgress)
}

export default commonApi
