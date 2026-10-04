/**
 * 模块发布表单配置（前端唯一来源）。
 *
 * 设计约定：
 * - 所有模块共用「标题 / 描述 / 图片视频 / 地点 / 时间 / 联系方式」这些通用字段；
 * - 模块专属字段放 `extFields`，提交时进入 `posts.ext_json`；
 * - 未登记的模块自动使用 `default`（只显示通用字段，ext 为空对象）；
 * - 后端 `posts_service.validate_module_ext()` 会再做一次权威校验；
 *   这里的 `required` / `min` 等只用于前端交互提示，不能替代后端校验。
 *
 * 新增模块时只需要：
 *   1. 在 MODULE_FORMS 里加一段 config；
 *   2. 在后端 validate_module_ext 里加对应校验（如需强制规则）；
 *   3. 在 backend default_modules / 后台模块管理里启用该 type。
 */

const CONDITION_OPTIONS = [
  { label: '全新', value: '全新' },
  { label: '九成新', value: '九成新' },
  { label: '八成新', value: '八成新' },
  { label: '有使用痕迹', value: '有使用痕迹' }
]

const TRADE_TYPE_OPTIONS = [
  { label: '面交', value: '面交' },
  { label: '快递', value: '快递' },
  { label: '都可以', value: '都可以' }
]

/** 通用字段默认文案（失物招领 / 未登记模块共用） */
const COMMON_FIELDS = {
  formHint: '除联系方式外，其余字段都可以留空。',
  titleLabel: '标题（选填）',
  titlePlaceholder: '例如：在图书馆丢了一把黑色雨伞',
  contentLabel: '描述（选填）',
  contentPlaceholder: '补充物品特征、丢失/捡到的经过等，便于核对',
  locationLabel: '地点（选填）',
  locationPlaceholder: '例如：图书馆三楼 / 二食堂二楼',
  mediaLabel: '图片 / 视频（选填）',
  time: {
    label: '时间（选填）',
    placeholder: '选择时间',
    required: false
  },
  extFields: []
}

export const MODULE_FORMS = {
  lost_found: {
    ...COMMON_FIELDS,
    time: {
      label: '时间（选填）',
      placeholder: '选择丢失或拾取的时间',
      required: false
    }
  },

  second_hand: {
    formHint: '二手交易需填写价格、交易时间与联系方式；商品名称和描述建议写清楚。',
    titleLabel: '商品名称',
    titlePlaceholder: '例如：九成新山地自行车',
    contentLabel: '商品描述',
    contentPlaceholder: '成色、购买时间、瑕疵、配件等，写得越清楚越容易卖出',
    locationLabel: '交易地点',
    locationPlaceholder: '例如：6 号宿舍楼下 / 地铁站 A 口',
    mediaLabel: '商品图片 / 视频（选填）',
    time: {
      label: '交易时间',
      placeholder: '选择交易的时间',
      required: true
    },
    extFields: [
      {
        key: 'price',
        label: '价格（元，必填）',
        component: 'number',
        required: true,
        props: { min: 0, precision: 2, step: 1 },
        placeholder: '请输入价格'
      },
      {
        key: 'original_price',
        label: '原价（选填）',
        component: 'number',
        props: { min: 0, precision: 2, step: 1 },
        placeholder: '请输入原价'
      },
      {
        key: 'condition',
        label: '成色',
        component: 'select',
        placeholder: '请选择成色',
        options: CONDITION_OPTIONS
      },
      {
        key: 'trade_type',
        label: '交易方式',
        component: 'select',
        placeholder: '请选择交易方式',
        options: TRADE_TYPE_OPTIONS
      }
    ]
  },

  default: { ...COMMON_FIELDS }
}

/** 未知模块回落到 default，避免页面因缺少配置而报错 */
export function getModuleForm(moduleCode) {
  return MODULE_FORMS[moduleCode] || MODULE_FORMS.default
}

/** 为某个模块生成专属字段的空表单 */
export function createEmptyExt(moduleCode) {
  const result = {}
  for (const field of getModuleForm(moduleCode).extFields || []) {
    if (field.component === 'number') {
      result[field.key] = field.default !== undefined ? field.default : null
    } else {
      result[field.key] = field.default !== undefined ? field.default : ''
    }
  }
  return result
}

/**
 * 把前端表单值整理成后端 ext_json。
 * - number 空值统一转 null；
 * - select / text 去首尾空格；
 * - 不做业务必填校验（validateExtForm 负责）。
 */
export function buildExtPayload(moduleCode, values) {
  const result = {}
  for (const field of getModuleForm(moduleCode).extFields || []) {
    const raw = values?.[field.key]
    if (raw === undefined || raw === null || raw === '') {
      result[field.key] = null
      continue
    }

    if (field.component === 'number') {
      const num = Number(raw)
      result[field.key] = Number.isNaN(num) ? null : num
    } else {
      result[field.key] = String(raw).trim()
    }
  }
  return result
}

/** 前端校验模块专属字段，返回错误文案；空字符串表示通过 */
export function validateExtForm(moduleCode, values) {
  for (const field of getModuleForm(moduleCode).extFields || []) {
    const value = values?.[field.key]
    if (field.required && (value === undefined || value === null || value === '')) {
      return `${field.label.replace(/（.*?）/, '')}不能为空`
    }
    if (field.component === 'number' && value !== undefined && value !== null && value !== '') {
      const num = Number(value)
      if (Number.isNaN(num)) {
        return `${field.label}必须是数字`
      }
      const min = field.props?.min
      if (min !== undefined && num < min) {
        return `${field.label}不能小于 ${min}`
      }
    }
  }
  return ''
}

export default MODULE_FORMS