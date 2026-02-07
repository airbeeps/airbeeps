<script setup lang="ts">
import { Handle, Position } from "@vue-flow/core";

interface Props {
  id: string;
  label: string;
  icon?: string;
  color?: string;
  hasInput?: boolean;
  hasOutput?: boolean;
}

const props = withDefaults(defineProps<Props>(), {
  color: "gray",
  hasInput: true,
  hasOutput: true,
});

const colorClasses: Record<string, string> = {
  blue: "border-blue-500 bg-blue-50 dark:bg-blue-950/30",
  green: "border-green-500 bg-green-50 dark:bg-green-950/30",
  purple: "border-purple-500 bg-purple-50 dark:bg-purple-950/30",
  orange: "border-orange-500 bg-orange-50 dark:bg-orange-950/30",
  pink: "border-pink-500 bg-pink-50 dark:bg-pink-950/30",
  gray: "border-gray-500 bg-gray-50 dark:bg-gray-950/30",
};
</script>

<template>
  <div
    class="relative min-w-[180px] rounded-lg border-2 p-3 shadow-md transition-shadow hover:shadow-lg"
    :class="colorClasses[props.color]"
  >
    <Handle v-if="hasInput" type="target" :position="Position.Left" class="!bg-gray-400" />

    <div class="flex items-center gap-2 border-b border-gray-200 pb-2 dark:border-gray-700">
      <component v-if="icon" :is="icon" class="h-4 w-4" />
      <span class="text-sm font-semibold">{{ label }}</span>
    </div>

    <div class="mt-2">
      <slot />
    </div>

    <Handle v-if="hasOutput" type="source" :position="Position.Right" class="!bg-gray-400" />
  </div>
</template>
