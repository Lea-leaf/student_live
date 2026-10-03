<script setup>
/**
 * 管理端 - 用户管理。
 * 需求：列表、搜索、详情、封禁/解封、重置密码、查看发帖记录。
 * 额外：彻底删除用户（级联清理帖子/评论/媒体文件，需输入学号二次确认）。
 */
import { onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Search } from '@element-plus/icons-vue'

import adminApi from '@/api/admin'
import { useAppStore } from '@/stores/app'
import { useUserStore } from '@/stores/user'
import { statusTagType } from '@/utils'

const router = useRouter()
const appStore = useAppStore()
const userStore = useUserStore()

const loading = ref(false)
const list = ref([])
const total = ref(0)
const selection = ref([])
const query = reactive({ page: 1, size: 10, keyword: '', role: '', status: '', order: 'newest' })

onMounted(load)

async function load() {
  loading.value = true
  try {
    const params = { page: query.page, size: query.size, order: query.order }
    if (query.keyword) params.keyword = query.keyword
    if (query.role) params.role = query.role
    if (query.status) params.status = query.status
    const data = await adminApi.users.list(params)
    list.value = data.list || []
    total.value = data.total || 0
  } catch (error) {
    list.value = []
  } finally {
    loading.value = false
  }
}

function onSearch() {
  query.page = 1
  load()
}

function onReset() {
  query.keyword = ''
  query.role = ''
  query.status = ''
  query.order = 'newest'
  query.page = 1
  load()
}

async function banUser(row) {
  try {
    const { value } = await ElMessageBox.prompt('请输入封禁原因', `封禁 ${row.display_name}`, {
      inputPlaceholder: '例如：发布违规信息',
      inputValidator: (text) => (text && text.trim() ? true : '请填写封禁原因'),
      confirmButtonText: '确认封禁',
      type: 'warning'
    })
    await adminApi.users.ban(row.id, { reason: value })
    ElMessage.success('已封禁')
    load()
  } catch (error) {
    // 取消或接口报错
  }
}

async function unbanUser(row) {
  try {
    await ElMessageBox.confirm(`确认解封 ${row.display_name} 吗？`, '解封确认', { type: 'warning' })
    await adminApi.users.unban(row.id)
    ElMessage.success('已解封')
    load()
  } catch (error) {
    // 取消
  }
}

async function resetPassword(row) {
  try {
    const { value } = await ElMessageBox.prompt(
      '留空则重置为默认密码 123456',
      `重置 ${row.display_name} 的密码`,
      { inputPlaceholder: '新密码（可留空）', confirmButtonText: '确认重置' }
    )
    const data = await adminApi.users.resetPassword(row.id, value ? { new_password: value } : {})
    ElMessageBox.alert(`账号：${data.student_id}\n新密码：${data.new_password}`, '重置成功', {
      confirmButtonText: '知道了'
    })
  } catch (error) {
    // 取消或接口报错
  }
}

async function batchBan() {
  if (!selection.value.length) {
    ElMessage.warning('请先勾选用户')
    return
  }
  try {
    const { value } = await ElMessageBox.prompt(
      `即将封禁 ${selection.value.length} 个账号，请填写原因`,
      '批量封禁',
      { inputPlaceholder: '封禁原因', confirmButtonText: '确认' }
    )
    const data = await adminApi.users.batchBan({
      user_ids: selection.value.map((item) => item.id),
      reason: value
    })
    ElMessage.success(`已封禁 ${data.affected} 个账号`)
    load()
  } catch (error) {
    // 取消或接口报错
  }
}

function goDetail(row) {
  router.push({ name: 'admin-user-detail', params: { id: row.id } })
}

/**
 * 彻底删除用户（不可恢复）。
 * 后端要求提交 confirm_student_id 做二次确认，这里先给用户看清后果，再要求输入学号。
 */
