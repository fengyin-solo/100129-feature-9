<template>
  <section class="page" data-module="returntrip">
    <header class="page-head">
      <div>
        <h2>回单管理</h2>
        <p class="page-desc">维护回执单，围绕回单编号、关联任务、签收方、签收日期做登记、签收与异常处理；编辑结果按回单编号保存。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">登记回执单</button>
        <button class="btn" type="button" @click="exportRows">导出回单管理清单</button>
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
        <span>回单编号</span>
        <input v-model="filters.keyword" placeholder="按回单编号检索" />
      </label>
      <label class="filter-item">
        <span>回单状态</span>
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
          <th>操作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)">
          <td>{{ row['回单编号'] ?? '—' }}</td>
          <td>{{ row['关联任务'] ?? '—' }}</td>
          <td>{{ row['签收方'] || '—' }}</td>
          <td>{{ row['签收日期'] || '—' }}</td>
          <td>{{ row['签收人'] || '—' }}</td>
          <td>{{ row['异常备注'] || '—' }}</td>
          <td>
            <a v-if="row['回单照片']" :href="resolveFile(row['回单照片'])" target="_blank" rel="noreferrer">查看照片</a>
            <span v-else>—</span>
          </td>
          <td>
            <span class="status-tag" :data-status="row.status">{{ row['回单状态'] || row.status }}</span>
          </td>
          <td class="row-actions">
            <button class="link" type="button" @click="openEdit(row)">签收/编辑</button>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 1" class="empty-state">暂无回单管理数据，可先登记回执单</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条回单管理记录</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>

    <!-- 签收 / 编辑弹窗：回单台账、签收弹窗与配送记录共用同一个状态口径 -->
    <div v-if="dialog.open" class="modal-mask" @click.self="closeDialog">
      <div class="modal">
        <header class="modal-head">
          <h3>{{ dialog.mode === 'create' ? '登记回执单' : `回单签收（${form['回单编号'] || ''}）` }}</h3>
          <button class="btn ghost" type="button" @click="closeDialog">关闭</button>
        </header>

        <div v-if="dialog.mode === 'edit'" class="modal-status">
          当前状态：<span class="status-tag" :data-status="form.status">{{ form['回单状态'] || form.status }}</span>
          <span class="modal-hint">关联任务：{{ form['关联任务'] || '—' }}</span>
        </div>

        <div class="form-grid">
          <label class="form-item">
            <span>回单编号 <em>*</em></span>
            <input v-model="form['回单编号']" :disabled="dialog.mode === 'edit'" />
          </label>
          <label class="form-item">
            <span>关联任务（配送任务编号）</span>
            <input v-model="form['关联任务']" :disabled="dialog.mode === 'edit'" placeholder="如 DOOR-0001" />
          </label>
          <label class="form-item">
            <span>签收方 <em>*</em></span>
            <input v-model="form['签收方']" placeholder="只保存到该回单编号" />
          </label>
          <label class="form-item">
            <span>签收日期 <em>*</em></span>
            <input v-model="form['签收日期']" type="date" />
          </label>
          <label class="form-item">
            <span>签收人</span>
            <input v-model="form['签收人']" />
          </label>
          <label class="form-item form-item-wide">
            <span>异常备注</span>
            <textarea v-model="form['异常备注']" rows="2" placeholder="记录异常时必填"></textarea>
          </label>
          <label class="form-item form-item-wide">
            <span>回单照片</span>
            <div class="photo-row">
              <input ref="fileInput" type="file" accept="image/*" @change="onPickPhoto" />
              <span v-if="uploading" class="modal-hint">上传中…</span>
              <a
                v-else-if="form['回单照片']"
                :href="resolveFile(form['回单照片'])"
                target="_blank"
                rel="noreferrer"
              >查看已留存照片</a>
              <span v-else class="modal-hint">未上传</span>
            </div>
          </label>
        </div>

        <div v-if="dialog.mode === 'edit' && history.length" class="history-box">
          <h4>修改痕迹</h4>
          <ul>
            <li v-for="(item, index) in history" :key="index">
              <span class="history-time">{{ item.time }}</span>
              <span>{{ item.summary }}</span>
              <span v-if="item.fields && Object.keys(item.fields).length" class="modal-hint">
                （{{ Object.entries(item.fields).map(([k, v]) => `${k}=${v}`).join('，') }}）
              </span>
            </li>
          </ul>
        </div>

        <p v-if="dialog.error" class="error-text">{{ dialog.error }}</p>

        <footer class="modal-foot">
          <button class="btn" type="button" :disabled="!!dialog.saving" @click="closeDialog">取消</button>
          <button class="btn" type="button" :disabled="!!dialog.saving" @click="saveFields">
            {{ dialog.saving === 'save' ? '保存中…' : '仅保存编辑' }}
          </button>
          <template v-if="dialog.mode === 'edit'">
            <button class="btn" type="button" :disabled="!!dialog.saving" @click="runAction('记录异常')">
              保存并记录异常
            </button>
            <button class="btn primary" type="button" :disabled="!!dialog.saving" @click="runAction('登记签收')">
              保存并登记签收
            </button>
          </template>
          <button v-else class="btn primary" type="button" :disabled="!!dialog.saving" @click="submitCreate">
            {{ dialog.saving === 'create' ? '登记中…' : '登记回执单' }}
          </button>
        </footer>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { request } from '@/api/client'

