<script setup lang="ts">
import { Plus, Share2, Pin, PinOff } from "lucide-vue-next";
import { Button } from "~/components/ui/button";
import { DropdownMenu, DropdownMenuContent } from "~/components/ui/dropdown-menu";
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from "~/components/ui/breadcrumb";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "~/components/ui/dialog";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "~/components/ui/tooltip";
import { Input } from "~/components/ui/input";
import { useMediaQuery } from "@vueuse/core";
import type {
  Assistant,
  Conversation,
  PaginatedResponse,
  Message,
  ConversationShareResponse,
} from "~/types/api";
import type {
  AgentStep,
  ContentChunkPayload,
  ImageAttachment,
  ReasoningTracePayload,
} from "~/composables/useStreamingChat";

definePageMeta({
  keepalive: true,
});

const route = useRoute();
const conversationId = route.params.id as string;

const userStore = useUserStore();
const configStore = useConfigStore();

// Use new conversation store for assistant and message data
const newConversationStore = useNewConversationStore();
const conversationsStore = useConversationsStore();

const handlePin = async () => {
  if (!assistant.value || !userStore.user) {
    return;
  }

  const isPinned = assistant.value.is_pinned;

  try {
    if (isPinned) {
      await $api(`/v1/assistants/${assistant.value.id}/pin`, {
        method: "DELETE",
      });
      assistant.value.is_pinned = false;
      showSuccess(t("assistants.unpinned"));
    } else {
      await $api(`/v1/assistants/${assistant.value.id}/pin`, {
        method: "POST",
      });
      assistant.value.is_pinned = true;
      showSuccess(t("assistants.pinned"));
    }
  } catch (e) {
    showError(t("common.error"));
  }
};

// Chat state
const messages = ref<Message[]>([]);
const newMessage = ref("");
const chatInputRef = ref();
const isLoading = ref(false);
const isStreaming = ref(false);
const messagesEnd = ref<HTMLElement>();
const currentConversationId = ref<string | null>(conversationId);
const streamingAssistantMessage = ref<Message | null>(null);
const conversationInfo = ref<Conversation | null>(null);
const isLoadingHistory = ref(false);
const assistant = ref<Assistant | null>(null);
const isNewConversation = ref(false); // Track if this is a new conversation

const showPinButton = computed(() => configStore.config.ui_show_pin_button !== false);
const showShareButton = computed(() => configStore.config.ui_show_share_button !== false);
const showMessageShareButton = computed(
  () => configStore.config.ui_show_message_share_button !== false
);
const showCreateButton = computed(() => configStore.config.ui_show_create_button !== false);

type ShareScope = "CONVERSATION" | "MESSAGE";
const shareDialogOpen = ref(false);
const shareDialogUrl = ref("");
const shareDialogLoading = ref(false);
const shareDialogScope = ref<ShareScope>("CONVERSATION");

const isDesktop = useMediaQuery("(min-width: 768px)");

const ensureAgentExecution = (message: Message): AgentStep[] => {
  if (!message.extra_data) {
    message.extra_data = {};
  }
  const extra: any = message.extra_data as any;
  if (!Array.isArray(extra.agent_execution)) {
    extra.agent_execution = [];
  }
  return extra.agent_execution as AgentStep[];
};

// Scroll control state
const shouldAutoScroll = ref(true);
const scrollContainer = ref<HTMLElement>();
const scrollContent = ref<HTMLElement>();
const hasScrollableContent = ref(false);

let contentResizeObserver: ResizeObserver | null = null;

// Debounced scroll function to improve performance
let scrollTimeoutId: ReturnType<typeof setTimeout> | null = null;
const debouncedScrollToBottom = () => {
  // Only execute when auto-scroll is allowed
  if (!shouldAutoScroll.value) return;

  if (scrollTimeoutId) {
    clearTimeout(scrollTimeoutId);
  }
  scrollTimeoutId = setTimeout(() => {
    scrollToBottom();
  }, 50); // 50ms debounce
};

