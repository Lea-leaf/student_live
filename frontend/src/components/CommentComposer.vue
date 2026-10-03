<script setup>
/**
 * 评论/私信通用输入框：文字 + 图片 + 语音。
 *
 * 图片与语音都先走 `/common/upload` 拿到后端 media 结构，再随文本提交；
 * 父组件在接口成功后调用 `reset()`，失败时内容不丢。
 */
import { computed, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Close, Picture } from '@element-plus/icons-vue'

import commonApi from '@/api/common'
import VoiceRecorder from '@/components/VoiceRecorder.vue'
import { useAppStore } from '@/stores/app'
import { formatSize } from '@/utils'

const props = defineProps({
  placeholder: { type: String, default: '说说你的看法' },
  buttonText: { type: String, default: '发表' },
  compact: { type: Boolean, default: false },
  disabled: { type: Boolean, default: false },
  loading: { type: Boolean, default: false },
  maxLength: { type: Number, default: 1000 }
})

const emit = defineEmits(['submit'])
const appStore = useAppStore()

const text = ref('')
const media = ref([])
const uploading = ref(false)
const uploadRef = ref(null)

const imageLimit = computed(() => Number(appStore.config.upload_max_mb_image || 10))
const audioLimit = computed(() => Number(appStore.config.upload_max_mb_audio || 5))
const canSubmit = computed(() => !props.disabled && !props.loading && !uploading.value
  && (text.value.trim().length > 0 || media.value.length > 0))

async function uploadMediaFile(file, limitMb, label) {
  if (file.size > limitMb * 1024 * 1024) {
    ElMessage.warning(`${label}超过大小限制（${limitMb}MB），当前 ${formatSize(file.size)}`)
    return
  }
  uploading.value = true
  try {
    const data = await commonApi.upload([file])
    media.value = media.value.concat(data.media || [])
    if (data.errors && data.errors.length) ElMessage.warning(data.errors.join('；'))
  } catch (error) {
    // 拦截器已提示
  } finally {
    uploading.value = false
  }
}

async function onImageChange(file) {
  const raw = file?.raw
  uploadRef.value?.clearFiles()
  if (raw) await uploadMediaFile(raw, imageLimit.value, '图片')
}

async function onVoiceRecorded(file) {
  await uploadMediaFile(file, audioLimit.value, '语音')
}

function removeMedia(index) {
  media.value.splice(index, 1)
}

function submit() {
  if (!canSubmit.value) return
  emit('submit', { content: text.value.trim(), media: media.value })
}

function reset() {
  text.value = ''
  media.value = []
  uploadRef.value?.clearFiles()
}

defineExpose({ reset })
</script>

<template>
  <div class="comment-composer" :class="{ 'is-compact': compact }">
    <el-input
      v-model="text"
      type="textarea"
      :rows="compact ? 2 : 3"
      :maxlength="maxLength"
      show-word-limit
      resize="none"
      :placeholder="placeholder"
      :disabled="disabled"
    />

    <div v-if="media.length" class="comment-composer__media">
      <div v-for="(item, index) in media" :key="item.id || item.url" class="comment-composer__media-item">
        <img v-if="item.type === 'image'" :src="item.url" alt="已上传图片" />
        <audio v-else :src="item.url" controls preload="none" />
        <el-button
          class="comment-composer__remove"
          size="small"
          type="danger"
          circle
          :icon="Close"
          @click="removeMedia(index)"
        />
      </div>
    </div>

    <div class="comment-composer__actions">
      <el-upload
        ref="uploadRef"
        :show-file-list="false"
        :auto-upload="false"
        accept="image/*"
        :on-change="onImageChange"
        :disabled="disabled || uploading"
      >
        <el-button size="small" :icon="Picture" :disabled="disabled || uploading">图片</el-button>
      </el-upload>

      <VoiceRecorder
        :max-seconds="60"
        :disabled="disabled || uploading"
        @recorded="onVoiceRecorded"
      />

      <span v-if="uploading" class="slp-text-sub">上传中</span>
      <div class="comment-composer__spacer" />
      <el-button
        type="primary"
        size="small"
        :loading="loading"
        :disabled="!canSubmit"
        @click="submit"
      >
        {{ buttonText }}
      </el-button>
    </div>
  </div>
</template>

<style scoped>
.comment-composer {
  border: 1px solid #ebeef5;
  border-radius: 8px;
  padding: 10px;
  background: #fff;
}

.comment-composer.is-compact {
  padding: 8px;
  background: #fafafa;
}

.comment-composer__media {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 8px;
}

.comment-composer__media-item {
  position: relative;
  max-width: 160px;
  height: 54px;
  display: flex;
  align-items: center;
}

.comment-composer__media-item img {
  width: 54px;
  height: 54px;
  object-fit: cover;
  border-radius: 6px;
  border: 1px solid #ebeef5;
}

.comment-composer__media-item audio {
  height: 40px;
}

.comment-composer__remove {
  position: absolute;
  top: -8px;
  right: -8px;
}

.comment-composer__actions {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 8px;
}

.comment-composer__spacer {
  flex: 1;
}
</style>