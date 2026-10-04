<script setup>
/**
 * 管理端 - 用户详情。
 * 需求：详情、查看发帖记录、封禁/解封、重置密码、角色调整。
 *
 * 权限分层（按 `capabilities` 显示，避免"点了才 403"）：
 * - **管理员**（`user.detail`）：全部区块 + 重置密码 + 调整角色；
 * - **审核员**（只有 `user.view`）：基础资料与统计、封禁 / 解封；
 *   发帖记录与登录日志区块不显示（后端同样拒绝），邮箱手机号也不下发。
 */
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { ArrowDown } from '@element-plus/icons-vue'

import adminApi from '@/api/admin'
import { useAppStore } from '@/stores/app'
import { useUserStore } from '@/stores/user'
import { formatTime, statusTagType } from '@/utils'

const route = useRoute()
const router = useRouter()
const appStore = useAppStore()
const userStore = useUserStore()

const userId = Number(route.params.id)
const loading = ref(false)
const user = ref({})
const stats = ref({})
const posts = reactive({ list: [], total: 0, page: 1, size: 10 })
const logs = reactive({ login_logs: [], operation_logs: [], login_total: 0 })

/** 能否查看敏感明细（发帖记录 / 登录日志）。审核员只有 user.view，看不到这些区块。 */
const canSeeDetail = computed(() => userStore.can('user.detail'))

/**
 * 可分配的角色：排除 `admin`。
 * 系统只允许一个管理员，管理员身份只能通过「管理员移交」获得 ——
 * 所以这里不给"任命管理员"的选项，避免点了一个必定失败的菜单。
 */
const assignableRoles = computed(() =>
  (appStore.enums.role || []).filter((item) => item.value !== 'admin')
)

onMounted(loadAll)

async function loadAll() {
  loading.value = true
  try {
    // 详情接口只需 user.view（审核员也有），但要按下发能力决定是否带敏感字段
    const detail = await adminApi.users.detail(userId)
    user.value = detail.user
    stats.value = detail.stats

    // 发帖记录 / 登录与操作日志需要 user.detail（仅管理员）
    // ⚠️ 必须按能力跳过，否则审核员打开本页会白挨两个 403 提示
    if (canSeeDetail.value) {
      const [postData, logData] = await Promise.all([
        adminApi.users.posts(userId, { page: posts.page, size: posts.size }),
        adminApi.users.logs(userId, { page: 1, size: 10 })
      ])
      posts.list = postData.list || []
      posts.total = postData.total || 0
      Object.assign(logs, logData)
    }
  } catch (error) {
    // 拦截器已提示
  } finally {
    loading.value = false
  }
}

async function loadPosts(page = 1) {
  posts.page = page
  const data = await adminApi.users.posts(userId, { page, size: posts.size })
  posts.list = data.list || []
  posts.total = data.total || 0
}

async function ban() {
  try {
    const { value } = await ElMessageBox.prompt('请输入封禁原因', '封禁账号', {
      inputValidator: (text) => (text && text.trim() ? true : '请填写封禁原因'),
      type: 'warning'
    })
    await adminApi.users.ban(userId, { reason: value })
    ElMessage.success('已封禁')
    loadAll()
  } catch (error) {
    // 取消
  }
}

async function unban() {
  try {
    await ElMessageBox.confirm('确认解封该账号吗？', '解封确认', { type: 'warning' })
    await adminApi.users.unban(userId)
    ElMessage.success('已解封')
    loadAll()
  } catch (error) {
    // 取消
  }
}

async function resetPassword() {
  try {
    const { value } = await ElMessageBox.prompt('留空则重置为 123456', '重置密码', {
      confirmButtonText: '确认重置'
    })
    const data = await adminApi.users.resetPassword(userId, value ? { new_password: value } : {})
    // ⚠️ 必须 await（或 catch）：ElMessageBox 在用户点 × / ESC 关闭时会 reject，
    // 不接住就会冒成 Uncaught (in promise) cancel
    await ElMessageBox.alert(`新密码：${data.new_password}`, '重置成功')
  } catch (error) {
    // 取消
  }
}

async function changeRole(role) {
  try {
    await adminApi.users.changeRole(userId, { role })
    ElMessage.success('角色已更新')
    loadAll()
  } catch (error) {
    loadAll()
  }
}

function goPost(post) {
  router.push({ name: 'admin-posts', query: { keyword: post.title || String(post.id) } })
}
</script>

