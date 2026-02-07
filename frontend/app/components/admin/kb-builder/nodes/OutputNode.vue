<script setup lang="ts">
import { CheckCircle } from "lucide-vue-next";
import BaseNode from "./BaseNode.vue";

interface Props {
  id: string;
  data: {
    previewResults?: {
      query: string;
      results: Array<{
        content: string;
        score: number;
        metadata?: Record<string, any>;
      }>;
    };
  };
}

const props = defineProps<Props>();

const truncateText = (text: string, maxLength: number = 100) => {
  if (text.length <= maxLength) return text;
  return text.slice(0, maxLength) + "...";
};
</script>

<template>
  <BaseNode :id="id" label="Output" color="gray" :has-output="false">
    <div class="min-w-[200px] space-y-2">
      <div v-if="!data.previewResults" class="text-muted-foreground text-xs">
        Run a preview query to see results
      </div>

      <div v-else class="space-y-2">
        <div class="text-xs">
          <span class="text-muted-foreground">Query:</span>
          <span class="ml-1 font-medium">{{ truncateText(data.previewResults.query, 50) }}</span>
        </div>

        <div class="max-h-48 space-y-1 overflow-y-auto">
          <div
            v-for="(result, idx) in data.previewResults.results.slice(0, 5)"
            :key="idx"
            class="rounded border bg-white p-2 text-xs dark:bg-gray-800"
          >
            <div class="flex items-center justify-between text-gray-500">
              <span>#{{ idx + 1 }}</span>
              <span v-if="result.score">{{ (result.score * 100).toFixed(1) }}%</span>
            </div>
            <div class="mt-1 text-gray-700 dark:text-gray-300">
              {{ truncateText(result.content) }}
            </div>
          </div>
        </div>

        <div v-if="data.previewResults.results.length > 5" class="text-muted-foreground text-xs">
          +{{ data.previewResults.results.length - 5 }} more results
        </div>
      </div>
    </div>
  </BaseNode>
</template>
