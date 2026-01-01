<script setup lang="ts">
import type { Assistant } from "~/types/api";

interface Props {
  assistant: Assistant;
  assistants?: Assistant[];
  title?: string | null;
  showLandingInput?: boolean;
}

const props = withDefaults(defineProps<Props>(), {
  showLandingInput: false,
});
const emit = defineEmits(["selectAssistant"]);
const { t } = useI18n();

const configStore = useConfigStore();
const showAssistantDropdown = computed(
  () => configStore.config.ui_show_assistant_dropdown !== false
);
const hasAssistantPicker = computed(() => {
  const enabled = showAssistantDropdown.value;
  const count = props.assistants?.length ?? 0;
  return enabled && count > 1;
});

const handleSelectAssistant = (value: string) => {
  emit("selectAssistant", value);
};
</script>

<template>
  <div
    class="from-background via-background to-muted/40 relative flex h-screen flex-col bg-gradient-to-b"
  >
    <AppHeader>
      <div class="flex min-w-0 items-center gap-3">
        <div v-if="hasAssistantPicker" class="w-64">
          <Select :model-value="assistant.id" @update:model-value="handleSelectAssistant">
            <SelectTrigger data-testid="assistant-select">
              <div class="flex items-center gap-2 truncate">
                <AssistantAvatar :assistant="assistant" class="size-4" />
                <span class="truncate">{{ assistant.name }}</span>
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
