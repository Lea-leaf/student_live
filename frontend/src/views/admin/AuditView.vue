<script setup>
/**
 * 管理端 - 审核工作台。
 *
 * 需求 6.4：默认管理员审核通过后才显示；审核状态：待审核 / 已通过 / 已拒绝。
 *
 * v1.4 新增「审核指派」：
 * - 管理员可把待审内容**指派 / 改派 / 收回**给审核员（可指派多位，各自一条）；
 * - 审核员可**自助认领**公共池里的内容（先到先得，被别人抢走时提示「已被 XX 认领」）；
 * - 认领 24 小时未处理会自动退回公共池；
 * - 三种视角：全部 / 我的 / 公共池；别人已认领的内容默认不出现，避免重复审。
 *
 * 权限说明：本页的所有操作按钮都由后端下发的字段驱动
 * （`can_audit` / `can_claim` / `can_assign` / `can_release`），前端不自己判断角色。
 */
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'

import adminApi from '@/api/admin'
import { useUserStore } from '@/stores/user'
import { statusTagType } from '@/utils'

const userStore = useUserStore()

const loading = ref(false)
const list = ref([])
const total = ref(0)
const selection = ref([])
const moduleOptions = ref([])
const assignees = ref([])
const stats = ref({ pool: 0, mine: 0, total: 0 })
const batchRemark = ref('')
const query = reactive({ page: 1, size: 10, type: '', scope: '' })

/** 当前账号能否指派审核员（后端字段驱动，管理员为 true） */
const canAssign = computed(() => userStore.isTrueAdmin)

onMounted(load)

async function load() {
  loading.value = true
  try {
    const params = { page: query.page, size: query.size }
    if (query.type) params.type = query.type
    if (query.scope) params.scope = query.scope
    const data = await adminApi.posts.pending(params)
    list.value = data.list || []
    total.value = data.total || 0
    stats.value = data.stats || { pool: 0, mine: 0, total: 0 }
    selection.value = []
    if (!moduleOptions.value.length) {
      const all = await adminApi.posts.list({ page: 1, size: 1 })
      moduleOptions.value = all.modules || []
    }
    if (canAssign.value && !assignees.value.length) {
      await loadAssignees()
    }
  } catch (error) {
    list.value = []
  } finally {
    loading.value = false
  }
}

async function loadAssignees() {
  try {
    const data = await adminApi.posts.assignees()
    assignees.value = data.list || []
  } catch (error) {
    assignees.value = []
  }
}

/** 认领（先到先得）：失败时后端返回 4005，拦截器已提示原因 */
async function claim(row) {
  try {
    await adminApi.posts.claim(row.id)
    ElMessage.success('认领成功，这条现在归你处理')
    load()
  } catch (error) {
    // 常见于「已被其他审核员认领」，刷新列表让对方的名字显示出来
    load()
  }
}

/** 放弃认领，退回公共池 */
async function release(row) {
  try {
    await ElMessageBox.confirm(
      `确认放弃「${row.title || '#' + row.id}」？退回后其他审核员可以认领。`,
      '放弃认领',
      { type: 'warning' }
    )
    await adminApi.posts.release(row.id)
    ElMessage.success('已退回公共池')
    load()
  } catch (error) {
    // 取消
  }
}

/** 管理员：指派 / 改派 / 收回 */
async function assign(row, assigneeId) {
  try {
    const data = await adminApi.posts.assign(row.id, { assignee_id: assigneeId })
    ElMessage.success(data?.assignee ? '已指派' : '已收回至公共池')
    load()
  } catch (error) {
    // 拦截器已提示
  }
}

async function auditOne(row, auditStatus) {
  const label = auditStatus === 'approved' ? '通过' : '拒绝'
  try {
    const { value } = await ElMessageBox.prompt(
      auditStatus === 'approved' ? '审核备注（选填）' : '请填写拒绝原因（会通知发布者）',
      `${label}「${row.title || row.id}」`,
      {
        inputPlaceholder: '审核意见',
        confirmButtonText: `确认${label}`,
        inputValidator: auditStatus === 'rejected'
          ? (text) => (text && text.trim() ? true : '拒绝时必须填写原因')
          : undefined,
        type: 'warning'
      }
    )
    await adminApi.posts.audit(row.id, { audit_status: auditStatus, remark: value || null })
    ElMessage.success(`已${label}`)
    load()
  } catch (error) {
    // 取消或接口报错
  }
}

async function batchAudit(auditStatus) {
  if (!selection.value.length) {
    ElMessage.warning('请先勾选要审核的信息')
    return
  }
  const label = auditStatus === 'approved' ? '通过' : '拒绝'
  try {
    await ElMessageBox.confirm(
      `确认批量${label} ${selection.value.length} 条信息吗？`,
      '批量审核',
      { type: 'warning' }
    )
    const data = await adminApi.posts.batchAudit({
      post_ids: selection.value.map((item) => item.id),
      audit_status: auditStatus,
      remark: batchRemark.value || null
    })
    // 后端会跳过「自己的帖子 / 别人负责的帖子」并说明原因，这里如实展示
    if (data.skipped?.length) {
      ElMessage.warning(`已处理 ${data.affected} 条，${data.skipped.length} 条被跳过`)
    } else {
      ElMessage.success(`已处理 ${data.affected} 条`)
    }
    batchRemark.value = ''
    load()
  } catch (error) {
    // 取消
  }
}

