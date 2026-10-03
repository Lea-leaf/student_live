<script setup>
/**
 * 语音录制组件（浏览器 MediaRecorder）。
 *
 * 交互：点击「语音」请求麦克风权限并开始录音，再次点击停止；
 * 停止后生成 File 通过 `recorded` 事件交给父组件上传（/common/upload）。
 * 默认最长 60 秒，避免录出超大文件（语音上传上限 5MB）。
 */
import { onUnmounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Microphone, VideoPause } from '@element-plus/icons-vue'

const props = defineProps({
  maxSeconds: { type: Number, default: 60 },
  disabled: { type: Boolean, default: false }
})

const emit = defineEmits(['recorded'])

const recording = ref(false)
const seconds = ref(0)
let mediaRecorder = null
let stream = null
let chunks = []
let tickTimer = null

function pickMimeType() {
  const candidates = [
    'audio/webm;codecs=opus',
    'audio/webm',
    'audio/ogg;codecs=opus',
    'audio/mp4'
  ]
  if (typeof MediaRecorder === 'undefined' || !MediaRecorder.isTypeSupported) return ''
  return candidates.find((item) => MediaRecorder.isTypeSupported(item)) || ''
}

function extensionOf(mime) {
  const type = String(mime || '').toLowerCase()
  if (type.includes('mp4')) return 'm4a'
  if (type.includes('ogg')) return 'ogg'
  if (type.includes('wav')) return 'wav'
  return 'webm'
}

function cleanup() {
  if (tickTimer) {
    clearInterval(tickTimer)
    tickTimer = null
  }
  if (stream) {
    stream.getTracks().forEach((track) => track.stop())
    stream = null
  }
  mediaRecorder = null
  chunks = []
}

async function start() {
  if (props.disabled || recording.value) return
  if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === 'undefined') {
    ElMessage.warning('当前浏览器不支持录音，请改用文字或图片')
    return
  }
  try {
    stream = await navigator.mediaDevices.getUserMedia({ audio: true })
  } catch (error) {
    ElMessage.warning('无法访问麦克风，请检查浏览器权限设置')
    return
  }

  const mimeType = pickMimeType()
  chunks = []
  try {
    mediaRecorder = mimeType
      ? new MediaRecorder(stream, { mimeType })
      : new MediaRecorder(stream)
  } catch (error) {
    ElMessage.warning('当前浏览器不支持该录音格式')
    cleanup()
    return
  }

  mediaRecorder.ondataavailable = (event) => {
    if (event.data && event.data.size) chunks.push(event.data)
  }
  mediaRecorder.onstop = () => {
    const type = mediaRecorder?.mimeType || mimeType || 'audio/webm'
    const blob = new Blob(chunks, { type })
    if (blob.size) {
      emit('recorded', new File([blob], `voice-${Date.now()}.${extensionOf(type)}`, { type }))
    }
    recording.value = false
    cleanup()
  }

  try {
    mediaRecorder.start()
  } catch (error) {
    ElMessage.warning('录音启动失败，请重试')
    cleanup()
    return
  }
  recording.value = true
  seconds.value = 0
  tickTimer = setInterval(() => {
    seconds.value += 1
    if (seconds.value >= props.maxSeconds) stop()
  }, 1000)
}

function stop() {
  if (!recording.value) return
  recording.value = false
  try {
    mediaRecorder?.stop()
  } catch (error) {
    cleanup()
  }
}

onUnmounted(() => {
  if (mediaRecorder && recording.value) {
    try {
      mediaRecorder.stop()
    } catch (error) {
      // 忽略卸载时的录音异常
    }
  }
  cleanup()
})
</script>

<template>
  <el-button
    v-if="!recording"
    size="small"
    :icon="Microphone"
    :disabled="disabled"
    @click="start"
  >
    语音
  </el-button>
  <el-button v-else type="danger" size="small" :icon="VideoPause" @click="stop">
    停止 {{ seconds }}s
  </el-button>
</template>