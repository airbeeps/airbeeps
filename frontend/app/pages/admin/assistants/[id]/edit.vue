<script setup lang="ts">
import { ref, computed, onMounted, watch } from "vue";
import { useRouter, useRoute } from "vue-router";
import { ArrowLeft, Save, X, Trash2, ChevronDown, ChevronUp, Info } from "lucide-vue-next";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "~/components/ui/tooltip";
import { Button } from "~/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "~/components/ui/card";
import { Input } from "~/components/ui/input";
import { Label } from "~/components/ui/label";
import { Switch } from "~/components/ui/switch";
import { Textarea } from "~/components/ui/textarea";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "~/components/ui/select";
import KnowledgeBaseConfig from "~/components/admin/KnowledgeBaseConfig.vue";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "~/components/ui/alert-dialog";
import { toast } from "vue-sonner";
import type {
  Assistant,
  Model,
  RagConfig,
  SystemConfigListResponse,
  SystemConfigItem,
} from "~/types/api";

const { t } = useI18n();

// Page metadata
definePageMeta({
  breadcrumb: "admin.pages.assistants.edit.breadcrumb",
  layout: "admin",
});

const router = useRouter();
const route = useRoute();
const assistantId = route.params.id as string;

// Fetch model list
const { data: models } = useAPI<Model[]>("/v1/admin/all-models?capabilities=chat", {
  server: false,
});

const modelOptions = computed(() =>
  (models.value ?? []).map((m) => ({ label: m.display_name, value: m.id }))
);

// State management
const loading = ref(false);
const saveLoading = ref(false);
const deleteLoading = ref(false);
const assistant = ref<Assistant | null>(null);

// Assistant mode + inheritance toggles + overrides
const mode = ref<"GENERAL" | "RAG">("GENERAL");
const useGlobalGenerationDefaults = ref(true);
const useGlobalRagDefaults = ref(true);
const generationOverride = ref({
  temperature: 0.7,
  max_tokens: 2048,
  additional_params_text: "{}",
});

// Global defaults (admin-configured)
const { data: configData } = await useAPI<SystemConfigListResponse>("/v1/admin/config", {
  server: false,
});
const allConfigs = computed<SystemConfigItem[]>(() => configData.value?.configs ?? []);
const generationDefaults = computed(() => {
  const raw = allConfigs.value.find((c) => c.key === "assistant_generation_defaults")?.value as any;
  return {
    temperature: typeof raw?.temperature === "number" ? raw.temperature : 0.7,
    max_tokens: typeof raw?.max_tokens === "number" ? raw.max_tokens : 2048,
    additional_params:
      raw?.additional_params && typeof raw.additional_params === "object"
        ? raw.additional_params
        : {},
  };
});
const ragDefaults = computed(() => {
  const raw = allConfigs.value.find((c) => c.key === "assistant_rag_defaults")?.value as any;
  return {
    retrieval_count: typeof raw?.retrieval_count === "number" ? raw.retrieval_count : 5,
    fetch_k: raw?.fetch_k,
    similarity_threshold:
      typeof raw?.similarity_threshold === "number" ? raw.similarity_threshold : 0.7,
    context_max_tokens: typeof raw?.context_max_tokens === "number" ? raw.context_max_tokens : 1200,
    search_type: typeof raw?.search_type === "string" ? raw.search_type : "similarity",
    mmr_lambda: typeof raw?.mmr_lambda === "number" ? raw.mmr_lambda : 0.5,
    skip_smalltalk: !!raw?.skip_smalltalk,
    skip_patterns: Array.isArray(raw?.skip_patterns) ? raw.skip_patterns : [],
    multi_query: !!raw?.multi_query,
    multi_query_count: typeof raw?.multi_query_count === "number" ? raw.multi_query_count : 3,
    rerank_top_k: raw?.rerank_top_k,
    rerank_model_id: raw?.rerank_model_id ?? undefined,
    hybrid_enabled: !!raw?.hybrid_enabled,
    hybrid_corpus_limit:
      typeof raw?.hybrid_corpus_limit === "number" ? raw.hybrid_corpus_limit : 1000,
  } as RagConfig;
});