type Row = Record<string, string | number | null>
type Stat = { label: string; value: number }
type HistoryItem = { time: string; summary: string; fields?: Record<string, string> }

const ENDPOINT = '/api/returntrip'
const columns = ['回单编号', '关联任务', '签收方', '签收日期', '签收人', '异常备注', '回单照片', '回单状态']
const statuses = ['待签收', '已签收', '有异常', '已上传']

const rows = ref<Row[]>([])
const total = ref(0)
const stats = ref<Stat[]>([
  { label: '待签收', value: 0 },
  { label: '已签收', value: 0 },
  { label: '有异常', value: 0 },
  { label: '已上传', value: 0 },
])
const errorMessage = ref('')
const filters = ref<{ keyword: string; status: string }>({ keyword: '', status: '' })

const fileInput = ref<HTMLInputElement | null>(null)
const uploading = ref(false)

const dialog = ref<{
  open: boolean
  mode: 'create' | 'edit'
  saving: '' | 'save' | 'action' | 'create'
  error: string
}>({ open: false, mode: 'create', saving: '', error: '' })
const form = ref<Row>({})
const history = ref<HistoryItem[]>([])
const editingId = ref<number | null>(null)

function emptyForm(): Row {
  return {
    回单编号: '',
    关联任务: '',
    签收方: '',
    签收日期: '',
    签收人: '',
    异常备注: '',
    回单照片: '',
    回单状态: '',
    status: '',
  }
}

function resolveFile(path: unknown): string {
  const value = String(path ?? '')
  if (!value) return '#'
  return value.startsWith('http') || value.startsWith('/uploads/') ? value : `/uploads/${value}`
}

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
  editingId.value = null
  form.value = emptyForm()
  history.value = []
  dialog.value = { open: true, mode: 'create', saving: '', error: '' }
}

async function openEdit(row: Row) {
  editingId.value = Number(row.id)
  dialog.value = { open: true, mode: 'edit', saving: '', error: '' }
  form.value = { ...emptyForm(), ...row }
  history.value = []
  try {
    const response = await request(`${ENDPOINT}/${row.id}`)
    if (response.ok) {
      const detail: Row & { history?: HistoryItem[] } = await response.json()
      form.value = { ...emptyForm(), ...detail }
      history.value = (detail.history ?? []).slice().reverse()
    }
  } catch {
    // 列表行数据已足够打开弹窗，详情拉取失败时不阻断编辑
  }
}

function closeDialog() {
  if (dialog.value.saving) return
  dialog.value.open = false
}

function fileToDataUrl(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(String(reader.result))
    reader.onerror = () => reject(new Error('照片读取失败'))
    reader.readAsDataURL(file)
  })
}

async function onPickPhoto(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file || editingId.value === null) return
  if (file.size > 8 * 1024 * 1024) {
    dialog.value.error = '照片不能超过 8MB'
    return
  }
  uploading.value = true
  dialog.value.error = ''
  try {
    const content = await fileToDataUrl(file)
    const response = await request(`${ENDPOINT}/${editingId.value}/photo`, {
      method: 'POST',
      body: JSON.stringify({ filename: file.name, content }),
    })
    const payload = await response.json().catch(() => null)
    if (!response.ok || !payload?.ok) {
      throw new Error(payload?.message ?? '照片上传失败')
    }
    form.value['回单照片'] = payload.entry?.['回单照片'] ?? ''
    history.value = (payload.entry?.history ?? []).slice().reverse()
  } catch (error) {
    dialog.value.error = error instanceof Error ? error.message : '照片上传失败'
  } finally {
    uploading.value = false
    if (fileInput.value) fileInput.value.value = ''
  }
}

function editablePayload(): Row {
  const keys = ['签收方', '签收日期', '签收人', '异常备注', '回单照片']
  const payload: Row = {}
  for (const key of keys) payload[key] = form.value[key] ?? ''
  return payload
}

