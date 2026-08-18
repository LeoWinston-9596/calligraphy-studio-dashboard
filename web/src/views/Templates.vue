<template>
  <!-- 评语模板库（规格书 §5.2）：所有人可增删改，按 书法/美术/通用 分组 -->
  <div class="tabs">
    <button v-for="c in categories" :key="c" :class="{ on: cat === c }" @click="cat = c">
      {{ c }}（{{ grouped[c]?.length || 0 }}）
    </button>
  </div>

  <div class="card">
    <h3>新增模板</h3>
    <div class="field">
      <textarea v-model="draft" placeholder="输入常用评语，老师上传作品时可一键选用"></textarea>
    </div>
    <button class="btn" :disabled="!draft.trim()" @click="add">添加到「{{ cat }}」</button>
  </div>

  <div v-if="!grouped[cat]?.length" class="empty">该分组暂无模板</div>
  <div v-for="t in grouped[cat]" :key="t.id" class="card">
    <EditBadge :count="t.edit_count" :badge="t.edit_badge" :logs-url="`/api/eval-templates/${t.id}/logs`" />
    <template v-if="editingId === t.id">
      <div class="field"><textarea v-model="editText"></textarea></div>
      <div class="row">
        <button class="btn sm" @click="save(t)">保存</button>
        <button class="btn ghost sm" @click="editingId = null">取消</button>
      </div>
    </template>
    <template v-else>
      <p style="margin:0 60px 10px 0;white-space:pre-wrap">{{ t.text }}</p>
      <div class="row">
        <button class="btn ghost sm" @click="startEdit(t)">编辑</button>
        <button class="btn ghost sm" @click="remove(t)">删除</button>
        <select class="btn ghost sm" :value="t.category" @change="move(t, $event.target.value)">
          <option v-for="c in categories" :key="c" :value="c">移到 {{ c }}</option>
        </select>
      </div>
    </template>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { del, get, patch, post, toast } from '../api'
import EditBadge from '../components/EditBadge.vue'

const categories = ['书法', '美术', '通用']
const cat = ref('通用')
const list = ref([])
const draft = ref('')
const editingId = ref(null)
const editText = ref('')

const grouped = computed(() => {
  const g = { 书法: [], 美术: [], 通用: [] }
  for (const t of list.value) (g[t.category] || (g[t.category] = [])).push(t)
  return g
})

async function load() { list.value = await get('/api/eval-templates') }

async function add() {
  await post('/api/eval-templates', { category: cat.value, text: draft.value.trim(), sort: list.value.length })
  draft.value = ''
  toast('已添加')
  await load()
}

function startEdit(t) { editingId.value = t.id; editText.value = t.text }

async function save(t) {
  const r = await patch(`/api/eval-templates/${t.id}`, { text: editText.value })
  editingId.value = null
  toast(r.changed.length ? '已保存' : '没有变更')
  await load()
}

async function move(t, category) {
  if (category === t.category) return
  await patch(`/api/eval-templates/${t.id}`, { category })
  toast('已移动到 ' + category)
  await load()
}

async function remove(t) {
  if (!confirm('确定删除这条模板吗？')) return
  await del(`/api/eval-templates/${t.id}`)
  toast('已删除')
  await load()
}

onMounted(load)
</script>
