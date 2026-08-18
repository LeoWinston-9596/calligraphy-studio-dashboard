<template>
  <!-- 老师多选：候选来自导入表，也允许临时加表里没有的名字 -->
  <div>
    <div class="chips">
      <button v-for="t in options" :key="t"
              :class="['chip', { on: modelValue.includes(t) }]"
              @click="toggle(t)">
        {{ t }}
        <span v-if="counts[t]" class="chip-num">{{ counts[t] }}班</span>
      </button>
    </div>
    <div v-if="extras.length" class="chips">
      <button v-for="t in extras" :key="t" class="chip on" @click="toggle(t)">
        {{ t }} ✕
      </button>
    </div>
    <div class="row" style="margin-top:6px">
      <input v-model="custom" placeholder="表格里没有的老师，输入后回车添加"
             @keyup.enter="addCustom" />
      <button class="btn ghost sm" style="flex:none" :disabled="!custom.trim()" @click="addCustom">
        添加
      </button>
    </div>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'

const props = defineProps({
  modelValue: { type: Array, default: () => [] },
  options: { type: Array, default: () => [] },
  counts: { type: Object, default: () => ({}) },
})
const emit = defineEmits(['update:modelValue'])

const custom = ref('')

// 已选中但不在候选列表里的（手动加的）
const extras = computed(() => props.modelValue.filter((t) => !props.options.includes(t)))

function toggle(name) {
  const next = props.modelValue.includes(name)
    ? props.modelValue.filter((t) => t !== name)
    : [...props.modelValue, name]
  emit('update:modelValue', next)
}

function addCustom() {
  const name = custom.value.trim()
  if (!name) return
  if (!props.modelValue.includes(name)) emit('update:modelValue', [...props.modelValue, name])
  custom.value = ''
}
</script>

<style scoped>
.chips { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 6px; }
.chip {
  border: 1px solid var(--line); background: #fff; color: var(--ink-2);
  border-radius: 99px; padding: 6px 12px; cursor: pointer; font-size: 13px;
}
.chip.on { background: var(--brand); color: #fff; border-color: var(--brand); }
.chip-num { opacity: .7; font-size: 11px; margin-left: 4px; }
</style>
