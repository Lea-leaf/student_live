<script setup>
/**
 * 发布 / 编辑信息页（失物招领 P0）。
 *
 * 字段规则来自需求 6.1：
 *   标题、描述、图片视频、地点、时间 均为选填，联系方式必填且公开可见；
 *   发布后按平台配置进入审核（管理员发帖直通）。
 *
 * 上传策略：选择文件后用 `POST /lost_found/posts/upload` 先传，拿到 url 再随表单提交，
 * 这样编辑时可以自由增删已上传的媒体。
 */
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus } from '@element-plus/icons-vue'

import lostFoundApi from '@/api/lostFound'
import { useAppStore } from '@/stores/app'
import { useUserStore } from '@/stores/user'
import { formatSize } from '@/utils'

const route = useRoute()
const router = useRouter()
const appStore = useAppStore()
const userStore = useUserStore()

const formRef = ref(null)
const submitting = ref(false)
const uploading = ref(false)
const uploadPercent = ref(0)
const mediaList = ref([])

const isEdit = computed(() => !!route.params.id)
const postId = computed(() => Number(route.params.id))

const form = reactive({
  title: '',
  content: '',
  location: '',
  happened_at: '',
  contact: ''
})

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
  }
  // 预填联系方式（用上次填写的，减少重复输入）
  if (!isEdit.value) {
    form.contact = localStorage.getItem('slp_last_contact') || ''
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
    mediaList.value = data.media || []
  } catch (error) {
    ElMessage.error('加载失败，可能无权编辑该信息')
    router.back()
  }
}

/** 选择文件 → 立即上传 */
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
  const confirmed = await confirmSecurityNotice()
  if (!confirmed) return

  submitting.value = true
  try {
    const payload = {
      title: form.title,
      content: form.content,
      location: form.location,
      happened_at: form.happened_at || null,
      contact: form.contact,
      media: mediaList.value
    }
    if (isEdit.value) {
      await lostFoundApi.update(postId.value, payload)
      ElMessage.success('修改成功')
      router.push({ name: 'post-detail', params: { id: postId.value } })
    } else {
      const data = await lostFoundApi.create(payload)
      localStorage.setItem('slp_last_contact', form.contact)
      ElMessage.success(data.audit_status === 'approved' ? '发布成功' : '发布成功，等待管理员审核后公开')
      router.push({ name: 'my-posts' })
    }
  } catch (error) {
    // 拦截器已提示
  } finally {
    submitting.value = false
  }
}

function onReset() {
  formRef.value?.resetFields()
  mediaList.value = []
}
</script>

<template>
  <div class="slp-container slp-page">
    <div class="slp-card">
      <h2 class="slp-mb-8">{{ isEdit ? '编辑信息' : '发布信息' }}</h2>
      <p class="slp-text-sub">
        {{ auditEnabled ? '发布后需管理员审核通过才会公开显示。' : '当前平台已关闭发帖审核，发布后立即公开。' }}
        除联系方式外，其余字段都可以留空。
      </p>

      <el-form
        ref="formRef"
        class="slp-mt-16"
        :model="form"
        :rules="rules"
        label-width="90px"
        label-position="top"
      >
        <el-form-item label="标题（选填）" prop="title">
          <el-input v-model="form.title" maxlength="60" show-word-limit placeholder="例如：在图书馆丢了一把黑色雨伞" />
        </el-form-item>

        <el-form-item label="描述（选填）" prop="content">
          <el-input
            v-model="form.content"
            type="textarea"
            :rows="5"
            maxlength="2000"
            show-word-limit
            placeholder="补充物品特征、丢失/捡到的经过等，便于核对"
          />
        </el-form-item>

        <el-form-item label="地点（选填）">
          <el-input v-model="form.location" maxlength="60" placeholder="例如：图书馆三楼 / 二食堂二楼" />
        </el-form-item>

        <el-form-item label="时间（选填）">
          <el-date-picker
            v-model="form.happened_at"
            type="datetime"
            placeholder="选择丢失或拾取的时间"
            value-format="YYYY-MM-DD HH:mm:ss"
            style="width: 100%"
          />
        </el-form-item>

        <el-form-item label="联系方式（必填，公开可见）" prop="contact">
          <el-input v-model="form.contact" maxlength="64" placeholder="例如：微信 xiaoming2021 / QQ 12345678" />
          <span class="slp-text-sub">该联系方式会公开展示，建议只留常用社交账号，请勿填写身份证等敏感信息。</span>
        </el-form-item>

        <el-form-item label="图片 / 视频（选填）">
          <div class="upload-area">
            <div v-for="(item, index) in mediaList" :key="item.url" class="upload-item">
              <video v-if="item.type === 'video'" :src="item.url" />
              <img v-else :src="item.url" alt="已上传" />
              <el-button class="upload-item__remove" size="small" type="danger" circle @click="removeMedia(index)">
                ×
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
            支持图片（≤{{ imageLimit }}MB）与视频（≤{{ videoLimit }}MB）；请勿上传身份证、银行卡等敏感内容。
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
