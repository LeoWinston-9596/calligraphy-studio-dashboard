<template>
  <p v-if="loading" class="muted">加载中…</p>
  <template v-else>
    <!-- 基本信息卡（可编辑） -->
    <div class="card">
      <EditBadge :count="s.edit_count" :badge="s.edit_badge" :logs-url="`/api/students/${s.id}/logs`" />
      <h3>{{ s.name }} <span class="pill gray">{{ s.status }}</span></h3>

      <template v-if="!editing">
        <div class="kv"><span class="k">学号</span><span class="v">{{ s.student_no || '—' }}</span></div>
        <div class="kv"><span class="k">手机号</span><span class="v">{{ s.phone || '—' }}<span v-if="s.phone_identity"> （{{ s.phone_identity }}）</span></span></div>
        <div class="kv" v-if="s.alt_phone"><span class="k">备用手机</span><span class="v">{{ s.alt_phone }}</span></div>
        <div class="kv"><span class="k">性别 / 年级</span><span class="v">{{ s.gender || '—' }} / {{ s.grade || '—' }}</span></div>
        <div class="kv" v-if="s.school"><span class="k">学校</span><span class="v">{{ s.school }}</span></div>
        <div class="kv"><span class="k">所在班级</span><span class="v">{{ (s.classes || []).join('、') || '—' }}</span></div>
        <div class="kv">
          <span class="k">跟进人</span>
          <span class="v">
            <template v-if="s.follow_up_persons?.length">
              <span v-for="t in s.follow_up_persons" :key="t" class="pill" style="margin-left:4px">{{ t }}</span>
            </template>
            <template v-else>—</template>
          </span>
        </div>
        <div class="kv" v-if="s.tags"><span class="k">标签</span><span class="v">{{ s.tags }}</span></div>
        <div class="kv" v-if="s.remark"><span class="k">备注</span><span class="v">{{ s.remark }}</span></div>
        <div class="kv"><span class="k">合计剩余</span><span class="v"><BalanceChip :balance="s.total_balance" /></span></div>
        <div class="row" style="margin-top:12px">
          <button class="btn ghost sm" @click="startEdit">编辑信息</button>
          <button class="btn ghost sm" @click="exportPortfolio">导出作品集</button>
          <button class="btn sm" @click="$router.push('/upload/' + s.id)">上传作品</button>
        </div>
      </template>

      <template v-else>
        <div class="row">
          <div class="field"><label>姓名</label><input v-model="form.name" /></div>
          <div class="field"><label>学号</label><input v-model="form.student_no" /></div>
        </div>
        <div class="row">
          <div class="field"><label>手机号</label><input v-model="form.phone" /></div>
          <div class="field"><label>年级</label><input v-model="form.grade" /></div>
        </div>
        <div class="row">
          <div class="field"><label>学校</label><input v-model="form.school" /></div>
          <div class="field"><label>来源</label><input v-model="form.source" /></div>
        </div>
        <p class="muted" style="margin:-4px 0 12px">
          跟进人按班级设置，见下方「班级与跟进人」。
        </p>
        <div class="field"><label>所在班级（多个用逗号分隔）</label><input v-model="form.classes" /></div>
        <div class="field"><label>标签</label><input v-model="form.tags" /></div>
        <div class="field"><label>备注</label><textarea v-model="form.remark"></textarea></div>
        <div class="row">
          <button class="btn" :disabled="saving" @click="save">保存</button>
          <button class="btn ghost" @click="editing = false">取消</button>
        </div>
      </template>
    </div>

    <!-- 班级与跟进人：一个学员可以在不同班跟不同老师 -->
    <h3 style="margin:16px 0 8px;font-size:15px">班级与跟进人</h3>
    <div v-if="!s.class_teachers?.length" class="empty">该学员还没有班级</div>
    <div v-for="ct in s.class_teachers" :key="ct.class_name" class="card">
      <EditBadge :count="ct.edit_count" :badge="ct.edit_badge" :logs-url="`/api/students/${s.id}/logs`" />
      <h3>{{ ct.class_name || '未分班' }}</h3>
      <div class="muted" style="margin-bottom:8px">{{ ct.course_name || '—' }}</div>

      <template v-if="editingClass === ct.class_name">
        <TeacherPicker v-model="draftTeachers" :options="store.meta.follow_up_persons || []"
                       :counts="classCounts" />
        <div class="row" style="margin-top:10px">
          <button class="btn sm" :disabled="saving" @click="saveTeachers(ct)">保存</button>
          <button class="btn ghost sm" @click="editingClass = null">取消</button>
        </div>
      </template>
      <template v-else>
        <div class="kv">
          <span class="k">跟进人</span>
          <span class="v">
            <template v-if="ct.teachers.length">
              <span v-for="t in ct.teachers" :key="t" class="pill" style="margin-left:4px">{{ t }}</span>
            </template>
            <template v-else><span class="muted">未设置</span></template>
          </span>
        </div>
        <div class="kv" v-if="ct.updated_by">
          <span class="k">最近修改</span><span class="v">{{ ct.updated_by }}</span>
        </div>
        <button class="btn ghost sm" style="margin-top:8px" @click="startEditTeachers(ct)">
          修改跟进人
        </button>
      </template>
    </div>

    <!-- 课时账户卡（两种口径） -->
    <h3 style="margin:16px 0 8px;font-size:15px">课时账户（{{ s.mode === 'imported' ? '导入口径' : '估算口径' }}）</h3>
    <div v-if="!s.accounts?.length" class="empty">暂无课时账户</div>
    <div v-for="a in s.accounts" :key="a.id" class="card">
      <h3>{{ a.course_name }} <span class="pill gray">{{ a.course_type }}</span></h3>
      <div class="muted" style="margin-bottom:8px">{{ a.class_name }}</div>
      <div class="kv"><span class="k">导入口径剩余</span><span class="v">{{ a.balance.imported }} 课时</span></div>
      <div class="kv">
        <span class="k">估算口径剩余</span>
        <span class="v">约 {{ a.balance.estimated }} 课时
          <button class="btn ghost sm" @click="a._open = !a._open">算式</button>
        </span>
      </div>
      <p v-if="a._open" class="muted">
        {{ a.balance.detail }}
        <span v-if="a.balance.used_dates.length">（评价日期：{{ a.balance.used_dates.join('、') }}）</span>
      </p>
      <div class="kv"><span class="k">购买 / 赠送 / 消耗</span><span class="v">{{ a.purchased }} / {{ a.gifted }} / {{ a.consumed }}</span></div>
      <div class="kv"><span class="k">缺课次数</span><span class="v">{{ a.absent_count }}</span></div>
      <div class="kv"><span class="k">到期时间</span><span class="v">{{ a.expire_date || '—' }}</span></div>
      <div class="kv"><span class="k">剩余课消金额</span><span class="v">¥{{ a.remaining_amount?.toFixed(2) }}</span></div>
    </div>

    <!-- 作品时间轴（倒序） -->
    <h3 style="margin:16px 0 8px;font-size:15px">作品时间轴（{{ timeline.length }}）</h3>
    <div v-if="!timeline.length" class="empty">还没有作品记录</div>
    <div v-for="a in timeline" :key="a.id" class="card timeline-item">
      <EditBadge :count="a.edit_count" :badge="a.edit_badge" :logs-url="`/api/artworks/${a.id}/logs`" />
      <h3>
        {{ a.lesson_date }}
        <span v-if="a.rating" class="pill">{{ a.rating }}</span>
      </h3>
      <div class="muted" style="margin-bottom:8px">{{ a.course_name }} · {{ a.class_name }} · {{ a.created_by }}</div>

      <div v-if="a.photos.length" class="photos">
        <img v-for="(p, i) in a.photos" :key="i" :src="p" @click="viewer = p" />
      </div>
      <p v-if="a.eval_type === 'text' && a.eval_text" style="white-space:pre-wrap;margin:10px 0 0">{{ a.eval_text }}</p>
      <audio v-if="a.eval_audio" :src="a.eval_audio" controls preload="none" />

      <!-- 语音的文字稿 -->
      <div v-if="a.eval_audio" class="transcript">
        <template v-if="editingTx === a.id">
          <textarea v-model="txDraft" rows="3"></textarea>
          <div class="row" style="margin-top:6px">
            <button class="btn sm" :disabled="saving" @click="saveTx(a)">保存文字稿</button>
            <button class="btn ghost sm" @click="editingTx = null">取消</button>
          </div>
        </template>
        <template v-else>
          <p v-if="a.transcript" style="white-space:pre-wrap;margin:0">
            {{ a.transcript }}
            <span class="pill gray" style="margin-left:4px">
              {{ a.transcript_edited ? '已人工校对' : '语音转文字' }}
            </span>
            <span v-if="a.transcript_corrections?.length" class="muted" style="font-size:12px">
              已纠正 {{ a.transcript_corrections.map(c => c.from + '→' + c.to).join('、') }}
            </span>
          </p>
          <p v-else-if="a.transcript_status === 'pending'" class="muted" style="margin:0">
            ⏳ 正在转文字…
          </p>
          <p v-else-if="a.transcript_status === 'failed'" class="muted" style="margin:0">
            转文字失败：{{ a.transcript_error }}
          </p>
          <p v-else class="muted" style="margin:0">未转文字</p>
          <div class="row" style="margin-top:6px">
            <button class="btn ghost sm" @click="startEditTx(a)">
              {{ a.transcript ? '校对文字稿' : '手动填写' }}
            </button>
            <button class="btn ghost sm" :disabled="saving" @click="retranscribe(a)">重新转写</button>
          </div>
        </template>
      </div>

      <div class="row" style="margin-top:10px">
        <button class="btn ghost sm" @click="startEditArt(a)">修改评价</button>
        <button class="btn ghost sm" @click="removeArt(a)">删除</button>
      </div>
    </div>
  </template>

  <div v-if="viewer" class="mask" @click="viewer = ''">
    <img :src="viewer" style="max-width:94vw;max-height:88vh;border-radius:10px" />
  </div>

  <Sheet v-if="editArt" title="修改评价" @close="editArt = null">
    <div class="field">
      <label>上课日期</label>
      <input v-model="artForm.lesson_date" type="date" />
    </div>
    <div class="field">
      <label>评价文字</label>
      <textarea v-model="artForm.eval_text"></textarea>
    </div>
    <div class="field">
      <label>评级</label>
      <select v-model="artForm.rating">
        <option value="">不评级</option>
        <option>优</option><option>良</option><option>需加强</option>
      </select>
    </div>
    <button class="btn block" :disabled="saving" @click="saveArt">保存修改</button>
  </Sheet>
