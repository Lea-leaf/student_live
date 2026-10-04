<script setup>
/**
 * 统一发布 / 编辑信息页。
 *
 * 设计约定（v1.3）：
 * - 所有模块共用同一个发布页：页面标题固定「发布信息 / 编辑信息」；
 * - 用户通过「选择发布类型」下拉自由切换模块，不再依赖 URL 里的 ?type=；
 * - 通用字段：标题、描述、图片视频、地点、时间(happened_at)、联系方式；
 * - 模块专属字段来自 config/moduleForms.js，提交时写入 posts.ext_json；
 * - 切换模块：保留通用字段；清空时间与上一模块的专属字段；切回来不恢复，需重新填。
 *
 * 上传策略：选择文件后用 `POST /lost_found/posts/upload` 先传，拿到 url 再随表单提交。
 */
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus } from '@element-plus/icons-vue'

import lostFoundApi from '@/api/lostFound'
import { useAppStore } from '@/stores/app'
import { useUserStore } from '@/stores/user'
import { formatSize } from '@/utils'
import {
  buildExtPayload,
  createEmptyExt,
  getModuleForm,
  validateExtForm
} from '@/config/moduleForms'

const route = useRoute()
const router = useRouter()
const appStore = useAppStore()
const userStore = useUserStore()

const LAST_PUBLISH_TYPE_KEY = 'slp_last_publish_type'
const LAST_CONTACT_KEY = 'slp_last_contact'

const formRef = ref(null)
const submitting = ref(false)
const uploading = ref(false)
const uploadPercent = ref(0)
const mediaList = ref([])

const isEdit = computed(() => !!route.params.id)
const postId = computed(() => Number(route.params.id))

/** 通用字段；模块专属字段放 extForm */
const form = reactive({
  type: 'lost_found',
  title: '',
  content: '',
  location: '',
  happened_at: '',
  contact: ''
})
const extForm = reactive({})

/** 当前模块表单配置：未知模块自动回落到 default */
const activeForm = computed(() => getModuleForm(form.type))
const activeExtFields = computed(() => activeForm.value.extFields || [])

/** 已启用模块列表；编辑旧帖子时，即使模块已被停用也补进选项，避免下拉空白 */
const moduleOptions = computed(() => {
  const list = [...(appStore.modules || [])]
  if (form.type && !list.some((item) => item.code === form.type)) {
    list.push({ code: form.type, name: appStore.moduleName(form.type) || form.type })
  }
  return list
})

/** 记住上次发布选择的模块；没有记录或模块被停用时回落到 lost_found */
function resolveDefaultType() {
  const codes = (appStore.modules || []).map((item) => item.code)
  const remembered = localStorage.getItem(LAST_PUBLISH_TYPE_KEY)
  if (remembered && codes.includes(remembered)) return remembered
  if (codes.includes('lost_found')) return 'lost_found'
  return codes[0] || 'lost_found'
}

/** 清空并重建模块专属字段；ext 传入时用于编辑回填 */
function resetExtForm(ext = null) {
  Object.keys(extForm).forEach((key) => { delete extForm[key] })
  Object.assign(extForm, createEmptyExt(form.type))
  if (ext && typeof ext === 'object') {
    for (const field of activeExtFields.value) {
      if (ext[field.key] !== undefined && ext[field.key] !== null) {
        extForm[field.key] = ext[field.key]
      }
    }
  }
}

/** 切换模块：通用字段保留；时间与模块专属字段清空，切回来不恢复 */
function onTypeChange() {
  resetExtForm()
  form.happened_at = ''
  if (!isEdit.value) {
    localStorage.setItem(LAST_PUBLISH_TYPE_KEY, form.type)
  }
}

const rules = {
  contact: [
    { required: true, message: '联系方式必填（将公开展示）', trigger: 'blur' },
    { min: 2, max: 64, message: '长度 2-64 个字符', trigger: 'blur' }
  ],
  title: [{ max: 60, message: '标题不超过 60 个字', trigger: 'blur' }],
  content: [{ max: 2000, message: '描述不超过 2000 个字', trigger: 'blur' }]
}

const auditEnabled = computed(() => {
  const value = appStore.config.post_audit_enabled
  return value === true || String(value) === '1'
})

const imageLimit = computed(() => Number(appStore.config.upload_max_mb_image || 10))
const videoLimit = computed(() => Number(appStore.config.upload_max_mb_video || 50))

onMounted(async () => {
  if (isEdit.value) {
    await loadPost()
    return
  }
  form.type = resolveDefaultType()
  resetExtForm()
  form.contact = localStorage.getItem(LAST_CONTACT_KEY) || ''
})

// appStore.modules 异步加载完成或后台模块变动时，确保当前选择仍然有效
watch(moduleOptions, (list) => {
  if (isEdit.value || !list.length) return
  if (!list.some((item) => item.code === form.type)) {
    form.type = resolveDefaultType()
    resetExtForm()
  }
})

