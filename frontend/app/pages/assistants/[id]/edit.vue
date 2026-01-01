<script setup lang="ts">
import { ref, computed, onMounted } from "vue";
import { useRouter, useRoute } from "vue-router";
import { Save, X } from "lucide-vue-next";
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
import { toast } from "vue-sonner";
import type { Assistant, Model } from "~/types/api";
import { useConfigStore } from "~/stores/config";

const { t } = useI18n();

useHead({
  title: t("assistantForm.editTitle"),
});

// Page metadata
definePageMeta({
  layout: "default",
});

const router = useRouter();
const route = useRoute();
const assistantId = route.params.id as string;
const configStore = useConfigStore();

// Fetch model list
const { data: models } = useAPI<Model[]>("/v1/models", { server: false });

const modelOptions = computed(() =>
  (models.value ?? [])
    .filter((m) => m.status === "ACTIVE")
    .map((m) => ({ label: m.display_name, value: m.id }))
);

// State management
const loading = ref(false);
const fetching = ref(true);

// Form data
const formData = ref<Partial<Assistant>>({
  name: "",
  avatar_file_path: "",
  description: "",
  system_prompt: "",
  model_id: "",
  max_history_messages: 10,
  is_public: false,
  status: "ACTIVE",
  followup_questions_enabled: true,
  followup_questions_count: null,
});

const followupsGlobalEnabled = ref(false);
const followupsGlobalMaxCount = ref(3);
const followupQuestionsCount = ref<string>("__global__");

onMounted(async () => {
  const cfg = await configStore.getConfig();
  followupsGlobalEnabled.value = cfg.ui_generate_followup_questions !== false;
  const n = Number(cfg.ui_followup_question_count ?? 3);
  followupsGlobalMaxCount.value = Number.isFinite(n) ? Math.max(1, Math.min(5, Math.trunc(n))) : 3;
});

// Fetch assistant details
const fetchAssistant = async () => {
  fetching.value = true;
  try {
    const { $api } = useNuxtApp();
    const data = await $api<Assistant>(`/v1/assistants/${assistantId}`);

    // Fill form data
    formData.value = {
      ...data,
      max_history_messages: Number(data.max_history_messages),
    };
    formData.value.followup_questions_enabled = data.followup_questions_enabled ?? true;
    followupQuestionsCount.value =
      typeof data.followup_questions_count === "number"
        ? String(
            Math.max(
              1,
              Math.min(followupsGlobalMaxCount.value, Math.trunc(data.followup_questions_count))
            )
          )
        : "__global__";
  } catch (error) {
    console.error("Failed to fetch assistant details:", error);
    toast.error(t("assistantForm.fetchFailed"));
    router.push("/assistants");
  } finally {
    fetching.value = false;
  }
};

onMounted(() => {
  fetchAssistant();
});

// Form validation errors
const errors = ref<Record<string, string>>({});

// Form validation
const validateForm = (): boolean => {
  const newErrors: Record<string, string> = {};

  if (!formData.value.name || formData.value.name.length < 2) {
    newErrors.name = t("assistantForm.nameError");
  }
  // description is optional now
  if (!formData.value.system_prompt || formData.value.system_prompt.length < 10) {
    newErrors.system_prompt = t("assistantForm.systemPromptError");
  }
  if (!formData.value.model_id) {
    newErrors.model_id = t("assistantForm.modelError");
  }

  errors.value = newErrors;
  return Object.keys(newErrors).length === 0;
};

// Update assistant
const updateAssistant = async () => {
  if (!validateForm()) {
    toast.error(t("assistantForm.validationError"));
    return;
  }

  loading.value = true;
  try {
    const { $api } = useNuxtApp();

    const submitData: any = { ...formData.value };
    if (submitData.followup_questions_enabled === false) {
      submitData.followup_questions_count = null;
    } else {
      submitData.followup_questions_count =
        followupQuestionsCount.value === "__global__"
          ? null
          : Math.min(
              followupsGlobalMaxCount.value,
              Math.max(1, Number(followupQuestionsCount.value))
            );
    }

    await $api(`/v1/assistants/${assistantId}`, {
      method: "PUT",
      body: submitData,
    });

    toast.success(t("assistantForm.updateSuccess"));
    router.push("/assistants");
  } catch (error) {
    console.error("Update failed:", error);
    toast.error(t("assistantForm.updateFailed"));
  } finally {
    loading.value = false;
  }
};

// Cancel action
const handleCancel = () => {
  router.push("/assistants");
};
</script>

