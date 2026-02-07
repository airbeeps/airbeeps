<script setup lang="ts">
import { ref } from "vue";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "~/components/ui/dialog";
import { Button } from "~/components/ui/button";
import { Input } from "~/components/ui/input";
import { Label } from "~/components/ui/label";
import { ScrollArea } from "~/components/ui/scroll-area";
import { Badge } from "~/components/ui/badge";
import { Search, Loader2, FileText } from "lucide-vue-next";

interface Props {
  open: boolean;
  loading?: boolean;
  results?: Array<{
    content: string;
    score?: number;
    similarity?: number;
    metadata?: Record<string, any>;
  }>;
}

const props = withDefaults(defineProps<Props>(), {
  loading: false,
  results: () => [],
});

const emit = defineEmits<{
  "update:open": [value: boolean];
  runQuery: [query: string];
}>();

const query = ref("");

const handleRunQuery = () => {
  if (query.value.trim()) {
    emit("runQuery", query.value.trim());
  }
};

const truncateText = (text: string, maxLength: number = 300) => {
  if (text.length <= maxLength) return text;
  return text.slice(0, maxLength) + "...";
};

const formatScore = (result: Props["results"][number]) => {
  const score = result.score ?? result.similarity;
  if (score === undefined || score === null) return null;
  return (score * 100).toFixed(1);
};
</script>

<template>
  <Dialog :open="open" @update:open="(v) => emit('update:open', v)">
    <DialogContent class="max-w-2xl">
      <DialogHeader>
        <DialogTitle>Test RAG Pipeline</DialogTitle>
        <DialogDescription>
          Run a test query to preview retrieval results with the current configuration.
        </DialogDescription>
      </DialogHeader>

      <div class="space-y-4">
        <!-- Query Input -->
        <div class="space-y-2">
          <Label for="preview-query">Test Query</Label>
          <div class="flex gap-2">
            <Input
              id="preview-query"
              v-model="query"
              placeholder="Enter a test question..."
              class="flex-1"
              @keydown.enter="handleRunQuery"
            />
            <Button :disabled="!query.trim() || loading" @click="handleRunQuery">
              <Loader2 v-if="loading" class="mr-2 h-4 w-4 animate-spin" />
              <Search v-else class="mr-2 h-4 w-4" />
              Search
            </Button>
          </div>
        </div>

        <!-- Results -->
        <div v-if="results.length > 0" class="space-y-2">
          <div class="flex items-center justify-between">
            <Label>Results</Label>
            <Badge variant="secondary">{{ results.length }} documents</Badge>
          </div>

          <ScrollArea class="h-[400px] rounded-md border">
            <div class="space-y-3 p-3">
              <div
                v-for="(result, idx) in results"
                :key="idx"
                class="bg-muted/30 rounded-lg border p-4"
              >
                <div class="mb-2 flex items-start justify-between">
                  <div class="flex items-center gap-2">
                    <Badge variant="outline" class="font-mono">#{{ idx + 1 }}</Badge>
                    <span
                      v-if="formatScore(result)"
                      class="text-sm text-green-600 dark:text-green-400"
                    >
                      {{ formatScore(result) }}% match
                    </span>
                  </div>
                  <div
                    v-if="result.metadata?.source"
                    class="flex items-center gap-1 text-xs text-gray-500"
                  >
                    <FileText class="h-3 w-3" />
                    {{ result.metadata.source }}
                  </div>
                </div>

                <div class="text-sm text-gray-700 dark:text-gray-300">
                  {{ truncateText(result.content) }}
                </div>

                <!-- Metadata badges -->
                <div v-if="result.metadata" class="mt-2 flex flex-wrap gap-1">
                  <Badge v-if="result.metadata.page_number" variant="secondary" class="text-xs">
                    Page {{ result.metadata.page_number }}
                  </Badge>
                  <Badge v-if="result.metadata.sheet" variant="secondary" class="text-xs">
                    Sheet: {{ result.metadata.sheet }}
                  </Badge>
                  <Badge
                    v-if="result.metadata.chunk_index !== undefined"
                    variant="secondary"
                    class="text-xs"
                  >
                    Chunk {{ result.metadata.chunk_index + 1 }}
                  </Badge>
                </div>
              </div>
            </div>
          </ScrollArea>
        </div>

        <!-- Empty state -->
        <div
          v-else-if="!loading"
          class="text-muted-foreground flex flex-col items-center justify-center py-12 text-center"
        >
          <Search class="mb-4 h-12 w-12 opacity-50" />
          <p>Enter a test query above to preview retrieval results.</p>
          <p class="mt-1 text-sm">Results will use the current pipeline configuration.</p>
        </div>

        <!-- Loading state -->
        <div v-if="loading && results.length === 0" class="flex items-center justify-center py-12">
          <Loader2 class="h-8 w-8 animate-spin text-gray-400" />
        </div>
      </div>
    </DialogContent>
  </Dialog>
</template>
