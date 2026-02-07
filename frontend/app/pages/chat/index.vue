<script setup lang="ts">
import type { Assistant, Message } from "~/types/api";
import { Button } from "~/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "~/components/ui/dialog";

const { t } = useI18n();

useHead({
  title: t("nav.newChat"),
});

const {
  data: pinnedAssistants,
  pending: pinnedPending,
  refresh: refreshPinned,
} = useAPI<Assistant[]>("/v1/assistants", {
  query: { scope: "pinned", limit: 50 },
  lazy: true,
});

const {
  data: popularAssistants,
  pending: popularPending,
  refresh: refreshPopular,
} = useAPI<Assistant[]>("/v1/assistants", {
  query: { sort_by: "usage_count", order: "desc", limit: 50 },
  lazy: true,
});

const assistants = computed<Assistant[]>(() => {
  const map = new Map<string, Assistant>();
  (pinnedAssistants.value ?? []).forEach((a) => map.set(a.id, a));
  (popularAssistants.value ?? []).forEach((a) => map.set(a.id, a));
  return Array.from(map.values());
});

const selectedAssistantId = ref<string | null>(null);

watchEffect(() => {
  if (!selectedAssistantId.value && assistants.value.length > 0) {
    selectedAssistantId.value = assistants.value[0].id;
  }
});

const selectedAssistant = computed<Assistant | null>(() => {
  return assistants.value.find((a) => a.id === selectedAssistantId.value) ?? null;
});

const messages = ref<Message[]>([]);
const newMessage = ref("");
const isLoading = ref(false);
const isCreatingConversation = ref(false);
const inputDisabled = ref(false);
const loginPromptShown = ref(false);
const pendingAuthCheck = ref<Promise<boolean> | null>(null);
const chatInputRef = ref();

const { $api } = useNuxtApp();
const newConversationStore = useNewConversationStore();
const conversationsStore = useConversationsStore();
const userStore = useUserStore();
const configStore = useConfigStore();
const { showError } = useNotifications();
const route = useRoute();

const loadingAssistants = computed(() => pinnedPending.value || popularPending.value);

const isAdmin = computed(() => Boolean(userStore.user?.is_superuser));

const ONBOARDING_DISMISS_KEY = "airbeeps.onboarding.no_assistants.dismissed";
const onboardingDismissed = ref(false);
const onboardingOpen = ref(false);

const hasAnyAssistants = computed(() => assistants.value.length > 0);

const maybeOpenOnboarding = () => {
  if (loadingAssistants.value) return;
  if (hasAnyAssistants.value) {
    onboardingOpen.value = false;
    return;
  }
  if (!onboardingDismissed.value) {
    onboardingOpen.value = true;
  }
};

const dismissOnboarding = () => {
  onboardingOpen.value = false;
  onboardingDismissed.value = true;
  if (process.client) {
    localStorage.setItem(ONBOARDING_DISMISS_KEY, "1");
  }
};

const refreshAssistants = async () => {
  await Promise.all([refreshPinned(), refreshPopular()]);
};

const supportsVision = computed(() => {
  if (!selectedAssistant.value?.model?.capabilities) return false;
  return selectedAssistant.value.model.capabilities.includes("vision");
});

// Use chat preferences store for model selector and web search state persistence
const chatPreferencesStore = useChatPreferencesStore();
const selectedModelId = computed(() => chatPreferencesStore.selectedModelId);
const webSearchEnabled = computed({
  get: () => chatPreferencesStore.webSearchEnabled,
  set: (val) => chatPreferencesStore.setWebSearchEnabled(val),
});

const showWebSearchToggle = computed(() => {
  // Security: Hide toggle until config is loaded
  if (!configStore.isLoaded) return false;
  const configAllows = configStore.config.ui_show_web_search_toggle !== false;
  const assistantHasWebSearch =
    selectedAssistant.value?.agent_enabled_tools?.includes("web_search");
  return configAllows && assistantHasWebSearch;
});

const handleModelSelect = (modelId: string | null) => {
  chatPreferencesStore.setSelectedModelId(modelId);
};

const resetPageState = () => {
  messages.value = [];
  newMessage.value = "";
  isLoading.value = false;
  isCreatingConversation.value = false;
  newConversationStore.cleanupOldConversations();
};

const ensureAuthenticated = async () => {
  if (userStore.user) {
    return true;
  }

  if (!pendingAuthCheck.value) {
    pendingAuthCheck.value = (async () => {
      try {
        const loggedIn = await userStore.fetchUser();
        if (loggedIn && userStore.user) {
          return true;
        }
      } catch (error) {
        console.error("Failed to fetch user state:", error);
      }

      if (!loginPromptShown.value) {
        showError(t("assistants.loginRequired"));
        loginPromptShown.value = true;
      }

      await navigateTo({
        path: "/sign-in",
        query: { redirect: route.fullPath },
      });
      return false;
    })().finally(() => {
      pendingAuthCheck.value = null;
    });
  }

  return pendingAuthCheck.value;
};