// Detect if user is near the bottom
const checkScrollPosition = () => {
  if (!scrollContainer.value) return;

  const { scrollTop, scrollHeight, clientHeight } = scrollContainer.value;
  const threshold = 30; // 30px threshold, stops auto-scroll after a small scroll
  const isNearBottom = scrollHeight - scrollTop - clientHeight < threshold;

  shouldAutoScroll.value = isNearBottom;

  // Check if content is actually scrollable
  hasScrollableContent.value = scrollHeight > clientHeight + 50; // 50px buffer
};

// Handle user scroll event
const handleScroll = () => {
  checkScrollPosition();
};

const observeScrollContent = () => {
  if (typeof window === "undefined" || typeof ResizeObserver === "undefined") {
    return;
  }

  if (!contentResizeObserver) {
    contentResizeObserver = new ResizeObserver(() => {
      if (shouldAutoScroll.value) {
        debouncedScrollToBottom();
      }
    });
  }

  if (scrollContent.value) {
    contentResizeObserver.observe(scrollContent.value);
  }
};

// Force scroll to bottom (used when sending new message)
const forceScrollToBottom = (behavior: ScrollBehavior = "smooth") => {
  shouldAutoScroll.value = true;
  nextTick(() => {
    scrollToBottom(behavior);
  });
};

// Scroll to show the user question (not all the way to bottom)
const scrollToUserQuestion = () => {
  // Don't auto-scroll to bottom during streaming - stay near the question
  shouldAutoScroll.value = false;
};

const waitForMediaRender = async () => {
  if (typeof window === "undefined") return;
  await nextTick();
  const container = scrollContent.value;
  if (!container) return;
  const images = Array.from(container.querySelectorAll("img"));
  if (images.length) {
    await Promise.all(
      images.map((img) => {
        if (img.complete) return Promise.resolve(true);
        return new Promise((resolve) => {
          const finish = () => resolve(true);
          img.addEventListener("load", finish, { once: true });
          img.addEventListener("error", finish, { once: true });
        });
      })
    );
  }
  if (typeof requestAnimationFrame !== "undefined") {
    await new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)));
  }
};

const ensureAssistantStreamingMessage = () => {
  if (streamingAssistantMessage.value) {
    return streamingAssistantMessage.value;
  }

  const placeholder: Message = {
    id: `assistant-temp-${Date.now()}`,
    content: "",
    message_type: "ASSISTANT",
    created_at: new Date().toISOString(),
    status: "STREAMING",
    extra_data: { media: [] },
  };
  messages.value.push(placeholder);
  streamingAssistantMessage.value = placeholder;
  return placeholder;
};

const finalizeAssistantStreamingMessage = (finalMessage: Message) => {
  if (!streamingAssistantMessage.value) {
    messages.value.push(finalMessage);
    return;
  }

  Object.assign(streamingAssistantMessage.value, finalMessage, {
    status: "FINAL",
  });
  streamingAssistantMessage.value = null;
};

const discardAssistantStreamingMessage = () => {
  const placeholder = streamingAssistantMessage.value;
  if (!placeholder) return;

  const index = messages.value.indexOf(placeholder);
  if (index !== -1) {
    messages.value.splice(index, 1);
  }
  streamingAssistantMessage.value = null;
};

const fetchAssistant = async (assistantId: string) => {
  try {
    assistant.value = await $api<Assistant>(`/v1/assistants/${assistantId}`);
  } catch (error) {
    return null;
  }
};

// Initialize assistant data
const initializeAssistant = async () => {
  const conversationData = newConversationStore.state.conversations[conversationId];
  if (conversationData?.assistant) {
    assistant.value = conversationData.assistant as Assistant;
  }
};

const { sendStreamingMessage, sendSyncMessage } = useStreamingChat();
const { showError, showSuccess } = useNotifications();
const { $api } = useNuxtApp();
const { t } = useI18n();

// Insufficient balance dialog
// const showInsufficientBalanceDialog = ref(false)
// const insufficientBalanceMessage = ref('')

