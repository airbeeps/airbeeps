<script setup lang="ts">
import { Loader2 } from "lucide-vue-next";
import { Button } from "~/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "~/components/ui/card";
import { Label } from "~/components/ui/label";
import { Switch } from "~/components/ui/switch";
import { Alert, AlertDescription, AlertTitle } from "~/components/ui/alert";
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "~/components/ui/select";
import type { SystemConfigItem, SystemConfigListResponse, Model } from "~/types/api";
import { useConfigStore } from "~/stores/config";

const TITLE_MODEL_KEY = "conversation_title_model_id";
const TITLE_MODEL_AUTO_VALUE = "__auto__";
const UI_SHOW_SHARE_KEY = "ui_show_share_button";
const UI_SHOW_MESSAGE_SHARE_KEY = "ui_show_message_share_button";
const UI_SHOW_MESSAGE_FEEDBACK_KEY = "ui_show_message_feedback_buttons";
const UI_SHOW_MESSAGE_STATS_KEY = "ui_show_message_stats";
const UI_SHOW_PIN_KEY = "ui_show_pin_button";
const UI_SHOW_CREATE_KEY = "ui_show_create_button";
const UI_SHOW_ASSISTANT_DROPDOWN_KEY = "ui_show_assistant_dropdown";
const UI_SHOW_AGENT_THINKING_KEY = "ui_show_agent_thinking";
const UI_SHOW_CHAT_SUGGESTIONS_KEY = "ui_show_chat_suggestions";
const UI_GENERATE_FOLLOWUP_QUESTIONS_KEY = "ui_generate_followup_questions";
const UI_FOLLOWUP_QUESTION_COUNT_KEY = "ui_followup_question_count";
const UI_SHOW_SIGNUP_TERMS_KEY = "ui_show_signup_terms";

const { t } = useI18n();

definePageMeta({
  layout: "admin",
  breadcrumb: "System Config",
});
const { showError, showSuccess } = useNotifications();
const { $api } = useNuxtApp();
const configStore = useConfigStore();

const { data, pending, error, refresh } = await useAPI<SystemConfigListResponse>(
  "/v1/admin/config",
  { server: false }
);

// Fetch chat-capable models for the dropdown
const { data: models } = useAPI<Model[]>("/v1/admin/all-models?capabilities=chat", {
  server: false,
});

const modelOptions = computed(() => {
  const options = [
    {
      label: t("admin.systemConfig.titleModel.emptyOption"),
      value: TITLE_MODEL_AUTO_VALUE,
    },
  ];
  if (models.value) {
    options.push(
      ...models.value.map((m) => ({
        label: m.display_name || m.name,
        value: m.id,
      }))
    );
  }
  return options;
});

const configs = computed<SystemConfigItem[]>(() => data.value?.configs ?? []);

// Title Model Config
const titleModelConfig = computed(() => configs.value.find((cfg) => cfg.key === TITLE_MODEL_KEY));
const titleModelId = ref<string>(TITLE_MODEL_AUTO_VALUE);

// UI visibility configs
const showShareButtonConfig = computed(() =>
  configs.value.find((cfg) => cfg.key === UI_SHOW_SHARE_KEY)
);
const showMessageShareButtonConfig = computed(() =>
  configs.value.find((cfg) => cfg.key === UI_SHOW_MESSAGE_SHARE_KEY)
);
const showMessageFeedbackButtonsConfig = computed(() =>
  configs.value.find((cfg) => cfg.key === UI_SHOW_MESSAGE_FEEDBACK_KEY)
);
const showMessageStatsConfig = computed(() =>
  configs.value.find((cfg) => cfg.key === UI_SHOW_MESSAGE_STATS_KEY)
);
const showPinButtonConfig = computed(() =>
  configs.value.find((cfg) => cfg.key === UI_SHOW_PIN_KEY)
);
const showCreateButtonConfig = computed(() =>
  configs.value.find((cfg) => cfg.key === UI_SHOW_CREATE_KEY)
);
const showAssistantDropdownConfig = computed(() =>
  configs.value.find((cfg) => cfg.key === UI_SHOW_ASSISTANT_DROPDOWN_KEY)
);
const showAgentThinkingConfig = computed(() =>
  configs.value.find((cfg) => cfg.key === UI_SHOW_AGENT_THINKING_KEY)
);
const showChatSuggestionsConfig = computed(() =>
  configs.value.find((cfg) => cfg.key === UI_SHOW_CHAT_SUGGESTIONS_KEY)
);
const generateFollowupQuestionsConfig = computed(() =>
  configs.value.find((cfg) => cfg.key === UI_GENERATE_FOLLOWUP_QUESTIONS_KEY)
);
const followupQuestionCountConfig = computed(() =>
  configs.value.find((cfg) => cfg.key === UI_FOLLOWUP_QUESTION_COUNT_KEY)
);
const showSignupTermsConfig = computed(() =>
  configs.value.find((cfg) => cfg.key === UI_SHOW_SIGNUP_TERMS_KEY)
);

