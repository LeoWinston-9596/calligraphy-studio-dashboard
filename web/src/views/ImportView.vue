<template>
  <!-- Excel 导入（规格书 §4）：拖拽上传 → 预览前 5 行 → 确认 → 覆盖式更新 -->
  <div class="card">
    <h3>导入教务导出的 Excel</h3>
    <p class="muted">支持 4 种格式，系统按列名自动识别：在读学员名单、学生报读课程、订单导出、收支明细。</p>
    <div class="drop" :class="{ over }" @click="picker.click()"
         @dragover.prevent="over = true" @dragleave.prevent="over = false" @drop.prevent="onDrop">
      <div style="font-size:30px">📄</div>
      {{ busy ? '解析中…' : '把文件拖到这里，或点击选择（.xls / .xlsx）' }}
    </div>
    <input ref="picker" type="file" accept=".xls,.xlsx" hidden @change="onPick" />
  </div>

  <!-- 预览 -->
  <div v-if="pv" class="card">
    <h3>预览：{{ pv.file_type_label }}</h3>
    <div class="kv"><span class="k">文件</span><span class="v">{{ pv.filename }}</span></div>
    <div class="kv"><span class="k">总行数</span><span class="v">{{ pv.total_rows }}</span></div>
    <div class="kv" v-if="pv.missing_columns.length">
      <span class="k">缺少的列</span><span class="v" style="color:var(--danger)">{{ pv.missing_columns.join('、') }}</span>
    </div>
    <p class="muted" style="margin:8px 0">前 5 行预览：</p>
    <div class="table-wrap">
      <table>
        <thead><tr><th v-for="c in pv.columns" :key="c">{{ c }}</th></tr></thead>
        <tbody>
          <tr v-for="(r, i) in pv.rows" :key="i"><td v-for="(v, j) in r" :key="j">{{ v }}</td></tr>
        </tbody>
      </table>
    </div>
    <p class="muted" style="margin:10px 0">
      ⚠️ 确认后将以本次文件为准<strong>整表覆盖更新</strong>同类型数据（导入不算编辑，不产生编辑角标）。
    </p>
    <div class="row">
      <button class="btn" :disabled="busy" @click="confirmImport">确认导入</button>
      <button class="btn ghost" @click="pv = null">取消</button>
    </div>
  </div>

  <!-- 导入报告 -->
  <div v-if="report" class="card">
    <h3>导入报告 · {{ report.file_type_label }}</h3>
    <div class="kv"><span class="k">导入时间</span><span class="v">{{ report.imported_at }}</span></div>
    <div class="kv"><span class="k">文件行数</span><span class="v">{{ report.rows }}</span></div>
    <div class="kv" v-if="report.students_created !== undefined"><span class="k">新增学员</span><span class="v">{{ report.students_created }}</span></div>
    <div class="kv" v-if="report.students_updated !== undefined"><span class="k">更新学员</span><span class="v">{{ report.students_updated }}</span></div>
    <div class="kv" v-if="report.students_off_list"><span class="k">不在最新名单</span><span class="v">{{ report.students_off_list }}</span></div>
    <div class="kv" v-if="report.accounts_imported !== undefined"><span class="k">课程账户</span><span class="v">{{ report.accounts_imported }}</span></div>
    <div class="kv" v-if="report.class_course_pairs"><span class="k">班级→课程映射</span><span class="v">{{ report.class_course_pairs }} 条</span></div>
    <div class="kv" v-if="report.orders_imported !== undefined"><span class="k">订单</span><span class="v">{{ report.orders_imported }}</span></div>
    <div class="kv" v-if="report.transactions_imported !== undefined"><span class="k">收支记录</span><span class="v">{{ report.transactions_imported }}</span></div>

    <template v-if="problems.length">
      <p class="muted" style="margin:10px 0 4px">无法匹配 / 需注意的行（{{ problems.length }}）：</p>
      <div class="table-wrap">
        <table>
          <thead><tr><th>行号</th><th>学员</th><th>原因</th></tr></thead>
          <tbody>
            <tr v-for="(u, i) in problems.slice(0, 100)" :key="i">
              <td>{{ u.row }}</td><td>{{ u.student || '—' }}</td>
              <td style="white-space:normal">{{ u.reason }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </template>
    <p v-else class="muted" style="margin-top:10px">✅ 全部行均已成功入库。</p>

    <!-- 偏差报告 -->
    <template v-if="report.deviation">
      <h3 style="margin-top:16px">偏差报告（上期估算 vs 本期导入）</h3>
      <p v-if="!report.deviation.available" class="muted">{{ report.deviation.reason }}</p>
      <template v-else>
        <p class="muted">
          对比上期（{{ report.deviation.prev_imported_at }}）共 {{ report.deviation.compared }} 个账户，
          差值 ≠ 0 的有 <strong>{{ report.deviation.count }}</strong> 个。系统不做任何自动修正。
        </p>
        <div v-if="report.deviation.count" class="table-wrap">
          <table>
            <thead><tr><th>学号</th><th>学员</th><th>课程</th><th>上期估算</th><th>本期导入</th><th>差值</th></tr></thead>
            <tbody>
              <tr v-for="(d, i) in report.deviation.items" :key="i">
                <td>{{ d.student_no }}</td><td>{{ d.student_name }}</td><td>{{ d.course_name }}</td>
                <td>{{ d.estimated }}</td><td>{{ d.actual }}</td>
                <td :style="{ color: d.diff > 0 ? 'var(--danger)' : 'var(--ok)' }">{{ d.diff > 0 ? '+' : '' }}{{ d.diff }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </template>
    </template>
  </div>

  <!-- 历史批次 -->
  <div class="card">
    <h3>导入历史</h3>
    <div v-if="!batches.length" class="muted">暂无记录</div>
    <div v-for="b in batches" :key="b.id" class="kv">
      <span class="k">{{ b.imported_at }}</span>
      <span class="v">
        {{ b.file_type_label }} · {{ b.row_count }} 行 · {{ b.imported_by }}
        <button class="btn ghost sm" @click="viewBatch(b.id)">查看报告</button>
      </span>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { get, post, refreshMeta, toast, upload } from '../api'

const picker = ref(null)
const over = ref(false)
const busy = ref(false)
const pv = ref(null)
const report = ref(null)
const batches = ref([])

const problems = computed(() => [
  ...(report.value?.unmatched || []),
  ...(report.value?.skipped || []),
])

function onPick(e) { const f = e.target.files?.[0]; if (f) send(f); e.target.value = '' }
function onDrop(e) { over.value = false; const f = e.dataTransfer.files?.[0]; if (f) send(f) }

async function send(file) {
  busy.value = true
  report.value = null
  try {
    const fd = new FormData()
    fd.append('file', file, file.name)
    pv.value = await upload('/api/imports/preview', fd)
  } catch (e) { toast('解析失败：' + e.message) } finally { busy.value = false }
}

async function confirmImport() {
  busy.value = true
  try {
    report.value = await post('/api/imports/confirm', { token: pv.value.token, filename: pv.value.filename })
    pv.value = null
    toast('导入完成')
    await refreshMeta()
    await loadBatches()
  } catch (e) { toast('导入失败：' + e.message) } finally { busy.value = false }
}

async function loadBatches() { batches.value = await get('/api/imports/batches') }

async function viewBatch(id) {
  const b = await get(`/api/imports/batches/${id}`)
  report.value = { ...b.summary, file_type_label: b.file_type_label, imported_at: b.imported_at }
  window.scrollTo({ top: 0, behavior: 'smooth' })
}

onMounted(loadBatches)
</script>