// Assistant status check
const isAssistantActive = computed(() => {
  return assistant.value?.status === "ACTIVE";
});

const shouldShowAssistantStatusWarning = computed(() => {
  if (!assistant.value) return false;
  return assistant.value.status !== "ACTIVE";
});

// Check if assistant's model supports vision (image input)
const supportsVision = computed(() => {
  if (!assistant.value?.model?.capabilities) return false;
  // Check if model has 'vision' capability
  return assistant.value.model.capabilities.includes("vision");
});

const assistantStatusMessage = computed(() => {
  if (!assistant.value) return "";
  if (assistant.value.status === "INACTIVE") {
    return t("chat.assistantInactive");
  }
  if (assistant.value.status === "DRAFT") {
    return t("chat.assistantDraft");
  }
  return "";
});

const streamingContent = computed(() => streamingAssistantMessage.value?.content ?? "");

// No longer use computed, use explicit state control
// const shouldShowStreamingLoading = computed(() => {
//   return isLoading.value && isStreaming.value && streamingContent.value.length === 0
// })

// Use explicit state to avoid computed reactivity delay
const shouldShowStreamingLoading = ref(false);

// Fetch conversation info from API
const fetchConversationInfo = async () => {
  try {
    const response = await $api<Conversation>(`/v1/conversations/${conversationId}`);
    conversationInfo.value = response;
    // Update assistant when API data is loaded
    fetchAssistant(conversationInfo.value.assistant_id);
    return response;
  } catch (error) {
    showError(t("chat.fetchConversationFailed"));
    return null;
  }
};

// Fetch conversation messages from API
const fetchConversationMessages = async () => {
  isLoadingHistory.value = true;
  try {
    const response = await $api<PaginatedResponse<Message>>(
      `/v1/conversations/${conversationId}/messages`
    );

    // Extract messages from paginated response
    const apiMessages = response.items || [];

    messages.value = apiMessages;
    await waitForMediaRender();
    forceScrollToBottom("auto");
    return apiMessages;
  } catch (error) {
    showError(t("chat.fetchHistoryFailed"));
    return [];
  } finally {
    isLoadingHistory.value = false;
  }
};

const buildShareUrl = (id: string) => {
  if (typeof window === "undefined") {
    return `/share/${id}`;
  }
  return `${window.location.origin}/share/${id}`;
};

const requestShareLink = async (
  payload: {
    conversation_id: string;
    scope: ShareScope;
    start_message_id?: string;
    end_message_id?: string;
  },
  scope: ShareScope
) => {
  shareDialogLoading.value = true;
  try {
    const response = await $api<ConversationShareResponse>("/v1/share-links", {
      method: "POST",
      body: payload,
    });
    const shareUrl = buildShareUrl(response.id);
    shareDialogUrl.value = shareUrl;
    shareDialogScope.value = scope;
    shareDialogOpen.value = true;

    if (typeof navigator !== "undefined" && navigator.clipboard) {
      try {
        await navigator.clipboard.writeText(shareUrl);
        showSuccess(t("chat.share.linkCopiedClipboard"));
      } catch (clipboardError) {
        // Clipboard copy failed silently
      }
    }
  } catch (error) {
    showError(t("chat.share.createFailed"));
  } finally {
    shareDialogLoading.value = false;
  }
};

const shareConversation = async () => {
  if (shareDialogLoading.value) return;
  if (!currentConversationId.value) {
    showError(t("chat.share.conversationNotReady"));
    return;
  }
  await requestShareLink(
    {
      conversation_id: currentConversationId.value,
      scope: "CONVERSATION",
    },
    "CONVERSATION"
  );
};

