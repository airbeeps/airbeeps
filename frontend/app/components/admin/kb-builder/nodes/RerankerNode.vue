<script setup lang="ts">
import { ref, onMounted } from "vue";
import { ListOrdered } from "lucide-vue-next";
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
import { Switch } from "~/components/ui/switch";

interface Props {
  id: string;
  data: {
    enabled: boolean;
    modelId?: string;
    modelName?: string;
    topK?: number;
  };
}

const props = defineProps<Props>();
const emit = defineEmits<{
  updateData: [data: Props["data"]];
}>();

interface RerankerModel {
  id: string;
  name: string;
  display_name?: string;
}

const rerankerModels = ref<RerankerModel[]>([]);
const loading = ref(false);

const loadModels = async () => {
  loading.value = true;
  try {
    const { $api } = useNuxtApp();
    const response = (await $api("/v1/admin/all-models?capabilities=reranker")) as RerankerModel[];
    rerankerModels.value = response || [];
  } catch (error) {
    console.error("Failed to load reranker models:", error);
    rerankerModels.value = [];
  } finally {
    loading.value = false;
  }
};

const update = (key: keyof Props["data"], value: any) => {
  emit("updateData", { ...props.data, [key]: value });
};

const updateModel = (value: string) => {
  const model = rerankerModels.value.find((m) => m.id === value);
  emit("updateData", {
    ...props.data,
    modelId: value === "__none__" ? undefined : value,
    modelName: value === "__none__" ? undefined : model?.display_name || model?.name || value,
  });
};

onMounted(() => {
  loadModels();
});
</script>

<template>
  <BaseNode :id="id" label="Reranker" color="pink">
    <div class="space-y-3">
      <div class="flex items-center justify-between">
        <Label class="text-xs">Enable Reranking</Label>
        <Switch :model-value="data.enabled" @update:model-value="(v) => update('enabled', v)" />
      </div>

      <template v-if="data.enabled">
        <div class="space-y-1">
          <Label class="text-xs">Model</Label>
          <Select
            :model-value="data.modelId || '__none__'"
            :disabled="loading"
            @update:model-value="updateModel"
          >
            <SelectTrigger class="h-8 text-xs">
              <SelectValue :placeholder="loading ? 'Loading...' : 'Select reranker'" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="__none__">None</SelectItem>
              <SelectItem v-for="model in rerankerModels" :key="model.id" :value="model.id">
                {{ model.display_name || model.name }}
              </SelectItem>
            </SelectContent>
          </Select>
        </div>

        <div class="space-y-1">
          <Label class="text-xs">Rerank Top K</Label>
          <Input
            type="number"
            :model-value="data.topK"
            placeholder="10"
            :min="1"
            :max="50"
            class="h-7 text-xs"
            @update:model-value="(v) => update('topK', parseInt(String(v)) || undefined)"
          />
        </div>
      </template>
    </div>
  </BaseNode>
</template>
