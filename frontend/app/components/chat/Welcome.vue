<script setup lang="ts">
import type { Assistant } from "~/types/api";
import { ArrowRight, Terminal, FileText, Sparkles, HelpCircle } from "lucide-vue-next";

const { t } = useI18n();

interface Props {
  assistant?: Assistant | null;
  showWelcome?: boolean;
}

const props = withDefaults(defineProps<Props>(), {
  showWelcome: true,
});

const emit = defineEmits(["select-suggestion"]);

const configStore = useConfigStore();
const showSuggestions = computed(() => {
  // Security: Hide suggestions until config is loaded to respect admin settings
  if (!configStore.isLoaded) return false;
  // Don't show generic suggestions for RAG assistants
  if (props.assistant?.mode === "RAG") {
    return false;
  }
  return configStore.config.ui_show_chat_suggestions !== false;
});

const descriptionText = computed(() => {
  return "";
});

const suggestions = [
  {
    icon: Sparkles,
    label: "Creative Writing",
    prompt: "Write a short story about a time traveler who gets stuck in 2024.",
    color: "text-purple-500",
    bg: "bg-purple-500/10",
    border: "border-purple-200 dark:border-purple-800",
  },
  {
    icon: Terminal,
    label: "Code Helper",
    prompt: "Write a Python script to scrape a website and save data to CSV.",
    color: "text-blue-500",
    bg: "bg-blue-500/10",
    border: "border-blue-200 dark:border-blue-800",
  },
  {
    icon: FileText,
    label: "Summarization",
    prompt: "Summarize the key points of a recent tech news article.",
    color: "text-green-500",
    bg: "bg-green-500/10",
    border: "border-green-200 dark:border-green-800",
  },
  {
    icon: HelpCircle,
    label: "Explain Concept",
    prompt: "Explain quantum computing to a 5-year old.",
    color: "text-amber-500",
    bg: "bg-amber-500/10",
    border: "border-amber-200 dark:border-amber-800",
  },
];

const handleSuggestionClick = (prompt: string) => {
  emit("select-suggestion", prompt);
};
</script>

<template>
  <div v-if="showWelcome" class="animate-in fade-in slide-in-from-bottom-4 py-16 duration-500">
    <div class="mx-auto max-w-2xl space-y-10 text-center">
      <div class="space-y-4">
        <div
          class="from-primary/20 to-primary/5 mb-4 inline-flex h-16 w-16 items-center justify-center rounded-2xl bg-gradient-to-br"
        >
          <Sparkles class="text-primary h-8 w-8" />
        </div>
        <h2
          class="from-foreground to-foreground/70 bg-gradient-to-br bg-clip-text text-3xl font-bold tracking-tight md:text-4xl"
        >
          {{ t("chat.input.greeting", "What can I help with?") }}
        </h2>
        <p
          v-if="descriptionText"
          class="text-muted-foreground mx-auto max-w-md text-lg leading-relaxed"
        >
          {{ descriptionText }}
        </p>
      </div>

      <!-- Suggestion Chips -->
      <div v-if="showSuggestions" class="grid grid-cols-1 gap-3 md:grid-cols-2">
        <button
          v-for="(suggestion, index) in suggestions"
          :key="index"
          @click="handleSuggestionClick(suggestion.prompt)"
          class="border-border/50 bg-card/50 hover:bg-card hover:border-border group flex items-center gap-3 rounded-2xl border p-4 text-left backdrop-blur-sm transition-all duration-300 hover:shadow-md"
          :style="{ animationDelay: `${index * 50}ms` }"
        >
          <div
            class="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl transition-transform group-hover:scale-105"
            :class="[suggestion.bg, suggestion.color]"
          >
            <component :is="suggestion.icon" class="h-5 w-5" />
          </div>
          <div class="min-w-0 flex-1">
            <div
              class="text-foreground group-hover:text-primary text-sm font-semibold transition-colors"
            >
              {{ suggestion.label }}
            </div>
            <div class="text-muted-foreground/80 mt-0.5 truncate text-xs">
              {{ suggestion.prompt }}
            </div>
          </div>
          <ArrowRight
            class="text-muted-foreground/50 h-4 w-4 -translate-x-2 opacity-0 transition-all duration-200 group-hover:translate-x-0 group-hover:opacity-100"
          />
        </button>
      </div>
    </div>
  </div>
</template>
