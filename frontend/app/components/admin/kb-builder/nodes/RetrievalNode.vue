<script setup lang="ts">
import { Search } from "lucide-vue-next";
import BaseNode from "./BaseNode.vue";
import { Input } from "~/components/ui/input";
import { Label } from "~/components/ui/label";
import { Switch } from "~/components/ui/switch";
import { Slider } from "~/components/ui/slider";

interface Props {
  id: string;
  data: {
    retrievalCount: number;
    similarityThreshold: number;
    hybridEnabled: boolean;
    hybridAlpha?: number; // 0 = pure BM25, 1 = pure vector
    multiQuery: boolean;
    multiQueryCount?: number;
  };
}

const props = defineProps<Props>();
const emit = defineEmits<{
  updateData: [data: Props["data"]];
}>();

const update = (key: keyof Props["data"], value: any) => {
  emit("updateData", { ...props.data, [key]: value });
};
</script>

<template>
  <BaseNode :id="id" label="Retrieval" color="orange">
    <div class="space-y-3">
      <div class="grid grid-cols-2 gap-2">
        <div class="space-y-1">
          <Label class="text-xs">Top K</Label>
          <Input
            type="number"
            :model-value="data.retrievalCount"
            :min="1"
            :max="20"
            class="h-7 text-xs"
            @update:model-value="(v) => update('retrievalCount', parseInt(String(v)) || 5)"
          />
        </div>
        <div class="space-y-1">
          <Label class="text-xs">Threshold</Label>
          <Input
            type="number"
            :model-value="data.similarityThreshold"
            :min="0"
            :max="1"
            :step="0.05"
            class="h-7 text-xs"
            @update:model-value="(v) => update('similarityThreshold', parseFloat(String(v)) || 0.7)"
          />
        </div>
      </div>

      <div class="space-y-2">
        <div class="flex items-center justify-between">
          <Label class="text-xs">Hybrid Search (BM25 + Vector)</Label>
          <Switch
            :model-value="data.hybridEnabled"
            @update:model-value="(v) => update('hybridEnabled', v)"
          />
        </div>

        <div v-if="data.hybridEnabled" class="space-y-1">
          <div class="flex justify-between text-xs text-gray-500">
            <span>BM25</span>
            <span>{{ Math.round((data.hybridAlpha || 0.5) * 100) }}%</span>
            <span>Vector</span>
          </div>
          <Slider
            :model-value="[data.hybridAlpha || 0.5]"
            :min="0"
            :max="1"
            :step="0.05"
            class="w-full"
            @update:model-value="(v) => update('hybridAlpha', v[0])"
          />
        </div>
      </div>

      <div class="space-y-2">
        <div class="flex items-center justify-between">
          <Label class="text-xs">Multi-Query</Label>
          <Switch
            :model-value="data.multiQuery"
            @update:model-value="(v) => update('multiQuery', v)"
          />
        </div>

        <div v-if="data.multiQuery" class="space-y-1">
          <Label class="text-xs">Query Variants</Label>
          <Input
            type="number"
            :model-value="data.multiQueryCount || 3"
            :min="2"
            :max="5"
            class="h-7 text-xs"
            @update:model-value="(v) => update('multiQueryCount', parseInt(String(v)) || 3)"
          />
        </div>
      </div>
    </div>
  </BaseNode>
</template>