async function saveFields() {
  if (editingId.value === null) return
  dialog.value.error = ''
  dialog.value.saving = 'save'
  try {
    const response = await request(`${ENDPOINT}/${editingId.value}`, {
      method: 'PUT',
      body: JSON.stringify({ values: editablePayload() }),
    })
    const payload = await response.json().catch(() => null)
    if (!response.ok || !payload?.ok) {
      throw new Error(payload?.message ?? '签收信息保存失败')
    }
    form.value = { ...form.value, ...payload.entry }
    history.value = (payload.entry?.history ?? []).slice().reverse()
    dialog.value.open = false
    await Promise.all([reload(), loadStats()])
  } catch (error) {
    dialog.value.error = error instanceof Error ? error.message : '签收信息保存失败'
  } finally {
    dialog.value.saving = ''
  }
}

async function runAction(action: string) {
  if (editingId.value === null) return
  dialog.value.error = ''
  if (action === '登记签收' && (!form.value['签收方'] || !form.value['签收日期'])) {
    dialog.value.error = '登记签收前需填写签收方与签收日期'
    return
  }
  if (action === '记录异常' && !form.value['异常备注']) {
    dialog.value.error = '记录异常前需填写异常备注'
    return
  }
  dialog.value.saving = 'action'
  try {
    const response = await request(`${ENDPOINT}/${editingId.value}/actions`, {
      method: 'POST',
      body: JSON.stringify({ values: { action, ...editablePayload() } }),
    })
    const payload = await response.json().catch(() => null)
    if (!response.ok || !payload?.ok) {
      throw new Error(payload?.message ?? '回单动作未生效')
    }
    form.value = { ...form.value, ...payload.entry }
    history.value = (payload.entry?.history ?? []).slice().reverse()
    dialog.value.open = false
    await Promise.all([reload(), loadStats()])
  } catch (error) {
    dialog.value.error = error instanceof Error ? error.message : '回单操作失败'
  } finally {
    dialog.value.saving = ''
  }
}

async function submitCreate() {
  dialog.value.error = ''
  if (!form.value['回单编号'] || !form.value['关联任务'] || !form.value['签收方']) {
    dialog.value.error = '请填写回单编号、关联任务与签收方'
    return
  }
  dialog.value.saving = 'create'
  try {
    const response = await request(ENDPOINT, {
      method: 'POST',
      body: JSON.stringify({
        values: {
          回单编号: form.value['回单编号'],
          关联任务: form.value['关联任务'],
          签收方: form.value['签收方'],
          签收日期: form.value['签收日期'],
          签收人: form.value['签收人'],
          异常备注: form.value['异常备注'],
        },
      }),
    })
    const payload = await response.json().catch(() => null)
    if (!response.ok || !payload?.ok) {
      throw new Error(payload?.message ?? '回执单登记失败')
    }
    dialog.value.open = false
    await Promise.all([reload(), loadStats()])
  } catch (error) {
    dialog.value.error = error instanceof Error ? error.message : '回执单登记失败'
  } finally {
    dialog.value.saving = ''
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
      throw new Error('回执单列表读取失败')
    }
    const payload = await response.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '回单管理列表读取失败'
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
.status-tag[data-status='已签收'] {
  background: #dcfce7;
  color: #166534;
}
.status-tag[data-status='有异常'] {
  background: #fee2e2;
  color: #991b1b;
}
.status-tag[data-status='已上传'] {
  background: #dbeafe;
  color: #1e40af;
}
.modal-mask {
  position: fixed;
  inset: 0;
  background: rgba(15, 23, 42, 0.45);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 50;
}
.modal {
  width: min(720px, 92vw);
  max-height: 88vh;
  overflow-y: auto;
  background: #fff;
  border-radius: 10px;
  padding: 16px 20px;
}
.modal-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.modal-head h3 {
  margin: 0;
  font-size: 16px;
}
.modal-status {
  margin: 10px 0;
  font-size: 13px;
  display: flex;
  gap: 12px;
  align-items: center;
}
.modal-hint {
  color: var(--muted);
  font-size: 12px;
}
.form-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px 14px;
}
.form-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 13px;
}
.form-item-wide {
  grid-column: 1 / -1;
}
.form-item em {
  color: #b42318;
  font-style: normal;
}
.form-item input,
.form-item textarea,
.form-item select {
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 6px 8px;
  font: inherit;
}
.form-item input:disabled {
  background: #f1f5f9;
  color: var(--muted);
}
.photo-row {
  display: flex;
  gap: 10px;
  align-items: center;
}
.history-box {
  margin-top: 12px;
  border-top: 1px dashed var(--border);
  padding-top: 8px;
  max-height: 140px;
  overflow-y: auto;
}
.history-box h4 {
  margin: 4px 0;
  font-size: 13px;
}
.history-box ul {
  margin: 0;
  padding-left: 16px;
  font-size: 12px;
  color: #475569;
}
.history-time {
  color: var(--muted);
  margin-right: 6px;
}
.modal-foot {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 14px;
}
</style>