// Follow-up questions (global + assistant-level overrides)
const followupsGlobalEnabled = computed(() => {
  const raw = allConfigs.value.find((c) => c.key === "ui_generate_followup_questions")
    ?.value as any;
  if (raw === undefined) return false;
  return String(raw).toLowerCase() !== "false";
});
const followupsGlobalMaxCount = computed(() => {
  const raw = allConfigs.value.find((c) => c.key === "ui_followup_question_count")?.value as any;
  const n = Number(raw ?? 3);
  if (!Number.isFinite(n)) return 3;
  const clamped = Math.max(1, Math.min(5, Math.trunc(n)));
  return clamped;
});
const followupQuestionsEnabled = ref(true);
const followupQuestionsCount = ref<string>("__global__");

// Form data
const formData = ref<Partial<Assistant>>({
  name: "",
  avatar_file_path: "",
  description: "",
  system_prompt: "",
  model_id: "",
  max_history_messages: undefined,
  is_public: false,
  status: "DRAFT",
});

// Form validation errors
const errors = ref<Record<string, string>>({});

// Knowledge base config state
const kbState = ref<{
  knowledge_base_ids: string[];
  rag_config?: RagConfig;
}>({
  knowledge_base_ids: [],
  rag_config: undefined,
});

const kbModelValue = computed({
  get: () => ({
    knowledge_base_ids: kbState.value.knowledge_base_ids,
    rag_config:
      mode.value === "RAG"
        ? useGlobalRagDefaults.value
          ? ragDefaults.value
          : (kbState.value.rag_config ?? ragDefaults.value)
        : undefined,
  }),
  set: (val: any) => {
    kbState.value.knowledge_base_ids = val?.knowledge_base_ids || [];
    if (!useGlobalRagDefaults.value) {
      kbState.value.rag_config = val?.rag_config;
    }
  },
});

// UI state
const systemPromptExpanded = ref(false);
const systemPromptPreview = computed(() => {
  const content = (formData.value.system_prompt || "").trim();
  if (!content) return t("admin.pages.assistants.create.modelConfig.systemPromptPlaceholder");
  if (content.length <= 220) return content;
  return `${content.slice(0, 220)}…`;
});

// Load assistant data
const loadAssistant = async () => {
  loading.value = true;
  try {
    const { $api } = useNuxtApp();
    const response = (await $api(`/v1/admin/assistants/${assistantId}`)) as any;
    assistant.value = response;

    // Initialize form data
    formData.value = {
      name: response.name || "",
      avatar_file_path: response.avatar_file_path || "",
      description: response.description || "",
      system_prompt: response.system_prompt || "",
      model_id: response.model_id || "",
      max_history_messages: response.max_history_messages,
      is_public: response.is_public || false,
      status: response.status || "DRAFT",
    };

    mode.value =
      (response.mode as any) || (response.knowledge_base_ids?.length ? "RAG" : "GENERAL");
    useGlobalGenerationDefaults.value = response.use_global_generation_defaults ?? true;
    useGlobalRagDefaults.value = response.use_global_rag_defaults ?? true;

    followupQuestionsEnabled.value = response.followup_questions_enabled ?? true;
    followupQuestionsCount.value =
      typeof response.followup_questions_count === "number"
        ? String(
            Math.max(
              1,
              Math.min(followupsGlobalMaxCount.value, Math.trunc(response.followup_questions_count))
            )
          )
        : "__global__";

    // Generation override values (only meaningful when not inheriting)
    generationOverride.value = {
      temperature:
        typeof response.temperature === "number"
          ? response.temperature
          : generationDefaults.value.temperature,
      max_tokens:
        typeof response.max_tokens === "number"
          ? response.max_tokens
          : generationDefaults.value.max_tokens,
      additional_params_text: JSON.stringify(
        (response as any)?.config?.additional_params ?? {},
        null,
        2
      ),
    };

    // Initialize knowledge base config
    kbState.value = {
      knowledge_base_ids: response.knowledge_base_ids || [],
      rag_config: response.rag_config || undefined,
    };
  } catch (error) {
    console.error("Failed to load assistant data:", error);
    toast.error(t("admin.pages.assistants.edit.loadFailed"));
    router.push("/admin/assistants");
  } finally {
    loading.value = false;
  }
};