/** 批量指派给某位审核员 */
async function batchAssign(assigneeId) {
  if (!selection.value.length) {
    ElMessage.warning('请先勾选要指派的信息')
    return
  }
  try {
    await ElMessageBox.confirm(
      `确认把 ${selection.value.length} 条指派给该审核员吗？`,
      '批量指派',
      { type: 'warning' }
    )
    const results = await Promise.all(
      selection.value.map((item) => adminApi.posts.assign(item.id, { assignee_id: assigneeId }))
    )
    ElMessage.success(`已指派 ${results.length} 条`)
    load()
  } catch (error) {
    // 取消或部分失败（拦截器已提示）
    load()
  }
}

/** 查看审核流水（指派 / 认领 / 退回 / 通过 / 拒绝） */
async function showLogs(row) {
  try {
    const data = await adminApi.posts.auditLogs(row.id)
    const rows = data.list || []
    const html = rows.length
      ? rows.map((item) => `<div style="line-height:1.9">
           <b>${item.created_at}</b>　${item.action_label}
           ｜操作人：${item.actor?.display_name || '系统'}
           ${item.assignee ? `｜对象：${item.assignee.display_name}` : ''}
           ${item.duration_ms ? `｜耗时：${Math.round(item.duration_ms / 60000)} 分钟` : ''}
           ${item.remark ? `<br/><span style="color:#909399">${item.remark}</span>` : ''}
         </div>`).join('')
      : '<div>暂无流水记录</div>'
    ElMessageBox.alert(html, `审核流水 #${row.id}`, {
      dangerouslyUseHTMLString: true,
      confirmButtonText: '关闭'
    }).catch(() => {
      // 用户点 × / ESC 关闭时会 reject，必须吞掉
    })
  } catch (error) {
    // 拦截器已提示
  }
}

function preview(row) {
  const media = (row.media || [])
    .map((item) => (item.type === 'video'
      ? `<video src="${item.url}" controls style="width:160px;height:120px;object-fit:cover"></video>`
      : `<img src="${item.url}" style="width:120px;height:120px;object-fit:cover;border-radius:6px"/>`))
    .join('')
  ElMessageBox.alert(
    `<div style="line-height:1.9">
       <b>标题：</b>${row.title || '（无标题）'}<br/>
       <b>描述：</b>${(row.content || '（无描述）').replace(/\n/g, '<br/>')}<br/>
       <b>地点：</b>${row.location || '-'}　<b>时间：</b>${row.happened_at || '-'}<br/>
       <b>联系方式：</b>${row.contact}<br/>
       <b>发布者：</b>${row.author?.display_name || '-'}（${row.author?.student_id || '-'}）<br/>
       <b>当前负责：</b>${row.assignee?.display_name || '公共池（无人认领）'}<br/>
       <div style="display:flex;gap:8px;flex-wrap:wrap;margin-top:8px">${media}</div>
     </div>`,
    `待审核 #${row.id}`,
    { dangerouslyUseHTMLString: true, confirmButtonText: '关闭' }
  ).catch(() => {
    // 用户点 × / ESC 关闭时会 reject，必须吞掉，否则报 Uncaught (in promise) cancel
  })
}
</script>

