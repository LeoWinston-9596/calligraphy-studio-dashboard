<template>
  <!-- 剩余课时角标：估算口径点击展开算式（规格书 §6.2） -->
  <span :class="['pill', level]" @click.stop="toggle" style="cursor:pointer">
    {{ balance ? balance.display : '—' }}
  </span>
  <div v-if="open && balance && balance.mode === 'estimated'" class="muted" style="margin-top:4px">
    {{ balance.detail }}
    <span v-if="balance.used_dates && balance.used_dates.length">
      （{{ balance.used_dates.join('、') }}）
    </span>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'

const props = defineProps({ balance: Object, threshold: { type: Number, default: 3 } })
const open = ref(false)

const level = computed(() => {
  if (!props.balance) return 'gray'
  const n = props.balance.current
  if (n <= 0) return 'red'
  if (n <= props.threshold) return 'red'
  if (n <= props.threshold * 2) return ''
  return 'green'
})

function toggle() {
  if (props.balance && props.balance.detail) open.value = !open.value
}
</script>