const showShareButton = ref(true);
const showMessageShareButton = ref(true);
const showMessageFeedbackButtons = ref(true);
const showMessageStats = ref(true);
const showPinButton = ref(true);
const showCreateButton = ref(true);
const showAssistantDropdown = ref(true);
const showAgentThinking = ref(true);
const showChatSuggestions = ref(true);
const generateFollowupQuestions = ref(false);
const followupQuestionCount = ref("3");
const showSignupTerms = ref(false);

// Unified watcher for all configs
watch(
  configs,
  (newConfigs) => {
    // Update Title Model
    const titleConfig = newConfigs.find((cfg) => cfg.key === TITLE_MODEL_KEY);
    const raw = titleConfig?.value;
    const asString = typeof raw === "string" ? raw.trim() : "";
    if (!raw || !asString || asString.toLowerCase() === "null") {
      titleModelId.value = TITLE_MODEL_AUTO_VALUE;
    } else {
      titleModelId.value = asString;
    }

    // UI visibility flags
    const shareCfg = newConfigs.find((cfg) => cfg.key === UI_SHOW_SHARE_KEY);
    showShareButton.value =
      shareCfg === undefined || String(shareCfg.value).toLowerCase() !== "false";

    const messageShareCfg = newConfigs.find((cfg) => cfg.key === UI_SHOW_MESSAGE_SHARE_KEY);
    showMessageShareButton.value =
      messageShareCfg === undefined || String(messageShareCfg.value).toLowerCase() !== "false";

    const messageFeedbackCfg = newConfigs.find((cfg) => cfg.key === UI_SHOW_MESSAGE_FEEDBACK_KEY);
    showMessageFeedbackButtons.value =
      messageFeedbackCfg === undefined ||
      String(messageFeedbackCfg.value).toLowerCase() !== "false";

    const messageStatsCfg = newConfigs.find((cfg) => cfg.key === UI_SHOW_MESSAGE_STATS_KEY);
    showMessageStats.value =
      messageStatsCfg === undefined || String(messageStatsCfg.value).toLowerCase() !== "false";

    const pinCfg = newConfigs.find((cfg) => cfg.key === UI_SHOW_PIN_KEY);
    showPinButton.value = pinCfg === undefined || String(pinCfg.value).toLowerCase() !== "false";

    const createCfg = newConfigs.find((cfg) => cfg.key === UI_SHOW_CREATE_KEY);
    showCreateButton.value =
      createCfg === undefined || String(createCfg.value).toLowerCase() !== "false";

    const dropdownCfg = newConfigs.find((cfg) => cfg.key === UI_SHOW_ASSISTANT_DROPDOWN_KEY);
    showAssistantDropdown.value =
      dropdownCfg === undefined || String(dropdownCfg.value).toLowerCase() !== "false";

    const thinkingCfg = newConfigs.find((cfg) => cfg.key === UI_SHOW_AGENT_THINKING_KEY);
    showAgentThinking.value =
      thinkingCfg === undefined || String(thinkingCfg.value).toLowerCase() !== "false";

    const suggestionsCfg = newConfigs.find((cfg) => cfg.key === UI_SHOW_CHAT_SUGGESTIONS_KEY);
    showChatSuggestions.value =
      suggestionsCfg === undefined || String(suggestionsCfg.value).toLowerCase() !== "false";

    const followupsEnabledCfg = newConfigs.find(
      (cfg) => cfg.key === UI_GENERATE_FOLLOWUP_QUESTIONS_KEY
    );
    // New feature: treat missing as disabled by default.
    generateFollowupQuestions.value =
      followupsEnabledCfg !== undefined &&
      String(followupsEnabledCfg.value).toLowerCase() !== "false";

    const countCfg = newConfigs.find((cfg) => cfg.key === UI_FOLLOWUP_QUESTION_COUNT_KEY);
    const parsedCount = Number(countCfg?.value ?? 3);
    const clamped =
      Number.isFinite(parsedCount) && parsedCount >= 1 && parsedCount <= 5
        ? Math.trunc(parsedCount)
        : 3;
    followupQuestionCount.value = String(clamped);

    const signupTermsCfg = newConfigs.find((cfg) => cfg.key === UI_SHOW_SIGNUP_TERMS_KEY);
    showSignupTerms.value =
      signupTermsCfg !== undefined && String(signupTermsCfg.value).toLowerCase() !== "false";
  },
  { immediate: true }
);

