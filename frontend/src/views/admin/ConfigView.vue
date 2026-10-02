<script setup>
/**
 * 管理端 - 系统配置。
 * 需求：「不要一次性写死，留好配置项」。
 * 这里的开关会立即影响后端行为（审核、验证码、游客权限、回收站条数、上传限制等）。
 */
import { computed, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'

import adminApi from '@/api/admin'
import { useAppStore } from '@/stores/app'

const appStore = useAppStore()

const loading = ref(false)
const saving = ref(false)
const grouped = ref({})
const draft = ref({})

/** 分组中文名 */
const groupNames = {
  common: '通用设置',
  security: '安全公告',
  audit: '审核与注册',
  guest: '游客权限',
  recycle: '回收站',
  upload: '上传限制'
}

/** 需要多行输入 / 开关渲染的配置项 */
const textareaKeys = ['security_notice_text', 'site_notice']
const switchKeys = [
  'security_notice_enabled', 'post_audit_enabled', 'register_captcha_enabled',
  'guest_can_list', 'guest_can_detail'
]

const groupKeys = computed(() => Object.keys(grouped.value))

onMounted(load)

async function load() {
  loading.value = true
  try {
    const data = await adminApi.configs.list()
    grouped.value = data.grouped || {}
    const d = {}
    ;(data.list || []).forEach((item) => {
      d[item.key] = switchKeys.includes(item.key)
        ? ['1', 'true', 'True', true].includes(item.value)
        : item.value
    })
    draft.value = d
  } catch (error) {
    grouped.value = {}
  } finally {
    loading.value = false
  }
}

function isSwitch(key) {
  return switchKeys.includes(key)
}

function isTextarea(key) {
  return textareaKeys.includes(key)
}

function isNumber(key) {
  const item = findItem(key)
  return item && item.value_type === 'int'
}

function findItem(key) {
  for (const rows of Object.values(grouped.value)) {
    const hit = rows.find((item) => item.key === key)
    if (hit) return hit
  }
  return null
}

/** 保存单个分组 */
async function saveGroup(group) {
  const rows = grouped.value[group] || []
  const items = rows.map((item) => ({
    key: item.key,
    value: isSwitch(item.key) ? (draft.value[item.key] ? '1' : '0') : draft.value[item.key]
  }))
  saving.value = true
  try {
    await adminApi.configs.update(items)
    await appStore.loadPublicConfig()
    ElMessage.success(`${groupNames[group] || group} 已保存`)
    load()
  } catch (error) {
    // 拦截器已提示
  } finally {
    saving.value = false
  }
}

async function resetAll() {
  try {
    await ElMessageBox.confirm('确认把所有配置恢复为默认值吗？', '恢复默认', { type: 'warning' })
    await adminApi.configs.reset()
    await appStore.loadPublicConfig()
    ElMessage.success('已恢复默认配置')
    load()
  } catch (error) {
    // 取消
  }
}
</script>

<template>
  <div v-loading="loading">
    <div class="slp-card">
      <div class="slp-flex-between">
        <div>
          <h3>系统配置</h3>
          <p class="slp-text-sub">
            配置保存在 system_configs 表，优先级高于代码默认值；保存后立即生效（缓存会自动失效）。
          </p>
        </div>
        <div class="slp-toolbar">
          <el-button @click="load">刷新</el-button>
          <el-button type="warning" plain @click="resetAll">恢复默认</el-button>
        </div>
      </div>
    </div>

    <div v-for="group in groupKeys" :key="group" class="slp-card">
      <div class="slp-flex-between slp-mb-16">
        <h4 style="margin: 0">{{ groupNames[group] || group }}</h4>
        <el-button type="primary" size="small" :loading="saving" @click="saveGroup(group)">
          保存本组
        </el-button>
      </div>

      <el-form label-width="200px" label-position="left">
        <el-form-item v-for="item in grouped[group]" :key="item.key" :label="item.title || item.key">
          <el-switch v-if="isSwitch(item.key)" v-model="draft[item.key]" />
          <el-input
            v-else-if="isTextarea(item.key)"
            v-model="draft[item.key]"
            type="textarea"
            :rows="4"
            style="max-width: 620px"
          />
          <el-input-number
            v-else-if="isNumber(item.key)"
            v-model="draft[item.key]"
            :min="0"
            :max="100000"
          />
          <el-input v-else v-model="draft[item.key]" style="max-width: 420px" />
          <div class="slp-text-sub">
            {{ item.description || '' }} <code>{{ item.key }}</code>
          </div>
        </el-form-item>
      </el-form>
    </div>

    <el-empty v-if="!loading && !groupKeys.length" description="没有配置项，请点击「恢复默认」或调用 /admin/configs/init" />
  </div>
</template>