</template>

<script setup>
import { computed, onMounted, onUnmounted, reactive, ref } from 'vue'
import { useRoute } from 'vue-router'
import { del, get, patch, post, refreshMeta, store, toast, upload } from '../api'
import BalanceChip from '../components/BalanceChip.vue'
import EditBadge from '../components/EditBadge.vue'
import Sheet from '../components/Sheet.vue'
import TeacherPicker from '../components/TeacherPicker.vue'

const route = useRoute()
const id = route.params.id
const s = ref({})
const timeline = ref([])
const loading = ref(true)
const editing = ref(false)
const saving = ref(false)
const viewer = ref('')
const editArt = ref(null)
const form = reactive({})
const artForm = reactive({})
const editingClass = ref(null)
const draftTeachers = ref([])
const teacherList = ref([])
const editingTx = ref(null)
const txDraft = ref('')
let txTimer = null

// 每个老师带几个班，选择时给个参考
const classCounts = computed(() => Object.fromEntries(
  teacherList.value.map((t) => [t.name, t.class_count])
))

async function load() {
  s.value = await get(`/api/students/${id}`)
  timeline.value = await get(`/api/students/${id}/timeline`)
}

onMounted(async () => {
  try {
    await load()
    teacherList.value = await get('/api/users/teachers')
    pollIfPending()
  } finally { loading.value = false }
})

