<script setup lang="ts">
import { ref, onMounted } from "vue";
import { Cpu } from "lucide-vue-next";
import BaseNode from "./BaseNode.vue";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "~/components/ui/select";
import { Label } from "~/components/ui/label";

interface Props {
  id: string;
  data: {
    modelId?: string;
    modelName?: string;
  };
}

const props = defineProps<Props>();
const emit = defineEmits<{
  updateData: [data: Props["data"]];
}>();

interface EmbeddingModel {
  id: string;
  name: string;
  display_name?: string;
  dimensions?: number;
}

const embeddingModels = ref<EmbeddingModel[]>([]);
const loading = ref(false);

const loadModels = async () => {
  loading.value = true;
  try {
    const { $api } = useNuxtApp();
    const response = (await $api(
      "/v1/admin/all-models?capabilities=embedding"
    )) as EmbeddingModel[];
    embeddingModels.value = response || [];
  } catch (error) {
    console.error("Failed to load embedding models:", error);
    embeddingModels.value = [];
  } finally {
    loading.value = false;
  }
};

const updateModel = (value: string) => {
  const model = embeddingModels.value.find((m) => m.id === value);
  emit("updateData", {
    ...props.data,
    modelId: value,
    modelName: model?.display_name || model?.name || value,
  });
};

onMounted(() => {
  loadModels();
});
</script>

<template>
  <BaseNode :id="id" label="Embedding" color="purple">
    <div class="space-y-2">
      <div class="space-y-1">
        <Label class="text-xs">Model</Label>
        <Select
          :model-value="data.modelId || ''"
          :disabled="loading || embeddingModels.length === 0"
          @update:model-value="updateModel"
        >
          <SelectTrigger class="h-8 text-xs">
            <SelectValue :placeholder="loading ? 'Loading...' : 'Select model'" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem v-for="model in embeddingModels" :key="model.id" :value="model.id">
              {{ model.display_name || model.name }}
            </SelectItem>
          </SelectContent>
        </Select>
      </div>

      <div v-if="data.modelName" class="flex items-center gap-1 text-xs text-gray-500">
        <Cpu class="h-3 w-3" />
        <span>{{ data.modelName }}</span>
      </div>
    </div>
  </BaseNode>
</template>
