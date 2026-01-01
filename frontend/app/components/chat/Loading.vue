<script setup lang="ts">
import { useMarkdown } from "~/composables/useMarkdown";

interface Props {
  assistant?: Assistant | null;
  message?: string;
  isStreaming?: boolean;
  streamingContent?: string;
}

const props = withDefaults(defineProps<Props>(), {
  message: "...",
  isStreaming: false,
  streamingContent: "",
});

const { renderMarkdown } = useMarkdown();

const renderedStreamingContent = computed(() => {
  return renderMarkdown(props.streamingContent || "");
});
</script>

<template>
  <div class="flex">
    <div class="w-full">
      <div v-if="isStreaming && streamingContent" class="markdown-content">
        <div v-html="renderedStreamingContent"></div>
        <span class="ml-1 inline-block h-4 w-2 animate-pulse bg-current"></span>
      </div>
      <div v-else class="flex items-center space-x-2">
        <div class="flex space-x-1">
          <div
            class="h-2 w-2 animate-bounce rounded-full bg-current"
            style="animation-delay: 0ms"
          ></div>
          <div
            class="h-2 w-2 animate-bounce rounded-full bg-current"
            style="animation-delay: 150ms"
          ></div>
          <div
            class="h-2 w-2 animate-bounce rounded-full bg-current"
            style="animation-delay: 300ms"
          ></div>
        </div>
        <p class="text-muted-foreground text-sm">{{ message }}</p>
      </div>
    </div>
  </div>
</template>

<style scoped>
@keyframes bounce {
  0%,
  80%,
  100% {
    transform: translateY(0);
  }

  40% {
    transform: translateY(-6px);
  }
}

.animate-bounce {
  animation: bounce 1.4s infinite;
}

.markdown-content > *:last-child {
  margin-bottom: 0 !important;
}
</style>