const handleShareMessage = async (message: Message) => {
  if (shareDialogLoading.value) return;
  if (!currentConversationId.value) {
    showError(t("chat.share.conversationNotReady"));
    return;
  }

  if (message.message_type !== "ASSISTANT") {
    showError(t("chat.share.selectAssistantReply"));
    return;
  }

  const messageIndex = messages.value.findIndex((msg) => msg.id === message.id);
  if (messageIndex <= 0) {
    showError(t("chat.share.userQuestionMissing"));
    return;
  }

  let relatedUserMessage: Message | null = null;
  for (let i = messageIndex - 1; i >= 0; i -= 1) {
    const candidate = messages.value[i];
    if (candidate && candidate.message_type === "USER") {
      relatedUserMessage = candidate;
      break;
    }
  }

  if (!relatedUserMessage) {
    showError(t("chat.share.matchingUserQuestionMissing"));
    return;
  }

  await requestShareLink(
    {
      conversation_id: currentConversationId.value,
      scope: "MESSAGE",
      start_message_id: relatedUserMessage.id,
      end_message_id: message.id,
    },
    "MESSAGE"
  );
};

const copyShareLink = async () => {
  if (!shareDialogUrl.value) return;
  if (typeof navigator === "undefined" || !navigator.clipboard) {
    showError(t("chat.share.copyNotSupported"));
    return;
  }
  try {
    await navigator.clipboard.writeText(shareDialogUrl.value);
    showSuccess(t("chat.share.linkCopied"));
  } catch (error) {
    showError(t("chat.share.copyFailed"));
  }
};

// Check for pending message from new conversation state
onMounted(async () => {
  // First check if we have conversation data from the store
  const conversationData = newConversationStore.state.conversations[conversationId];
  // Initialize assistant data immediately
  initializeAssistant();
  observeScrollContent();

  if (conversationData?.userMessage && conversationData.isTransitioning) {
    // This is a new conversation from the store
    isNewConversation.value = true;

    // Convert store message format to local format
    const convertedUserMessage: Message = {
      ...conversationData.userMessage,
      message_type: conversationData.userMessage.message_type === "USER" ? "USER" : "ASSISTANT",
    };

    // Add the user message immediately to the UI
    messages.value.push(convertedUserMessage);

    // Send the message content without adding to UI again
    const initialImages = convertedUserMessage.extra_data?.images as ImageAttachment[] | undefined;
    sendMessageFromStore(conversationData.userMessage.content, initialImages);

    // Mark transition as complete
    newConversationStore.completeTransition(conversationId);

    // Clear the conversation data after successful processing
    newConversationStore.clearConversationData(conversationId);
  } else {
    // This might be an existing conversation, fetch things in parallel
    isNewConversation.value = false;
    const [conversation] = await Promise.all([
      fetchConversationInfo(),
      fetchConversationMessages(),
    ]);
  }

  if (conversationInfo.value) {
    useHead({
      title: conversationInfo.value.title,
    });
  }

  // Focus the input after mount
  nextTick(() => {
    chatInputRef.value?.focus();
  });
});

watch(scrollContent, (newEl, oldEl) => {
  if (contentResizeObserver && oldEl) {
    contentResizeObserver.unobserve(oldEl);
  }
  if (newEl) {
    observeScrollContent();
  }
});

const sendMessage = async (images?: any[]) => {
  if (!newMessage.value.trim() || isLoading.value || !assistant.value) return;

  // Check if assistant is active
  if (!isAssistantActive.value) {
    showError(assistantStatusMessage.value);
    return;
  }

  const messageContent = newMessage.value.trim();
  newMessage.value = "";
  isLoading.value = true;
  isStreaming.value = true;

  // Add user message to UI immediately
  const userMessage: Message = {
    id: Date.now().toString(),
    content: messageContent,
    message_type: "USER",
    created_at: new Date().toISOString(),
    extra_data: images && images.length > 0 ? { images } : undefined,
  };
  messages.value.push(userMessage);

  // Scroll to show the user's question, but don't auto-scroll to bottom during streaming
  // This mimics ChatGPT behavior - user stays near their question
  nextTick(() => {
    scrollToBottom("smooth");
    // After initial scroll, disable auto-scroll so response doesn't push user down
    setTimeout(() => {
      scrollToUserQuestion();
    }, 300);
  });

  await sendMessageInternal(messageContent, userMessage, images);
};