async function loadPost() {
  try {
    const data = await lostFoundApi.detail(postId.value)
    form.title = data.title || ''
    form.content = data.content || ''
    form.location = data.location || ''
    form.happened_at = data.happened_at || ''
    form.contact = data.contact || ''
    form.type = data.type || 'lost_found'
    resetExtForm(data.ext || {})
    mediaList.value = data.media || []
  } catch (error) {
    ElMessage.error('加载失败，可能无权编辑该信息')
    router.back()
  }
}

/** 选择文件  立即上传 */
async function onFileChange(uploadFile) {
  const raw = uploadFile.raw
  if (!raw) return
  const isVideo = (raw.type || '').startsWith('video')
  const maxMb = isVideo ? videoLimit.value : imageLimit.value
  if (raw.size > maxMb * 1024 * 1024) {
    ElMessage.error(`文件超过大小限制（${maxMb}MB），当前 ${formatSize(raw.size)}`)
    return
  }
  uploading.value = true
  uploadPercent.value = 0
  try {
    const data = await lostFoundApi.upload([raw], (percent) => {
      uploadPercent.value = percent
    })
    mediaList.value = mediaList.value.concat(data.media || [])
    if (data.errors && data.errors.length) {
      ElMessage.warning(data.errors.join('；'))
    } else {
      ElMessage.success('上传成功')
    }
  } catch (error) {
    // 拦截器已提示
  } finally {
    uploading.value = false
  }
}

function removeMedia(index) {
  mediaList.value.splice(index, 1)
}

/** 发布前的安全公告确认（需求 4.3） */
async function confirmSecurityNotice() {
  const identity = userStore.studentId || 'guest'
  const key = 'slp_security_notice_ack'
  const raw = localStorage.getItem(key)
  if (raw) {
    try {
      if (JSON.parse(raw).identity === identity) return true
    } catch (error) {
      // 忽略解析失败，继续弹窗
    }
  }
  try {
    await ElMessageBox.confirm(
      appStore.config.security_notice_text ||
        '不要上传身份证、银行卡、家庭住址等敏感隐私信息；管理员可查看所有发布内容；联系方式公开可见。',
      '安全公告',
      { confirmButtonText: '我已了解并继续', showCancelButton: true, type: 'warning' }
    )
    localStorage.setItem(key, JSON.stringify({ identity, at: Date.now() }))
    return true
  } catch (error) {
    return false
  }
}

async function onSubmit() {
  if (formRef.value) {
    const valid = await formRef.value.validate().catch(() => false)
    if (!valid) return
  }

  // 模块专属字段：数值类型 / 必填项统一在前端先校验一次
  const extError = validateExtForm(form.type, extForm)
  if (extError) {
    ElMessage.error(extError)
    return
  }

  // 时间是否必填由模块配置决定（如二手交易：交易时间必填）
  const timeConfig = activeForm.value.time || {}
  if (timeConfig.required && !form.happened_at) {
    ElMessage.error(`请选择${timeConfig.label || '时间'}`)
    return
  }

  const confirmed = await confirmSecurityNotice()
  if (!confirmed) return

  submitting.value = true
  try {
    const payload = {
      type: form.type,
      title: form.title,
      content: form.content,
      location: form.location,
      happened_at: form.happened_at || null,
      contact: form.contact,
      media: mediaList.value,
      ext: buildExtPayload(form.type, extForm)
    }

    if (isEdit.value) {
      await lostFoundApi.update(postId.value, payload)
      ElMessage.success('修改成功')
      router.push({ name: 'post-detail', params: { id: postId.value } })
      return
    }

    const data = await lostFoundApi.create(payload)
    localStorage.setItem(LAST_CONTACT_KEY, form.contact)
    localStorage.setItem(LAST_PUBLISH_TYPE_KEY, form.type)
    ElMessage.success(data.audit_status === 'approved' ? '发布成功' : '发布成功，等待管理员审核后公开')
    router.push({ name: 'my-posts' })
  } catch (error) {
    // 拦截器已提示
  } finally {
    submitting.value = false
  }
}

function onReset() {
  form.title = ''
  form.content = ''
  form.location = ''
  form.happened_at = ''
  form.contact = localStorage.getItem(LAST_CONTACT_KEY) || ''
  if (!isEdit.value) {
    form.type = resolveDefaultType()
  }
  resetExtForm()
  mediaList.value = []
  formRef.value?.clearValidate()
}
</script>

