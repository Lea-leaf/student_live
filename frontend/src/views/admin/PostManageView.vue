<script setup>
/**
 * 管理端 - 内容管理（全模块帖子）。
 * 需求：所有帖子、按模块/状态筛选、审核、删除、置顶。
 */
import { onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Search } from '@element-plus/icons-vue'

import adminApi from '@/api/admin'
import { useAppStore } from '@/stores/app'
import { statusTagType } from '@/utils'

const route = useRoute()
const router = useRouter()
const appStore = useAppStore()

const loading = ref(false)
const list = ref([])
const total = ref(0)
const moduleOptions = ref([])
const query = reactive({
  page: 1,
  size: 10,
  keyword: '',
  type: '',
  status: '',
  audit_status: '',
  is_deleted: '0',
  order: 'newest'
})

onMounted(() => {
  if (route.query.keyword) query.keyword = String(route.query.keyword)
  load()
})

async function load() {
  loading.value = true
  try {
    const params = { page: query.page, size: query.size, is_deleted: query.is_deleted, order: query.order }
    Object.keys(params).forEach((key) => {
      if (params[key] === '' || params[key] === null) delete params[key]
    })
    ;['keyword', 'type', 'status', 'audit_status'].forEach((key) => {
      if (query[key]) params[key] = query[key]
    })
    const data = await adminApi.posts.list(params)
    list.value = data.list || []
    total.value = data.total || 0
    moduleOptions.value = data.modules || []
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
  Object.assign(query, {
    page: 1, keyword: '', type: '', status: '', audit_status: '', is_deleted: '0', order: 'newest'
  })
  load()
}

async function audit(row, auditStatus) {
  const label = auditStatus === 'approved' ? '通过' : '拒绝'
  try {
    const { value } = await ElMessageBox.prompt(
      auditStatus === 'approved' ? '可填写审核备注（选填）' : '请填写拒绝原因',
      `${label}该信息`,
      { inputPlaceholder: '审核意见', confirmButtonText: `确认${label}`, type: 'warning' }
    )
    await adminApi.posts.audit(row.id, { audit_status: auditStatus, remark: value || null })
    ElMessage.success(`已${label}`)
    load()
  } catch (error) {
    // 取消或接口报错
  }
}

async function toggleTop(row) {
  try {
    await adminApi.posts.toggleTop(row.id, { is_top: !row.is_top })
    ElMessage.success(row.is_top ? '已取消置顶' : '已置顶')
    load()
  } catch (error) {
    // 拦截器已提示
  }
}

async function removePost(row) {
  try {
    await ElMessageBox.confirm(
      `确认删除「${row.title || row.id}」吗？删除后进入回收站，可恢复。`,
      '删除确认',
      { type: 'warning', confirmButtonText: '确认删除' }
    )
    await adminApi.posts.remove(row.id)
    ElMessage.success('已删除并移入回收站')
    load()
  } catch (error) {
    // 取消
  }
}

async function changeStatus(row, status) {
  try {
    await adminApi.posts.changeStatus(row.id, { status })
    ElMessage.success('状态已更新')
    load()
  } catch (error) {
    // 拦截器已提示
  }
}

function viewDetail(row) {
  ElMessageBox.alert(
    `<div style="line-height:1.8">
       <b>标题：</b>${row.title || '（无标题）'}<br/>
       <b>描述：</b>${(row.content || '（无描述）').replace(/\n/g, '<br/>')}<br/>
       <b>地点：</b>${row.location || '-'}<br/>
       <b>时间：</b>${row.happened_at || '-'}<br/>
       <b>联系方式：</b>${row.contact}<br/>
       <b>发布者：</b>${row.author?.display_name || '-'}（${row.author?.student_id || '-'}）<br/>
       <b>审核备注：</b>${row.audit_remark || '-'}
     </div>`,
    `帖子 #${row.id} 详情`,
    { dangerouslyUseHTMLString: true, confirmButtonText: '关闭' }
  )
}
</script>

<template>
  <div>
    <div class="slp-card">
      <div class="slp-toolbar">
        <el-input
          v-model="query.keyword"
          placeholder="搜索标题 / 描述 / 联系方式"
          :prefix-icon="Search"
          clearable
          style="width: 240px"
          @keyup.enter="onSearch"
        />
        <el-select v-model="query.type" placeholder="全部模块" clearable style="width: 150px">
          <el-option
            v-for="item in moduleOptions"
            :key="item.code"
            :label="item.name"
            :value="item.code"
          />
        </el-select>
        <el-select v-model="query.status" placeholder="业务状态" clearable style="width: 130px">
          <el-option
            v-for="item in appStore.enums.post_status"
            :key="item.value"
            :label="item.label"
            :value="item.value"
          />
        </el-select>
        <el-select v-model="query.audit_status" placeholder="审核状态" clearable style="width: 130px">
          <el-option
            v-for="item in appStore.enums.audit_status"
            :key="item.value"
            :label="item.label"
            :value="item.value"
          />
        </el-select>
        <el-select v-model="query.is_deleted" style="width: 130px">
          <el-option label="未删除" value="0" />
          <el-option label="已删除" value="1" />
        </el-select>
        <el-button type="primary" @click="onSearch">查询</el-button>
        <el-button @click="onReset">重置</el-button>
      </div>
    </div>

    <div class="slp-card">
      <el-table v-loading="loading" :data="list" size="small">
        <el-table-column prop="id" label="ID" width="65" />
        <el-table-column label="标题" min-width="180" show-overflow-tooltip>
          <template #default="{ row }">
            <el-tag v-if="row.is_top" type="danger" size="small" effect="dark">顶</el-tag>
            <span>{{ row.title || '（无标题）' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="模块" width="100">
          <template #default="{ row }">{{ row.module_name || row.type }}</template>
        </el-table-column>
        <el-table-column label="发布者" width="130">
          <template #default="{ row }">{{ row.author?.display_name || '-' }}</template>
        </el-table-column>
        <el-table-column prop="contact" label="联系方式" width="160" show-overflow-tooltip />
        <el-table-column label="业务状态" width="100">
          <template #default="{ row }">
            <el-tag :type="statusTagType(row.status)" size="small">{{ row.status_label }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="审核" width="100">
          <template #default="{ row }">
            <el-tag :type="statusTagType(row.audit_status)" size="small" effect="plain">
              {{ row.audit_status_label }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="created_at" label="发布时间" width="160" />
        <el-table-column label="操作" width="290" fixed="right">
          <template #default="{ row }">
            <el-button text type="primary" size="small" @click="viewDetail(row)">查看</el-button>
            <template v-if="row.audit_status === 'pending'">
              <el-button text type="success" size="small" @click="audit(row, 'approved')">通过</el-button>
              <el-button text type="danger" size="small" @click="audit(row, 'rejected')">拒绝</el-button>
            </template>
            <el-button text size="small" @click="toggleTop(row)">{{ row.is_top ? '取消置顶' : '置顶' }}</el-button>
            <el-dropdown @command="(status) => changeStatus(row, status)">
              <el-button text size="small">改状态</el-button>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item command="ongoing">进行中</el-dropdown-item>
                  <el-dropdown-item command="claimed">已认领</el-dropdown-item>
                  <el-dropdown-item command="expired">已过期</el-dropdown-item>
                  <el-dropdown-item command="closed">已关闭</el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
            <el-button
              v-if="!row.is_deleted"
              text
              type="danger"
              size="small"
              @click="removePost(row)"
            >
              删除
            </el-button>
          </template>
        </el-table-column>
      </el-table>

      <el-empty v-if="!loading && !list.length" description="没有符合条件的帖子" :image-size="70" />

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
