<script setup lang="ts">
import { ref, computed, watch, onMounted } from "vue";
import { VueFlow, useVueFlow, type Node, type Edge, MarkerType } from "@vue-flow/core";
import { Background } from "@vue-flow/background";
import { Controls } from "@vue-flow/controls";
import { MiniMap } from "@vue-flow/minimap";
import "@vue-flow/core/dist/style.css";
import "@vue-flow/core/dist/theme-default.css";
import "@vue-flow/controls/dist/style.css";
import "@vue-flow/minimap/dist/style.css";

import DocumentSourceNode from "./nodes/DocumentSourceNode.vue";
import ChunkingNode from "./nodes/ChunkingNode.vue";
import EmbeddingNode from "./nodes/EmbeddingNode.vue";
import RetrievalNode from "./nodes/RetrievalNode.vue";
import RerankerNode from "./nodes/RerankerNode.vue";
import OutputNode from "./nodes/OutputNode.vue";
import PipelinePreview from "./PipelinePreview.vue";
import { Button } from "~/components/ui/button";
import { Play, RotateCcw } from "lucide-vue-next";
import type { RagConfig } from "~/types/api";

interface Props {
  modelValue: {
    knowledge_base_ids?: string[];
    rag_config?: RagConfig;
  };
  knowledgeBaseName?: string;
  documentCount?: number;
  disabled?: boolean;
}

const props = withDefaults(defineProps<Props>(), {
  disabled: false,
  documentCount: 0,
});

const emit = defineEmits<{
  "update:modelValue": [value: Props["modelValue"]];
}>();

// Node type mappings
const nodeTypes = {
  documentSource: DocumentSourceNode,
  chunking: ChunkingNode,
  embedding: EmbeddingNode,
  retrieval: RetrievalNode,
  reranker: RerankerNode,
  output: OutputNode,
};