<template>
  <div class="slp-container slp-page">
    <div class="slp-card">
      <h2 class="slp-mb-8">{{ isEdit ? '编辑信息' : '发布信息' }}</h2>
      <p class="slp-text-sub">
        {{ auditEnabled ? '发布后需管理员审核通过才会公开显示。' : '当前平台已关闭发帖审核，发布后立即公开。' }}
        {{ activeForm.formHint }}
      </p>

      <el-form
        ref="formRef"
        class="slp-mt-16"
        :model="form"
        :rules="rules"
        label-width="90px"
        label-position="top"
      >
        <el-form-item label="选择发布类型">
          <el-select
            v-model="form.type"
            :disabled="isEdit"
            style="width: 260px"
            @change="onTypeChange"
          >
            <el-option
              v-for="item in moduleOptions"
              :key="item.code"
              :label="item.name"
              :value="item.code"
            />
          </el-select>
          <span class="slp-text-sub">不同模块的字段和状态文案会不同</span>
        </el-form-item>

        <el-form-item :label="activeForm.titleLabel" prop="title">
          <el-input
            v-model="form.title"
            maxlength="60"
            show-word-limit
            :placeholder="activeForm.titlePlaceholder"
          />
        </el-form-item>

        <el-form-item :label="activeForm.contentLabel" prop="content">
          <el-input
            v-model="form.content"
            type="textarea"
            :rows="5"
            maxlength="2000"
            show-word-limit
            :placeholder="activeForm.contentPlaceholder"
          />
        </el-form-item>

        <el-form-item :label="activeForm.locationLabel">
          <el-input
            v-model="form.location"
            maxlength="60"
            :placeholder="activeForm.locationPlaceholder"
          />
        </el-form-item>

        <el-form-item :label="activeForm.time.label" :required="activeForm.time.required">
          <el-date-picker
            v-model="form.happened_at"
            type="datetime"
            :placeholder="activeForm.time.placeholder"
            value-format="YYYY-MM-DD HH:mm:ss"
            style="width: 100%"
          />
        </el-form-item>

        <!-- 模块专属字段：由 moduleForms.js 配置驱动 -->
        <el-form-item
          v-for="field in activeExtFields"
          :key="field.key"
          :label="field.label"
          :required="field.required"
        >
          <el-input-number
            v-if="field.component === 'number'"
            v-model="extForm[field.key]"
            v-bind="field.props || {}"
            :placeholder="field.placeholder"
            style="width: 200px"
          />
          <el-select
            v-else-if="field.component === 'select'"
            v-model="extForm[field.key]"
            :placeholder="field.placeholder || '请选择'"
            style="width: 200px"
          >
            <el-option
              v-for="option in field.options || []"
              :key="option.value"
              :label="option.label"
              :value="option.value"
            />
          </el-select>
          <el-input
            v-else
            v-model="extForm[field.key]"
            :placeholder="field.placeholder || ''"
            style="max-width: 360px"
          />
          <span v-if="field.hint" class="slp-text-sub">{{ field.hint }}</span>
        </el-form-item>

        <el-form-item label="联系方式（必填，公开可见）" prop="contact">
          <el-input v-model="form.contact" maxlength="64" placeholder="例如：微信 xiaoming2021 / QQ 12345678" />
          <span class="slp-text-sub">该联系方式会公开展示，建议只留常用社交账号，请勿填写身份证等敏感信息。</span>
        </el-form-item>

        <el-form-item :label="activeForm.mediaLabel">
          <div class="upload-area">
            <div v-for="(item, index) in mediaList" :key="item.url" class="upload-item">
              <video v-if="item.type === 'video'" :src="item.url" />
              <img v-else :src="item.url" alt="已上传" />
              <el-button class="upload-item__remove" size="small" type="danger" circle @click="removeMedia(index)">
                
              </el-button>
            </div>

            <el-upload
              :show-file-list="false"
              :auto-upload="false"
              accept="image/*,video/*"
              :on-change="onFileChange"
            >
              <div class="upload-trigger" v-loading="uploading">
                <el-icon :size="22"><Plus /></el-icon>
                <span>添加文件</span>
              </div>
            </el-upload>
          </div>
          <span class="slp-text-sub">
            支持图片（{{ imageLimit }}MB）与视频（{{ videoLimit }}MB）；请勿上传身份证、银行卡等敏感内容。
            <template v-if="uploading"> 上传中 {{ uploadPercent }}%</template>
          </span>
        </el-form-item>

        <el-form-item>
          <el-button type="primary" :loading="submitting" @click="onSubmit">
            {{ isEdit ? '保存修改' : '确认发布' }}
          </el-button>
          <el-button @click="onReset">重置</el-button>
          <el-button text @click="router.back()">取消</el-button>
        </el-form-item>
      </el-form>
    </div>
  </div>
</template>

<style scoped>
.upload-area {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.upload-item {
  position: relative;
  width: 100px;
  height: 100px;
}

.upload-item img,
.upload-item video {
  width: 100%;
  height: 100%;
  object-fit: cover;
  border-radius: 8px;
  border: 1px solid #ebeef5;
}

.upload-item__remove {
  position: absolute;
  top: -8px;
  right: -8px;
}

.upload-trigger {
  width: 100px;
  height: 100px;
  border: 1px dashed #dcdfe6;
  border-radius: 8px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 4px;
  color: #909399;
  cursor: pointer;
  font-size: 12px;
}

.upload-trigger:hover {
  border-color: var(--slp-primary);
  color: var(--slp-primary);
}
</style>