<template>
  <div v-loading="loading">
    <div class="slp-card">
      <el-button text @click="router.back()">← 返回用户列表</el-button>
    </div>

    <el-row :gutter="12">
      <el-col :xs="24" :md="8">
        <div class="slp-card">
          <div style="text-align: center">
            <el-avatar :size="64" :src="user.avatar">{{ (user.display_name || '?').slice(0, 1) }}</el-avatar>
            <h3 class="slp-mt-8">{{ user.display_name }}</h3>
            <el-space>
              <el-tag :type="user.is_admin ? 'danger' : (user.is_staff ? 'warning' : 'info')">{{ user.role_label }}</el-tag>
              <el-tag :type="statusTagType(user.status)">{{ user.status_label }}</el-tag>
            </el-space>
          </div>

          <el-descriptions class="slp-mt-16" :column="1" border size="small">
            <el-descriptions-item label="学号">{{ user.student_id }}</el-descriptions-item>
            <el-descriptions-item label="用户名">{{ user.username }}</el-descriptions-item>
            <el-descriptions-item label="邮箱">{{ user.email || '-' }}</el-descriptions-item>
            <el-descriptions-item label="注册时间">{{ user.created_at }}</el-descriptions-item>
            <el-descriptions-item label="最后登录">{{ user.last_login_at || '-' }}</el-descriptions-item>
            <el-descriptions-item label="登录IP">{{ user.last_login_ip || '-' }}</el-descriptions-item>
            <el-descriptions-item v-if="user.ban_reason" label="封禁原因">
              <span style="color: #f56c6c">{{ user.ban_reason }}</span>
            </el-descriptions-item>
          </el-descriptions>

          <div class="slp-toolbar slp-mt-16">
            <el-button v-if="user.status === 'active'" type="danger" plain @click="ban">封禁</el-button>
            <el-button v-else type="success" plain @click="unban">解封</el-button>
            <!-- 重置密码：后端要求 user.detail 能力，审核员没有，按钮也不显示 -->
            <el-button
              v-if="userStore.can('user.detail')"
              type="warning"
              plain
              @click="resetPassword"
            >重置密码</el-button>
            <!--
              调整角色：管理员专有能力（`user.role`），审核员看不到，后端同样会拦。
              ⚠️ 下拉里**不列「管理员」** —— 系统只允许一个管理员，
              管理员身份只能通过「管理员移交」获得（在用户管理页右上角）。
              不该显示一个"点了必定被拒"的选项。
            -->
            <el-dropdown v-if="userStore.can('user.role') && assignableRoles.length">
              <el-button plain>调整角色<el-icon><ArrowDown /></el-icon></el-button>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item
                    v-for="item in assignableRoles"
                    :key="item.value"
                    :disabled="item.value === user.role"
                    @click="changeRole(item.value)"
                  >
                    {{ item.label }}
                    <span v-if="item.value === user.role" class="slp-text-sub">（当前）</span>
                  </el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
          </div>
        </div>

        <div class="slp-card">
          <h3 class="slp-mb-8">发帖统计</h3>
          <el-descriptions :column="1" border size="small">
            <el-descriptions-item label="总发帖">{{ stats.post_total || 0 }}</el-descriptions-item>
            <el-descriptions-item label="待审核">{{ stats.post_pending || 0 }}</el-descriptions-item>
            <el-descriptions-item label="已删除">{{ stats.post_deleted || 0 }}</el-descriptions-item>
            <el-descriptions-item label="成功登录">{{ stats.login_count || 0 }}</el-descriptions-item>
          </el-descriptions>
        </div>
      </el-col>

      <el-col :xs="24" :md="16">
        <!-- 发帖记录 / 登录日志 / 操作日志：需要 user.detail，审核员看不到 -->
        <el-alert
          v-if="!canSeeDetail"
          class="slp-mb-16"
          type="info"
          show-icon
          :closable="false"
          title="你的身份看不到发帖记录与日志"
          description="这些属于用户敏感明细，仅管理员可查看。你仍可在此封禁 / 解封普通用户。"
        />
        <template v-if="canSeeDetail">
        <div class="slp-card">
          <h3 class="slp-mb-16">发帖记录</h3>
          <el-table :data="posts.list" size="small">
            <el-table-column prop="id" label="ID" width="65" />
            <el-table-column prop="title" label="标题" show-overflow-tooltip />
            <el-table-column label="状态" width="90">
              <template #default="{ row }">
                <el-tag :type="statusTagType(row.status)" size="small">{{ row.status_label }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="审核" width="90">
              <template #default="{ row }">
                <el-tag :type="statusTagType(row.audit_status)" size="small" effect="plain">
                  {{ row.audit_status_label }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="删除" width="70" align="center">
              <template #default="{ row }">
                <el-tag v-if="row.is_deleted" type="danger" size="small">是</el-tag>
                <span v-else>-</span>
              </template>
            </el-table-column>
            <el-table-column prop="created_at" label="发布时间" width="160" />
            <el-table-column label="操作" width="80">
              <template #default="{ row }">
                <el-button text type="primary" size="small" @click="goPost(row)">查看</el-button>
              </template>
            </el-table-column>
          </el-table>
          <div v-if="posts.total > posts.size" class="slp-mt-16" style="text-align: right">
            <el-pagination
              layout="prev, pager, next, total"
              :total="posts.total"
              :page-size="posts.size"
              :current-page="posts.page"
              background
              @current-change="loadPosts"
            />
          </div>
        </div>

        <div class="slp-card">
          <h3 class="slp-mb-16">最近登录记录</h3>
          <el-table :data="logs.login_logs" size="small">
            <el-table-column label="结果" width="80">
              <template #default="{ row }">
                <el-tag :type="row.success ? 'success' : 'danger'" size="small">
                  {{ row.success ? '成功' : '失败' }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="ip" label="IP" width="140" />
            <el-table-column prop="message" label="说明" show-overflow-tooltip />
            <el-table-column prop="created_at" label="时间" width="160" />
          </el-table>
          <el-empty v-if="!logs.login_logs.length" description="暂无登录记录" :image-size="60" />
        </div>

        <div class="slp-card">
          <h3 class="slp-mb-16">最近操作日志</h3>
          <el-table :data="logs.operation_logs" size="small">
            <el-table-column prop="module" label="模块" width="110" />
            <el-table-column prop="action" label="动作" width="120" />
            <el-table-column prop="target_type" label="对象" width="90" />
            <el-table-column prop="target_id" label="对象ID" width="80" />
            <el-table-column prop="ip" label="IP" width="140" />
            <el-table-column label="时间" width="160">
              <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
            </el-table-column>
          </el-table>
          <el-empty v-if="!logs.operation_logs.length" description="暂无操作日志" :image-size="60" />
        </div>
        </template>
      </el-col>
    </el-row>
  </div>
</template>
