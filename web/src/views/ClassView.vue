<template>
  <div class="card">
    <h3>{{ className }}</h3>
    <div class="muted">课程：{{ data.course_name || '—' }} · 学员 {{ data.count || 0 }} 人</div>
  </div>

  <p v-if="loading" class="muted">加载中…</p>
  <div v-else-if="!data.items?.length" class="empty">该班级暂无学员</div>

  <div v-else class="grid-3">
    <div v-for="s in data.items" :key="s.id" class="cell" @click="$router.push('/upload/' + s.id)">
      <div class="name">{{ s.name }}</div>
      <BalanceChip :balance="s.balance" :threshold="threshold" />
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { get, store } from '../api'
import BalanceChip from '../components/BalanceChip.vue'

const route = useRoute()
const className = computed(() => decodeURIComponent(route.params.name))
const data = ref({})
const loading = ref(true)
const threshold = ref(3)

onMounted(async () => {
  try {
    data.value = await get(`/api/classes/${encodeURIComponent(className.value)}/students`)
    const s = await get('/api/settings')
    threshold.value = Number(s.settings.renew_threshold) || 3
  } finally { loading.value = false }
})
</script>