watch(
  generationDefaults,
  (d) => {
    if (useGlobalGenerationDefaults.value) {
      generationOverride.value = {
        temperature: d.temperature,
        max_tokens: d.max_tokens,
        additional_params_text: JSON.stringify(d.additional_params ?? {}, null, 2),
      };
    }
  },
  { immediate: true }
);

watch(useGlobalGenerationDefaults, (useGlobal) => {
  if (useGlobal) {
    const d = generationDefaults.value;
    generationOverride.value = {
      temperature: d.temperature,
      max_tokens: d.max_tokens,
      additional_params_text: JSON.stringify(d.additional_params ?? {}, null, 2),
    };
  }
});

watch(useGlobalRagDefaults, (useGlobal) => {
  if (!useGlobal && !kbState.value.rag_config) {
    kbState.value.rag_config = ragDefaults.value;
  }
});

watch(mode, (m) => {
  if (m === "GENERAL") {
    kbState.value.knowledge_base_ids = [];
    kbState.value.rag_config = undefined;
    useGlobalRagDefaults.value = true;
  }
});

// Form validation
const validateForm = (): boolean => {
  const newErrors: Record<string, string> = {};

  if (!formData.value.name || formData.value.name.length < 2) {
    newErrors.name = t("admin.pages.assistants.create.validation.nameMin");
  }
  // description is optional now
  if (!formData.value.system_prompt || formData.value.system_prompt.length < 10) {
    newErrors.system_prompt = t("admin.pages.assistants.create.validation.systemPromptMin");
  }
  if (!formData.value.model_id) {
    newErrors.model_id = t("admin.pages.assistants.create.validation.modelRequired");
  }
  if (!formData.value.status) {
    newErrors.status = t("admin.pages.assistants.create.validation.statusRequired");
  }
  if (
    mode.value === "RAG" &&
    (!kbState.value.knowledge_base_ids || kbState.value.knowledge_base_ids.length === 0)
  ) {
    newErrors.knowledge_base_ids = "Select at least one knowledge base for RAG mode";
  }

  errors.value = newErrors;
  return Object.keys(newErrors).length === 0;
};

// Build detailed validation error message
const getValidationErrorMessage = (errorObj: Record<string, string>): string => {
  const fieldNames: Record<string, string> = {
    name: t("admin.pages.assistants.create.basicInfo.nameLabel"),
    system_prompt: t("admin.pages.assistants.create.modelConfig.systemPromptLabel"),
    model_id: t("admin.pages.assistants.create.modelConfig.modelLabel"),
    status: t("admin.pages.assistants.create.publishSettings.statusLabel"),
    knowledge_base_ids: "Knowledge Base",
  };
  const missingFields = Object.keys(errorObj).map((key) => fieldNames[key] || key);
  if (missingFields.length === 1) {
    return `Please fill in the required field: ${missingFields[0]}`;
  }
  return `Please fill in the required fields: ${missingFields.join(", ")}`;
};

