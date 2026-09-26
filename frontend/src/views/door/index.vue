<template>
  <section class="page" data-module="door">
    <header class="page-head">
      <div>
        <h2>门到门配送管理</h2>
        <p class="page-desc">维护配送任务，围绕任务编号、关联调度、配送站点、配送地址做登记、筛选与状态流转；完成签收会同步关联回单状态。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">登记配送任务</button>
        <button class="btn" type="button" @click="exportRows">导出门到门配送清单</button>
      </div>
    </header>

    <div class="stat-row">
      <article
        v-for="item in stats"
        :key="item.label"
        class="stat-card"
        :class="{ active: filters.status === item.label }"
        role="button"
        tabindex="0"
        @click="toggleStatusFilter(item.label)"
        @keydown.enter="toggleStatusFilter(item.label)"
      >
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <form class="filter-bar" @submit.prevent="reload">
      <label class="filter-item">
        <span>任务编号</span>
        <input v-model="filters.keyword" placeholder="按任务编号检索" />
      </label>
      <label class="filter-item">
        <span>配送状态</span>
        <select v-model="filters.status">
          <option value="">全部状态</option>
          <option v-for="status in statuses" :key="status" :value="status">{{ status }}</option>
        </select>
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)">
          <td v-for="column in tableColumns" :key="column">
            <span v-if="column === '配送状态'" class="status-tag" :data-status="row.status">{{ row[column] ?? row.status }}</span>
            <template v-else>{{ row[column] ?? '—' }}</template>
          </td>
          <td class="row-actions">
            <button
              v-for="action in actions"
              :key="action"
              class="link"
              type="button"
              @click="runAction(action, row)"
            >
              {{ action }}
            </button>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="tableColumns.length + 1" class="empty-state">暂无门到门配送数据，可先登记配送任务</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条门到门配送记录</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { request } from '@/api/client'

type Row = Record<string, string | number | null>
type Stat = { label: string; value: number }

const ENDPOINT = '/api/door'
// columns 保留给筛选/导出语义，表格实际列里「配送状态」是与回单台账同步后的状态
const columns = ['任务编号', '关联调度', '配送站点', '配送地址', '配送人员', '计划时段', '签收方式', '配送状态']
const tableColumns = columns
const actions = ['开始配送', '确认送达', '完成签收']
const statuses = ['待配送', '配送中', '已送达', '已签收']

const rows = ref<Row[]>([])
const total = ref(0)
const stats = ref<Stat[]>(statuses.map((label) => ({ label, value: 0 })))
const errorMessage = ref('')
const filters = ref<{ keyword: string; status: string }>({ keyword: '', status: '' })

function resetFilters() {
  filters.value = { keyword: '', status: '' }
  void reload()
}

function toggleStatusFilter(label: string) {
  filters.value.status = filters.value.status === label ? '' : label
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

function openCreate() {
  errorMessage.value = '配送任务登记入口尚未接入审批流'
}

async function runAction(action: string, row: Row) {
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ action }),
    })
    if (!response.ok) {
      throw new Error('门到门配送动作未生效，请稍后重试')
    }
    await Promise.all([reload(), loadStats()])
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '门到门配送操作失败'
  }
}

async function loadStats() {
  try {
    const response = await request(`${ENDPOINT}/stats`)
    if (!response.ok) return
    const payload = await response.json()
    if (Array.isArray(payload.items)) {
      stats.value = statuses.map((label) => {
        const hit = payload.items.find((item: Stat) => item.label === label)
        return { label, value: hit?.value ?? 0 }
      })
    }
  } catch {
    // 统计失败不阻塞列表使用
  }
}

async function reload() {
  errorMessage.value = ''
  const query = new URLSearchParams()
  if (filters.value.keyword) query.set('keyword', filters.value.keyword)
  if (filters.value.status) query.set('status', filters.value.status)
  try {
    const response = await request(`${ENDPOINT}?${query.toString()}`)
    if (!response.ok) {
      throw new Error('配送任务列表读取失败')
    }
    const payload = await response.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '门到门配送列表读取失败'
  }
}

onMounted(() => {
  void reload()
  void loadStats()
})
</script>

<style scoped>
.stat-card {
  cursor: pointer;
  transition: border-color 0.15s ease, box-shadow 0.15s ease;
}
.stat-card.active {
  border-color: var(--brand);
  box-shadow: 0 0 0 1px var(--brand) inset;
}
.status-tag {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 10px;
  font-size: 12px;
  background: #eef2f7;
  color: #475569;
}
.status-tag[data-status='配送中'] {
  background: #fef9c3;
  color: #854d0e;
}
.status-tag[data-status='已送达'] {
  background: #dbeafe;
  color: #1e40af;
}
.status-tag[data-status='已签收'] {
  background: #dcfce7;
  color: #166534;
}
</style>
