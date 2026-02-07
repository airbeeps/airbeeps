<script setup lang="ts">
import { ref, computed, onMounted } from "vue";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "~/components/ui/card";
import { Label } from "~/components/ui/label";
import { Input } from "~/components/ui/input";
import { Button } from "~/components/ui/button";
import { Badge } from "~/components/ui/badge";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "~/components/ui/select";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "~/components/ui/tabs";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "~/components/ui/tooltip";
import { RefreshCw, Database, Info, Workflow, Settings2 } from "lucide-vue-next";
import { toast } from "vue-sonner";
import type { KnowledgeBase, RagConfig } from "~/types/api";
import { KBPipelineBuilder } from "./kb-builder";

const { t } = useI18n();

// View mode: form or visual builder
const viewMode = ref<"form" | "visual">("form");

interface Props {
  modelValue: {
    knowledge_base_ids?: string[];
    rag_config?: RagConfig;
  };
  disabled?: boolean;
  settingsReadOnly?: boolean;
}

const props = withDefaults(defineProps<Props>(), {
  disabled: false,
  settingsReadOnly: false,
});

const emit = defineEmits<{
  "update:modelValue": [value: Props["modelValue"]];
}>();

// State management
const knowledgeBases = ref<KnowledgeBase[]>([]);
const rerankerModels = ref<{ label: string; value: string }[]>([]);
const loading = ref(false);

// Computed properties
const localValue = computed({
  get: () => {
    return {
      knowledge_base_ids: props.modelValue.knowledge_base_ids || [],
      retrieval_count: props.modelValue.rag_config?.retrieval_count || 5,
      fetch_k: props.modelValue.rag_config?.fetch_k,
      similarity_threshold: props.modelValue.rag_config?.similarity_threshold || 0.7,
      skip_smalltalk: props.modelValue.rag_config?.skip_smalltalk ?? false,
      skip_patterns: props.modelValue.rag_config?.skip_patterns || [],
      multi_query: props.modelValue.rag_config?.multi_query ?? false,
      multi_query_count: props.modelValue.rag_config?.multi_query_count || 3,
      rerank_top_k: props.modelValue.rag_config?.rerank_top_k,
      rerank_model_id: props.modelValue.rag_config?.rerank_model_id,
      hybrid_enabled: props.modelValue.rag_config?.hybrid_enabled ?? false,
      hybrid_corpus_limit: props.modelValue.rag_config?.hybrid_corpus_limit || 1000,
    };
  },
  set: (value) => {
    emit("update:modelValue", {
      knowledge_base_ids: value.knowledge_base_ids,
      rag_config: {
        retrieval_count: value.retrieval_count,
        fetch_k: value.fetch_k,
        similarity_threshold: value.similarity_threshold,
        skip_smalltalk: value.skip_smalltalk,
        skip_patterns: value.skip_patterns,
        multi_query: value.multi_query,
        multi_query_count: value.multi_query_count,
        rerank_top_k: value.rerank_top_k,
        rerank_model_id: value.rerank_model_id,
        hybrid_enabled: value.hybrid_enabled,
        hybrid_corpus_limit: value.hybrid_corpus_limit,
      },
    });
  },
});

// Only count KBs that actually exist (filter out deleted ones)
const selectedCount = computed(() => {
  const existingKbIds = new Set(knowledgeBases.value.map((kb) => kb.id));
  return localValue.value.knowledge_base_ids.filter((id) => existingKbIds.has(id)).length;
});

// Methods
const loadKnowledgeBases = async () => {
  loading.value = true;
  try {
    const { $api } = useNuxtApp();
    const response = (await $api("/v1/admin/rag/knowledge-bases/all")) as any;
    knowledgeBases.value = response.items || response || [];
  } catch (error) {
    console.error("Failed to load knowledge base list:", error);
    knowledgeBases.value = [];
    toast.error(t("components.fileUpload.loadKnowledgeBasesFailed"));
  } finally {
    loading.value = false;
  }
};