// Update assistant
const updateAssistant = async () => {
  if (!validateForm()) {
    toast.error(getValidationErrorMessage(errors.value));
    return;
  }

  saveLoading.value = true;
  try {
    const { $api } = useNuxtApp();

    const parseAdditionalParams = () => {
      const text = (generationOverride.value.additional_params_text || "").trim();
      if (!text) return {};
      const parsed = JSON.parse(text);
      if (parsed === null || typeof parsed !== "object" || Array.isArray(parsed)) {
        throw new Error("Generation additional params must be a JSON object");
      }
      return parsed;
    };

    const submitData: any = {
      ...formData.value,
      mode: mode.value,
      use_global_generation_defaults: useGlobalGenerationDefaults.value,
      use_global_rag_defaults: mode.value === "RAG" ? useGlobalRagDefaults.value : true,
      knowledge_base_ids: mode.value === "RAG" ? kbState.value.knowledge_base_ids : [],
      followup_questions_enabled: followupQuestionsEnabled.value,
      followup_questions_count: followupQuestionsEnabled.value
        ? followupQuestionsCount.value === "__global__"
          ? null
          : Math.min(
              followupsGlobalMaxCount.value,
              Math.max(1, Number(followupQuestionsCount.value))
            )
        : null,
    };

    if (!useGlobalGenerationDefaults.value) {
      submitData.temperature = generationOverride.value.temperature;
      submitData.max_tokens = generationOverride.value.max_tokens;
      submitData.config = {
        ...(submitData.config || {}),
        additional_params: parseAdditionalParams(),
      };
    } else {
      delete submitData.temperature;
      delete submitData.max_tokens;
    }

    if (mode.value === "RAG" && !useGlobalRagDefaults.value) {
      submitData.rag_config = kbState.value.rag_config;
    } else {
      delete submitData.rag_config;
    }

    await $api(`/v1/admin/assistants/${assistantId}`, {
      method: "PUT",
      body: submitData,
    });

    toast.success(t("admin.pages.assistants.edit.updateSuccess"));
    router.push("/admin/assistants");
  } catch (error) {
    console.error("Update failed:", error);
    toast.error(t("admin.pages.assistants.edit.updateFailed"));
  } finally {
    saveLoading.value = false;
  }
};

// Delete assistant
const deleteAssistant = async () => {
  deleteLoading.value = true;
  try {
    const { $api } = useNuxtApp();
    await $api(`/v1/admin/assistants/${assistantId}`, {
      method: "DELETE",
    });

    toast.success(t("admin.pages.assistants.edit.deleteSuccess"));
    router.push("/admin/assistants");
  } catch (error) {
    console.error("Delete failed:", error);
    toast.error(t("admin.pages.assistants.edit.deleteFailed"));
  } finally {
    deleteLoading.value = false;
  }
};

// Cancel action
const handleCancel = () => {
  router.push("/admin/assistants");
};

// Page initialization
onMounted(() => {
  loadAssistant();
});
</script>

