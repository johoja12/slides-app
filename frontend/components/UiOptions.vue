<script setup lang="ts">
import UiButton from "./UiButton.vue";
defineProps<{
  label: string;
  modelValue: string;
  options: { value: string; label: string }[];
}>();
defineEmits<{ "update:modelValue": [value: string] }>();
</script>
<template>
  <div class="ui-options" role="group" :aria-label="label">
    <span class="option-label">{{ label }}</span>
    <div class="option-buttons">
      <UiButton
        v-for="option in options"
        :key="option.value"
        :aria-pressed="modelValue === option.value"
        @click="$emit('update:modelValue', option.value)"
        >{{ option.label }}</UiButton
      >
    </div>
  </div>
</template>
