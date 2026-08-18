<template>
  <div class="mask" @click.self="$emit('close')">
    <div class="sheet">
      <h3 v-if="title">{{ title }}</h3>
      <slot />
      <button class="btn ghost block" style="margin-top:14px" @click="$emit('close')">关闭</button>
    </div>
  </div>
</template>

<script setup>
defineProps({ title: String })
defineEmits(['close'])
</script>
