/** 失物招领模块接口 */
import request, { upload } from './request'
import { API } from './index'

export const lostFoundApi = {
  /**
   * 帖子列表
   * @param {object} params { page, size, keyword, status, mine, all, sort }
   */
  list: (params) => request.get(API.lostFound.list, { params }),

  /** 帖子详情 */
  detail: (id) => request.get(API.lostFound.detail(id)),

  /**
   * 发布帖子（JSON 方式，媒体先通过 upload 上传）
   * @param {object} data { title, content, location, happened_at, contact, media }
   */
  create: (data) => request.post(API.lostFound.create, data),

  /**
   * 发布帖子（multipart，媒体随表单一起提交）
   * @param {object} data 表单字段
   * @param {File[]} files 文件
   */
  createWithFiles: (data, files, onProgress) =>
    upload(API.lostFound.create, files, data, onProgress),

  /** 单独上传图片/视频 */
  upload: (files, onProgress) => upload(API.lostFound.upload, files, {}, onProgress),

  /** 编辑帖子 */
  update: (id, data) => request.put(API.lostFound.update(id), data),

  /** 删除帖子（软删除进回收站） */
  remove: (id) => request.delete(API.lostFound.remove(id)),

  /** 我的发布 */
  myPosts: (params) => request.get(API.lostFound.myPosts, { params }),

  /** 拼单：修改目标人数 / 当前人数（仅单主，仅 group_buy） */
  updateCount: (id, data) => request.patch(API.lostFound.count(id), data),

  /** 更新状态：{ status, reason } */
  updateStatus: (id, data) => request.post(API.lostFound.status(id), data),

  /** 标记已认领 */
  claim: (id) => request.post(API.lostFound.claim(id)),

  /** 模块元信息（状态字典、字段要求；?type= 切换模块） */
  meta: (params) => request.get(API.lostFound.meta, { params })
}

export default lostFoundApi
