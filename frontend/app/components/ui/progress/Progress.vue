<script setup lang="ts">
import { ProgressIndicator, ProgressRoot, type ProgressRootProps } from "reka-ui";
import { cn } from "@/lib/utils";
import { reactiveOmit } from "@vueuse/core";
import { computed, type HTMLAttributes } from "vue";

const props = withDefaults(defineProps<ProgressRootProps & { class?: HTMLAttributes["class"] }>(), {
  modelValue: 0,
});

const delegatedProps = reactiveOmit(props, "class");
</script>

<template>
  <ProgressRoot
    v-bind="delegatedProps"
    :class="cn('bg-secondary relative h-4 w-full overflow-hidden rounded-full', props.class)"
  >
    <ProgressIndicator
      class="bg-primary h-full w-full flex-1 transition-all"
      :style="`transform: translateX(-${100 - (props.modelValue ?? 0)}%);`"
    />
  </ProgressRoot>
</template>