// Pipeline state
interface PipelineState {
  chunking: {
    strategy: "auto" | "semantic" | "hierarchical" | "sentence";
    chunkSize?: number;
    chunkOverlap?: number;
  };
  embedding: {
    modelId?: string;
    modelName?: string;
  };
  retrieval: {
    retrievalCount: number;
    similarityThreshold: number;
    hybridEnabled: boolean;
    hybridAlpha?: number;
    multiQuery: boolean;
    multiQueryCount?: number;
  };
  reranker: {
    enabled: boolean;
    modelId?: string;
    modelName?: string;
    topK?: number;
  };
  output: {
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

const pipelineState = ref<PipelineState>({
  chunking: {
    strategy: "auto",
    chunkSize: undefined,
    chunkOverlap: undefined,
  },
  embedding: {
    modelId: undefined,
    modelName: undefined,
  },
  retrieval: {
    retrievalCount: props.modelValue.rag_config?.retrieval_count || 5,
    similarityThreshold: props.modelValue.rag_config?.similarity_threshold || 0.7,
    hybridEnabled: props.modelValue.rag_config?.hybrid_enabled || false,
    hybridAlpha: 0.5,
    multiQuery: props.modelValue.rag_config?.multi_query || false,
    multiQueryCount: props.modelValue.rag_config?.multi_query_count || 3,
  },
  reranker: {
    enabled: !!props.modelValue.rag_config?.rerank_model_id,
    modelId: props.modelValue.rag_config?.rerank_model_id,
    topK: props.modelValue.rag_config?.rerank_top_k,
  },
  output: {},
});

// Create nodes
const nodes = computed<Node[]>(() => [
  {
    id: "documents",
    type: "documentSource",
    position: { x: 50, y: 150 },
    data: {
      documentCount: props.documentCount,
      knowledgeBaseName: props.knowledgeBaseName,
    },
  },
  {
    id: "chunking",
    type: "chunking",
    position: { x: 280, y: 100 },
    data: pipelineState.value.chunking,
  },
  {
    id: "embedding",
    type: "embedding",
    position: { x: 510, y: 150 },
    data: pipelineState.value.embedding,
  },
  {
    id: "retrieval",
    type: "retrieval",
    position: { x: 740, y: 80 },
    data: pipelineState.value.retrieval,
  },
  {
    id: "reranker",
    type: "reranker",
    position: { x: 970, y: 120 },
    data: pipelineState.value.reranker,
  },
  {
    id: "output",
    type: "output",
    position: { x: 1200, y: 100 },
    data: pipelineState.value.output,
  },
]);

// Create edges
const edges = computed<Edge[]>(() => [
  {
    id: "e1-2",
    source: "documents",
    target: "chunking",
    animated: true,
    markerEnd: MarkerType.ArrowClosed,
  },
  {
    id: "e2-3",
    source: "chunking",
    target: "embedding",
    animated: true,
    markerEnd: MarkerType.ArrowClosed,
  },
  {
    id: "e3-4",
    source: "embedding",
    target: "retrieval",
    animated: true,
    markerEnd: MarkerType.ArrowClosed,
  },
  {
    id: "e4-5",
    source: "retrieval",
    target: "reranker",
    animated: true,
    markerEnd: MarkerType.ArrowClosed,
  },
  {
    id: "e5-6",
    source: "reranker",
    target: "output",
    animated: true,
    markerEnd: MarkerType.ArrowClosed,
  },
]);

// Handle node data updates
const handleNodeUpdate = (nodeId: string, data: any) => {
  if (nodeId === "chunking") {
    pipelineState.value.chunking = data;
  } else if (nodeId === "embedding") {
    pipelineState.value.embedding = data;
  } else if (nodeId === "retrieval") {
    pipelineState.value.retrieval = data;
  } else if (nodeId === "reranker") {
    pipelineState.value.reranker = data;
  }
};

// Sync pipeline state to RagConfig
watch(
  pipelineState,
  (state) => {
    const ragConfig: RagConfig = {
      retrieval_count: state.retrieval.retrievalCount,
      similarity_threshold: state.retrieval.similarityThreshold,
      hybrid_enabled: state.retrieval.hybridEnabled,
      multi_query: state.retrieval.multiQuery,
      multi_query_count: state.retrieval.multiQueryCount,
      rerank_model_id: state.reranker.enabled ? state.reranker.modelId : undefined,
      rerank_top_k: state.reranker.enabled ? state.reranker.topK : undefined,
    };

    emit("update:modelValue", {
      ...props.modelValue,
      rag_config: ragConfig,
    });
  },
  { deep: true }
);

// Preview functionality
const showPreview = ref(false);
const previewLoading = ref(false);

const runPreview = async (query: string) => {
  if (!props.modelValue.knowledge_base_ids?.length) {
    return;
  }

  previewLoading.value = true;
  try {
    const { $api } = useNuxtApp();
    const response = (await $api(
      `/v1/admin/rag/knowledge-bases/${props.modelValue.knowledge_base_ids[0]}/preview`,
      {
        method: "POST",
        body: {
          query,
          rag_config: {
            retrieval_count: pipelineState.value.retrieval.retrievalCount,
            similarity_threshold: pipelineState.value.retrieval.similarityThreshold,
            hybrid_enabled: pipelineState.value.retrieval.hybridEnabled,
            multi_query: pipelineState.value.retrieval.multiQuery,
            multi_query_count: pipelineState.value.retrieval.multiQueryCount,
            rerank_model_id: pipelineState.value.reranker.enabled
              ? pipelineState.value.reranker.modelId
              : undefined,
            rerank_top_k: pipelineState.value.reranker.enabled
              ? pipelineState.value.reranker.topK
              : undefined,
          },
        },
      }
    )) as any;

    pipelineState.value.output = {
      previewResults: {
        query,
        results: response.documents || [],
      },
    };
  } catch (error) {
    console.error("Preview failed:", error);
  } finally {
    previewLoading.value = false;
  }
};

const resetLayout = () => {
  // Reset to default positions - VueFlow handles this internally
};

// Initialize from props
onMounted(() => {
  if (props.modelValue.rag_config) {
    const config = props.modelValue.rag_config;
    pipelineState.value.retrieval = {
      retrievalCount: config.retrieval_count || 5,
      similarityThreshold: config.similarity_threshold || 0.7,
      hybridEnabled: config.hybrid_enabled || false,
      hybridAlpha: 0.5,
      multiQuery: config.multi_query || false,
      multiQueryCount: config.multi_query_count || 3,
    };
    pipelineState.value.reranker = {
      enabled: !!config.rerank_model_id,
      modelId: config.rerank_model_id,
      topK: config.rerank_top_k,
    };
  }
});
</script>

<template>
  <div class="flex h-full flex-col">
    <!-- Toolbar -->
    <div class="flex items-center justify-between border-b p-2">
      <div class="text-sm font-medium">RAG Pipeline Builder</div>
      <div class="flex items-center gap-2">
        <Button
          variant="outline"
          size="sm"
          :disabled="!modelValue.knowledge_base_ids?.length"
          @click="showPreview = true"
        >
          <Play class="mr-1 h-4 w-4" />
          Test Query
        </Button>
        <Button variant="ghost" size="sm" @click="resetLayout">
          <RotateCcw class="h-4 w-4" />
        </Button>
      </div>
    </div>

    <!-- Flow Canvas -->
    <div class="relative flex-1">
      <VueFlow
        :nodes="nodes"
        :edges="edges"
        :node-types="nodeTypes"
        :default-viewport="{ x: 0, y: 0, zoom: 0.8 }"
        :min-zoom="0.3"
        :max-zoom="1.5"
        fit-view-on-init
        class="h-full w-full"
        @node-click="(event) => {}"
      >
        <Background pattern-color="#94a3b8" :gap="16" />
        <Controls />
        <MiniMap pannable zoomable />

        <!-- Custom node event handling -->
        <template #node-chunking="{ id, data }">
          <ChunkingNode :id="id" :data="data" @update-data="(d) => handleNodeUpdate(id, d)" />
        </template>
        <template #node-embedding="{ id, data }">
          <EmbeddingNode :id="id" :data="data" @update-data="(d) => handleNodeUpdate(id, d)" />
        </template>
        <template #node-retrieval="{ id, data }">
          <RetrievalNode :id="id" :data="data" @update-data="(d) => handleNodeUpdate(id, d)" />
        </template>
        <template #node-reranker="{ id, data }">
          <RerankerNode :id="id" :data="data" @update-data="(d) => handleNodeUpdate(id, d)" />
        </template>
        <template #node-output="{ id, data }">
          <OutputNode :id="id" :data="data" />
        </template>
        <template #node-documentSource="{ id, data }">
          <DocumentSourceNode :id="id" :data="data" />
        </template>
      </VueFlow>
    </div>

    <!-- Preview Dialog -->
    <PipelinePreview
      v-model:open="showPreview"
      :loading="previewLoading"
      :results="pipelineState.output.previewResults?.results || []"
      @run-query="runPreview"
    />
  </div>
</template>

<style>
.vue-flow__node {
  background: transparent;
  border: none;
  padding: 0;
}

.vue-flow__handle {
  width: 10px;
  height: 10px;
}

.vue-flow__edge-path {
  stroke: #94a3b8;
  stroke-width: 2;
}

.vue-flow__edge.animated path {
  stroke-dasharray: 5;
  animation: dashdraw 0.5s linear infinite;
}

@keyframes dashdraw {
  from {
    stroke-dashoffset: 10;
  }
}
</style>