const loadRerankerModels = async () => {
  try {
    const { $api } = useNuxtApp();
    const response = (await $api("/v1/admin/all-models?capabilities=reranker")) as any[];
    rerankerModels.value = (response || []).map((m: any) => ({
      label: m.display_name || m.name || m.id,
      value: m.id,
    }));
  } catch (error) {
    console.error("Failed to load reranker models:", error);
    rerankerModels.value = [];
  }
};

const toggleKnowledgeBaseSelection = (kbId: string, event: Event) => {
  const checked = (event.target as HTMLInputElement).checked;
  const currentIds = [...localValue.value.knowledge_base_ids];

  if (checked) {
    if (!currentIds.includes(kbId)) {
      currentIds.push(kbId);
    }
  } else {
    const index = currentIds.indexOf(kbId);
    if (index > -1) {
      currentIds.splice(index, 1);
    }
  }

  localValue.value = {
    ...localValue.value,
    knowledge_base_ids: currentIds,
  };
};

const updateRetrievalCount = (value: string | number) => {
  const num = typeof value === "number" ? value : parseInt(value);
  if (!isNaN(num)) {
    localValue.value = {
      ...localValue.value,
      retrieval_count: num,
    };
  }
};

const updateFetchK = (value: string | number) => {
  const num = typeof value === "number" ? value : parseInt(value);
  localValue.value = {
    ...localValue.value,
    fetch_k: isNaN(num) ? undefined : num,
  };
};

const updateSimilarityThreshold = (value: string | number) => {
  const num = typeof value === "number" ? value : parseFloat(value);
  if (!isNaN(num)) {
    localValue.value = {
      ...localValue.value,
      similarity_threshold: num,
    };
  }
};

const updateSkipSmalltalk = (event: Event) => {
  const checked = (event.target as HTMLInputElement).checked;
  localValue.value = {
    ...localValue.value,
    skip_smalltalk: checked,
  };
};

const updateSkipPatterns = (value: string | number) => {
  const text = typeof value === "number" ? String(value) : value;
  const patterns = text
    .split(",")
    .map((s) => s.trim())
    .filter((s) => s.length > 0);
  localValue.value = {
    ...localValue.value,
    skip_patterns: patterns,
  };
};

const updateMultiQueryCount = (value: string | number) => {
  const num = typeof value === "number" ? value : parseInt(value);
  if (!isNaN(num)) {
    localValue.value = {
      ...localValue.value,
      multi_query_count: num,
    };
  }
};

const updateRerankTopK = (value: string | number) => {
  const num = typeof value === "number" ? value : parseInt(value);
  localValue.value = {
    ...localValue.value,
    rerank_top_k: isNaN(num) ? undefined : num,
  };
};

const updateRerankModel = (value: string | null) => {
  localValue.value = {
    ...localValue.value,
    rerank_model_id: !value || value === "__none__" ? undefined : value,
  };
};

const updateHybridCorpusLimit = (value: string | number) => {
  const num = typeof value === "number" ? value : parseInt(value);
  if (!isNaN(num)) {
    localValue.value = {
      ...localValue.value,
      hybrid_corpus_limit: num,
    };
  }
};

// Lifecycle
onMounted(() => {
  loadKnowledgeBases();
  loadRerankerModels();
});
</script>

