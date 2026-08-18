<template>
  <!-- 编辑角标（规格书 §7）：0 不显示，1 已编辑，2 已二次编辑，≥3 已多次编辑 -->
  <button v-if="text" :class="inline ? 'badge-inline' : 'badge'" @click.stop="open">
    {{ text }}
  </button>

  <Sheet v-if="showing" title="编辑记录" @close="showing = false">
    <p v-if="loading" class="muted">加载中…</p>
    <p v-else-if="!logs.length" class="muted">暂无编辑记录</p>
    <div v-for="log in logs" :key="log.id" class="log-item">
      <div class="meta">
        {{ log.edited_at }} · {{ log.editor }}
        <span v-if="log.action === 'delete'" class="pill red">删除</span>
        <span v-else-if="log.action === 'restore'" class="pill green">恢复</span>
      </div>
      <div v-for="(c, i) in log.changes" :key="i" class="chg">
        <strong>{{ c.field_label || c.field }}</strong>：
        <template v-if="c.note">{{ c.note }}</template>
        <template v-else>
          <span class="old">{{ fmt(c.old) }}</span>
          <span> → </span>
          <span class="new">{{ fmt(c.new) }}</span>
        </template>
      </div>
    </div>
  </Sheet>
</template>

<script setup>
import { computed, ref } from 'vue'
import { get } from '../api'
import Sheet from './Sheet.vue'

const props = defineProps({
  count: { type: Number, default: 0 },
  badge: { type: String, default: '' },
  logsUrl: { type: String, required: true },
  inline: { type: Boolean, default: false },
})

const showing = ref(false)
const loading = ref(false)
const logs = ref([])

const text = computed(() => {
  if (props.badge) return props.badge
  const n = props.count || 0
  if (n <= 0) return ''
  return n === 1 ? '已编辑' : n === 2 ? '已二次编辑' : '已多次编辑'
})

async function open() {
  showing.value = true
  loading.value = true
  try { logs.value = await get(props.logsUrl) } finally { loading.value = false }
}

function fmt(v) {
  if (v === null || v === undefined || v === '') return '（空）'
  if (Array.isArray(v)) return v.length ? v.join('、') : '（空）'
  if (v === true) return '是'
  if (v === false) return '否'
  return String(v)
}
</script>
