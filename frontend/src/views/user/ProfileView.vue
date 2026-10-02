<script setup>
/**
 * 个人中心：资料修改 + 修改密码 + 账号信息。
 */
import { computed, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'

import authApi from '@/api/auth'
import { useUserStore } from '@/stores/user'

const router = useRouter()
const userStore = useUserStore()

const profileRef = ref(null)
const passwordRef = ref(null)
const savingProfile = ref(false)
const savingPassword = ref(false)

const profileForm = reactive({
  nickname: userStore.user?.nickname || '',
  avatar: userStore.user?.avatar || ''
})

const passwordForm = reactive({
  old_password: '',
  new_password: '',
  confirm_password: ''
})

const profileRules = {
  nickname: [
    { required: true, message: '请输入昵称', trigger: 'blur' },
    { pattern: /^[A-Za-z0-9_\u4e00-\u9fa5]{2,20}$/, message: '昵称 2-20 位中文、字母或数字', trigger: 'blur' }
  ]
}

const passwordRules = {
  old_password: [{ required: true, message: '请输入原密码', trigger: 'blur' }],
  new_password: [
    { required: true, message: '请输入新密码', trigger: 'blur' },
    { min: 6, max: 64, message: '密码长度 6-64 位', trigger: 'blur' }
  ],
  confirm_password: [
    { required: true, message: '请再次输入新密码', trigger: 'blur' },
    {
      validator: (rule, value, callback) => {
        if (value !== passwordForm.new_password) callback(new Error('两次输入的密码不一致'))
        else callback()
      },
      trigger: 'blur'
    }
  ]
}

const user = computed(() => userStore.user || {})

async function saveProfile() {
  const valid = await profileRef.value?.validate().catch(() => false)
  if (!valid) return
  savingProfile.value = true
  try {
    await userStore.updateProfile({ ...profileForm })
    ElMessage.success('资料已更新')
  } catch (error) {
    // 拦截器已提示
  } finally {
    savingProfile.value = false
  }
}

async function savePassword() {
  const valid = await passwordRef.value?.validate().catch(() => false)
  if (!valid) return
  savingPassword.value = true
  try {
    await authApi.changePassword({
      old_password: passwordForm.old_password,
      new_password: passwordForm.new_password
    })
    ElMessage.success('密码已修改，请重新登录')
    await userStore.logout()
    router.push({ name: 'login' })
  } catch (error) {
    // 拦截器已提示
  } finally {
    savingPassword.value = false
  }
}
</script>

<template>
  <div class="slp-container slp-page">
    <el-row :gutter="16">
      <el-col :xs="24" :md="8">
        <div class="slp-card" style="text-align: center">
          <el-avatar :size="72" :src="user.avatar">
            {{ (user.display_name || '?').slice(0, 1) }}
          </el-avatar>
          <h3 class="slp-mt-8">{{ user.display_name }}</h3>
          <p class="slp-text-sub">学号：{{ user.student_id }}</p>
          <el-tag :type="user.is_admin ? 'danger' : 'info'">{{ user.role_label }}</el-tag>
          <el-descriptions class="slp-mt-16" :column="1" border size="small">
            <el-descriptions-item label="账号状态">
              <el-tag :type="user.status === 'active' ? 'success' : 'danger'" size="small">
                {{ user.status_label }}
              </el-tag>
            </el-descriptions-item>
            <el-descriptions-item label="注册时间">{{ user.created_at || '-' }}</el-descriptions-item>
            <el-descriptions-item label="最后登录">{{ user.last_login_at || '-' }}</el-descriptions-item>
            <el-descriptions-item label="登录次数">{{ user.login_count || 0 }}</el-descriptions-item>
            <el-descriptions-item label="发布数量">{{ user.post_count || 0 }}</el-descriptions-item>
          </el-descriptions>

          <el-button
            v-if="user.is_admin"
            class="slp-mt-16"
            type="primary"
            plain
            style="width: 100%"
            @click="router.push({ name: 'admin-dashboard' })"
          >
            进入管理后台
          </el-button>
        </div>
      </el-col>

      <el-col :xs="24" :md="16">
        <div class="slp-card">
          <h3 class="slp-mb-16">修改资料</h3>
          <el-form ref="profileRef" :model="profileForm" :rules="profileRules" label-width="90px">
            <el-form-item label="昵称" prop="nickname">
              <el-input v-model="profileForm.nickname" maxlength="20" />
            </el-form-item>
            <el-form-item label="头像地址">
              <el-input v-model="profileForm.avatar" placeholder="可填写图片 URL（也可先上传再复制地址）" />
            </el-form-item>
            <el-form-item>
              <el-button type="primary" :loading="savingProfile" @click="saveProfile">保存资料</el-button>
            </el-form-item>
          </el-form>
        </div>

        <div class="slp-card">
          <h3 class="slp-mb-16">修改密码</h3>
          <el-form ref="passwordRef" :model="passwordForm" :rules="passwordRules" label-width="90px">
            <el-form-item label="原密码" prop="old_password">
              <el-input v-model="passwordForm.old_password" type="password" show-password />
            </el-form-item>
            <el-form-item label="新密码" prop="new_password">
              <el-input v-model="passwordForm.new_password" type="password" show-password />
            </el-form-item>
            <el-form-item label="确认密码" prop="confirm_password">
              <el-input v-model="passwordForm.confirm_password" type="password" show-password />
            </el-form-item>
            <el-form-item>
              <el-button type="primary" :loading="savingPassword" @click="savePassword">修改密码</el-button>
            </el-form-item>
          </el-form>
        </div>
      </el-col>
    </el-row>
  </div>
</template>