<template>
  <div>
    <div class="slp-card">
      <div class="slp-toolbar">
        <el-radio-group v-model="query.scope" @change="() => { query.page = 1; load() }">
          <el-radio-button value="">全部</el-radio-button>
          <el-radio-button value="mine">我的（{{ stats.mine }}）</el-radio-button>
          <el-radio-button value="pool">公共池（{{ stats.pool }}）</el-radio-button>
        </el-radio-group>
        <el-select v-model="query.type" placeholder="全部模块" clearable style="width: 150px" @change="load">
          <el-option v-for="item in moduleOptions" :key="item.code" :label="item.name" :value="item.code" />
        </el-select>
        <el-button @click="load">刷新</el-button>
      </div>

      <div class="slp-toolbar slp-mt-8">
        <el-input v-model="batchRemark" placeholder="批量审核备注（选填）" style="width: 200px" />
        <el-button type="success" :disabled="!selection.length" @click="batchAudit('approved')">
          批量通过（{{ selection.length }}）
        </el-button>
        <el-button type="danger" plain :disabled="!selection.length" @click="batchAudit('rejected')">
          批量拒绝
        </el-button>
        <!-- 批量指派：仅管理员可见 -->
        <template v-if="canAssign">
          <el-select
            placeholder="批量指派给…"
            style="width: 180px"
            :disabled="!selection.length"
            @change="(value) => batchAssign(value)"
          >
            <el-option
              v-for="item in assignees"
              :key="item.id"
              :label="`${item.display_name}（${item.role_label}，待审 ${item.pending_count}）`"
              :value="item.id"
            />
          </el-select>
        </template>
      </div>

      <p class="slp-text-sub slp-mt-8">
        待审核 {{ total }} 条（公共池 {{ stats.pool }} · 我的 {{ stats.mine }}）。
        审核通过后信息才会在公开列表中显示；拒绝时请填写原因，系统会自动通知发布者。
        <template v-if="canAssign">
          已认领的内容会显示负责人，被指派后 24 小时内未处理会自动退回公共池。
        </template>
      </p>
    </div>

    <div v-loading="loading">
      <div v-for="row in list" :key="row.id" class="slp-card">
        <div class="audit-row">
          <el-checkbox
            :model-value="selection.some((item) => item.id === row.id)"
            @change="(checked) => {
              if (checked) selection = selection.concat([row])
              else selection = selection.filter((item) => item.id !== row.id)
            }"
          />
          <div class="audit-row__body">
            <div class="slp-flex-between slp-mb-8">
              <h3 class="audit-row__title">#{{ row.id }} {{ row.title || '（无标题）' }}</h3>
              <div class="audit-row__tags">
                <el-tag type="warning" size="small">待审核</el-tag>
                <el-tag size="small" effect="plain">{{ row.module_name || row.type }}</el-tag>
                <!-- 指派状态标识 -->
                <el-tag v-if="row.assignee" type="success" size="small" effect="plain">
                  负责：{{ row.assignee.display_name }}
                </el-tag>
                <el-tag v-else size="small" type="info" effect="plain">公共池</el-tag>
                <el-tag v-if="row.is_self_post" size="small" type="danger" effect="plain">
                  自己的帖子（不可自审）
                </el-tag>
              </div>
            </div>
            <p class="slp-text-sub slp-mb-8" style="white-space: pre-line">{{ row.content || '（无描述）' }}</p>
            <div class="post-card__meta slp-mb-8">
              <span>地点：{{ row.location || '-' }}</span>
              <span>时间：{{ row.happened_at || '-' }}</span>
              <span>联系方式：{{ row.contact }}</span>
              <span>发布者：{{ row.author?.display_name }}（{{ row.author?.student_id }}）</span>
              <span>{{ row.created_at }}</span>
              <span v-if="row.assignment_expires_at">认领到期：{{ row.assignment_expires_at }}</span>
            </div>
            <div v-if="(row.media || []).length" class="audit-row__media">
              <template v-for="item in row.media" :key="item.url">
                <video v-if="item.type === 'video'" :src="item.url" />
                <img v-else :src="item.url" alt="配图" />
              </template>
            </div>
            <div class="slp-toolbar slp-mt-8">
              <el-button size="small" @click="preview(row)">查看完整内容</el-button>
              <el-button
                v-if="row.can_audit"
                size="small"
                type="success"
                @click="auditOne(row, 'approved')"
              >通过</el-button>
              <el-button
                v-if="row.can_audit"
                size="small"
                type="danger"
                plain
                @click="auditOne(row, 'rejected')"
              >拒绝</el-button>

              <!-- 认领 / 放弃（先到先得） -->
              <el-button v-if="row.can_claim" size="small" type="primary" plain @click="claim(row)">
                认领
              </el-button>
              <el-button v-if="row.can_release" size="small" plain @click="release(row)">
                放弃认领
              </el-button>

              <!-- 指派（仅管理员） -->
              <el-select
                v-if="row.can_assign"
                placeholder="指派给…"
                size="small"
                style="width: 170px"
                @change="(value) => assign(row, value)"
              >
                <el-option
                  v-for="item in assignees"
                  :key="item.id"
                  :label="`${item.display_name}（待审 ${item.pending_count}）`"
                  :value="item.id"
                />
                <el-option label="收回至公共池" :value="null" />
              </el-select>

              <el-button size="small" text @click="showLogs(row)">审核流水</el-button>
            </div>
          </div>
        </div>
      </div>

      <el-empty v-if="!loading && !list.length" description="暂无待审核信息 🎉" />
    </div>

    <div v-if="total > query.size" class="slp-mt-16" style="text-align: center">
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
</template>

<style scoped>
.audit-row {
  display: flex;
  gap: 12px;
  align-items: flex-start;
}

.audit-row__body {
  flex: 1;
  min-width: 0;
}

.audit-row__title {
  margin: 0;
  font-size: 16px;
}

.audit-row__tags {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
  justify-content: flex-end;
}

.audit-row__media {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.audit-row__media img,
.audit-row__media video {
  width: 90px;
  height: 90px;
  object-fit: cover;
  border-radius: 6px;
  border: 1px solid #ebeef5;
}
</style>