const handleFollowupSelect = async (prompt: string) => {
  const text = (prompt || "").trim();
  if (!text) return;
  // Respect global/assistant availability checks already in sendMessage.
  newMessage.value = text;
  await nextTick();
  await sendMessage();
};

// Send message without adding user message to UI (for store-based messages)
const sendMessageFromStore = async (messageContent: string, images?: ImageAttachment[]) => {
  if (!assistant.value) return;

  isLoading.value = true;
  isStreaming.value = true;

  // Scroll to show the user's question, then disable auto-scroll
  nextTick(() => {
    scrollToBottom("smooth");
    setTimeout(() => {
      scrollToUserQuestion();
    }, 300);
  });

  // Find the existing user message in the UI (should be the last one)
  const existingUserMessage = messages.value[messages.value.length - 1];
  if (existingUserMessage && existingUserMessage.message_type === "USER") {
    const existingImages =
      images ?? (existingUserMessage.extra_data?.images as ImageAttachment[] | undefined);
    await sendMessageInternal(messageContent, existingUserMessage, existingImages);
  } else {
    // Fallback: create a new user message if not found
    const userMessage: Message = {
      id: Date.now().toString(),
      content: messageContent,
      message_type: "USER",
      created_at: new Date().toISOString(),
      extra_data: images && images.length > 0 ? { images } : undefined,
    };
    await sendMessageInternal(messageContent, userMessage, images);
  }
};

