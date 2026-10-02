<script setup>
/**
 * 注册页：学号 + 验证码（图形验证码，可后台关闭）。
 * 验证码图片为后端生成的 SVG data URI，点击可刷新。
 */
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Lock, Picture, User } from '@element-plus/icons-vue'

import authApi from '@/api/auth'
import { useAppStore } from '@/stores/app'
import { useUserStore } from '@/stores/user'

const router = useRouter()
const appStore = useAppStore()
const userStore = useUserStore()

const formRef = ref(null)
const loading = ref(false)
const captchaLoading = ref(false)
const captcha = reactive({ id: '', image: '', debug: '' })

const form = reactive({
  student_id: '',
  nickname: '',
  password: '',
  confirm_password: '',
  captcha: ''
})

const captchaEnabled = computed(() => {
  const value = appStore.config.register_captcha_enabled
  return value === true || String(value) === '1'
})

const rules = computed(() => ({
  student_id: [
    { required: true, message: '请输入学号', trigger: 'blur' },
    { pattern: /^[A-Za-z0-9]{4,20}$/, message: '学号只能是 4-20 位字母或数字', trigger: 'blur' }
  ],
  nickname: [
    { pattern: /^[A-Za-z0-9_\u4e00-\u9fa5]{2,20}$/, message: '昵称 2-20 位中文、字母或数字', trigger: 'blur' }
  ],
  password: [
    { required: true, message: '请输入密码', trigger: 'blur' },
    { min: 6, max: 64, message: '密码长度 6-64 位', trigger: 'blur' }
  ],
  confirm_password: [
    { required: true, message: '请再次输入密码', trigger: 'blur' },
    {
      validator: (rule, value, callback) => {
        if (value !== form.password) callback(new Error('两次输入的密码不一致'))
        else callback()
      },
      trigger: 'blur'
    }
  ],
  captcha: captchaEnabled.value
    ? [{ required: true, message: '请输入验证码', trigger: 'blur' }]
    : []
}))

async function refreshCaptcha() {
  captchaLoading.value = true
  try {
    const data = await authApi.captcha()
    captcha.id = data.captcha_id
    captcha.image = data.image
    captcha.debug = data.debug_code || ''
    form.captcha = ''
  } catch (error) {
    // 拦截器已提示
  } finally {
    captchaLoading.value = false
  }
}

async function onSubmit() {
  if (formRef.value) {
    const valid = await formRef.value.validate().catch(() => false)
    if (!valid) return
  }
  loading.value = true
  try {
    await userStore.register({
      student_id: form.student_id,
      nickname: form.nickname || undefined,
      password: form.password,
      confirm_password: form.confirm_password,
      captcha_id: captcha.id,
      captcha: form.captcha
    })
    ElMessage.success('注册成功，已自动登录')
    router.replace({ name: 'home' })
  } catch (error) {
    // 验证码错误等：刷新验证码重试
    if (captchaEnabled.value) refreshCaptcha()
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  if (captchaEnabled.value) refreshCaptcha()
})
</script>

<template>
  <div>
    <h2 class="register-title">注册账号</h2>
    <p class="slp-text-sub slp-mb-16">仅限本校学生，使用学号注册</p>

    <el-form ref="formRef" :model="form" :rules="rules" label-position="top">
      <el-form-item label="学号" prop="student_id">
        <el-input v-model="form.student_id" placeholder="例如 20210001" :prefix-icon="User" clearable />
      </el-form-item>
      <el-form-item label="昵称（选填）" prop="nickname">
        <el-input v-model="form.nickname" placeholder="不填则默认使用学号" clearable />
      </el-form-item>
      <el-form-item label="密码" prop="password">
        <el-input v-model="form.password" type="password" :prefix-icon="Lock" show-password />
      </el-form-item>
      <el-form-item label="确认密码" prop="confirm_password">
        <el-input v-model="form.confirm_password" type="password" :prefix-icon="Lock" show-password />
      </el-form-item>

      <el-form-item v-if="captchaEnabled" label="验证码" prop="captcha">
        <div class="captcha-row">
          <el-input
            v-model="form.captcha"
            placeholder="输入右侧字符"
            :prefix-icon="Picture"
            maxlength="6"
          />
          <img
            v-if="captcha.image"
            :src="captcha.image"
            class="captcha-image"
            title="点击刷新验证码"
            alt="验证码"
            @click="refreshCaptcha"
          />
          <el-button v-else :loading="captchaLoading" @click="refreshCaptcha">获取验证码</el-button>
        </div>
        <span v-if="captcha.debug" class="slp-text-sub">开发环境验证码：{{ captcha.debug }}</span>
      </el-form-item>

      <el-form-item>
        <el-button type="primary" :loading="loading" style="width: 100%" @click="onSubmit">
          注册并登录
        </el-button>
      </el-form-item>
    </el-form>

    <div class="slp-flex-between">
      <router-link :to="{ name: 'login' }">已有账号？去登录</router-link>
      <router-link :to="{ name: 'home' }">返回首页</router-link>
    </div>
  </div>
</template>

<style scoped>
.register-title {
  margin: 0 0 6px;
  font-size: 20px;
}

.captcha-row {
  display: flex;
  gap: 10px;
  width: 100%;
  align-items: center;
}

.captcha-image {
  height: 40px;
  width: 120px;
  border: 1px solid #dcdfe6;
  border-radius: 4px;
  cursor: pointer;
  flex-shrink: 0;
}
</style>
