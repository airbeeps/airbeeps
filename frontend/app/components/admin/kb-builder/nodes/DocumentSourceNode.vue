<script setup lang="ts">
import { computed } from "vue";
import { FileText } from "lucide-vue-next";
import BaseNode from "./BaseNode.vue";

interface Props {
  id: string;
  data: {
    documentCount?: number;
    knowledgeBaseName?: string;
  };
}

const props = defineProps<Props>();

const displayText = computed(() => {
  if (props.data.knowledgeBaseName) {
    return props.data.knowledgeBaseName;
  }
  return `${props.data.documentCount || 0} documents`;
});
</script>

<template>
  <BaseNode :id="id" label="Documents" color="blue" :has-input="false">
    <div class="flex items-center gap-2 text-sm text-gray-600 dark:text-gray-400">
      <FileText class="h-4 w-4" />
      <span>{{ displayText }}</span>
    </div>
  </BaseNode>
</template>