async function removeUser(row) {
  let media = null
  try {
    media = await adminApi.users.media(row.id)
  } catch (error) {
    // 拿不到媒体清单不阻塞删除流程
  }

  const mediaLine = media
    ? `\n该用户有 ${media.db_record_count} 条媒体记录，磁盘占用 ${media.files_on_disk} 个文件 / ${(media.bytes_on_disk / 1024).toFixed(1)} KB，将一并删除。`
    : ''

  try {
    const { value } = await ElMessageBox.prompt(
      `⚠️ 彻底删除不可恢复！\n\n将删除：该用户的全部帖子、评论、收藏、私信、通知，` +
        `以及磁盘目录 uploads\\${row.student_id}\\ 下的所有文件。${mediaLine}\n\n` +
        `请输入该用户的学号「${row.student_id}」以确认：`,
      `删除用户 ${row.display_name}`,
      {
        inputPlaceholder: row.student_id,
        inputValidator: (text) => (text && text.trim() === row.student_id
          ? true
          : '输入的学号与目标用户不一致'),
        confirmButtonText: '确认彻底删除',
        confirmButtonClass: 'el-button--danger',
        type: 'error'
      }
    )

    const data = await adminApi.users.remove(row.id, { confirm_student_id: value.trim() })
    const totalFiles = (data.media_files || 0) + (data.leftover_files || 0)
    ElMessageBox.alert(
      `已删除用户 ${data.student_id}\n\n` +
        `帖子 ${data.posts} 条｜评论 ${data.comments} 条｜收藏 ${data.favorites} 条\n` +
        `媒体记录 ${data.media_rows} 条｜磁盘文件 ${totalFiles} 个`,
      '删除完成',
      { confirmButtonText: '知道了', type: 'success' }
    )
    load()
  } catch (error) {
    // 取消或接口报错
  }
}
</script>

<template>
  <div>
    <div class="slp-card">
      <div class="slp-toolbar">
        <el-input
          v-model="query.keyword"
          placeholder="搜索学号 / 用户名 / 昵称"
          :prefix-icon="Search"
          clearable
          style="width: 240px"
          @keyup.enter="onSearch"
        />
        <el-select v-model="query.role" placeholder="全部角色" clearable style="width: 150px">
          <el-option
            v-for="item in appStore.enums.role"
            :key="item.value"
            :label="item.label"
            :value="item.value"
          />
        </el-select>
        <el-select v-model="query.status" placeholder="全部状态" clearable style="width: 130px">
          <el-option
            v-for="item in appStore.enums.user_status"
            :key="item.value"
            :label="item.label"
            :value="item.value"
          />
        </el-select>
        <el-select v-model="query.order" style="width: 140px">
          <el-option label="最新注册" value="newest" />
          <el-option label="最早注册" value="oldest" />
          <el-option label="发帖最多" value="posts" />
        </el-select>
        <el-button type="primary" @click="onSearch">查询</el-button>
        <el-button @click="onReset">重置</el-button>
        <div style="flex: 1"></div>
        <el-button type="danger" plain :disabled="!selection.length" @click="batchBan">
          批量封禁（{{ selection.length }}）
        </el-button>
      </div>
    </div>

    <div class="slp-card">
      <el-table
        v-loading="loading"
        :data="list"
        size="small"
        @selection-change="(rows) => (selection = rows)"
      >
        <el-table-column type="selection" width="45" />
        <el-table-column prop="id" label="ID" width="70" />
        <el-table-column label="用户" min-width="160">
          <template #default="{ row }">
            <div class="user-cell">
              <el-avatar :size="26" :src="row.avatar">{{ (row.display_name || '?').slice(0, 1) }}</el-avatar>
              <div>
                <div>{{ row.display_name }}</div>
                <div class="slp-text-sub">学号 {{ row.student_id }}</div>
              </div>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="角色" width="110">
          <template #default="{ row }">
            <el-tag :type="row.is_admin ? 'danger' : 'info'" size="small">{{ row.role_label }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="statusTagType(row.status)" size="small">{{ row.status_label }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="post_count" label="发帖" width="70" align="center" />
        <el-table-column prop="login_count" label="登录" width="70" align="center" />
        <el-table-column prop="created_at" label="注册时间" width="160" />
        <el-table-column prop="last_login_at" label="最后登录" width="160" />
        <el-table-column label="操作" width="230" fixed="right">
          <template #default="{ row }">
            <el-button text type="primary" size="small" @click="goDetail(row)">详情</el-button>
            <el-button
              v-if="row.status === 'active'"
              text
              type="danger"
              size="small"
              @click="banUser(row)"
            >
              封禁
            </el-button>
            <el-button v-else text type="success" size="small" @click="unbanUser(row)">解封</el-button>
            <el-button text type="warning" size="small" @click="resetPassword(row)">重置密码</el-button>
            <el-button
              v-if="userStore.user && userStore.user.id !== row.id"
              text
              type="danger"
              size="small"
              @click="removeUser(row)"
            >
              删除
            </el-button>
          </template>
        </el-table-column>
      </el-table>

      <el-empty v-if="!loading && !list.length" description="没有符合条件的用户" :image-size="70" />

      <div v-if="total > query.size" class="slp-mt-16" style="text-align: right">
        <el-pagination
          layout="prev, pager, next, total"
          :total="total"
          :page-size="query.size"
          :current-page="query.page"
          background
          @current-change="(page) => { query.page = page; load() }"
        />
      </div>
    </div>
  </div>
</template>

<style scoped>
.user-cell {
  display: flex;
  align-items: center;
  gap: 8px;
}
</style>
