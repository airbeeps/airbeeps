<script setup lang="ts">
import { computed } from "vue";
import { Scissors } from "lucide-vue-next";
import BaseNode from "./BaseNode.vue";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "~/components/ui/select";
import { Input } from "~/components/ui/input";
import { Label } from "~/components/ui/label";

interface Props {
  id: string;
  data: {
    strategy: "auto" | "semantic" | "hierarchical" | "sentence";
    chunkSize?: number;
    chunkOverlap?: number;
  };
}

const props = defineProps<Props>();
const emit = defineEmits<{
  updateData: [data: Props["data"]];
}>();

const strategyOptions = [
  { value: "auto", label: "Auto (Smart)" },
  { value: "semantic", label: "Semantic" },
  { value: "hierarchical", label: "Hierarchical" },
  { value: "sentence", label: "Sentence-based" },
];

const strategyDescriptions: Record<string, string> = {
  auto: "Automatically selects best strategy",
  semantic: "Groups by meaning boundaries",
  hierarchical: "Parent-child chunk structure",
  sentence: "Splits on sentence boundaries",
};

const updateStrategy = (value: string) => {
  emit("updateData", { ...props.data, strategy: value as Props["data"]["strategy"] });
};

const updateChunkSize = (value: string) => {
  const num = parseInt(value);
  emit("updateData", { ...props.data, chunkSize: isNaN(num) ? undefined : num });
};

const updateChunkOverlap = (value: string) => {
  const num = parseInt(value);
  emit("updateData", { ...props.data, chunkOverlap: isNaN(num) ? undefined : num });
};
</script>

<template>
  <BaseNode :id="id" label="Chunking" color="green">
    <div class="space-y-3">
      <div class="space-y-1">
        <Label class="text-xs">Strategy</Label>
        <Select :model-value="data.strategy" @update:model-value="updateStrategy">
          <SelectTrigger class="h-8 text-xs">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem v-for="opt in strategyOptions" :key="opt.value" :value="opt.value">
              {{ opt.label }}
            </SelectItem>
          </SelectContent>
        </Select>
        <p class="text-muted-foreground text-xs">
          {{ strategyDescriptions[data.strategy] }}
        </p>
      </div>

      <div class="grid grid-cols-2 gap-2">
        <div class="space-y-1">
          <Label class="text-xs">Size</Label>
          <Input
            type="number"
            :model-value="data.chunkSize"
            placeholder="512"
            class="h-7 text-xs"
            @update:model-value="(v) => updateChunkSize(String(v))"
          />
        </div>
        <div class="space-y-1">
          <Label class="text-xs">Overlap</Label>
          <Input
            type="number"
            :model-value="data.chunkOverlap"
            placeholder="50"
            class="h-7 text-xs"
            @update:model-value="(v) => updateChunkOverlap(String(v))"
          />
        </div>
      </div>
    </div>
  </BaseNode>
</template>
