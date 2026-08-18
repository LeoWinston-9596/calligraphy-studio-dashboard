<template>
  <!-- 学员看板列表（规格书 §5.1） -->
  <div class="search">
    <input v-model="q" placeholder="姓名 / 学号 / 手机号" @keyup.enter="reload" />
    <select v-model="className" @change="reload">
      <option value="">全部班级</option>
      <option v-for="c in store.meta.classes" :key="c" :value="c">{{ c }}</option>
    </select>
    <select v-model="courseName" @change="reload">
      <option value="">全部课程</option>
      <option v-for="c in store.meta.courses" :key="c" :value="c">{{ c }}</option>
    </select>
    <select v-model="person" @change="reload">
      <option value="">全部跟进人</option>
      <option v-for="p in store.meta.follow_up_persons" :key="p" :value="p">{{ p }}</option>
    </select>
    <button class="btn sm" @click="reload">搜索</button>
  </div>

  <p class="muted" style="margin-bottom:8px">共 {{ total }} 人</p>
  <p v-if="loading" class="muted">加载中…</p>
  <div v-else-if="!items.length" class="empty">没有匹配的学员</div>

  <div v-for="s in items" :key="s.id" class="list-row" @click="$router.push('/students/' + s.id)">
    <div class="main">
      <div class="name">
        {{ s.name }}
        <span v-if="s.status !== '在读'" class="pill gray">{{ s.status }}</span>
        <EditBadge inline :count="s.edit_count" :badge="s.edit_badge" :logs-url="`/api/students/${s.id}/logs`" />
      </div>
      <div class="sub">
        {{ s.student_no }} · {{ s.phone }} · {{ (s.classes || []).join('、') || '无班级' }}
        <template v-if="s.follow_up_persons?.length"> · 跟进 {{ s.follow_up_persons.join('、') }}</template>
      </div>
    </div>
    <BalanceChip :balance="s.balance" :threshold="threshold" />
  </div>

  <div v-if="items.length < total" class="center" style="margin-top:12px">
    <button class="btn ghost" :disabled="loading" @click="more">加载更多</button>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { get, store } from '../api'
import BalanceChip from '../components/BalanceChip.vue'
import EditBadge from '../components/EditBadge.vue'

const q = ref('')
const className = ref('')
const courseName = ref('')
const person = ref('')
const items = ref([])
const total = ref(0)
const page = ref(1)
const loading = ref(false)
const threshold = ref(3)

async function load(append = false) {
  loading.value = true
  try {
    const data = await get('/api/students', {
      q: q.value, class_name: className.value, course_name: courseName.value,
      follow_up_person: person.value, page: page.value, page_size: 50,
    })
    items.value = append ? [...items.value, ...data.items] : data.items
    total.value = data.total
  } finally { loading.value = false }
}

function reload() { page.value = 1; load(false) }
function more() { page.value += 1; load(true) }

onMounted(async () => {
  const s = await get('/api/settings')
  threshold.value = Number(s.settings.renew_threshold) || 3
  load()
})
</script>