onUnmounted(() => clearTimeout(txTimer))

function startEditTx(a) {
  editingTx.value = a.id
  txDraft.value = a.transcript || ''
}

async function saveTx(a) {
  saving.value = true
  try {
    const r = await patch(`/api/artworks/${a.id}/transcript`, { text: txDraft.value })
    toast(r.changed?.length ? '文字稿已保存' : '没有变更')
    editingTx.value = null
    await load()
  } catch (e) { toast('保存失败：' + e.message) } finally { saving.value = false }
}

async function retranscribe(a) {
  saving.value = true
  try {
    await post(`/api/artworks/${a.id}/transcribe`)
    toast('已重新转写')
    await load()
  } catch (e) { toast(e.message) } finally { saving.value = false }
}

// 有正在转写的条目就轮询，转完自动刷新出来
function pollIfPending() {
  clearTimeout(txTimer)
  if (timeline.value.some((a) => a.transcript_status === 'pending')) {
    txTimer = setTimeout(async () => { await load(); pollIfPending() }, 4000)
  }
}

function startEditTeachers(ct) {
  editingClass.value = ct.class_name
  draftTeachers.value = [...ct.teachers]
}

async function saveTeachers(ct) {
  saving.value = true
  try {
    const r = await patch(`/api/students/${id}/class-teachers`, {
      class_name: ct.class_name,
      teachers: draftTeachers.value,
    })
    toast(r.changed.length ? '跟进人已更新' : '没有变更')
    editingClass.value = null
    await load()
    await refreshMeta()
  } catch (e) { toast('保存失败：' + e.message) } finally { saving.value = false }
}