<template>
  <div class="container mx-auto space-y-6 py-6">
    <!-- Header navigation -->
    <div class="flex items-center justify-between">
      <div class="flex items-center gap-4">
        <Button variant="ghost" size="sm" @click="handleCancel">
          <ArrowLeft class="mr-2 h-4 w-4" />
          {{ t("admin.back") }}
        </Button>
        <div>
          <h1 class="text-2xl font-bold">{{ t("admin.pages.assistants.edit.title") }}</h1>
          <p class="text-muted-foreground">
            {{
              assistant?.name
                ? t("admin.pages.assistants.edit.editing", { name: assistant.name })
                : t("admin.loading")
            }}
          </p>
        </div>
      </div>

      <!-- Delete button -->
      <AlertDialog>
        <AlertDialogTrigger as-child>
          <Button variant="destructive" size="sm" :disabled="loading">
            <Trash2 class="mr-2 h-4 w-4" />
            {{ t("admin.delete") }}
          </Button>
        </AlertDialogTrigger>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{{
              t("admin.pages.assistants.edit.deleteConfirm.title")
            }}</AlertDialogTitle>
            <AlertDialogDescription>
              {{
                t("admin.pages.assistants.edit.deleteConfirm.description", {
                  name: assistant?.name,
                })
              }}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{{ t("admin.cancel") }}</AlertDialogCancel>
            <AlertDialogAction
              @click="deleteAssistant"
              :disabled="deleteLoading"
              class="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              {{ t("admin.confirm") }}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>

    <!-- Loading state -->
    <div v-if="loading" class="flex justify-center py-12">
      <div class="border-primary h-8 w-8 animate-spin rounded-full border-b-2"></div>
    </div>

    <!-- Form card -->
    <Card v-else-if="assistant" class="max-w-4xl">
      <CardHeader>
        <CardTitle>{{ t("admin.pages.assistants.edit.title") }}</CardTitle>
        <CardDescription>
          {{ t("admin.pages.assistants.edit.description") }}
        </CardDescription>
      </CardHeader>
      <CardContent>
        <form @submit.prevent="updateAssistant" class="space-y-6">
          <!-- Basic info -->
          <div class="space-y-4">
            <!-- Avatar -->
            <div class="space-y-2">
              <Label for="avatar">{{
                t("admin.pages.assistants.create.basicInfo.avatarLabel")
              }}</Label>
              <AvatarUpload
                id="avatar"
                v-model="formData.avatar_file_path"
                :initial-url="assistant?.avatar_url"
                :disabled="saveLoading"
              />
            </div>

            <!-- Name -->
            <div class="space-y-2">
              <Label for="name">
                {{ t("admin.pages.assistants.create.basicInfo.nameLabel") }}
                <span class="text-destructive">*</span>
              </Label>
              <Input
                id="name"
                v-model="formData.name"
                :placeholder="t('admin.pages.assistants.create.basicInfo.namePlaceholder')"
                :class="{ 'border-destructive': errors.name }"
                :disabled="saveLoading"
              />
              <div v-if="errors.name" class="text-destructive text-sm">
                {{ errors.name }}
              </div>
            </div>

            <!-- Description -->
            <div class="space-y-2">
              <Label for="description">
                {{ t("admin.pages.assistants.create.basicInfo.descriptionLabel") }}
              </Label>
              <Textarea
                id="description"
                v-model="formData.description"
                :placeholder="t('admin.pages.assistants.create.basicInfo.descriptionPlaceholder')"
                :rows="3"
                :class="{ 'border-destructive': errors.description }"
                :disabled="saveLoading"
              />
              <div v-if="errors.description" class="text-destructive text-sm">
                {{ errors.description }}
              </div>
            </div>

            <!-- Mode -->
            <div class="space-y-2">
              <Label for="mode">Mode</Label>
              <Select v-model="mode" :disabled="saveLoading">
                <SelectTrigger>
                  <SelectValue placeholder="Select mode" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="GENERAL">General</SelectItem>
                  <SelectItem value="RAG">RAG</SelectItem>
                </SelectContent>
              </Select>
              <div class="text-muted-foreground text-sm">
                Choose General for regular chat, or RAG to use knowledge bases.
              </div>
            </div>
          </div>

          <!-- Model config -->
          <div class="space-y-4">
            <h3 class="text-lg font-medium">
              {{ t("admin.pages.assistants.create.modelConfig.title") }}
            </h3>

            <!-- System prompt -->
            <div class="space-y-2">
              <div class="flex items-center justify-between">
                <Label for="system_prompt">
                  {{ t("admin.pages.assistants.create.modelConfig.systemPromptLabel") }}
                  <span class="text-destructive">*</span>
                </Label>
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  class="h-8 w-8"
                  @click="systemPromptExpanded = !systemPromptExpanded"
                  :aria-expanded="systemPromptExpanded"
                  :aria-controls="'system_prompt'"
                >
                  <ChevronDown v-if="!systemPromptExpanded" class="h-4 w-4" />
                  <ChevronUp v-else class="h-4 w-4" />
                </Button>
              </div>

              <div v-if="!systemPromptExpanded" class="bg-muted/40 space-y-2 rounded-md border p-3">
                <div class="text-muted-foreground text-xs">
                  {{ t("admin.pages.assistants.create.modelConfig.systemPromptPlaceholder") }}
                </div>
                <div class="text-foreground line-clamp-3 text-sm whitespace-pre-wrap">
                  {{ systemPromptPreview }}
                </div>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  class="mt-1"
                  @click="systemPromptExpanded = true"
                >
                  <ChevronDown class="mr-1 h-4 w-4" /> {{ t("common.expand") || "Expand" }}
                </Button>
              </div>

              <Textarea
                v-else
                id="system_prompt"
                v-model="formData.system_prompt"
                :placeholder="
                  t('admin.pages.assistants.create.modelConfig.systemPromptPlaceholder')
                "
                :rows="8"
                :class="{ 'border-destructive': errors.system_prompt }"
                :disabled="saveLoading"
              />
              <div v-if="errors.system_prompt" class="text-destructive text-sm">
                {{ errors.system_prompt }}
              </div>
              <div class="text-muted-foreground text-sm">
                {{ t("admin.pages.assistants.create.modelConfig.systemPromptHelp") }}
              </div>
            </div>

            <!-- Model selection -->
            <div class="space-y-2">
              <Label for="model_id">
                {{ t("admin.pages.assistants.create.modelConfig.modelLabel") }}
                <span class="text-destructive">*</span>
              </Label>
              <Select v-model="formData.model_id" :disabled="saveLoading">
                <SelectTrigger :class="{ 'border-destructive': errors.model_id }">
                  <SelectValue
                    :placeholder="t('admin.pages.assistants.create.modelConfig.modelPlaceholder')"
                  />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem v-for="model in modelOptions" :key="model.value" :value="model.value">
                    {{ model.label }}
                  </SelectItem>
                </SelectContent>
              </Select>
              <div v-if="errors.model_id" class="text-destructive text-sm">
                {{ errors.model_id }}
              </div>
              <div class="text-muted-foreground text-sm">
                {{ t("admin.pages.assistants.create.modelConfig.modelHelp") }}
              </div>
            </div>

            <!-- History -->
            <div class="space-y-2">
              <Label for="max_history_messages">{{
                t("admin.pages.assistants.create.modelConfig.maxHistoryLabel")
              }}</Label>
              <Input
                id="max_history_messages"
                v-model.number="formData.max_history_messages"
                type="number"
                placeholder="10"
                min="0"
                max="100"
                :disabled="saveLoading"
                class="max-w-xs"
              />
              <div class="text-muted-foreground text-sm">
                {{ t("admin.pages.assistants.create.modelConfig.maxHistoryHelp") }}
              </div>
            </div>
          </div>

          <!-- Generation Defaults -->
          <div class="space-y-4">
            <h3 class="text-lg font-medium">Generation</h3>
            <div class="bg-muted/30 space-y-3 rounded-md border p-4">
              <div class="flex items-center justify-between gap-3">
                <div class="text-sm font-semibold">Use global generation defaults</div>
                <div class="flex items-center gap-2">
                  <Button
                    v-if="!useGlobalGenerationDefaults"
                    type="button"
                    variant="outline"
                    size="sm"
                    :disabled="saveLoading"
                    @click="useGlobalGenerationDefaults = true"
                  >
                    Reset to global
                  </Button>
                  <Switch
                    id="use-global-generation"
                    :model-value="useGlobalGenerationDefaults"
                    @update:model-value="(v: boolean) => (useGlobalGenerationDefaults = v)"
                    :disabled="saveLoading"
                  />
                </div>
              </div>
              <div class="grid grid-cols-1 gap-4 md:grid-cols-2">
                <div class="space-y-2">
                  <Label for="gen-temperature">Temperature</Label>
                  <Input
                    id="gen-temperature"
                    type="number"
                    :model-value="
                      useGlobalGenerationDefaults
                        ? generationDefaults.temperature
                        : generationOverride.temperature
                    "
                    :disabled="saveLoading || useGlobalGenerationDefaults"
                    min="0"
                    max="2"
                    step="0.1"
                    @update:modelValue="(v: any) => (generationOverride.temperature = Number(v))"
                  />
                </div>
                <div class="space-y-2">
                  <Label for="gen-max-tokens">Max tokens</Label>
                  <Input
                    id="gen-max-tokens"
                    type="number"
                    :model-value="
                      useGlobalGenerationDefaults
                        ? generationDefaults.max_tokens
                        : generationOverride.max_tokens
                    "
                    :disabled="saveLoading || useGlobalGenerationDefaults"
                    min="1"
                    max="100000"
                    @update:modelValue="(v: any) => (generationOverride.max_tokens = Number(v))"
                  />
                </div>
              </div>
              <div class="space-y-2">
                <Label for="gen-additional">Additional params (JSON)</Label>
                <Textarea
                  id="gen-additional"
                  :model-value="
                    useGlobalGenerationDefaults
                      ? JSON.stringify(generationDefaults.additional_params || {}, null, 2)
                      : generationOverride.additional_params_text
                  "
                  :disabled="saveLoading || useGlobalGenerationDefaults"
                  :rows="6"
                  class="font-mono text-xs"
                  @update:modelValue="
                    (v: any) => (generationOverride.additional_params_text = String(v))
                  "
                />
              </div>
            </div>
          </div>

          <!-- Follow-up Questions -->
          <div class="space-y-4">
            <h3 class="text-lg font-medium">Follow-up Questions</h3>
            <div class="bg-muted/30 space-y-3 rounded-md border p-4">
              <div v-if="!followupsGlobalEnabled" class="text-muted-foreground text-sm">
                Disabled globally in System Config. Enable
                <strong>Generate Follow-up Questions</strong> to use this feature.
              </div>
              <div class="flex items-center justify-between gap-3">
                <div class="text-sm font-semibold">Enable follow-up questions</div>
                <Switch
                  id="assistant-followups-enabled"
                  :model-value="followupQuestionsEnabled"
                  @update:model-value="(v: boolean) => (followupQuestionsEnabled = v)"
                  :disabled="saveLoading || !followupsGlobalEnabled"
                />
              </div>
              <div class="space-y-2">
                <Label for="assistant-followups-count">Follow-up count</Label>
                <Select
                  v-model="followupQuestionsCount"
                  :disabled="saveLoading || !followupsGlobalEnabled || !followupQuestionsEnabled"
                >
                  <SelectTrigger id="assistant-followups-count" class="max-w-xs">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="__global__">
                      Use global ({{ followupsGlobalMaxCount }})
                    </SelectItem>
                    <SelectItem
                      v-for="n in Array.from({ length: followupsGlobalMaxCount }, (_, i) => i + 1)"
                      :key="n"
                      :value="String(n)"
                    >
                      {{ n }}
                    </SelectItem>
                  </SelectContent>
                </Select>
                <div class="text-muted-foreground text-sm">
                  Max allowed: {{ followupsGlobalMaxCount }} (set in System Config).
                </div>
              </div>
            </div>
          </div>

          <!-- Publish settings -->
          <div class="space-y-4">
            <h3 class="text-lg font-medium">
              {{ t("admin.pages.assistants.create.publishSettings.title") }}
            </h3>

            <!-- Public toggle -->
            <div class="flex items-center space-x-2">
              <input
                id="is_public"
                type="checkbox"
                v-model="formData.is_public"
                :disabled="saveLoading"
                class="text-primary focus:ring-primary h-4 w-4 rounded border-gray-300"
              />
              <Label for="is_public" class="cursor-pointer text-sm">
                {{ t("admin.pages.assistants.create.publishSettings.isPublicLabel") }}
              </Label>
            </div>

            <!-- Status -->
            <div class="space-y-2">
              <div class="flex items-center gap-1">
                <Label for="status">
                  {{ t("admin.pages.assistants.create.publishSettings.statusLabel") }}
                  <span class="text-destructive">*</span>
                </Label>
                <TooltipProvider>
                  <Tooltip>
                    <TooltipTrigger as-child>
                      <button
                        type="button"
                        class="inline-flex cursor-help"
                        aria-label="status-help"
                      >
                        <Info class="text-muted-foreground h-3.5 w-3.5" />
                      </button>
                    </TooltipTrigger>
                    <TooltipContent side="right" class="max-w-xs text-left">
                      <div class="space-y-1">
                        <div><strong>Active:</strong> Working normally and available to users</div>
                        <div><strong>Inactive:</strong> Paused and unavailable to users</div>
                        <div>
                          <strong>Draft:</strong> Configuration incomplete, visible only to admins
                        </div>
                      </div>
                    </TooltipContent>
                  </Tooltip>
                </TooltipProvider>
              </div>
              <Select v-model="formData.status" :disabled="saveLoading">
                <SelectTrigger :class="{ 'border-destructive': errors.status }">
                  <SelectValue
                    :placeholder="
                      t('admin.pages.assistants.create.publishSettings.statusPlaceholder')
                    "
                  />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="ACTIVE">{{
                    t("admin.pages.assistants.create.publishSettings.statuses.active")
                  }}</SelectItem>
                  <SelectItem value="INACTIVE">{{
                    t("admin.pages.assistants.create.publishSettings.statuses.inactive")
                  }}</SelectItem>
                  <SelectItem value="DRAFT">{{
                    t("admin.pages.assistants.create.publishSettings.statuses.draft")
                  }}</SelectItem>
                </SelectContent>
              </Select>
              <div v-if="errors.status" class="text-destructive text-sm">
                {{ errors.status }}
              </div>
            </div>
          </div>
        </form>
      </CardContent>
    </Card>

    <!-- RAG Config -->
    <div v-if="assistant && mode === 'RAG'" class="max-w-4xl space-y-4">
      <div class="flex items-center justify-between">
        <div class="text-lg font-medium">RAG</div>
        <div class="flex items-center gap-2">
          <Label for="use-global-rag" class="text-sm">Use global RAG defaults</Label>
          <Button
            v-if="!useGlobalRagDefaults"
            type="button"
            variant="outline"
            size="sm"
            :disabled="saveLoading"
            @click="useGlobalRagDefaults = true"
          >
            Reset to global
          </Button>
          <Switch
            id="use-global-rag"
            :model-value="useGlobalRagDefaults"
            @update:model-value="(v: boolean) => (useGlobalRagDefaults = v)"
            :disabled="saveLoading"
          />
        </div>
      </div>
      <div v-if="errors.knowledge_base_ids" class="text-destructive text-sm">
        {{ errors.knowledge_base_ids }}
      </div>
      <KnowledgeBaseConfig
        v-model="kbModelValue"
        :disabled="saveLoading"
        :settingsReadOnly="useGlobalRagDefaults"
      />
    </div>

    <!-- Action buttons -->
    <Card v-if="assistant" class="max-w-4xl">
      <CardContent class="pt-6">
        <div class="flex justify-end gap-3">
          <Button variant="outline" @click="handleCancel" :disabled="saveLoading">
            <X class="mr-2 h-4 w-4" />
            {{ t("admin.cancel") }}
          </Button>
          <Button @click="updateAssistant" :disabled="saveLoading">
            <Save class="mr-2 h-4 w-4" />
            {{ t("admin.save") }}
          </Button>
        </div>
      </CardContent>
    </Card>

    <!-- Metadata info -->
    <Card v-if="assistant" class="max-w-4xl">
      <CardHeader>
        <CardTitle class="text-lg">{{ t("admin.pages.assistants.edit.metadata.title") }}</CardTitle>
      </CardHeader>
      <CardContent class="grid grid-cols-2 gap-4 text-sm">
        <div>
          <div class="text-muted-foreground">
            {{ t("admin.pages.assistants.edit.metadata.id") }}
          </div>
          <div class="font-mono text-xs">{{ assistant.id }}</div>
        </div>
        <div>
          <div class="text-muted-foreground">
            {{ t("admin.pages.assistants.edit.metadata.createdAt") }}
          </div>
          <div>{{ new Date(assistant.created_at).toLocaleString() }}</div>
        </div>
        <div>
          <div class="text-muted-foreground">
            {{ t("admin.pages.assistants.edit.metadata.updatedAt") }}
          </div>
          <div>{{ new Date(assistant.updated_at).toLocaleString() }}</div>
        </div>
        <div>
          <div class="text-muted-foreground">
            {{ t("admin.pages.assistants.edit.metadata.owner") }}
          </div>
          <div>
            {{
              assistant.owner_name ||
              assistant.owner_id ||
              t("admin.pages.assistants.edit.metadata.system")
            }}
          </div>
        </div>
      </CardContent>
    </Card>
  </div>
</template>
