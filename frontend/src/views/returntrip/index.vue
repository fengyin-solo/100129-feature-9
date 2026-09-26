<template>
  <section class="page" data-module="returntrip">
    <header class="page-head">
      <div>
        <h2>回单管理</h2>
        <p class="page-desc">维护回执单，围绕回单编号、关联任务、签收方、签收日期做登记、签收与状态流转，编辑结果按回单编号持久保存。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">登记回执单</button>
        <button class="btn" type="button" @click="exportRows">导出回单清单</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
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
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)">
          <td v-for="column in columns" :key="column">
            <template v-if="column === '回单照片'">
              <a v-if="isPhoto(row[column])" :href="String(row[column])" target="_blank" rel="noopener">
                <img class="receipt-thumb" :src="String(row[column])" alt="回单照片" />
              </a>
              <span v-else-if="row[column]">
                <a :href="String(row[column])" target="_blank" rel="noopener">查看附件</a>
              </span>
              <span v-else>—</span>
            </template>
            <template v-else>{{ row[column] || '—' }}</template>
          </td>
          <td class="row-actions">
            <button class="link" type="button" @click="openEdit(row)">签收/编辑</button>
            <button class="link" type="button" @click="openAbnormal(row)">记录异常</button>
            <button class="link" type="button" @click="openUpload(row)">上传回单</button>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 1" class="empty-state">暂无回单数据，可先登记回执单</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条回单记录</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>

    <div v-if="dialog.visible" class="modal-mask" @click.self="closeDialog">
      <div class="modal">
        <h3 class="modal-title">{{ dialog.title }}</h3>
        <div v-if="dialog.mode === 'abnormal'" class="form-grid">
          <label class="form-item form-wide">
            <span>异常备注 *</span>
            <textarea v-model="form.异常备注" rows="3" placeholder="填写签收时发现的异常情况"></textarea>
          </label>
        </div>
        <div v-else-if="dialog.mode === 'photo'" class="form-grid">
          <label class="form-item form-wide">
            <span>回单照片 *</span>
            <input type="file" accept="image/*" @change="onPickPhoto" />
            <small class="form-hint">照片随回单编号一起留存，重新打开仍是这一张。</small>
            <a v-if="form.回单照片" :href="form.回单照片" target="_blank" rel="noopener">
              <img class="receipt-preview" :src="form.回单照片" alt="回单照片预览" />
            </a>
          </label>
        </div>
        <div v-else class="form-grid">
          <label class="form-item">
            <span>回单编号 *</span>
            <input v-model="form.回单编号" :disabled="dialog.mode === 'edit'" placeholder="例如 RETU-0009" />
          </label>
          <label class="form-item">
            <span>关联任务（配送任务编号）</span>
            <input v-model="form.关联任务" placeholder="例如 DOOR-0001，用于与配送记录同步" />
          </label>
          <label class="form-item">
            <span>签收方</span>
            <input v-model="form.签收方" placeholder="签收单位/门店" />
          </label>
          <label class="form-item">
            <span>签收日期</span>
            <input v-model="form.签收日期" type="date" />
          </label>
          <label class="form-item">
            <span>签收人</span>
            <input v-model="form.签收人" placeholder="实际签收人" />
          </label>
          <label class="form-item">
            <span>回单状态</span>
            <select v-model="form.status">
              <option v-for="status in statuses" :key="status" :value="status">{{ status }}</option>
            </select>
          </label>
          <label class="form-item form-wide">
            <span>异常备注</span>
            <textarea v-model="form.异常备注" rows="2" placeholder="没有异常可留空"></textarea>
          </label>
          <label class="form-item form-wide">
            <span>回单照片</span>
            <input type="file" accept="image/*" @change="onPickPhoto" />
            <a v-if="form.回单照片" :href="form.回单照片" target="_blank" rel="noopener">
              <img class="receipt-preview" :src="form.回单照片" alt="回单照片预览" />
            </a>
          </label>
        </div>
        <div class="modal-foot">
          <span v-if="dialog.error" class="error-text">{{ dialog.error }}</span>
          <button class="btn ghost" type="button" @click="closeDialog">取消</button>
          <button class="btn primary" type="button" :disabled="saving" @click="saveDialog">
            {{ saving ? '保存中…' : '保存' }}
          </button>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'

