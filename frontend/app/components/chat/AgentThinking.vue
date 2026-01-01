<script setup lang="ts">
import {
  Brain,
  Search,
  Database,
  Code,
  FileText,
  Zap,
  ChevronDown,
  Copy,
  Check,
} from "lucide-vue-next";
import { useClipboard } from "@vueuse/core";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "~/components/ui/collapsible";

export interface AgentStep {
  type: "agent_action" | "agent_observation" | "agent_thought";
  tool?: string;
  tool_display_name?: string;
  observation?: string;
  description?: string;
  thought?: string;
  timestamp?: number;
}

interface Props {
  steps: AgentStep[];
  isThinking?: boolean;
  assistantName?: string;
  modelName?: string;
}

const props = withDefaults(defineProps<Props>(), {
  isThinking: false,
  assistantName: undefined,
  modelName: undefined,
});

const { t } = useI18n();

// Tool icon mapping
const getToolIcon = (toolName?: string) => {
  if (!toolName) return Brain;

  const iconMap: Record<string, any> = {
    knowledge_base_query: Database,
    web_search: Search,
    code_interpreter: Code,
    file_reader: FileText,
    calculator: Zap,
  };

  return iconMap[toolName] || Brain;
};

// Get the display text for the step
const getStepText = (step: AgentStep) => {
  if (step.type === "agent_thought") {
    return step.thought || step.description || "";
  }
  return step.description || step.observation || t("chat.agentThinking.processing");
};

// Control collapse state - collapsed by default
const isOpen = ref(false);

const reasoningText = computed(() => {
  const thoughtSteps = props.steps
    .filter((step) => step.type === "agent_thought")
    .map((step) => (step.thought || step.description || "").trim())
    .filter(Boolean);
  return thoughtSteps.join("\n\n");
});

const toolSteps = computed(() => props.steps.filter((step) => step.type !== "agent_thought"));

const summary = computed(() => {
  const parts: string[] = [];
  if (reasoningText.value) parts.push("Reasoning");
  if (toolSteps.value.length) {
    parts.push(`${toolSteps.value.length} step${toolSteps.value.length === 1 ? "" : "s"}`);
  }
  if (!parts.length && !props.isThinking) {
    parts.push("No trace");
  }
  return parts.join(" · ");
});

const { copy, copied } = useClipboard();
const handleCopy = () => {
  if (reasoningText.value) {
    copy(reasoningText.value);
  }
};
</script>

<template>
  <div class="w-full">
    <Collapsible v-model:open="isOpen" class="space-y-2">
      <div class="flex justify-start">
        <CollapsibleTrigger as-child>
          <button
            type="button"
            class="bg-muted/30 hover:bg-muted/50 inline-flex max-w-full items-center gap-2 rounded-full border px-3 py-1.5 text-xs transition-colors"
          >
            <span class="relative inline-flex">
              <Brain
                class="text-muted-foreground h-3.5 w-3.5"
                :class="{ 'animate-pulse': isThinking }"
              />
              <span
                v-if="isThinking"
                class="bg-primary/15 absolute -inset-1 animate-ping rounded-full"
              ></span>
            </span>

            <span class="text-foreground font-medium">
              {{
                isThinking
                  ? t("chat.agentThinking.thinking")
                  : t("chat.agentThinking.thinkingProcess")
              }}
            </span>

            <span v-if="summary" class="text-muted-foreground truncate">
              {{ summary }}
            </span>

            <ChevronDown
              class="text-muted-foreground h-3.5 w-3.5 transition-transform"
              :class="{ 'rotate-180': isOpen }"
            />
          </button>
        </CollapsibleTrigger>
      </div>

      <CollapsibleContent class="space-y-3">
        <!-- Reasoning trace (only visible when expanded) -->
        <div v-if="reasoningText" class="bg-card group relative rounded-md border p-3">
          <div
            class="text-muted-foreground mb-2 flex items-center justify-between text-xs font-medium"
          >
            <span>Reasoning trace</span>
            <button
              @click.stop="handleCopy"
              class="hover:bg-muted text-muted-foreground hover:text-foreground rounded-md p-1 opacity-0 transition-colors group-hover:opacity-100"
              title="Copy trace"
            >
              <Check v-if="copied" class="h-3.5 w-3.5" />
              <Copy v-else class="h-3.5 w-3.5" />
            </button>
          </div>
          <pre
            class="text-foreground max-h-64 overflow-auto font-mono text-xs leading-relaxed whitespace-pre-wrap"
            >{{ reasoningText }}</pre
          >
        </div>

        <!-- Tool / agent steps -->
        <div v-if="toolSteps.length" class="bg-card rounded-md border p-3">
          <div class="text-muted-foreground mb-2 text-xs font-medium">Steps</div>
          <div class="space-y-2">
            <div v-for="(step, index) in toolSteps" :key="index" class="flex items-start gap-2">
              <component
                :is="getToolIcon(step.tool)"
                class="text-muted-foreground mt-0.5 h-4 w-4 flex-shrink-0"
              />
              <div class="min-w-0 flex-1">
                <div class="text-foreground text-sm break-words">
                  <span v-if="step.tool_display_name" class="font-medium">
                    {{ step.tool_display_name }}
                  </span>
                  <span v-if="step.tool_display_name"> — </span>
                  <span class="text-muted-foreground">{{ getStepText(step) }}</span>
                </div>
              </div>
            </div>
          </div>
        </div>

        <div
          v-if="!reasoningText && !toolSteps.length"
          class="bg-card text-muted-foreground rounded-md border p-3 text-sm"
        >
          <div class="text-foreground font-medium">No reasoning trace for this message.</div>
          <div class="mt-1 text-xs">
            <span v-if="assistantName"
              >Assistant: <span class="font-mono">{{ assistantName }}</span></span
            >
            <span v-if="assistantName && modelName"> · </span>
            <span v-if="modelName"
              >Model: <span class="font-mono">{{ modelName }}</span></span
            >
          </div>
          <div class="mt-2 text-xs">
            Reasoning traces typically appear only for reasoning-capable models (e.g. o1/o3,
            DeepSeek-R1, gpt-oss) or when agent tools are enabled.
          </div>
        </div>

        <!-- Loading animation when thinking -->
        <div v-if="isThinking" class="flex items-center gap-2 px-1">
          <div class="flex space-x-1">
            <div
              class="bg-muted-foreground h-1.5 w-1.5 animate-bounce rounded-full"
              style="animation-delay: 0ms"
            ></div>
            <div
              class="bg-muted-foreground h-1.5 w-1.5 animate-bounce rounded-full"
              style="animation-delay: 150ms"
            ></div>
            <div
              class="bg-muted-foreground h-1.5 w-1.5 animate-bounce rounded-full"
              style="animation-delay: 300ms"
            ></div>
          </div>
          <span class="text-muted-foreground text-xs">{{
            t("chat.agentThinking.processing")
          }}</span>
        </div>
      </CollapsibleContent>
    </Collapsible>
  </div>
</template>

<style scoped>
@keyframes bounce {
  0%,
  80%,
  100% {
    transform: translateY(0);
  }
  40% {
    transform: translateY(-6px);
  }
}

.animate-bounce {
  animation: bounce 1.4s infinite;
}
</style>