const isSaving = ref(false);

const handleSaveTitleModel = async () => {
  const selectedValue =
    titleModelId.value === TITLE_MODEL_AUTO_VALUE ? null : titleModelId.value.trim() || null;

  isSaving.value = true;
  try {
    const payload = titleModelConfig.value
      ? { value: selectedValue, is_enabled: true }
      : {
          key: TITLE_MODEL_KEY,
          value: selectedValue,
          description: t("admin.systemConfig.titleModel.heading"),
          is_public: false,
          is_enabled: true,
        };
    const url = titleModelConfig.value ? `/v1/admin/config/${TITLE_MODEL_KEY}` : "/v1/admin/config";
    const method = titleModelConfig.value ? "PUT" : "POST";

    await $api(url, {
      method,
      body: payload,
    });

    await refresh();
    showSuccess(t("admin.systemConfig.messages.saveSuccess"));
  } catch (err) {
    console.error("Failed to save system config", err);
    showError(t("admin.systemConfig.messages.saveFailed"));
  } finally {
    isSaving.value = false;
  }
};

const saveToggleConfig = async (
  key: string,
  currentConfig: ReturnType<typeof computed>,
  value: boolean,
  description: string,
  isPublic = true
) => {
  isSaving.value = true;
  try {
    const payload = currentConfig.value
      ? { value: value, is_enabled: true }
      : {
          key,
          value,
          description,
          is_public: isPublic,
          is_enabled: true,
        };
    const url = currentConfig.value ? `/v1/admin/config/${key}` : "/v1/admin/config";
    const method = currentConfig.value ? "PUT" : "POST";

    await $api(url, {
      method,
      body: payload,
    });

    await refresh();
    if (isPublic) {
      // Keep the in-app config store in sync so UI flags take effect without hard refresh.
      await configStore.loadConfig(true);
    }
    showSuccess(t("admin.systemConfig.messages.saveSuccess"));
  } catch (err: any) {
    showError(err.message || t("admin.systemConfig.messages.saveFailed"));
  } finally {
    isSaving.value = false;
  }
};

const saveValueConfig = async (
  key: string,
  currentConfig: ReturnType<typeof computed>,
  value: any,
  description: string,
  isPublic = true
) => {
  isSaving.value = true;
  try {
    const payload = currentConfig.value
      ? { value: value, is_enabled: true }
      : {
          key,
          value,
          description,
          is_public: isPublic,
          is_enabled: true,
        };
    const url = currentConfig.value ? `/v1/admin/config/${key}` : "/v1/admin/config";
    const method = currentConfig.value ? "PUT" : "POST";

    await $api(url, {
      method,
      body: payload,
    });

    await refresh();
    if (isPublic) {
      await configStore.loadConfig(true);
    }
    showSuccess(t("admin.systemConfig.messages.saveSuccess"));
  } catch (err: any) {
    showError(err.message || t("admin.systemConfig.messages.saveFailed"));
  } finally {
    isSaving.value = false;
  }
};

const handleSaveShowShareButton = async (value: boolean) =>
  saveToggleConfig(
    UI_SHOW_SHARE_KEY,
    showShareButtonConfig,
    value,
    t("admin.systemConfig.ui.showShareDescription")
  );

const handleSaveShowMessageShareButton = async (value: boolean) =>
  saveToggleConfig(
    UI_SHOW_MESSAGE_SHARE_KEY,
    showMessageShareButtonConfig,
    value,
    t("admin.systemConfig.ui.showMessageShareDescription")
  );

const handleSaveShowMessageFeedbackButtons = async (value: boolean) =>
  saveToggleConfig(
    UI_SHOW_MESSAGE_FEEDBACK_KEY,
    showMessageFeedbackButtonsConfig,
    value,
    t("admin.systemConfig.ui.showMessageFeedbackDescription")
  );

const handleSaveShowMessageStats = async (value: boolean) =>
  saveToggleConfig(
    UI_SHOW_MESSAGE_STATS_KEY,
    showMessageStatsConfig,
    value,
    t("admin.systemConfig.ui.showMessageStatsDescription")
  );

const handleSaveShowPinButton = async (value: boolean) =>
  saveToggleConfig(
    UI_SHOW_PIN_KEY,
    showPinButtonConfig,
    value,
    t("admin.systemConfig.ui.showPinDescription")
  );