import { request } from '@/api/client'

type Row = Record<string, string | number | null>
type DialogMode = 'create' | 'edit' | 'abnormal' | 'photo'

const ENDPOINT = '/api/returntrip'
const columns = ['回单编号', '关联任务', '签收方', '签收日期', '签收人', '异常备注', '回单照片', '回单状态']
const statuses = ['待签收', '已签收', '有异常', '已上传']

const rows = ref<Row[]>([])
const total = ref(0)
const errorMessage = ref('')
const filters = reactive<{ keyword: string; status: string }>({ keyword: '', status: '' })

const stats = ref([
  { label: '待签收回单', value: 0 },
  { label: '已签收回单', value: 0 },
  { label: '异常回单', value: 0 },
  { label: '已上传回单', value: 0 },
])

const emptyForm = () => ({
  回单编号: '',
  关联任务: '',
  签收方: '',
  签收日期: '',
  签收人: '',
  异常备注: '',
  回单照片: '',
  status: '待签收',
})

const dialog = reactive<{
  visible: boolean
  mode: DialogMode
  title: string
  id: number | null
  error: string
}>({ visible: false, mode: 'create', title: '', id: null, error: '' })
const form = ref(emptyForm())
const saving = ref(false)

function resetFilters() {
  filters.keyword = ''
  filters.status = ''
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

function isPhoto(value: string | number | null | undefined): boolean {
  return typeof value === 'string' && value.startsWith('data:image/')
}

function onPickPhoto(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  if (file.size > 4 * 1024 * 1024) {
    dialog.error = '照片不能超过 4MB，请压缩后再上传'
    input.value = ''
    return
  }
  const reader = new FileReader()
  reader.onload = () => {
    form.value.回单照片 = String(reader.result ?? '')
    dialog.error = ''
  }
  reader.onerror = () => {
    dialog.error = '照片读取失败，请换一张再试'
  }
  reader.readAsDataURL(file)
}

function openCreate() {
  form.value = emptyForm()
  Object.assign(dialog, { visible: true, mode: 'create', title: '登记回执单', id: null, error: '' })
}

async function openEdit(row: Row) {
  dialog.error = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}`)
    if (!response.ok) throw new Error('回单明细读取失败')
    const detail = (await response.json()) as Row
    form.value = {
      回单编号: String(detail['回单编号'] ?? ''),
      关联任务: String(detail['关联任务'] ?? ''),
      签收方: String(detail['签收方'] ?? ''),
      签收日期: String(detail['签收日期'] ?? ''),
      签收人: String(detail['签收人'] ?? ''),
      异常备注: String(detail['异常备注'] ?? ''),
      回单照片: String(detail['回单照片'] ?? ''),
      status: String(detail['status'] ?? detail['回单状态'] ?? '待签收'),
    }
    Object.assign(dialog, { visible: true, mode: 'edit', title: `签收 / 编辑回单 ${form.value.回单编号}`, id: Number(row.id), error: '' })
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '回单明细读取失败'
  }
}

function openAbnormal(row: Row) {
  form.value = { ...emptyForm(), 异常备注: String(row['异常备注'] ?? ''), status: '有异常' }
  Object.assign(dialog, { visible: true, mode: 'abnormal', title: `记录异常 ${row['回单编号']}`, id: Number(row.id), error: '' })
}

function openUpload(row: Row) {
  form.value = { ...emptyForm(), 回单照片: String(row['回单照片'] ?? ''), status: '已上传' }
  Object.assign(dialog, { visible: true, mode: 'photo', title: `上传回单照片 ${row['回单编号']}`, id: Number(row.id), error: '' })
}

function closeDialog() {
  dialog.visible = false
  dialog.id = null
  dialog.error = ''
}

async function saveDialog() {
  dialog.error = ''
  if (dialog.id === null) {
    const required: Array<keyof typeof form.value> = ['回单编号', '关联任务', '签收方']
    const missing = required.filter((key) => !form.value[key].trim())
    if (missing.length) {
      dialog.error = `请填写${missing.join('、')}`
      return
    }
    saving.value = true
    try {
      const response = await request(ENDPOINT, {
        method: 'POST',
        body: JSON.stringify({ values: { ...form.value } }),
      })
      const payload = await response.json()
      if (!response.ok || payload.ok === false) {
        throw new Error(payload.message || '回执单登记失败')
      }
    } catch (error) {
      dialog.error = error instanceof Error ? error.message : '回执单登记失败'
      saving.value = false
      return
    }
  } else if (dialog.mode === 'abnormal') {
    if (!form.value.异常备注.trim()) {
      dialog.error = '请填写异常备注'
      return
    }
    saving.value = true
    try {
      const response = await request(`${ENDPOINT}/${dialog.id}/actions`, {
        method: 'POST',
        body: JSON.stringify({ values: { action: '记录异常', 异常备注: form.value.异常备注 } }),
      })
      const payload = await response.json()
      if (!response.ok || payload.ok === false) {
        throw new Error(payload.message || '异常记录未生效')
      }
    } catch (error) {
      dialog.error = error instanceof Error ? error.message : '异常记录未生效'
      saving.value = false
      return
    }
  } else if (dialog.mode === 'photo') {
    if (!form.value.回单照片) {
      dialog.error = '请先选择回单照片'
      return
    }
    saving.value = true
    try {
      const response = await request(`${ENDPOINT}/${dialog.id}/actions`, {
        method: 'POST',
        body: JSON.stringify({ values: { action: '上传回单', 回单照片: form.value.回单照片 } }),
      })
      const payload = await response.json()
      if (!response.ok || payload.ok === false) {
        throw new Error(payload.message || '回单照片未保存')
      }
    } catch (error) {
      dialog.error = error instanceof Error ? error.message : '回单照片未保存'
      saving.value = false
      return
    }
  } else {
    saving.value = true
    try {
      const response = await request(`${ENDPOINT}/${dialog.id}`, {
        method: 'PUT',
        body: JSON.stringify({ values: { ...form.value } }),
      })
      const payload = await response.json()
      if (!response.ok || payload.ok === false) {
        throw new Error(payload.message || '签收信息未保存')
      }
    } catch (error) {
      dialog.error = error instanceof Error ? error.message : '签收信息未保存'
      saving.value = false
      return
    }
  }
  saving.value = false
  closeDialog()
  await reload()
}

async function reload() {
  errorMessage.value = ''
  const query = new URLSearchParams()
  if (filters.keyword.trim()) query.set('keyword', filters.keyword.trim())
  if (filters.status) query.set('status', filters.status)
  try {
    const response = await request(`${ENDPOINT}?${query.toString()}`)
    if (!response.ok) {
      throw new Error('回执单列表读取失败')
    }
    const payload = await response.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
    updateStats()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '回单列表读取失败'
  }
}

async function updateStats() {
  // 统计口径始终取全量数据，避免当前筛选条件让分组结论失真。
  try {
    const response = await request(`${ENDPOINT}?size=200`)
    const payload = await response.json()
    const all = (payload.items ?? []) as Row[]
    stats.value[0].value = all.filter((row) => row['回单状态'] === '待签收').length
    stats.value[1].value = all.filter((row) => row['回单状态'] === '已签收').length
    stats.value[2].value = all.filter((row) => row['回单状态'] === '有异常').length
    stats.value[3].value = all.filter((row) => row['回单状态'] === '已上传').length
  } catch {
    // 统计失败不阻塞列表使用
  }
}

onMounted(reload)
</script>