// Internal function to handle the actual message sending
const sendMessageInternal = async (
  messageContent: string,
  userMessage: Message,
  images?: any[]
) => {
  // console.log('sendMessageInternal called with images:', images)
  try {
    shouldShowStreamingLoading.value = true;
    const streamingMsg = ensureAssistantStreamingMessage();
    // Initialize / reset execution log for streaming display
    ensureAgentExecution(streamingMsg).length = 0;
    let currentReasoningContent = "";

    // console.log('Calling sendStreamingMessage with images:', images)
    await sendStreamingMessage(
      messageContent,
      currentConversationId.value || undefined,
      // onChunk
      (content_chunk: ContentChunkPayload) => {
        const assistantMessage = ensureAssistantStreamingMessage();
        const chunkContent = content_chunk?.content ?? "";
        if (chunkContent) {
          assistantMessage.content += chunkContent;
          shouldShowStreamingLoading.value = false;
        }

        if (content_chunk?.media?.length) {
          const currentMedia = assistantMessage.extra_data?.media ?? [];
          assistantMessage.extra_data = {
            ...(assistantMessage.extra_data || {}),
            media: [...currentMedia, ...content_chunk.media],
          };
          shouldShowStreamingLoading.value = false;
        }
        if (shouldAutoScroll.value) {
          debouncedScrollToBottom();
        }
      },
      // onComplete
      async (finalMessage: Message) => {
        shouldShowStreamingLoading.value = false;
        isStreaming.value = false;

        // Replace the temporary user message ID with the real UUID if provided
        if (finalMessage.user_message_id && userMessage.id !== finalMessage.user_message_id) {
          const userMessageIndex = messages.value.findIndex((msg) => msg.id === userMessage.id);
          if (userMessageIndex !== -1) {
            const existingUserMessage = messages.value[userMessageIndex];
            if (existingUserMessage) {
              const updatedUserMessage = {
                ...existingUserMessage,
                id: finalMessage.user_message_id,
              };
              messages.value[userMessageIndex] = updatedUserMessage;
              userMessage.id = finalMessage.user_message_id;
            }
          }
        }

        finalizeAssistantStreamingMessage(finalMessage);

        const mediaRenderPromise = waitForMediaRender();

        // Generate title for new conversations after first assistant response
        if (isNewConversation.value && currentConversationId.value) {
          const assistantMessageCount = messages.value.filter(
            (msg) => msg.message_type === "ASSISTANT"
          ).length;
          if (assistantMessageCount === 1) {
            try {
              await conversationsStore.generateTitle(currentConversationId.value);
              // Reset the flag after generating title
              isNewConversation.value = false;
            } catch (error) {
              // Failed to generate title - not critical
            }
          }
        }

        isLoading.value = false;

        await mediaRenderPromise;

        nextTick(() => {
          if (shouldAutoScroll.value) {
            debouncedScrollToBottom();
          }
        });
      },
      // onError
      (error) => {
        shouldShowStreamingLoading.value = false;

        // Remove the user message if sending failed
        const failedUserMessageIndex = messages.value.findIndex((msg) => msg.id === userMessage.id);
        if (failedUserMessageIndex !== -1) {
          messages.value.splice(failedUserMessageIndex, 1);
        }
        discardAssistantStreamingMessage();
        isStreaming.value = false;
        isLoading.value = false;

        // Check if this is a balance insufficient error
        const isBalanceError =
          error.includes("Insufficient balance") ||
          error.includes("balance") ||
          error.toLowerCase().includes("insufficient");

        if (isBalanceError) {
          // Show balance insufficient dialog instead of toast
          // insufficientBalanceMessage.value = error
          // showInsufficientBalanceDialog.value = true
          showError(error);
        } else {
          // Show regular error
          showError(`${t("chat.sendFailed")}: ${error}`);
        }
      },
      // onAgentStep
      (step: AgentStep) => {
        const assistantMessage = ensureAssistantStreamingMessage();
        ensureAgentExecution(assistantMessage).push(step);
        if (shouldAutoScroll.value) {
          nextTick(() => {
            debouncedScrollToBottom();
          });
        }
      },
      // onReasoningTrace
      (trace: ReasoningTracePayload) => {
        const assistantMessage = ensureAssistantStreamingMessage();
        const execution = ensureAgentExecution(assistantMessage);

        if (trace.content) {
          currentReasoningContent += trace.content;
          // Update or create reasoning step
          const existingReasoningIndex = execution.findIndex(
            (step) =>
              step.type === "agent_thought" && step.description === "Model reasoning process"
          );
          const thoughtStep: AgentStep = {
            type: "agent_thought",
            thought: currentReasoningContent,
            description: "Model reasoning process",
            timestamp: Date.now(),
          };
          if (existingReasoningIndex >= 0) {
            execution[existingReasoningIndex] = thoughtStep;
          } else {
            execution.push(thoughtStep);
          }
        }
        if (trace.is_final) {
          // Finalize reasoning trace
          if (currentReasoningContent) {
            const trimmed = currentReasoningContent.trim();
            const existingReasoningIndex = execution.findIndex(
              (step) =>
                step.type === "agent_thought" && step.description === "Model reasoning process"
            );
            if (existingReasoningIndex >= 0) {
              execution[existingReasoningIndex] = {
                type: "agent_thought",
                thought: trimmed,
                description: "Model reasoning process",
                timestamp: Date.now(),
              };
            }
            currentReasoningContent = "";
          }
        }
        if (shouldAutoScroll.value) {
          nextTick(() => {
            debouncedScrollToBottom();
          });
        }
      },
      // images
      images
    );
  } catch (error) {
    // Remove the user message if sending failed
    shouldShowStreamingLoading.value = false;
    const failedUserMessageIndex = messages.value.findIndex((msg) => msg.id === userMessage.id);
    if (failedUserMessageIndex !== -1) {
      messages.value.splice(failedUserMessageIndex, 1);
    }
    discardAssistantStreamingMessage();
    isStreaming.value = false;
    isLoading.value = false;

    // Show error to user
    showError(
      `${t("chat.sendFailed")}: ${error instanceof Error ? error.message : t("chat.unknownError")}`
    );
  }
};

const scrollToBottom = (behavior: ScrollBehavior = "smooth") => {
  if (scrollContainer.value) {
    scrollContainer.value.scrollTo({
      top: scrollContainer.value.scrollHeight,
      behavior,
    });
    return;
  }

  if (messagesEnd.value) {
    messagesEnd.value.scrollIntoView({ behavior });
  }
};