const handleSaveShowCreateButton = async (value: boolean) =>
  saveToggleConfig(
    UI_SHOW_CREATE_KEY,
    showCreateButtonConfig,
    value,
    t("admin.systemConfig.ui.showCreateDescription")
  );

const handleSaveShowAssistantDropdown = async (value: boolean) =>
  saveToggleConfig(
    UI_SHOW_ASSISTANT_DROPDOWN_KEY,
    showAssistantDropdownConfig,
    value,
    t("admin.systemConfig.ui.showAssistantDropdownDescription")
  );

const handleSaveShowAgentThinking = async (value: boolean) =>
  saveToggleConfig(
    UI_SHOW_AGENT_THINKING_KEY,
    showAgentThinkingConfig,
    value,
    t("admin.systemConfig.ui.showAgentThinkingDescription")
  );

const handleSaveShowChatSuggestions = async (value: boolean) =>
  saveToggleConfig(
    UI_SHOW_CHAT_SUGGESTIONS_KEY,
    showChatSuggestionsConfig,
    value,
    t("admin.systemConfig.ui.showChatSuggestionsDescription")
  );

const handleSaveGenerateFollowupQuestions = async (value: boolean) =>
  saveToggleConfig(
    UI_GENERATE_FOLLOWUP_QUESTIONS_KEY,
    generateFollowupQuestionsConfig,
    value,
    t("admin.systemConfig.ui.generateFollowupQuestionsDescription")
  );

const handleSaveFollowupQuestionCount = async (value: string) => {
  const num = Number(value);
  const clamped = Number.isFinite(num) && num >= 1 && num <= 5 ? Math.trunc(num) : 3;
  followupQuestionCount.value = String(clamped);
  await saveValueConfig(
    UI_FOLLOWUP_QUESTION_COUNT_KEY,
    followupQuestionCountConfig,
    clamped,
    t("admin.systemConfig.ui.followupQuestionCountDescription")
  );
};

const handleSaveShowSignupTerms = async (value: boolean) =>
  saveToggleConfig(
    UI_SHOW_SIGNUP_TERMS_KEY,
    showSignupTermsConfig,
    value,
    t("admin.systemConfig.ui.showSignupTermsDescription")
  );
</script>