function startEdit() {
  Object.assign(form, {
    name: s.value.name, student_no: s.value.student_no, phone: s.value.phone,
    grade: s.value.grade, school: s.value.school,
    source: s.value.source, tags: s.value.tags,
    remark: s.value.remark, classes: (s.value.classes || []).join('，'),
  })
  editing.value = true
}

async function save() {
  saving.value = true
  try {
    const r = await patch(`/api/students/${id}`, { ...form })
    toast(r.changed.length ? `已保存，${r.changed.length} 处变更` : '没有变更')
    editing.value = false
    await load()
  } catch (e) { toast('保存失败：' + e.message) } finally { saving.value = false }
}

function startEditArt(a) {
  editArt.value = a
  Object.assign(artForm, { lesson_date: a.lesson_date, eval_text: a.eval_text, rating: a.rating })
}

async function saveArt() {
  saving.value = true
  try {
    const fd = new FormData()
    fd.append('lesson_date', artForm.lesson_date)
    fd.append('eval_text', artForm.eval_text || '')
    fd.append('rating', artForm.rating || '')
    if ((artForm.eval_text || '').trim() && editArt.value.eval_type === 'none') fd.append('eval_type', 'text')
    const r = await upload(`/api/artworks/${editArt.value.id}`, fd, 'PATCH')
    toast(r.changed?.length ? '已保存修改' : '没有变更')
    editArt.value = null
    await load()
  } catch (e) { toast('保存失败：' + e.message) } finally { saving.value = false }
}

async function removeArt(a) {
  if (!confirm(`确定删除 ${a.lesson_date} 的这条记录吗？删除后可在编辑记录中查看。`)) return
  await del(`/api/artworks/${a.id}`)
  toast('已删除')
  await load()
  await refreshMeta()
}

function exportPortfolio() {
  window.open(`/api/students/${id}/portfolio`, '_blank')
}
</script>