// Clean up conversation data when component is unmounted
onUnmounted(() => {
  // This handles edge cases where the conversation data wasn't processed
  newConversationStore.clearConversationData(conversationId);

  // Clean up scroll timeout
  if (scrollTimeoutId) {
    clearTimeout(scrollTimeoutId);
  }

  // Clean up resize observer
  if (contentResizeObserver) {
    contentResizeObserver.disconnect();
    contentResizeObserver = null;
  }
});
</script>

<template>
  <div class="relative flex h-screen flex-col overflow-hidden">
    <!-- Header -->
    <AppHeader>
      <Breadcrumb>
        <BreadcrumbList>
          <BreadcrumbItem class="hidden md:block">
            <BreadcrumbLink as-child>
              <NuxtLink to="/assistants">
                {{ t("chat.breadcrumbAssistants") }}
              </NuxtLink>
            </BreadcrumbLink>
          </BreadcrumbItem>
          <BreadcrumbSeparator class="hidden md:block" />
          <BreadcrumbItem>
            <BreadcrumbPage class="flex items-center">
              <AssistantAvatar
                :assistant="assistant"
                class="mr-1 inline-block size-4 align-middle"
              />
              {{ assistant?.name || t("common.loading") }}
            </BreadcrumbPage>
          </BreadcrumbItem>
        </BreadcrumbList>
      </Breadcrumb>

      <template #right>
        <div v-if="assistant" class="flex items-center gap-2">
          <Button
            v-if="userStore.user && showPinButton"
            variant="outline"
            size="icon"
            :title="assistant.is_pinned ? t('assistants.unpin') : t('assistants.pin')"
            @click="handlePin"
          >
            <PinOff v-if="assistant.is_pinned" class="text-primary fill-primary h-4 w-4" />
            <Pin v-else class="h-4 w-4" />
          </Button>

          <TooltipProvider v-if="showShareButton">
            <Tooltip>
              <TooltipTrigger as-child>
                <Button
                  variant="outline"
                  :size="isDesktop ? 'sm' : 'icon'"
                  class="border-amber-200 text-amber-600 transition-colors hover:bg-amber-50 dark:border-amber-800 dark:text-amber-400 dark:hover:bg-amber-950"
                  :disabled="shareDialogLoading || !currentConversationId"
                  @click="shareConversation"
                >
                  <Share2 class="h-4 w-4" :class="{ 'mr-2': isDesktop }" />
                  <span v-if="isDesktop">{{ t("chat.share.button") }}</span>
                </Button>
              </TooltipTrigger>
            </Tooltip>
          </TooltipProvider>

          <DropdownMenu v-if="showCreateButton">
            <DropdownMenuTrigger as-child>
              <Button variant="outline" size="icon" :title="t('chat.newConversation')">
                <Plus />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent>
              <DropdownMenuItem as-child>
                <NuxtLink :to="`/chatwith/${assistant.id}`">
                  {{ t("chat.actions.withCurrentAssistant") }}
                </NuxtLink>
              </DropdownMenuItem>
              <DropdownMenuItem>
                <NuxtLink to="/assistants">
                  {{ t("chat.actions.chooseAnotherAssistant") }}
                </NuxtLink>
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </template>
    </AppHeader>

    <!-- Chat content area with scroll event -->
    <div
      ref="scrollContainer"
      class="min-h-0 flex-1 overflow-y-auto scroll-smooth pb-[200px]"
      @scroll="handleScroll"
    >
      <div ref="scrollContent" class="p-4 md:p-6">
        <div class="mx-auto max-w-3xl space-y-6">
          <!-- Welcome message -->
          <ChatWelcome
            :assistant="assistant"
            :show-welcome="messages.length === 0 && !isLoadingHistory"
          />

          <!-- Loading history indicator -->
          <ChatLoading
            v-if="isLoadingHistory"
            :assistant="assistant"
            :message="t('chat.loadingHistory')"
          />

          <!-- Messages -->
          <ChatMessage
            v-for="message in messages"
            :key="message.id"
            :message="message"
            :assistant="assistant"
            :enable-share="showMessageShareButton"
            :enable-followups="true"
            @share="handleShareMessage"
            @quote="
              (text) => {
                newMessage = `> ${text}\n\n${newMessage}`;
                nextTick(() => chatInputRef.value?.focus());
              }
            "
            @followup="handleFollowupSelect"
          />

          <!-- Loading indicator / Streaming message -->
          <ChatLoading
            v-if="shouldShowStreamingLoading"
            :assistant="assistant"
            :is-streaming="isStreaming"
          />

          <div ref="messagesEnd" />
        </div>
      </div>
    </div>

    <Dialog v-model:open="shareDialogOpen">
      <DialogContent class="sm:max-w-[480px]">
        <DialogHeader>
          <DialogTitle>
            {{
              t(
                shareDialogScope === "CONVERSATION"
                  ? "chat.share.titleConversation"
                  : "chat.share.titleMessage"
              )
            }}
          </DialogTitle>
          <DialogDescription>
            {{ t("chat.share.description") }}
          </DialogDescription>
        </DialogHeader>
        <div class="space-y-3">
          <div class="flex items-center gap-2">
            <Input v-model="shareDialogUrl" readonly class="flex-1" />
            <Button variant="secondary" @click="copyShareLink">
              {{ t("chat.share.copy") }}
            </Button>
          </div>
          <p class="text-muted-foreground text-xs break-all">
            {{ shareDialogUrl }}
          </p>
        </div>
      </DialogContent>
    </Dialog>

    <!-- Scroll to bottom button -->
    <Transition
      enter-active-class="transition-all duration-300 ease-out"
      enter-from-class="opacity-0 translate-y-4 scale-95"
      enter-to-class="opacity-100 translate-y-0 scale-100"
      leave-active-class="transition-all duration-200 ease-in"
      leave-from-class="opacity-100 translate-y-0 scale-100"
      leave-to-class="opacity-0 translate-y-4 scale-95"
    >
      <button
        v-if="!shouldAutoScroll && hasScrollableContent && messages.length > 0"
        class="bg-foreground/90 text-background hover:bg-foreground border-border/20 absolute bottom-28 left-1/2 z-40 flex h-8 w-8 -translate-x-1/2 items-center justify-center rounded-full border shadow-lg backdrop-blur-sm transition-all duration-200"
        :title="t('chat.scrollToBottom')"
        @click="forceScrollToBottom('smooth')"
      >
        <svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path
            stroke-linecap="round"
            stroke-linejoin="round"
            stroke-width="2"
            d="M19 14l-7 7m0 0l-7-7m7 7V3"
          />
        </svg>
      </button>
    </Transition>

    <!-- Input area -->
    <div
      class="bg-background/95 pointer-events-none absolute right-0 bottom-0 left-0 z-50 border-t border-transparent backdrop-blur-sm"
    >
      <div class="pointer-events-auto p-4 md:p-5">
        <div class="mx-auto max-w-3xl">
          <!-- Assistant status warning -->
          <div
            v-if="shouldShowAssistantStatusWarning"
            class="mb-3 rounded-xl border border-yellow-200 bg-yellow-50 p-3 text-sm text-yellow-800 shadow-sm dark:border-yellow-800 dark:bg-yellow-900/20 dark:text-yellow-200"
          >
            <div class="flex items-center gap-2">
              <span class="text-lg">⚠️</span>
              <span>{{ assistantStatusMessage }}</span>
            </div>
          </div>

          <ChatInput
            ref="chatInputRef"
            v-model="newMessage"
            :disabled="!isAssistantActive"
            :send-disabled="isLoading || !newMessage.trim() || !isAssistantActive"
            :supports-vision="supportsVision"
            @send="sendMessage"
          />
        </div>
      </div>
    </div>
  </div>
</template>