<template>
  <div class="space-y-6">
    <Alert v-if="error" variant="destructive">
      <AlertTitle>{{ t("common.error") }}</AlertTitle>
      <AlertDescription>
        {{ error?.message || t("admin.systemConfig.messages.saveFailed") }}
      </AlertDescription>
    </Alert>

    <Card>
      <CardHeader>
        <CardTitle>{{ t("admin.systemConfig.titleModel.heading") }}</CardTitle>
        <CardDescription>
          {{ t("admin.systemConfig.titleModel.description") }}
        </CardDescription>
      </CardHeader>
      <CardContent>
        <form class="space-y-4" @submit.prevent="handleSaveTitleModel">
          <div class="space-y-2">
            <Label for="title-model-id">{{ t("admin.systemConfig.titleModel.label") }}</Label>
            <Select v-model="titleModelId">
              <SelectTrigger id="title-model-id">
                <SelectValue :placeholder="t('admin.systemConfig.titleModel.placeholder')" />
              </SelectTrigger>
              <SelectContent>
                <SelectGroup>
                  <SelectItem
                    v-for="option in modelOptions"
                    :key="option.value"
                    :value="option.value"
                  >
                    {{ option.label }}
                  </SelectItem>
                </SelectGroup>
              </SelectContent>
            </Select>
            <p class="text-muted-foreground text-sm">
              {{ t("admin.systemConfig.titleModel.helper") }}
            </p>
          </div>
          <div class="flex flex-wrap gap-2">
            <Button type="submit" :disabled="isSaving">
              <Loader2 v-if="isSaving" class="mr-2 h-4 w-4 animate-spin" />
              {{ t("admin.systemConfig.actions.save") }}
            </Button>
          </div>
        </form>
      </CardContent>
    </Card>

    <Card>
      <CardHeader>
        <CardTitle>{{ t("admin.systemConfig.ui.title") }}</CardTitle>
        <CardDescription>
          {{ t("admin.systemConfig.ui.description") }}
        </CardDescription>
      </CardHeader>
      <CardContent class="space-y-4">
        <div class="flex items-center space-x-2">
          <Switch
            id="ui-show-share"
            :model-value="showShareButton"
            @update:model-value="handleSaveShowShareButton"
            :disabled="isSaving"
          />
          <Label for="ui-show-share">
            {{ t("admin.systemConfig.ui.showShareLabel") }}
          </Label>
        </div>
        <div class="flex items-center space-x-2">
          <Switch
            id="ui-show-message-share"
            :model-value="showMessageShareButton"
            @update:model-value="handleSaveShowMessageShareButton"
            :disabled="isSaving"
          />
          <Label for="ui-show-message-share">
            {{ t("admin.systemConfig.ui.showMessageShareLabel") }}
          </Label>
        </div>
        <div class="flex items-center space-x-2">
          <Switch
            id="ui-show-message-feedback"
            :model-value="showMessageFeedbackButtons"
            @update:model-value="handleSaveShowMessageFeedbackButtons"
            :disabled="isSaving"
          />
          <Label for="ui-show-message-feedback">
            {{ t("admin.systemConfig.ui.showMessageFeedbackLabel") }}
          </Label>
        </div>
        <div class="flex items-center space-x-2">
          <Switch
            id="ui-show-message-stats"
            :model-value="showMessageStats"
            @update:model-value="handleSaveShowMessageStats"
            :disabled="isSaving"
          />
          <Label for="ui-show-message-stats">
            {{ t("admin.systemConfig.ui.showMessageStatsLabel") }}
          </Label>
        </div>
        <div class="flex items-center space-x-2">
          <Switch
            id="ui-show-pin"
            :model-value="showPinButton"
            @update:model-value="handleSaveShowPinButton"
            :disabled="isSaving"
          />
          <Label for="ui-show-pin">
            {{ t("admin.systemConfig.ui.showPinLabel") }}
          </Label>
        </div>
        <div class="flex items-center space-x-2">
          <Switch
            id="ui-show-create"
            :model-value="showCreateButton"
            @update:model-value="handleSaveShowCreateButton"
            :disabled="isSaving"
          />
          <Label for="ui-show-create">
            {{ t("admin.systemConfig.ui.showCreateLabel") }}
          </Label>
        </div>
        <div class="flex items-center space-x-2">
          <Switch
            id="ui-show-assistant-dropdown"
            :model-value="showAssistantDropdown"
            @update:model-value="handleSaveShowAssistantDropdown"
            :disabled="isSaving"
          />
          <Label for="ui-show-assistant-dropdown">
            {{ t("admin.systemConfig.ui.showAssistantDropdownLabel") }}
          </Label>
        </div>
        <div class="flex items-center space-x-2">
          <Switch
            id="ui-show-agent-thinking"
            :model-value="showAgentThinking"
            @update:model-value="handleSaveShowAgentThinking"
            :disabled="isSaving"
          />
          <Label for="ui-show-agent-thinking">
            {{ t("admin.systemConfig.ui.showAgentThinkingLabel") }}
          </Label>
        </div>
        <div class="flex items-center space-x-2">
          <Switch
            id="ui-show-chat-suggestions"
            :model-value="showChatSuggestions"
            @update:model-value="handleSaveShowChatSuggestions"
            :disabled="isSaving"
          />
          <Label for="ui-show-chat-suggestions">
            {{ t("admin.systemConfig.ui.showChatSuggestionsLabel") }}
          </Label>
        </div>

        <div class="flex items-center space-x-2">
          <Switch
            id="ui-generate-followups"
            :model-value="generateFollowupQuestions"
            @update:model-value="handleSaveGenerateFollowupQuestions"
            :disabled="isSaving"
          />
          <Label for="ui-generate-followups">
            {{ t("admin.systemConfig.ui.generateFollowupQuestionsLabel") }}
          </Label>
        </div>

        <div class="space-y-2">
          <Label for="ui-followup-count">
            {{ t("admin.systemConfig.ui.followupQuestionCountLabel") }}
          </Label>
          <Select
            v-model="followupQuestionCount"
            :disabled="isSaving || !generateFollowupQuestions"
            @update:model-value="handleSaveFollowupQuestionCount"
          >
            <SelectTrigger id="ui-followup-count" class="max-w-xs">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectGroup>
                <SelectItem v-for="n in [1, 2, 3, 4, 5]" :key="n" :value="String(n)">
                  {{ n }}
                </SelectItem>
              </SelectGroup>
            </SelectContent>
          </Select>
          <p class="text-muted-foreground text-sm">
            {{ t("admin.systemConfig.ui.followupQuestionCountDescription") }}
          </p>
        </div>

        <div class="flex items-center space-x-2">
          <Switch
            id="ui-show-signup-terms"
            :model-value="showSignupTerms"
            @update:model-value="handleSaveShowSignupTerms"
            :disabled="isSaving"
          />
          <Label for="ui-show-signup-terms">
            {{ t("admin.systemConfig.ui.showSignupTermsLabel") }}
          </Label>
        </div>
      </CardContent>
    </Card>
  </div>
</template>
