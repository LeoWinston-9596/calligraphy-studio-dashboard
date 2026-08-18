<template>
  <!-- 老师工作台（规格书 §5.2）：我的班级 → 班级学员九宫格 → 上传页 -->
  <div class="tabs">
    <button :class="{ on: scope === 'mine' }" @click="scope = 'mine'">
      我的班级<span v-if="mine.length">（{{ mine.length }}）</span>
    </button>
    <button :class="{ on: scope === 'all' }" @click="scope = 'all'">全部班级（{{ all.length }}）</button>
  </div>

  <div class="search">
    <input v-model="kw" placeholder="搜索班级名称" />
  </div>

  <p v-if="scope === 'mine' && !mine.length" class="muted" style="margin-bottom:12px">
    当前账号还没匹配到班级。到<RouterLink to="/users">用户管理</RouterLink>把账号对到导入表里的「跟进人」，
    以后新开的班导入后会自动归属。下面先显示全部班级。
  </p>
  <p v-else-if="scope === 'mine' && store.meta.auto_bind_classes" class="muted" style="margin-bottom:12px">
    按导入表「跟进人：{{ (store.meta.teacher_names || []).join('、') || store.user.name }}」自动匹配，共 {{ mine.length }} 个班。
  </p>

  <div v-if="!shown.length" class="empty">暂无班级数据，请先在<RouterLink to="/import">数据导入</RouterLink>中导入「学生报读课程」。</div>

  <div v-else class="grid-auto">
    <div v-for="c in shown" :key="c" class="cell" @click="$router.push('/class/' + encodeURIComponent(c))">
      <div class="name">{{ c }}</div>
      <div class="muted">{{ store.meta.class_course_map[c] || '—' }}</div>
    </div>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import { store } from '../api'

const scope = ref('mine')
const kw = ref('')

const all = computed(() => store.meta.classes || [])
const mine = computed(() => (store.meta.my_classes || []).filter((c) => all.value.includes(c)))

const shown = computed(() => {
  const base = scope.value === 'mine' && mine.value.length ? mine.value : all.value
  const k = kw.value.trim()
  return k ? base.filter((c) => c.includes(k)) : base
})
</script>