<template>
  <Card>
    <CardHeader>
      <div class="flex items-center justify-between">
        <div>
          <CardTitle class="flex items-center gap-2">
            <Database class="h-5 w-5" />
            {{ t("components.knowledgeBaseConfig.title") }}
          </CardTitle>
          <CardDescription>
            {{ t("components.knowledgeBaseConfig.description") }}
          </CardDescription>
        </div>
        <!-- View Mode Tabs -->
        <Tabs v-model="viewMode" class="w-auto">
          <TabsList class="grid w-[200px] grid-cols-2">
            <TabsTrigger value="form" class="flex items-center gap-1">
              <Settings2 class="h-4 w-4" />
              Form
            </TabsTrigger>
            <TabsTrigger value="visual" class="flex items-center gap-1">
              <Workflow class="h-4 w-4" />
              Visual
            </TabsTrigger>
          </TabsList>
        </Tabs>
      </div>
    </CardHeader>
    <CardContent class="space-y-6">
      <!-- Visual Builder View -->
      <div v-if="viewMode === 'visual'" class="h-[500px] rounded-lg border">
        <KBPipelineBuilder
          :model-value="modelValue"
          :knowledge-base-name="
            knowledgeBases.find((kb) => localValue.knowledge_base_ids.includes(kb.id))?.name
          "
          :document-count="0"
          :disabled="disabled"
          @update:model-value="(v) => emit('update:modelValue', v)"
        />
      </div>

      <!-- Form View -->
      <TooltipProvider v-else>
        <div class="space-y-6">
          <!-- Knowledge base selection -->
          <div class="space-y-3">
            <div class="flex items-center justify-between">
              <Label class="text-sm font-medium">
                {{ t("components.knowledgeBaseConfig.selectKnowledgeBase") }}
                <span v-if="selectedCount > 0" class="text-muted-foreground">
                  {{
                    t("components.knowledgeBaseConfig.selectedCount", {
                      count: selectedCount,
                    })
                  }}
                </span>
              </Label>
              <Button variant="outline" size="sm" @click="loadKnowledgeBases" :disabled="loading">
                <RefreshCw class="mr-1 h-4 w-4" :class="{ 'animate-spin': loading }" />
                {{ t("components.knowledgeBaseConfig.refresh") }}
              </Button>
            </div>

            <!-- Knowledge base list -->
            <div class="max-h-40 space-y-2 overflow-y-auto rounded-md border p-3">
              <div v-if="loading" class="text-muted-foreground py-4 text-center">
                {{ t("components.knowledgeBaseConfig.loading") }}
              </div>
              <div
                v-else-if="knowledgeBases.length === 0"
                class="text-muted-foreground py-4 text-center"
              >
                {{ t("components.knowledgeBaseConfig.noKnowledgeBases") }}
              </div>
              <div
                v-else
                v-for="kb in knowledgeBases"
                :key="kb.id"
                class="hover:bg-muted flex items-start space-x-3 rounded p-2 transition-colors"
              >
                <input
                  :id="`kb-${kb.id}`"
                  type="checkbox"
                  :checked="localValue.knowledge_base_ids.includes(kb.id)"
                  :disabled="disabled"
                  @change="(e) => toggleKnowledgeBaseSelection(kb.id, e)"
                  class="text-primary focus:ring-primary mt-1 h-4 w-4 rounded border-gray-300"
                />
                <Label :for="`kb-${kb.id}`" class="flex-1 cursor-pointer space-y-1">
                  <div class="text-sm font-medium">{{ kb.name }}</div>
                  <div class="text-muted-foreground text-xs">
                    {{ kb.description }}
                  </div>
                </Label>
              </div>
            </div>
          </div>

          <!-- Retrieval basics -->
          <div class="bg-muted/30 space-y-3 rounded-md border p-4">
            <div class="text-foreground text-sm font-semibold">Retrieval basics</div>
            <div class="grid grid-cols-1 gap-4 md:grid-cols-3">
              <div class="space-y-2">
                <div class="flex items-center gap-1">
                  <Label for="retrieval-count" class="text-sm font-medium">
                    {{ t("components.knowledgeBaseConfig.retrievalCount") }}
                  </Label>
                  <Tooltip>
                    <TooltipTrigger as-child>
                      <button
                        type="button"
                        class="inline-flex cursor-help"
                        aria-label="retrieval-count-help"
                      >
                        <Info class="text-muted-foreground h-3.5 w-3.5" />
                      </button>
                    </TooltipTrigger>
                    <TooltipContent side="top" class="max-w-xs text-left">
                      {{ t("components.knowledgeBaseConfig.retrievalCountHelp") }}
                    </TooltipContent>
                  </Tooltip>
                </div>
                <Input
                  id="retrieval-count"
                  type="number"
                  :model-value="localValue.retrieval_count"
                  :disabled="disabled || settingsReadOnly"
                  :min="1"
                  :max="20"
                  placeholder="5"
                  @update:modelValue="updateRetrievalCount"
                />
              </div>

              <div class="space-y-2">
                <div class="flex items-center gap-1">
                  <Label for="fetch-k" class="text-sm font-medium">
                    {{ t("components.knowledgeBaseConfig.fetchK") }}
                  </Label>
                  <Tooltip>
                    <TooltipTrigger as-child>
                      <button
                        type="button"
                        class="inline-flex cursor-help"
                        aria-label="fetch-k-help"
                      >
                        <Info class="text-muted-foreground h-3.5 w-3.5" />
                      </button>
                    </TooltipTrigger>
                    <TooltipContent side="top" class="max-w-xs text-left">
                      {{ t("components.knowledgeBaseConfig.fetchKHelp") }}
                    </TooltipContent>
                  </Tooltip>
                </div>
                <Input
                  id="fetch-k"
                  type="number"
                  :model-value="localValue.fetch_k ?? ''"
                  :disabled="disabled || settingsReadOnly"
                  :min="1"
                  :max="500"
                  placeholder="Auto (3x K)"
                  @update:modelValue="updateFetchK"
                />
              </div>

              <div class="space-y-2">
                <div class="flex items-center gap-1">
                  <Label for="similarity-threshold" class="text-sm font-medium">
                    {{ t("components.knowledgeBaseConfig.similarityThreshold") }}
                  </Label>
                  <Tooltip>
                    <TooltipTrigger as-child>
                      <button
                        type="button"
                        class="inline-flex cursor-help"
                        aria-label="similarity-threshold-help"
                      >
                        <Info class="text-muted-foreground h-3.5 w-3.5" />
                      </button>
                    </TooltipTrigger>
                    <TooltipContent side="top" class="max-w-xs text-left">
                      {{ t("components.knowledgeBaseConfig.similarityThresholdHelp") }}
                    </TooltipContent>
                  </Tooltip>
                </div>
                <Input
                  id="similarity-threshold"
                  type="number"
                  :model-value="localValue.similarity_threshold"
                  :disabled="disabled || settingsReadOnly"
                  :min="0"
                  :max="1"
                  :step="0.01"
                  placeholder="0.7"
                  @update:modelValue="updateSimilarityThreshold"
                />
              </div>
            </div>
          </div>

          <!-- Advanced recall / rerank -->
          <div class="bg-muted/30 space-y-3 rounded-md border p-4">
            <div class="text-foreground text-sm font-semibold">Advanced recall & rerank</div>
            <div class="grid grid-cols-1 gap-4 md:grid-cols-2">
              <div class="space-y-2">
                <div class="flex items-center gap-2">
                  <input
                    id="multi-query"
                    type="checkbox"
                    :checked="localValue.multi_query"
                    :disabled="disabled || loading || settingsReadOnly"
                    @change="
                      (e) =>
                        (localValue.value = {
                          ...localValue.value,
                          multi_query: (e.target as HTMLInputElement).checked,
                        })
                    "
                    class="text-primary focus:ring-primary h-4 w-4 rounded border-gray-300"
                  />
                  <Label for="multi-query" class="cursor-pointer text-sm font-medium">
                    Multi-query recall
                  </Label>
                  <Tooltip>
                    <TooltipTrigger as-child>
                      <button
                        type="button"
                        class="inline-flex cursor-help"
                        aria-label="multi-query-help"
                      >
                        <Info class="text-muted-foreground h-3.5 w-3.5" />
                      </button>
                    </TooltipTrigger>
                    <TooltipContent side="top" class="max-w-xs text-left">
                      {{ t("components.knowledgeBaseConfig.multiQueryHelp") }}
                    </TooltipContent>
                  </Tooltip>
                </div>
                <div class="space-y-2">
                  <div class="space-y-1">
                    <Label for="multi-query-count" class="text-xs font-medium">Alt queries</Label>
                    <Input
                      id="multi-query-count"
                      type="number"
                      :model-value="localValue.multi_query_count"
                      :disabled="disabled || settingsReadOnly || !localValue.multi_query"
                      min="1"
                      max="5"
                      @update:modelValue="updateMultiQueryCount"
                    />
                  </div>
                  <div class="grid grid-cols-1 gap-2 md:grid-cols-2">
                    <div class="space-y-1">
                      <div class="flex items-center gap-1">
                        <Label for="rerank-top-k" class="text-xs font-medium">Rerank top K</Label>
                        <Tooltip>
                          <TooltipTrigger as-child>
                            <button
                              type="button"
                              class="inline-flex cursor-help"
                              aria-label="rerank-topk-help"
                            >
                              <Info class="text-muted-foreground h-3 w-3" />
                            </button>
                          </TooltipTrigger>
                          <TooltipContent side="top" class="max-w-xs text-left">
                            {{ t("components.knowledgeBaseConfig.rerankTopKHelp") }}
                          </TooltipContent>
                        </Tooltip>
                      </div>
                      <Input
                        id="rerank-top-k"
                        type="number"
                        :model-value="localValue.rerank_top_k"
                        :disabled="disabled || settingsReadOnly"
                        min="1"
                        max="50"
                        placeholder="Optional"
                        @update:modelValue="updateRerankTopK"
                      />
                    </div>
                    <div class="space-y-1">
                      <div class="flex items-center gap-1">
                        <Label for="rerank-model" class="text-xs font-medium">Reranker model</Label>
                        <Tooltip>
                          <TooltipTrigger as-child>
                            <button
                              type="button"
                              class="inline-flex cursor-help"
                              aria-label="reranker-help"
                            >
                              <Info class="text-muted-foreground h-3 w-3" />
                            </button>
                          </TooltipTrigger>
                          <TooltipContent side="top" class="max-w-xs text-left">
                            {{ t("components.knowledgeBaseConfig.rerankModelHelp") }}
                          </TooltipContent>
                        </Tooltip>
                      </div>
                      <Select
                        id="rerank-model"
                        class="w-full"
                        :disabled="disabled || settingsReadOnly || rerankerModels.length === 0"
                        :model-value="localValue.rerank_model_id || '__none__'"
                        @update:modelValue="updateRerankModel"
                      >
                        <SelectTrigger>
                          <SelectValue placeholder="Select reranker (optional)" />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="__none__">None</SelectItem>
                          <SelectItem
                            v-for="model in rerankerModels"
                            :key="model.value"
                            :value="model.value"
                          >
                            {{ model.label }}
                          </SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                  </div>
                </div>
              </div>

              <div class="space-y-2">
                <div class="flex items-center gap-2">
                  <input
                    id="hybrid-enabled"
                    type="checkbox"
                    :checked="localValue.hybrid_enabled"
                    :disabled="disabled || loading || settingsReadOnly"
                    @change="
                      (e) =>
                        (localValue.value = {
                          ...localValue.value,
                          hybrid_enabled: (e.target as HTMLInputElement).checked,
                        })
                    "
                    class="text-primary focus:ring-primary h-4 w-4 rounded border-gray-300"
                  />
                  <Label for="hybrid-enabled" class="cursor-pointer text-sm font-medium">
                    Hybrid (BM25 + dense)
                  </Label>
                  <Tooltip>
                    <TooltipTrigger as-child>
                      <button
                        type="button"
                        class="inline-flex cursor-help"
                        aria-label="hybrid-help"
                      >
                        <Info class="text-muted-foreground h-3.5 w-3.5" />
                      </button>
                    </TooltipTrigger>
                    <TooltipContent side="top" class="max-w-xs text-left">
                      {{ t("components.knowledgeBaseConfig.hybridHelp") }}
                    </TooltipContent>
                  </Tooltip>
                </div>
                <div class="space-y-1">
                  <Label for="hybrid-corpus-limit" class="text-xs font-medium"
                    >BM25 corpus cap</Label
                  >
                  <Input
                    id="hybrid-corpus-limit"
                    type="number"
                    :model-value="localValue.hybrid_corpus_limit"
                    :disabled="disabled || settingsReadOnly || !localValue.hybrid_enabled"
                    min="100"
                    max="5000"
                    @update:modelValue="updateHybridCorpusLimit"
                  />
                </div>
              </div>
            </div>
          </div>
          <!-- Skip small-talk -->
          <div class="mt-4 grid grid-cols-1 gap-4 md:grid-cols-2">
            <div class="space-y-2">
              <div class="flex items-center gap-2">
                <input
                  id="skip-smalltalk"
                  type="checkbox"
                  :checked="localValue.skip_smalltalk"
                  :disabled="disabled || loading || settingsReadOnly"
                  @change="updateSkipSmalltalk"
                  class="text-primary focus:ring-primary h-4 w-4 rounded border-gray-300"
                />
                <Label for="skip-smalltalk" class="cursor-pointer text-sm font-medium">
                  {{ t("components.knowledgeBaseConfig.skipSmalltalk") }}
                </Label>
                <Tooltip>
                  <TooltipTrigger as-child>
                    <button
                      type="button"
                      class="inline-flex cursor-help"
                      aria-label="skip-smalltalk-help"
                    >
                      <Info class="text-muted-foreground h-3.5 w-3.5" />
                    </button>
                  </TooltipTrigger>
                  <TooltipContent side="top" class="max-w-xs text-left">
                    {{ t("components.knowledgeBaseConfig.skipSmalltalkHelp") }}
                  </TooltipContent>
                </Tooltip>
              </div>
            </div>

            <div class="space-y-2" v-if="localValue.skip_smalltalk">
              <div class="flex items-center gap-2">
                <Label for="skip-patterns" class="text-sm font-medium">
                  {{ t("components.knowledgeBaseConfig.skipPatterns") }}
                </Label>
                <Tooltip>
                  <TooltipTrigger as-child>
                    <button
                      type="button"
                      class="inline-flex cursor-help"
                      aria-label="skip-patterns-help"
                    >
                      <Info class="text-muted-foreground h-3 w-3" />
                    </button>
                  </TooltipTrigger>
                  <TooltipContent side="top" class="max-w-xs text-left">
                    {{ t("components.knowledgeBaseConfig.skipPatternsHelp") }}
                  </TooltipContent>
                </Tooltip>
              </div>
              <Input
                id="skip-patterns"
                type="text"
                :model-value="localValue.skip_patterns.join(', ')"
                :disabled="disabled || settingsReadOnly"
                placeholder="hi, hello, thanks"
                @update:modelValue="updateSkipPatterns"
              />
            </div>
          </div>

          <!-- Config description -->
          <div class="bg-muted/50 space-y-2 rounded-md p-3 text-sm">
            <div class="font-medium">
              {{ t("components.knowledgeBaseConfig.configDescription") }}
            </div>
            <ul class="text-muted-foreground ml-4 space-y-1 text-xs">
              <li>
                •
                <strong>{{ t("components.knowledgeBaseConfig.retrievalCount") }}:</strong>
                {{ t("components.knowledgeBaseConfig.configTips.retrievalCount") }}
              </li>
              <li>
                •
                <strong>{{ t("components.knowledgeBaseConfig.similarityThreshold") }}:</strong>
                {{ t("components.knowledgeBaseConfig.configTips.similarityThreshold") }}
              </li>
              <li>• {{ t("components.knowledgeBaseConfig.configTips.recommended") }}</li>
            </ul>
          </div>
        </div>
      </TooltipProvider>
    </CardContent>
  </Card>
</template>