const handleInputFocus = async () => {
  if (userStore.user) {
    return;
  }
  inputDisabled.value = true;
  await ensureAuthenticated();
};

const handleInputKeydown = async (event: KeyboardEvent) => {
  if (await ensureAuthenticated()) {
    return;
  }
  event.preventDefault();
  event.stopPropagation();
};

const sendMessage = async (images?: any[]) => {
  if (!(await ensureAuthenticated())) {
    return;
  }

  if (!newMessage.value.trim() || isLoading.value || !selectedAssistant.value) return;

  const assistantId = selectedAssistant.value.id;
  const messageContent = newMessage.value.trim();
  newMessage.value = "";
  isLoading.value = true;
  isCreatingConversation.value = true;

  const userMessage: Message = {
    id: Date.now().toString(),
    content: messageContent,
    message_type: "USER",
    created_at: new Date().toISOString(),
    extra_data: images && images.length > 0 ? { images } : undefined,
  };
  messages.value.push(userMessage);

  try {
    const conversation = await conversationsStore.createConversation(assistantId);
    if (!conversation) {
      messages.value = messages.value.filter((msg) => msg.id !== userMessage.id);
      isLoading.value = false;
      isCreatingConversation.value = false;
      return;
    }

    if (selectedAssistant.value) {
      newConversationStore.setConversationData(
        conversation.id,
        userMessage,
        selectedAssistant.value
      );
    }

    resetPageState();
    await navigateTo(`/chat/${conversation.id}`);
  } catch (error) {
    console.error("Failed to initiate conversation:", error);
    messages.value = messages.value.filter((msg) => msg.id !== userMessage.id);
    isLoading.value = false;
    isCreatingConversation.value = false;
    showError(
      `${t("chat.sendFailed")}: ${error instanceof Error ? error.message : t("chat.unknownError")}`
    );
  }
};

const handleAssistantChange = (assistantId: string) => {
  if (assistantId === selectedAssistantId.value) return;
  selectedAssistantId.value = assistantId;
  resetPageState();
};

const handleSuggestionSelect = (prompt: string) => {
  newMessage.value = prompt;
  sendMessage();
};

const showLanding = computed(() => {
  return messages.value.length === 0 && !isCreatingConversation.value;
});

// Security: Hide toggles until config is loaded to respect admin settings
const showMessageShareButton = computed(
  () => configStore.isLoaded && configStore.config.ui_show_message_share_button !== false
);

const showAssistantDropdown = computed(
  () => configStore.isLoaded && configStore.config.ui_show_assistant_dropdown !== false
);

onMounted(() => {
  resetPageState();
  if (process.client) {
    onboardingDismissed.value = localStorage.getItem(ONBOARDING_DISMISS_KEY) === "1";
  }
  maybeOpenOnboarding();
  // Focus the input after mount
  nextTick(() => {
    chatInputRef.value?.focus();
  });
});

onUnmounted(() => {
  resetPageState();
});

watch(
  () => userStore.user,
  (val) => {
    if (val) {
      inputDisabled.value = false;
    }
  }
);

watchEffect(() => {
  // Re-evaluate onboarding visibility when assistant list loads/changes.
  if (process.client) {
    maybeOpenOnboarding();
  }
});
</script>

