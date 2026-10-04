<script setup>
/**
 * 管理员移交对话框（系统只允许存在一个管理员）。
 *
 * 两阶段流程：
 *   ① 选定接任者 → 对方立刻成为管理员，但**冻结 24 小时**（期间用不了后台）
 *      自己仍是管理员、功能照常，随时可以撤销
 *   ② 24 小时到期后自动落地：自己变普通用户，对方解冻正式上任
 *
 * 时间口径：统一用**服务器返回的北京时间**校准倒计时，不依赖浏览器本机时钟
 * （本机时区/时间不准会导致倒计时与实际生效时间对不上）。
 */
import { computed, onUnmounted, reactive, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'

import adminApi from '@/api/admin'

const props = defineProps({
  modelValue: { type: Boolean, default: false }
})
const emit = defineEmits(['update:modelValue', 'finished'])

const loading = ref(false)
const submitting = ref(false)
const status = ref({ handover_pending: false })
const candidates = ref([])
const form = reactive({ user_id: null, reason: '' })
/** 服务器时间与本机时间的差值（毫秒）：本机时间 + 该差值 = 服务器北京时间 */
const clockSkew = ref(0)
const now = ref(Date.now())
let timer = null

const visible = computed({
  get: () => props.modelValue,
  set: (value) => emit('update:modelValue', value)
})

const isInitiator = computed(() => status.value.handover_role === 'initiator')
const isTarget = computed(() => status.value.handover_role === 'target')

/** 服务器视角的当前时间（北京时间） */
const serverNow = computed(() => new Date(now.value + clockSkew.value))

const deadline = computed(() => {
  const raw = status.value.handover_deadline
  if (!raw) return null
  // 后端返回 'YYYY-MM-DD HH:mm:ss'（北京时间），按本地解析后再减掉时区差
  const parsed = new Date(String(raw).replace(/-/g, '/'))
  return Number.isNaN(parsed.getTime()) ? null : parsed
})

/** 剩余时间文本：xx 小时 xx 分 xx 秒 */
const remainingText = computed(() => {
  if (!deadline.value) return '—'
  const diff = deadline.value - serverNow.value
  if (diff <= 0) return '即将生效'
  const totalSeconds = Math.floor(diff / 1000)
  const hours = Math.floor(totalSeconds / 3600)
  const minutes = Math.floor((totalSeconds % 3600) / 60)
  const seconds = totalSeconds % 60
  return `${hours} 小时 ${minutes} 分 ${seconds} 秒`
})

const remainingPercent = computed(() => {
  if (!deadline.value) return 0
  const windowMs = (status.value.window_hours || 24) * 3600 * 1000
  const left = deadline.value - serverNow.value
  if (left <= 0) return 100
  return Math.min(100, Math.max(0, Math.round((1 - left / windowMs) * 100)))
})

async function load() {
  loading.value = true
  try {
    const data = await adminApi.handover.status()
    status.value = data
    candidates.value = data.candidates || []
    // 用服务器时间校准本机时钟
    if (data.server_now) {
      const serverTime = new Date(String(data.server_now).replace(/-/g, '/')).getTime()
      if (!Number.isNaN(serverTime)) clockSkew.value = serverTime - Date.now()
    }
    if (!data.handover_pending) {
      form.user_id = null
      form.reason = ''
    }
  } catch (error) {
    // 拦截器已提示
  } finally {
    loading.value = false
  }
}

watch(visible, (open) => {
  if (open) {
    load()
    timer = setInterval(() => { now.value = Date.now() }, 1000)
  } else if (timer) {
    clearInterval(timer)
    timer = null
  }
})

onUnmounted(() => {
  if (timer) clearInterval(timer)
})

async function submit() {
  if (!form.user_id) {
    ElMessage.warning('请先选择接任者')
    return
  }
  const target = candidates.value.find((item) => item.id === form.user_id)
  try {
    await ElMessageBox.confirm(
      `确认把管理员权限移交给「${target?.display_name || form.user_id}」？\n\n` +
        `· 对方立刻获得管理员身份，但 24 小时内后台功能处于冻结状态；\n` +
        `· 这 24 小时内你仍是管理员，可随时撤销；\n` +
        `· 到期未撤销，你将变为普通用户，对方正式上任。\n\n` +
        `时间以北京时间 ${status.value.server_now || ''} 为准。`,
      '管理员移交',
      { type: 'warning', confirmButtonText: '确认移交' }
    )
    submitting.value = true
    const data = await adminApi.handover.start({
      user_id: form.user_id,
      reason: form.reason || null
    })
    ElMessage.success(data.msg || `已发起移交，${data.effective_at} 生效`)
    await load()
    emit('finished')
  } catch (error) {
    // 取消或接口报错
  } finally {
    submitting.value = false
  }
}

async function cancel() {
  try {
    await ElMessageBox.confirm(
      '撤销后对方的临时管理员身份会被收回，你继续担任管理员。确认撤销？',
      '撤销移交',
      { type: 'warning', confirmButtonText: '确认撤销' }
    )
    await adminApi.handover.cancel()
    ElMessage.success('已撤销移交，你仍是管理员')
    await load()
    emit('finished')
  } catch (error) {
    // 取消或接口报错
  }
}

async function finalizeNow() {
  try {
    const data = await adminApi.handover.finalize()
    ElMessage.success(data.msg || '已结算')
    emit('finished')
    visible.value = false
  } catch (error) {
    // 未到期时后端会拒绝，拦截器已提示
  }
}
</script>

<template>
  <el-dialog v-model="visible" title="管理员移交" width="560px" :close-on-click-modal="false">
    <div v-loading="loading">
      <!-- 当前没有进行中的移交：选人发起 -->
      <template v-if="!status.handover_pending">
        <el-alert type="warning" :closable="false" show-icon class="slp-mb-16">
          <template #title>系统只允许存在一个管理员</template>
          <template #default>
            所以管理员不能直接把自己降级。要让出权限，请在此指定接任者：
            对方会以<b>原有身份</b>继续工作 24 小时，到期才正式上任；这期间你随时可以反悔。
          </template>
        </el-alert>

        <el-form label-width="90px">
          <el-form-item label="接任者">
            <el-select
              v-model="form.user_id"
              placeholder="从普通用户 / 审核员中选择"
              filterable
              style="width: 100%"
            >
              <el-option
                v-for="item in candidates"
                :key="item.id"
                :label="`${item.display_name}（${item.student_id} · ${item.role_label}）`"
                :value="item.id"
              />
            </el-select>
            <div v-if="!candidates.length" class="slp-text-sub slp-mt-8">
              没有可接管的账号（已排除自己、被封禁账号与现有管理员）。
            </div>
            <div v-else class="slp-text-sub slp-mt-8">
              接任者可以是普通用户或审核员 —— 被选中后会升为管理员。
            </div>
          </el-form-item>
          <el-form-item label="移交说明">
            <el-input
              v-model="form.reason"
              placeholder="选填，例如：毕业交接 / 换届"
              maxlength="100"
              show-word-limit
            />
          </el-form-item>
        </el-form>

        <el-descriptions :column="1" border size="small">
          <el-descriptions-item label="当前北京时间">
            {{ status.server_now || '—' }}
          </el-descriptions-item>
          <el-descriptions-item label="反悔期">{{ status.window_hours || 24 }} 小时</el-descriptions-item>
        </el-descriptions>
      </template>

      <!-- 进行中：发起人视角 -->
      <template v-else>
        <el-result
          :icon="isTarget ? 'warning' : 'success'"
          :title="isTarget ? '你已被指定为管理员（待上任）' : '管理员移交进行中'"
        >
          <template #sub-title>
            <div style="line-height: 2">
              <div v-if="isInitiator">
                接任者：<b>{{ status.handover_to?.display_name }}（{{ status.handover_to?.student_id }}）</b>
              </div>
              <div v-else>
                发起人：<b>{{ status.handover_from?.display_name || '—' }}</b>
              </div>
              <div>生效时间（北京时间）：<b>{{ status.handover_deadline }}</b></div>
              <div>
                剩余：<b style="color: #e6a23c">{{ remainingText }}</b>
              </div>
            </div>
          </template>
        </el-result>

        <el-progress :percentage="remainingPercent" :stroke-width="12" status="warning" />
        <p class="slp-text-sub slp-mt-8">
          <template v-if="isInitiator">
            在这段时间内你仍然是管理员，功能照常使用；到期未撤销则你变为普通用户。
          </template>
          <template v-else>
            到期前你以<b>原有身份</b>继续工作（原本是审核员就照常审核），
            但拿不到管理员那些权限（系统配置 / 模块 / 角色 / 回收站），
            发的帖子也仍需审核。到期后自动上任；期间发起人可随时撤销。
          </template>
        </p>

        <div class="slp-toolbar slp-mt-16">
          <el-button v-if="status.can_cancel" type="danger" plain @click="cancel">
            撤销移交（反悔）
          </el-button>
          <!-- 仅演示 / 排障：正常到点后任意后台请求都会自动落地 -->
          <el-button text @click="finalizeNow">立即结算（演示用）</el-button>
        </div>
      </template>
    </div>

    <template #footer>
      <el-button @click="visible = false">关闭</el-button>
      <el-button
        v-if="!status.handover_pending"
        type="primary"
        :loading="submitting"
        :disabled="!form.user_id"
        @click="submit"
      >
        发起移交
      </el-button>
    </template>
  </el-dialog>
</template>
