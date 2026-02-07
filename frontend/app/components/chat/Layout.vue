<script setup lang="ts">
import type { Assistant, Model } from "~/types/api";
import { ChevronDown } from "lucide-vue-next";

interface Props {
  assistant: Assistant;
  assistants?: Assistant[];
  title?: string | null;
  showLandingInput?: boolean;
  selectedModelId?: string | null;
}

const props = withDefaults(defineProps<Props>(), {
  showLandingInput: false,
  selectedModelId: null,
});
const emit = defineEmits(["selectAssistant", "selectModel"]);
const { t } = useI18n();

const configStore = useConfigStore();
// Security: Hide toggles until config is loaded to respect admin settings
const showAssistantDropdown = computed(
  () => configStore.isLoaded && configStore.config.ui_show_assistant_dropdown !== false
);
const showModelSelector = computed(
  () => configStore.isLoaded && configStore.config.ui_show_model_selector !== false
);
const hasAssistantPicker = computed(() => {
  const enabled = showAssistantDropdown.value;
  const count = props.assistants?.length ?? 0;
  return enabled && count > 1;
});

// Fetch available models for the selector
const { data: availableModels } = useAPI<Model[]>("/v1/models", {
  server: false,
  lazy: true,
});

// Filter models to only show active chat-capable models
const chatModels = computed(() => {
  if (!availableModels.value) return [];
  return availableModels.value.filter(
    (m) => m.status === "ACTIVE" && m.capabilities?.includes("chat")
  );
});

// Current effective model (selected override or assistant default)
const currentModelId = computed(() => {
  return props.selectedModelId || props.assistant.model_id;
});

const currentModelName = computed(() => {
  if (props.selectedModelId && chatModels.value.length > 0) {
    const found = chatModels.value.find((m) => m.id === props.selectedModelId);
    if (found) return found.display_name || found.name;
  }
  return props.assistant.model?.display_name || props.assistant.model?.name || "Model";
});

const handleSelectAssistant = (value: string) => {
  emit("selectAssistant", value);
};

const handleSelectModel = (value: string) => {
  // If selecting the assistant's default model, emit null to clear override
  if (value === props.assistant.model_id) {
    emit("selectModel", null);
  } else {
    emit("selectModel", value);
  }
};
</script>

<template>
  <div
    class="from-background via-background to-muted/40 relative flex h-screen flex-col bg-gradient-to-b"
  >
    <AppHeader>
      <div class="flex min-w-0 items-center gap-3">
        <!-- Assistant selector -->
        <div v-if="hasAssistantPicker" class="max-w-48">
          <Select :model-value="assistant.id" @update:model-value="handleSelectAssistant">
            <SelectTrigger data-testid="assistant-select" class="h-8">
              <div class="flex items-center gap-2 truncate">
                <AssistantAvatar :assistant="assistant" class="size-4" />
                <span class="truncate text-sm">{{ assistant.name }}</span>
              </div>
            </SelectTrigger>
            <SelectContent>
              <SelectItem v-for="option in assistants" :key="option.id" :value="option.id">
                <div class="flex items-center gap-2 truncate">
                  <AssistantAvatar :assistant="option" class="size-4" />
                  <span class="truncate">{{ option.name }}</span>
                </div>
              </SelectItem>
            </SelectContent>
          </Select>
        </div>
        <div v-else class="flex items-center gap-2 truncate text-sm font-medium">
          <AssistantAvatar :assistant="assistant" class="size-4" />
          <span class="truncate">{{ assistant.name }}</span>
        </div>

        <!-- Model selector (compact dropdown) -->
        <template v-if="showModelSelector && chatModels.length > 1">
          <span class="text-muted-foreground/50 text-xs">·</span>
          <Select :model-value="currentModelId" @update:model-value="handleSelectModel">
            <SelectTrigger
              data-testid="model-select"
              class="text-muted-foreground hover:text-foreground h-7 w-auto gap-1 border-none bg-transparent px-2 text-xs shadow-none"
            >
              <span class="max-w-32 truncate">{{ currentModelName }}</span>
              <ChevronDown class="size-3 opacity-50" />
            </SelectTrigger>
            <SelectContent align="start">
              <SelectItem
                v-for="model in chatModels"
                :key="model.id"
                :value="model.id"
                class="text-sm"
              >
                <div class="flex items-center gap-2">
                  <span>{{ model.display_name || model.name }}</span>
                  <span
                    v-if="model.id === assistant.model_id"
                    class="text-muted-foreground text-xs"
                  >
                    (default)
                  </span>
                </div>
              </SelectItem>
            </SelectContent>
          </Select>
        </template>
      </div>
    </AppHeader>

    <!-- Chat content area -->
    <div
      class="flex-1 overflow-y-auto scroll-smooth"
      :class="props.showLandingInput ? 'flex items-center justify-center' : ''"
    >
      <div :class="[props.showLandingInput ? 'w-full px-5' : 'w-full p-4 pb-52 md:p-6']">
        <div
          :class="[
            'mx-auto space-y-6 leading-relaxed',
            props.showLandingInput ? 'max-w-3xl text-center' : 'max-w-3xl',
          ]"
        >
          <slot />

          <div v-if="props.showLandingInput" class="mt-6">
            <slot name="input" />
          </div>
        </div>
      </div>
    </div>

    <!-- Input area slot -->
    <div
      v-if="!props.showLandingInput"
      class="pointer-events-none absolute right-0 bottom-0 left-0 z-50"
    >
      <div class="pointer-events-auto p-4 md:p-5">
        <div class="mx-auto max-w-3xl">
          <slot name="input" />
        </div>
      </div>
    </div>
  </div>
</template>