<template>
  <div class="flex h-screen flex-col">
    <!-- Fallback header so settings stay reachable when no assistants exist -->
    <AppHeader v-if="!selectedAssistant">
      <div class="flex items-center gap-2">
        <span class="font-semibold">{{ t("nav.newChat") }}</span>
      </div>
    </AppHeader>

    <div v-if="loadingAssistants" class="flex flex-1 items-center justify-center">
      <div class="border-primary h-8 w-8 animate-spin rounded-full border-b-2" />
    </div>

    <div v-else-if="!selectedAssistant" class="flex flex-1 items-center justify-center px-4">
      <Dialog v-model:open="onboardingOpen">
        <DialogContent class="sm:max-w-[560px]">
          <DialogHeader>
            <DialogTitle>{{ $t("assistants.onboarding.title") }}</DialogTitle>
            <DialogDescription>
              {{ $t("assistants.onboarding.subtitle") }}
            </DialogDescription>
          </DialogHeader>

          <div class="space-y-4">
            <div class="border-border/60 bg-muted/30 rounded-lg border p-4">
              <p class="font-medium">
                {{
                  isAdmin
                    ? $t("assistants.onboarding.adminTitle")
                    : $t("assistants.onboarding.userTitle")
                }}
              </p>
              <p v-if="!isAdmin" class="text-muted-foreground mt-2 text-sm">
                {{ $t("assistants.onboarding.userHelp") }}
              </p>
            </div>

            <div v-if="isAdmin" class="space-y-2">
              <p class="text-sm font-medium">
                {{ $t("assistants.onboarding.stepsTitle") }}
              </p>
              <ol class="text-muted-foreground list-inside list-decimal space-y-2 text-sm">
                <li>{{ $t("assistants.onboarding.steps.provider") }}</li>
                <li>{{ $t("assistants.onboarding.steps.model") }}</li>
                <li>{{ $t("assistants.onboarding.steps.assistant") }}</li>
              </ol>
            </div>
          </div>

          <DialogFooter
            class="flex-col-reverse gap-3 sm:flex-col sm:items-stretch sm:justify-start"
          >
            <div class="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
              <Button variant="outline" @click="dismissOnboarding">
                {{ $t("assistants.onboarding.actions.dismiss") }}
              </Button>
              <Button variant="secondary" @click="refreshAssistants">
                {{ $t("assistants.onboarding.actions.refresh") }}
              </Button>
            </div>

            <div v-if="isAdmin" class="flex flex-wrap gap-2 sm:justify-end">
              <Button variant="outline" @click="navigateTo('/admin')">
                {{ $t("assistants.onboarding.actions.openAdmin") }}
              </Button>
              <Button
                variant="outline"
                class="whitespace-normal"
                @click="navigateTo('/admin/model-providers')"
              >
                {{ $t("assistants.onboarding.actions.openProviders") }}
              </Button>
              <Button
                variant="outline"
                class="whitespace-normal"
                @click="navigateTo('/admin/models')"
              >
                {{ $t("assistants.onboarding.actions.openModels") }}
              </Button>
              <Button @click="navigateTo('/admin/assistants/create')">
                {{ $t("assistants.onboarding.actions.createAssistant") }}
              </Button>
            </div>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <!-- Non-modal empty state (still visible after dismiss) -->
      <div v-if="!onboardingOpen" class="w-full max-w-2xl text-center">
        <div class="border-border/70 bg-card/70 rounded-2xl border p-8 shadow-sm backdrop-blur-sm">
          <p class="text-lg font-semibold">
            {{ $t("assistants.noAssistants") }}
          </p>
          <p class="text-muted-foreground mt-2 text-sm">
            {{
              isAdmin
                ? $t("assistants.onboarding.adminTitle")
                : $t("assistants.onboarding.userHelp")
            }}
          </p>
          <div class="mt-6 flex flex-wrap justify-center gap-2">
            <Button variant="secondary" @click="refreshAssistants">
              {{ $t("assistants.onboarding.actions.refresh") }}
            </Button>
            <template v-if="isAdmin">
              <Button variant="outline" @click="navigateTo('/admin')">
                {{ $t("assistants.onboarding.actions.openAdmin") }}
              </Button>
              <Button variant="outline" @click="navigateTo('/admin/model-providers')">
                {{ $t("assistants.onboarding.actions.openProviders") }}
              </Button>
              <Button variant="outline" @click="navigateTo('/admin/models')">
                {{ $t("assistants.onboarding.actions.openModels") }}
              </Button>
              <Button @click="navigateTo('/admin/assistants/create')">
                {{ $t("assistants.onboarding.actions.createAssistant") }}
              </Button>
            </template>
          </div>
        </div>
      </div>
    </div>

    <ChatLayout
      v-else
      :assistant="selectedAssistant"
      :assistants="assistants"
      :show-landing-input="showLanding"
      :selected-model-id="selectedModelId"
      @select-assistant="handleAssistantChange"
      @select-model="handleModelSelect"
    >
      <ChatWelcome
        v-if="showLanding"
        :assistant="selectedAssistant"
        :show-welcome="true"
        @select-suggestion="handleSuggestionSelect"
      />

      <ChatMessage
        v-for="message in messages"
        v-else
        :key="message.id"
        :message="message"
        :assistant="selectedAssistant"
        :enable-share="showMessageShareButton"
      />

      <ChatLoading
        v-if="isCreatingConversation"
        :assistant="selectedAssistant"
        :message="t('chat.creatingConversation', 'Creating new conversation...')"
      />

      <template #input>
        <ChatInput
          ref="chatInputRef"
          v-model="newMessage"
          :disabled="inputDisabled || isLoading"
          :send-disabled="inputDisabled || isLoading || !newMessage.trim()"
          :supports-vision="supportsVision"
          :show-web-search-toggle="showWebSearchToggle"
          :web-search-enabled="webSearchEnabled"
          @update:web-search-enabled="webSearchEnabled = $event"
          @keydown="handleInputKeydown"
          @focus="handleInputFocus"
          @click="handleInputFocus"
          @send="sendMessage"
        />
      </template>
    </ChatLayout>
  </div>
</template>
