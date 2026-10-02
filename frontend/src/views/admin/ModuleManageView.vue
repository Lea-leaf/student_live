<script setup>
/**
 * 管理端 - 模块管理。
 * 需求：启用/禁用、排序、配置，后台可新增模块（如「其他」）。
 * 说明：模块是数据行，不是代码；新增后前端导航会自动出现（/common/modules）。
 */
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'

import adminApi from '@/api/admin'

const loading = ref(false)
const list = ref([])
const dialogVisible = ref(false)
const editing = ref(null)
const saving = ref(false)

const form = reactive({
  code: '',
  name: '',
  icon: 'Grid',
  description: '',
  sort_order: 100,
  enabled: true,
  configText: '{\n  "audit": true\n}'
})

onMounted(load)

async function load() {
  loading.value = true
  try {
    const data = await adminApi.modules.list()
    list.value = data.list || []
  } catch (error) {
    list.value = []
  } finally {
    loading.value = false
  }
}

function openCreate() {
  editing.value = null
  Object.assign(form, {
    code: '',
    name: '',
    icon: 'Grid',
    description: '',
    sort_order: (list.value.length + 1) * 10,
    enabled: true,
    configText: '{\n  "audit": true\n}'
  })
  dialogVisible.value = true
}

function openEdit(row) {
  editing.value = row
  Object.assign(form, {
    code: row.code,
    name: row.name,
    icon: row.icon || 'Grid',
    description: row.description || '',
    sort_order: row.sort_order,
    enabled: row.enabled,
    configText: JSON.stringify(row.config || {}, null, 2)
  })
  dialogVisible.value = true
}

async function submit() {
  if (!form.name.trim()) {
    ElMessage.warning('请填写模块名称')
    return
  }
  if (!editing.value && !/^[a-z][a-z0-9_]{1,63}$/.test(form.code.trim())) {
    ElMessage.warning('模块标识需为小写字母开头，可含数字与下划线')
    return
  }
  let config = {}
  try {
    config = form.configText.trim() ? JSON.parse(form.configText) : {}
  } catch (error) {
    ElMessage.error('模块配置必须是合法 JSON')
    return
  }

  saving.value = true
  try {
    if (editing.value) {
      await adminApi.modules.update(editing.value.id, {
        name: form.name,
        icon: form.icon,
        description: form.description,
        sort_order: Number(form.sort_order),
        config
      })
      ElMessage.success('模块已更新')
    } else {
      await adminApi.modules.create({
        code: form.code.trim(),
        name: form.name,
        icon: form.icon,
        description: form.description,
        sort_order: Number(form.sort_order),
        enabled: form.enabled,
        config
      })
      ElMessage.success('模块已创建')
    }
    dialogVisible.value = false
    load()
  } catch (error) {
    // 拦截器已提示
  } finally {
    saving.value = false
  }
}

async function toggle(row) {
  try {
    await adminApi.modules.toggle(row.id, { enabled: !row.enabled })
    ElMessage.success(row.enabled ? '已禁用' : '已启用')
    load()
  } catch (error) {
    // 拦截器已提示
  }
}

async function changeSort(row) {
  try {
    await adminApi.modules.reorder([{ id: row.id, sort_order: Number(row.sort_order) }])
    ElMessage.success('排序已保存')
    load()
  } catch (error) {
    // 拦截器已提示
  }
}

async function remove(row) {
  try {
    await ElMessageBox.confirm(
      `确认删除模块「${row.name}」吗？模块下还有帖子时无法删除。`,
      '删除确认',
      { type: 'warning', confirmButtonText: '确认删除' }
    )
    await adminApi.modules.remove(row.id)
    ElMessage.success('模块已删除')
    load()
  } catch (error) {
    // 取消
  }
}
</script>

<template>
  <div>
    <div class="slp-card">
      <div class="slp-flex-between">
        <div>
          <h3>模块管理</h3>
          <p class="slp-text-sub">
            模块以数据行形式存在，新增模块无需改代码；启用后立即出现在前台导航与筛选器中。
          </p>
        </div>
        <el-button type="primary" @click="openCreate">新增模块</el-button>
      </div>
    </div>

    <div class="slp-card">
      <el-table v-loading="loading" :data="list" size="small">
        <el-table-column prop="sort_order" label="排序" width="110">
          <template #default="{ row }">
            <el-input-number
              v-model="row.sort_order"
              size="small"
              :min="0"
              :max="9999"
              controls-position="right"
              style="width: 96px"
              @change="changeSort(row)"
            />
          </template>
        </el-table-column>
        <el-table-column prop="name" label="模块名称" width="140" />
        <el-table-column prop="code" label="标识（posts.type）" width="150" />
        <el-table-column prop="description" label="简介" min-width="200" show-overflow-tooltip />
        <el-table-column label="帖子数" width="90" align="center">
          <template #default="{ row }">{{ row.post_count }}</template>
        </el-table-column>
        <el-table-column label="待审核" width="90" align="center">
          <template #default="{ row }">
            <el-tag v-if="row.pending_count" type="warning" size="small">{{ row.pending_count }}</el-tag>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column label="内置" width="80" align="center">
          <template #default="{ row }">
            <el-tag v-if="row.is_system" size="small" type="info">内置</el-tag>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="120">
          <template #default="{ row }">
            <el-switch
              :model-value="row.enabled"
              active-text="启用"
              inactive-text="禁用"
              inline-prompt
              @change="toggle(row)"
            />
          </template>
        </el-table-column>
        <el-table-column label="操作" width="150" fixed="right">
          <template #default="{ row }">
            <el-button text type="primary" size="small" @click="openEdit(row)">编辑</el-button>
            <el-button
              text
              type="danger"
              size="small"
              :disabled="row.is_system"
              @click="remove(row)"
            >
              删除
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <el-dialog v-model="dialogVisible" :title="editing ? '编辑模块' : '新增模块'" width="560px">
      <el-form :model="form" label-width="110px">
        <el-form-item label="模块标识" required>
          <el-input v-model="form.code" :disabled="!!editing" placeholder="例如 other / second_hand" />
          <span class="slp-text-sub">作为帖子的 type 值，创建后不可修改</span>
        </el-form-item>
        <el-form-item label="模块名称" required>
          <el-input v-model="form.name" placeholder="例如 其他" />
        </el-form-item>
        <el-form-item label="图标名">
          <el-input v-model="form.icon" placeholder="Element Plus 图标名，例如 Grid / MoreFilled" />
        </el-form-item>
        <el-form-item label="简介">
          <el-input v-model="form.description" maxlength="120" />
        </el-form-item>
        <el-form-item label="排序">
          <el-input-number v-model="form.sort_order" :min="0" :max="9999" />
          <span class="slp-text-sub">数字越小越靠前</span>
        </el-form-item>
        <el-form-item label="是否启用">
          <el-switch v-model="form.enabled" />
        </el-form-item>
        <el-form-item label="模块配置">
          <el-input v-model="form.configText" type="textarea" :rows="4" />
          <span class="slp-text-sub">JSON 格式，例如 { "audit": true }，供模块做差异化扩展</span>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="submit">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>
