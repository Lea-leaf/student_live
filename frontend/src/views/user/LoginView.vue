<script setup>
/**
 * 登录页：学号（或用户名）+ 密码。
 * 登录成功后：管理员默认进后台，普通用户回到来源页或首页。
 */
import { computed, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Lock, User } from '@element-plus/icons-vue'

import { useAppStore } from '@/stores/app'
import { useUserStore } from '@/stores/user'

const route = useRoute()
const router = useRouter()
const userStore = useUserStore()
const appStore = useAppStore()

const formRef = ref(null)
const loading = ref(false)

const form = reactive({
  student_id: '',
  password: ''
})

const rules = {
  student_id: [{ required: true, message: '请输入学号或用户名', trigger: 'blur' }],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }]
}

const siteName = computed(() => appStore.siteName)

async function onSubmit() {
  if (formRef.value) {
    const valid = await formRef.value.validate().catch(() => false)
    if (!valid) return
  }
  loading.value = true
  try {
    const user = await userStore.login({ ...form })
    ElMessage.success(`欢迎回来，${user.display_name || user.student_id}`)
    const redirect = route.query.redirect ? String(route.query.redirect) : ''
    if (redirect) {
      router.replace(redirect)
    } else if (user.is_admin) {
      router.replace({ name: 'admin-dashboard' })
    } else {
      router.replace({ name: 'home' })
    }
  } catch (error) {
    // 错误提示已由 axios 拦截器统一处理
  } finally {
    loading.value = false
  }
}

/** 答辩演示用：一键填入测试账号 */
function fillDemo(role) {
  if (role === 'admin') {
    form.student_id = 'admin'
    form.password = 'admin123'
  } else {
    form.student_id = '20210001'
    form.password = '123456'
  }
}
</script>

<template>
  <div>
    <h2 class="login-title">登录 {{ siteName }}</h2>
    <p class="slp-text-sub slp-mb-16">使用学号登录，未注册请先注册账号</p>

    <el-form ref="formRef" :model="form" :rules="rules" label-position="top" @keyup.enter="onSubmit">
      <el-form-item label="学号 / 用户名" prop="student_id">
        <el-input v-model="form.student_id" placeholder="请输入学号" :prefix-icon="User" clearable />
      </el-form-item>
      <el-form-item label="密码" prop="password">
        <el-input
          v-model="form.password"
          type="password"
          placeholder="请输入密码"
          :prefix-icon="Lock"
          show-password
        />
      </el-form-item>
      <el-form-item>
        <el-button type="primary" :loading="loading" style="width: 100%" @click="onSubmit">
          登录
        </el-button>
      </el-form-item>
    </el-form>

    <div class="slp-flex-between">
      <router-link :to="{ name: 'register' }">还没有账号？去注册</router-link>
      <router-link :to="{ name: 'home' }">先随便看看</router-link>
    </div>

    <el-divider>演示账号</el-divider>
    <div class="demo-buttons">
      <el-button size="small" @click="fillDemo('user')">普通用户 20210001 / 123456</el-button>
      <el-button size="small" type="warning" plain @click="fillDemo('admin')">
        管理员 admin / admin123
      </el-button>
    </div>
  </div>
</template>

<style scoped>
.login-title {
  margin: 0 0 6px;
  font-size: 20px;
}

.demo-buttons {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.demo-buttons .el-button {
  margin-left: 0;
}
</style>