<template>
  <div class="absolute inset-0 flex flex-col overflow-hidden rounded-[inherit]">
    <AppHeader>
      <Breadcrumb>
        <BreadcrumbList>
          <BreadcrumbItem>
            <BreadcrumbLink as-child>
              <NuxtLink to="/assistants">
                {{ t("chat.breadcrumbAssistants") }}
              </NuxtLink>
            </BreadcrumbLink>
          </BreadcrumbItem>
          <BreadcrumbSeparator />
          <BreadcrumbItem>
            <BreadcrumbPage>{{ t("assistantForm.editTitle") }}</BreadcrumbPage>
          </BreadcrumbItem>
        </BreadcrumbList>
      </Breadcrumb>
    </AppHeader>

    <div class="flex-1 overflow-y-auto">
      <div class="container mx-auto max-w-4xl space-y-6 py-6">
        <div v-if="fetching" class="flex justify-center py-12">
          <div class="border-primary h-8 w-8 animate-spin rounded-full border-b-2"></div>
        </div>

        <template v-else>
          <!-- Form card -->
          <Card>
            <CardHeader>
              <CardTitle>{{ t("assistantForm.basicInfo") }}</CardTitle>
              <CardDescription>
                {{ t("assistantForm.basicInfoDesc") }}
              </CardDescription>
            </CardHeader>
            <CardContent>
              <form @submit.prevent="updateAssistant" class="space-y-6">
                <!-- Basic info -->
                <div class="space-y-4">
                  <!-- Avatar -->
                  <div class="space-y-2">
                    <Label for="avatar">{{ t("assistantForm.avatar") }}</Label>
                    <AvatarUpload
                      id="avatar"
                      v-model="formData.avatar_file_path"
                      :disabled="loading"
                    />
                    <div class="text-muted-foreground text-sm">
                      {{ t("assistantForm.avatarHelp") }}
                    </div>
                  </div>

                  <!-- Name -->
                  <div class="space-y-2">
                    <Label for="name">
                      {{ t("assistantForm.name") }} <span class="text-destructive">*</span>
                    </Label>
                    <Input
                      id="name"
                      v-model="formData.name"
                      :placeholder="t('assistantForm.namePlaceholder')"
                      :class="{ 'border-destructive': errors.name }"
                      :disabled="loading"
                    />
                    <div v-if="errors.name" class="text-destructive text-sm">
                      {{ errors.name }}
                    </div>
                  </div>
                  <!-- Description -->
                  <div class="space-y-2">
                    <Label for="description">
                      {{ t("assistantForm.description") }}
                    </Label>
                    <Textarea
                      id="description"
                      v-model="formData.description"
                      :placeholder="t('assistantForm.descriptionPlaceholder')"
                      :rows="3"
                      :class="{ 'border-destructive': errors.description }"
                      :disabled="loading"
                    />
                    <div v-if="errors.description" class="text-destructive text-sm">
                      {{ errors.description }}
                    </div>
                  </div>
                </div>

                <!-- Model config -->
                <div class="space-y-4">
                  <h3 class="text-lg font-medium">{{ t("assistantForm.modelConfig") }}</h3>

                  <!-- System prompt -->
                  <div class="space-y-2">
                    <Label for="system_prompt">
                      {{ t("assistantForm.systemPrompt") }} <span class="text-destructive">*</span>
                    </Label>
                    <Textarea
                      id="system_prompt"
                      v-model="formData.system_prompt"
                      :placeholder="t('assistantForm.systemPromptPlaceholder')"
                      :rows="5"
                      :class="{ 'border-destructive': errors.system_prompt }"
                      :disabled="loading"
                    />
                    <div v-if="errors.system_prompt" class="text-destructive text-sm">
                      {{ errors.system_prompt }}
                    </div>
                    <div class="text-muted-foreground text-sm">
                      {{ t("assistantForm.systemPromptHelp") }}
                    </div>
                  </div>

                  <!-- Model selection -->
                  <div class="space-y-2">
                    <Label for="model_id">
                      {{ t("assistantForm.model") }} <span class="text-destructive">*</span>
                    </Label>
                    <Select v-model="formData.model_id" :disabled="loading">
                      <SelectTrigger :class="{ 'border-destructive': errors.model_id }">
                        <SelectValue :placeholder="t('assistantForm.modelPlaceholder')" />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem
                          v-for="model in modelOptions"
                          :key="model.value"
                          :value="model.value"
                        >
                          {{ model.label }}
                        </SelectItem>
                      </SelectContent>
                    </Select>
                    <div v-if="errors.model_id" class="text-destructive text-sm">
                      {{ errors.model_id }}
                    </div>
                    <div class="text-muted-foreground text-sm">
                      {{ t("assistantForm.modelHelp") }}
                    </div>
                  </div>

                  <!-- Parameter config -->
                  <div class="space-y-2">
                    <Label for="max_history_messages">{{ t("assistantForm.maxHistory") }}</Label>
                    <Input
                      id="max_history_messages"
                      v-model.number="formData.max_history_messages"
                      type="number"
                      placeholder="10"
                      min="0"
                      max="100"
                      :disabled="loading"
                    />
                    <div class="text-muted-foreground text-sm">
                      {{ t("assistantForm.maxHistoryHelp") }}
                    </div>
                  </div>
                </div>

                <!-- Follow-up Questions -->
                <div class="space-y-4">
                  <h3 class="text-lg font-medium">{{ t("assistantForm.followupsTitle") }}</h3>
                  <div class="bg-muted/30 space-y-3 rounded-md border p-4">
                    <div v-if="!followupsGlobalEnabled" class="text-muted-foreground text-sm">
                      {{ t("assistantForm.followupsGloballyDisabled") }}
                    </div>
                    <div class="flex items-center justify-between gap-3">
                      <div class="text-sm font-semibold">
                        {{ t("assistantForm.followupsEnableLabel") }}
                      </div>
                      <Switch
                        id="assistant-followups-enabled"
                        :model-value="formData.followup_questions_enabled !== false"
                        @update:model-value="
                          (v: boolean) => (formData.followup_questions_enabled = v)
                        "
                        :disabled="loading || !followupsGlobalEnabled"
                      />
                    </div>
                    <div class="space-y-2">
                      <Label for="assistant-followups-count">
                        {{ t("assistantForm.followupsCountLabel") }}
                      </Label>
                      <Select
                        v-model="followupQuestionsCount"
                        :disabled="
                          loading ||
                          !followupsGlobalEnabled ||
                          formData.followup_questions_enabled === false
                        "
                      >
                        <SelectTrigger id="assistant-followups-count" class="max-w-xs">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="__global__">
                            {{
                              t("assistantForm.followupsUseGlobal", {
                                count: followupsGlobalMaxCount,
                              })
                            }}
                          </SelectItem>
                          <SelectItem
                            v-for="n in Array.from(
                              { length: followupsGlobalMaxCount },
                              (_, i) => i + 1
                            )"
                            :key="n"
                            :value="String(n)"
                          >
                            {{ n }}
                          </SelectItem>
                        </SelectContent>
                      </Select>
                      <div class="text-muted-foreground text-sm">
                        {{
                          t("assistantForm.followupsMaxAllowed", { count: followupsGlobalMaxCount })
                        }}
                      </div>
                    </div>
                  </div>
                </div>

                <!-- Publish settings -->
                <div class="space-y-4">
                  <h3 class="text-lg font-medium">{{ t("assistantForm.publishSettings") }}</h3>

                  <!-- Is public -->
                  <div class="flex items-center space-x-2">
                    <input
                      id="is_public"
                      type="checkbox"
                      v-model="formData.is_public"
                      :disabled="loading"
                      class="text-primary focus:ring-primary h-4 w-4 rounded border-gray-300"
                    />
                    <Label for="is_public" class="cursor-pointer text-sm">
                      {{ t("assistantForm.isPublic") }}
                    </Label>
                  </div>

                  <!-- Status -->
                  <div class="space-y-2">
                    <Label for="status">
                      {{ t("assistantForm.status") }} <span class="text-destructive">*</span>
                    </Label>
                    <Select v-model="formData.status" :disabled="loading">
                      <SelectTrigger>
                        <SelectValue :placeholder="t('assistantForm.statusPlaceholder')" />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="ACTIVE">{{
                          t("assistantForm.statusActive")
                        }}</SelectItem>
                        <SelectItem value="DRAFT">{{ t("assistantForm.statusDraft") }}</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                </div>
              </form>
            </CardContent>
          </Card>

          <!-- Action buttons -->
          <Card>
            <CardContent class="pt-6">
              <div class="flex justify-end gap-3">
                <Button variant="outline" @click="handleCancel" :disabled="loading">
                  <X class="mr-2 h-4 w-4" />
                  {{ t("common.cancel") }}
                </Button>
                <Button @click="updateAssistant" :disabled="loading">
                  <Save class="mr-2 h-4 w-4" />
                  {{ t("assistantForm.saveButton") }}
                </Button>
              </div>
            </CardContent>
          </Card>
        </template>
      </div>
    </div>
  </div>
</template>
