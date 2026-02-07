<script setup lang="ts">
import { nextTick, onMounted, onUnmounted, watch } from "vue";
import { useMarkdown } from "~/composables/useMarkdown";
import { useConfigStore } from "~/stores/config";
import {
  Copy,
  Share,
  Check,
  Quote,
  ThumbsUp,
  ThumbsDown,
  Loader2,
  Info,
  Pencil,
  X,
} from "lucide-vue-next";
import type { Assistant, Message } from "~/types/api";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogDescription,
  DialogFooter,
  DialogTitle,
} from "~/components/ui/dialog";
import { useNuxtApp } from "#app";

interface Props {
  message: Message;
  assistant?: Assistant | null;
  enableShare?: boolean;
  enableFollowups?: boolean;
  forceCompleted?: boolean;
}

const props = withDefaults(defineProps<Props>(), {
  enableShare: true,
  enableFollowups: true,
  forceCompleted: false,
});

const emit = defineEmits<{
  (e: "share", message: Message): void;
  (e: "quote", content: string): void;
  (e: "followup", content: string): void;
  (e: "edit", messageId: string, newContent: string): void;
  (e: "regenerate", messageId: string): void;
}>();

// Use markdown composable
const { t } = useI18n();
const { renderMarkdown } = useMarkdown();
const { showError, showSuccess } = useNotifications();

// State management
const copySuccess = ref(false);
type FeedbackRating = "UP" | "DOWN";
const feedbackDialogOpen = ref(false);
const feedbackRating = ref<FeedbackRating>("UP");
const feedbackReasons = ref<string[]>([]);
const feedbackComment = ref("");
const feedbackSubmitting = ref(false);
const feedbackSubmittedRating = ref<FeedbackRating | null>(null);

// Message editing state
const isEditing = ref(false);
const editContent = ref("");
const editSaving = ref(false);

const startEdit = () => {
  editContent.value = props.message.content;
  isEditing.value = true;
};

const cancelEdit = () => {
  isEditing.value = false;
  editContent.value = "";
};

const saveEdit = () => {
  if (editSaving.value) return;
  const trimmed = editContent.value.trim();
  if (!trimmed || trimmed === props.message.content) {
    cancelEdit();
    return;
  }
  emit("edit", props.message.id, trimmed);
  isEditing.value = false;
  editContent.value = "";
};

// Check if message was edited
const wasEdited = computed(() => !!props.message.edited_at);

const statsDialogOpen = ref(false);

const messageStats = computed(() => {
  const tokenUsage = props.message.extra_data?.token_usage;
  const executionTime = props.message.extra_data?.execution_time_ms;

  if (!tokenUsage && !executionTime) return null;

  return {
    inputTokens: tokenUsage?.input_tokens ?? 0,
    outputTokens: tokenUsage?.output_tokens ?? 0,
    totalTokens: tokenUsage?.total_tokens ?? 0,
    timeMs: executionTime ?? 0,
  };
});

const configStore = useConfigStore();
// Security: Hide toggles until config is loaded to respect admin settings
const showAgentThinking = computed(
  () => configStore.isLoaded && configStore.config.ui_show_agent_thinking !== false
);
const showMessageFeedbackButtons = computed(
  () => configStore.isLoaded && configStore.config.ui_show_message_feedback_buttons !== false
);
const showMessageStats = computed(
  () => configStore.isLoaded && configStore.config.ui_show_message_stats !== false
);
const showFollowupsGlobally = computed(
  () => configStore.isLoaded && configStore.config.ui_generate_followup_questions !== false
);
const followupMaxCount = computed(() => {
  const raw = configStore.config.ui_followup_question_count;
  const num = typeof raw === "number" ? raw : Number(raw ?? 3);
  if (!Number.isFinite(num)) return 3;
  return Math.max(1, Math.min(5, Math.trunc(num)));
});
const modelName = computed(() => {
  return props.assistant?.model?.name || props.assistant?.model?.display_name || undefined;
});

const FEEDBACK_REASONS_UP = ["Helpful", "Accurate", "Clear", "Good formatting", "Good citations"];
const FEEDBACK_REASONS_DOWN = [
  "Incorrect",
  "Incomplete",
  "Off-topic",
  "Hard to understand",
  "Citations missing/wrong",
  "Other",
];

// Max characters allowed for feedback comment
const FEEDBACK_COMMENT_MAX_CHARS = 500;

const availableFeedbackReasons = computed(() =>
  feedbackRating.value === "UP" ? FEEDBACK_REASONS_UP : FEEDBACK_REASONS_DOWN
);

const openFeedbackDialog = (rating: FeedbackRating) => {
  feedbackRating.value = rating;
  feedbackReasons.value = [];
  feedbackComment.value = "";
  feedbackDialogOpen.value = true;
};

const toggleFeedbackReason = (reason: string) => {
  const idx = feedbackReasons.value.indexOf(reason);
  if (idx >= 0) {
    feedbackReasons.value.splice(idx, 1);
  } else {
    feedbackReasons.value.push(reason);
  }
};

watch(feedbackDialogOpen, (open) => {
  if (!open) {
    feedbackReasons.value = [];
    feedbackComment.value = "";
  }
});

const agentSteps = computed(() => {
  if (props.message.message_type !== "ASSISTANT") return [];

  // Get agent execution log (includes both agent mode steps and Gemini reasoning traces)
  const execution = props.message.extra_data?.agent_execution;
  if (Array.isArray(execution) && execution.length > 0) {
    return execution;
  }

  return [];
});

const isUuid = (value: string) => {
  return /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(value);
};

const isStreamingMessage = computed(() => {
  if (props.forceCompleted) {
    return false;
  }
  if (props.message.status === "STREAMING") {
    return true;
  }
  return !isUuid(props.message.id);
});

const followupQuestions = computed<string[]>(() => {
  if (props.message.message_type !== "ASSISTANT") return [];
  const raw = props.message.extra_data?.followup_questions;
  if (!Array.isArray(raw)) return [];
  return raw.map((q) => (q == null ? "" : String(q)).trim()).filter(Boolean);
});

const displayedFollowupQuestions = computed(() =>
  followupQuestions.value.slice(0, followupMaxCount.value)
);

const showFollowupQuestions = computed(() => {
  if (!props.enableFollowups) return false;
  if (!showFollowupsGlobally.value) return false;
  if (isStreamingMessage.value) return false;
  return displayedFollowupQuestions.value.length > 0;
});

const handleFollowupClick = (question: string) => {
  const trimmed = (question || "").trim();
  if (!trimmed) return;
  emit("followup", trimmed);
};

// Compute rendered content
const renderedContent = computed(() => {
  const defaultPanel = isStreamingMessage.value ? "code" : "preview";
  const base = renderMarkdown(props.message.content, {
    defaultSvgPanel: defaultPanel,
  });
  return injectCitations(base, displayCitations.value);
});

// Copy message content
const copyMessage = async () => {
  try {
    await navigator.clipboard.writeText(props.message.content);
    copySuccess.value = true;
    setTimeout(() => {
      copySuccess.value = false;
    }, 2000); // Restore original icon after 2 seconds
  } catch (err) {
    // Copy failed silently
  }
};

const handleShare = () => {
  emit("share", props.message);
};

const decodeAttr = (value: string | null): string => {
  if (!value) return "";
  try {
    return decodeURIComponent(value);
  } catch (error) {
    return value;
  }
};

const normalizeCitations = (raw: any, startIndex: number = 1) => {
  if (!Array.isArray(raw)) return [];
  return raw.map((item, idx) => {
    const candidate = Number(item?.index ?? startIndex + idx);
    const index = Number.isFinite(candidate) && candidate > 0 ? candidate : startIndex + idx;
    return {
      ...(item || {}),
      index,
    };
  });
};

const getReferencedIndexes = (content: string): Set<number> => {
  const set = new Set<number>();
  if (!content) return set;
  // Match both [n] and 【n】formats, with optional suffixes like †L1-L4
  const regex = /(?:\[(\d+)\]|【(\d+)(?:[†\w\-\d]*)?】)/g;
  let match: RegExpExecArray | null;
  while ((match = regex.exec(content)) !== null) {
    const idx = Number(match[1] || match[2]);
    if (Number.isFinite(idx) && idx > 0) {
      set.add(idx);
    }
  }
  return set;
};

const buildCitationMap = (items: any[]) => {
  const map = new Map<number, any>();
  items.forEach((item) => {
    const key = Number(item?.index);
    if (Number.isFinite(key) && key > 0 && !map.has(key)) {
      map.set(key, item);
    }
  });
  return map;
};

function injectCitations(html: string, citationsList: any[]): string {
  if (!citationsList?.length) return html;
  if (typeof window === "undefined" || typeof DOMParser === "undefined") return html;

  const map = buildCitationMap(citationsList);
  if (!map.size) return html;

  const parser = new DOMParser();
  const doc = parser.parseFromString(`<div>${html}</div>`, "text/html");
  const container = doc.body.firstElementChild;
  if (!container) return html;

  // Match both [n] and 【n】formats (with optional suffixes like †L1-L4)
  const citationRegex = /(?:\[(\d+)\]|【(\d+)(?:[†\w\-\d]*)?】)/g;
  const skipTags = new Set(["CODE", "PRE", "KBD", "SAMP", "A"]);

  const walk = (node: Node) => {
    if (node.nodeType === Node.ELEMENT_NODE) {
      const el = node as HTMLElement;
      if (skipTags.has(el.tagName)) return;
      el.childNodes.forEach((child) => walk(child));
      return;
    }

    if (node.nodeType !== Node.TEXT_NODE) return;
    const text = node.textContent;
    if (!text) return;

    citationRegex.lastIndex = 0;
    let match: RegExpExecArray | null;
    let lastIndex = 0;
    const fragment = doc.createDocumentFragment();
    let hasMatch = false;

    while ((match = citationRegex.exec(text)) !== null) {
      const full = match[0];
      const numStr = match[1] || match[2]; // First group is [n], second is 【n】
      const idx = Number(numStr);
      const citation = map.get(idx);
      if (!citation) {
        continue;
      }
      hasMatch = true;
      const before = text.slice(lastIndex, match.index);
      if (before) {
        fragment.appendChild(doc.createTextNode(before));
      }
      const sup = doc.createElement("sup");
      sup.className = "citation-marker";
      sup.dataset.citationIndex = String(idx);
      sup.title = citation.title || citation.display_name || "View source";
      sup.textContent = `[${numStr}]`; // Normalize to [n] format
      fragment.appendChild(sup);
      lastIndex = match.index + full.length;
    }

    if (!hasMatch) return;
    const after = text.slice(lastIndex);
    if (after) {
      fragment.appendChild(doc.createTextNode(after));
    }
    node.parentNode?.replaceChild(fragment, node);
  };

  walk(container);
  return container.innerHTML;
}

const messageRoot = ref<HTMLElement | null>(null);

interface RenderableImage {
  id?: string;
  url: string;
  alt?: string;
}

const imagePreviewOpen = ref(false);
const previewImage = ref<RenderableImage | null>(null);

const openImagePreview = (image: RenderableImage) => {
  previewImage.value = image;
  imagePreviewOpen.value = true;
};

watch(imagePreviewOpen, (open) => {
  if (!open) {
    previewImage.value = null;
  }
});

const userImages = computed<RenderableImage[]>(() => {
  if (props.message.message_type !== "USER") {
    return [];
  }
  const images = props.message.extra_data?.images;
  if (!Array.isArray(images)) {
    return [];
  }
  return images
    .map((img: any, index: number) => {
      const url = img?.url || img?.data_url || img?.dataUrl;
      if (!url) return null;
      return {
        id: img?.id || `user-image-${props.message.id}-${index}`,
        url,
        alt: img?.alt || t("chat.userImageAlt", { index: index + 1 }),
      };
    })
    .filter((item): item is RenderableImage => item !== null && typeof item === "object");
});

const assistantImages = computed<RenderableImage[]>(() => {
  if (props.message.message_type !== "ASSISTANT") {
    return [];
  }
  const mediaItems = props.message.extra_data?.media;
  if (!Array.isArray(mediaItems)) {
    return [];
  }
  return mediaItems
    .filter((item) => item?.type === "image" && (item.url || item.data_url))
    .map((item) => ({
      id: item.id,
      url: item.url || item.data_url,
      alt: item.alt || t("chat.generatedImageAlt"),
    }));
});

const hasRenderableImages = computed(() => {
  return userImages.value.length > 0 || assistantImages.value.length > 0;
});

// Citations (Excel-focused)
const citations = computed<any[]>(() => normalizeCitations(props.message.extra_data?.citations));
const referencedIndexes = computed(() => getReferencedIndexes(props.message.content));
const displayCitations = computed(() => {
  if (referencedIndexes.value.size === 0) return citations.value;
  const filtered = citations.value.filter((c) => referencedIndexes.value.has(Number(c.index)));
  return filtered.length ? filtered : citations.value;
});

const citationMap = computed(() => buildCitationMap(displayCitations.value));

const previewOpen = ref(false);
const previewData = ref<any>(null);
const previewLoading = ref(false);
const { $api } = useNuxtApp();

// Handle PDF image load error - fall back to text preview
const handlePdfImageError = () => {
  if (previewData.value?.type === "pdf-page" && previewData.value.snippet) {
    // Convert to text preview when image fails
    previewData.value = {
      type: "text",
      title: previewData.value.title,
      content: previewData.value.snippet,
      metadata: previewData.value.metadata,
    };
  }
};

const submitFeedback = async () => {
  if (feedbackSubmitting.value) return;
  if (!isUuid(props.message.id)) return;

  const comment = feedbackComment.value.trim();
  const reasons = Array.from(new Set(feedbackReasons.value)).slice(0, 20);

  if (!comment && reasons.length === 0) {
    showError(t("chat.feedback.validationRequired"));
    return;
  }

  try {
    feedbackSubmitting.value = true;
    await $api(`/v1/messages/${props.message.id}/feedback`, {
      method: "POST",
      body: {
        rating: feedbackRating.value,
        reasons,
        comment: comment || null,
        extra_data: {
          source: "chat-ui",
        },
      },
    });
    feedbackSubmittedRating.value = feedbackRating.value;
    feedbackDialogOpen.value = false;
    showSuccess(t("chat.feedback.submitted"));
  } catch (error: any) {
    showError(t("chat.feedback.submitFailed"));
  } finally {
    feedbackSubmitting.value = false;
  }
};

const previewCitation = async (citation: any) => {
  if (!citation) return;
  const fileType = citation.file_type || citation.metadata?.file_type;
  const filePath = citation.file_path || citation.metadata?.file_path;

  // Handle PDF files - show actual page image (NotebookLM-style)
  if (fileType && String(fileType).toLowerCase() === "pdf") {
    const documentId = citation.document_id || citation.metadata?.document_id;
    const pageNumber = citation.metadata?.page_number || citation.metadata?.page_start || 1;

    // Show the actual PDF page as an image - reliable and trustworthy
    if (documentId || filePath) {
      const params = new URLSearchParams();
      if (documentId) params.append("document_id", documentId);
      if (filePath) params.append("file_path", filePath);
      params.append("page_number", String(pageNumber));
      params.append("dpi", "150");

      // Get the PDF download URL for the download button
      let pdfDownloadUrl: string | undefined;
      if (filePath) {
        try {
          const fileUrl = await $api<{ url: string }>(
            `/v1/files/url/${encodeURIComponent(filePath)}`
          );
          pdfDownloadUrl = fileUrl?.url;
        } catch {
          // Ignore - download button will be hidden
        }
      }

      previewData.value = {
        type: "pdf-page",
        title: citation.display_name || citation.title || "PDF Source",
        imageUrl: `/api/v1/rag/documents/preview-pdf-page?${params.toString()}`,
        pdfDownloadUrl: pdfDownloadUrl,
        snippet: citation.snippet,
        metadata: {
          file_type: fileType,
          document_id: documentId,
          file_path: filePath,
          page_number: pageNumber,
          chunk_index: citation.metadata?.chunk_index,
          score: citation.score,
        },
      };
      previewOpen.value = true;
      return;
    }

    // Fallback: show text snippet if no page image available
    if (citation.snippet) {
      previewData.value = {
        type: "text",
        title: citation.display_name || citation.title || "PDF Content",
        content: citation.snippet,
        metadata: {
          file_type: fileType,
          document_id: documentId,
          chunk_index: citation.metadata?.chunk_index,
          score: citation.score,
        },
      };
      previewOpen.value = true;
    }
    return;
  }

  // Handle other document types (DOCX, PPTX, TXT, MD, HTML) - use chunk preview or snippet
  const textBasedTypes = ["docx", "doc", "pptx", "ppt", "txt", "md", "html", "json", "xml"];
  if (fileType && textBasedTypes.includes(String(fileType).toLowerCase())) {
    // Try to fetch full chunk content if chunk_id is available
    const chunkId = citation.chunk_id || citation.metadata?.chunk_id;
    if (chunkId) {
      try {
        previewLoading.value = true;
        const data = await $api(`/v1/rag/chunks/${chunkId}/preview`);
        previewData.value = {
          type: "chunk",
          title: data.document_title || citation.display_name || citation.title || "Source Content",
          content: data.content,
          metadata: {
            file_type: data.file_type || fileType,
            document_id: data.document_id,
            chunk_id: data.chunk_id,
            chunk_index: data.chunk_index,
            page_number: data.page_number,
            sheet: data.sheet,
            row_number: data.row_number,
            score: citation.score,
          },
        };
        previewOpen.value = true;
        return;
      } catch {
        // Fall through to snippet fallback
      } finally {
        previewLoading.value = false;
      }
    }

    // Fallback: show snippet if available
    if (citation.snippet) {
      previewData.value = {
        type: "text",
        title: citation.display_name || citation.title || "Source Content",
        content: citation.snippet,
        metadata: {
          file_type: fileType,
          document_id: citation.document_id || citation.metadata?.document_id,
          chunk_index: citation.metadata?.chunk_index,
          score: citation.score,
        },
      };
      previewOpen.value = true;
      return;
    }
    // Fallback: try to open external URL if no snippet
    const externalUrl =
      citation.preview_url || citation.url || citation.source_url || citation.metadata?.source_url;
    if (externalUrl) {
      window.open(externalUrl, "_blank");
    }
    return;
  }

  // Non-Excel fallback: use chunk preview, snippet, or open URL
  if (!fileType || !["xls", "xlsx", "csv", "excel"].includes(String(fileType).toLowerCase())) {
    // Try to fetch full chunk content if chunk_id is available
    const chunkId = citation.chunk_id || citation.metadata?.chunk_id;
    if (chunkId) {
      try {
        previewLoading.value = true;
        const data = await $api(`/v1/rag/chunks/${chunkId}/preview`);
        previewData.value = {
          type: "chunk",
          title: data.document_title || citation.display_name || citation.title || "Source Content",
          content: data.content,
          metadata: {
            file_type: data.file_type || fileType,
            document_id: data.document_id,
            chunk_id: data.chunk_id,
            chunk_index: data.chunk_index,
            page_number: data.page_number,
            sheet: data.sheet,
            row_number: data.row_number,
            score: citation.score,
          },
        };
        previewOpen.value = true;
        return;
      } catch {
        // Fall through to snippet fallback
      } finally {
        previewLoading.value = false;
      }
    }

    // Prefer showing snippet in modal (consistent UX like NotebookLM)
    if (citation.snippet) {
      previewData.value = {
        type: "text",
        title: citation.display_name || citation.title || "Source Content",
        content: citation.snippet,
        metadata: {
          file_type: fileType,
          document_id: citation.document_id || citation.metadata?.document_id,
          chunk_index: citation.metadata?.chunk_index,
          score: citation.score,
        },
      };
      previewOpen.value = true;
      return;
    }
    // Fallback: open URL if no snippet available
    const externalUrl =
      citation.preview_url || citation.url || citation.source_url || citation.metadata?.source_url;
    if (externalUrl) {
      window.open(externalUrl, "_blank");
    }
    return;
  }
  // Excel/CSV file handling - filePath already declared above
  const documentId = citation.document_id || citation.metadata?.document_id;
  const rowNumber = citation.row_number || citation.metadata?.row_number || 2;
  if (!filePath) return;
  const params = new URLSearchParams({
    file_path: filePath,
    row_number: String(rowNumber),
  });
  if (documentId) {
    params.append("document_id", documentId);
  }
  const sheet = citation.sheet || citation.metadata?.sheet;
  if (sheet) params.append("sheet", sheet);
  try {
    previewLoading.value = true;
    const data = await $api(`/v1/rag/documents/preview-row?${params.toString()}`);
    previewData.value = data;
    previewOpen.value = true;
  } catch (error) {
    // Failed to fetch row preview
  } finally {
    previewLoading.value = false;
  }
};

const setActivePreviewPanel = (panelsElement: HTMLElement, targetPanel: string) => {
  const current = panelsElement.dataset.activePanel;
  if (current === targetPanel) return;
  panelsElement.dataset.activePanel = targetPanel;
  const panels = panelsElement.querySelectorAll<HTMLElement>("[data-panel]");
  panels.forEach((panel) => {
    const panelName = panel.getAttribute("data-panel");
    if (panelName === targetPanel) {
      panel.style.display = "";
    } else {
      panel.style.display = "none";
    }
  });

  const relatedButtons = messageRoot.value?.querySelectorAll<HTMLElement>(
    `[data-preview-panels="${panelsElement.id}"]`
  );
  relatedButtons?.forEach((button) => {
    const buttonTarget = button.getAttribute("data-preview-toggle");
    button.setAttribute("data-state", buttonTarget === targetPanel ? "active" : "inactive");
  });
};

const updatePreviewPanels = (mode: "streaming" | "final") => {
  if (!messageRoot.value) return;
  const containers = messageRoot.value.querySelectorAll<HTMLElement>("[data-preview-default]");
  containers.forEach((container) => {
    const target =
      mode === "streaming"
        ? container.getAttribute("data-preview-streaming") || "code"
        : container.getAttribute("data-preview-final") || "preview";
    container.setAttribute("data-preview-default", target);
    setActivePreviewPanel(container, target);
  });
};

const handleMarkdownClick = (event: MouseEvent) => {
  const target = event.target as HTMLElement | null;
  if (!target) return;

  const citationTarget = target.closest(".citation-marker") as HTMLElement | null;
  if (citationTarget) {
    const indexAttr = citationTarget.dataset.citationIndex || citationTarget.textContent || "";
    const index = Number((indexAttr || "").replace(/[^0-9]/g, ""));
    const citation = citationMap.value.get(index);
    if (citation) {
      previewCitation(citation);
    }
    return;
  }

  const toggleButton = target.closest("[data-preview-toggle]") as HTMLElement | null;
  if (toggleButton) {
    const panelName = toggleButton.getAttribute("data-preview-toggle");
    const panelsId = toggleButton.getAttribute("data-preview-panels");
    if (panelName && panelsId) {
      const panelsElement = document.getElementById(panelsId);
      if (panelsElement) {
        setActivePreviewPanel(panelsElement, panelName);
      }
    }
    return;
  }

  const downloadTrigger = target.closest("[data-preview-download]") as HTMLElement | null;
  if (downloadTrigger) {
    const encodedContent = downloadTrigger.getAttribute("data-svg-content");
    if (!encodedContent) return;
    const fileName =
      decodeAttr(downloadTrigger.getAttribute("data-download-name")) || "preview.svg";
    const content = decodeAttr(encodedContent);
    try {
      const blob = new Blob([content], { type: "image/svg+xml;charset=utf-8" });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = fileName;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(url);
    } catch (error) {
      // Failed to download SVG
    }
    return;
  }

  // Handle copy-code action (CSP-safe alternative to inline onclick)
  const copyButton = target.closest("[data-action='copy-code']") as HTMLElement | null;
  if (copyButton) {
    const container = copyButton.closest(".code-block-container");
    if (!container) return;
    const codeEl = container.querySelector("code");
    if (!codeEl) return;
    const defaultLabel = decodeAttr(copyButton.getAttribute("data-copy-label"));
    const successLabel = decodeAttr(copyButton.getAttribute("data-copied-label"));
    const textSpan = copyButton.querySelector(".copy-text");
    try {
      navigator.clipboard.writeText(codeEl.textContent || "");
      if (textSpan) {
        textSpan.textContent = successLabel;
      }
      copyButton.classList.add("copied");
      setTimeout(() => {
        if (textSpan) {
          textSpan.textContent = defaultLabel;
        }
        copyButton.classList.remove("copied");
      }, 2000);
    } catch (error) {
      // Clipboard copy failed
    }
    return;
  }
};

const selectionMenuVisible = ref(false);
const selectionMenuPosition = ref({ top: 0, left: 0 });
const selectedText = ref("");

const handleSelection = () => {
  const selection = window.getSelection();
  if (!selection || selection.isCollapsed) {
    selectionMenuVisible.value = false;
    return;
  }

  const text = selection.toString().trim();
  if (!text) {
    selectionMenuVisible.value = false;
    return;
  }

  // Check if selection is within this message
  if (messageRoot.value && messageRoot.value.contains(selection.anchorNode)) {
    const range = selection.getRangeAt(0);
    const rect = range.getBoundingClientRect();

    selectedText.value = text;
    selectionMenuPosition.value = {
      top: rect.top - 40, // Position above selection
      left: rect.left + rect.width / 2, // Center horizontally
    };
    selectionMenuVisible.value = true;
  } else {
    selectionMenuVisible.value = false;
  }
};

const handleQuote = () => {
  if (selectedText.value) {
    emit("quote", selectedText.value);
    selectionMenuVisible.value = false;
    window.getSelection()?.removeAllRanges();
  }
};

// Close menu when clicking outside
const handleClickOutside = (event: MouseEvent) => {
  const target = event.target as HTMLElement;
  if (selectionMenuVisible.value && !target.closest(".selection-menu")) {
    selectionMenuVisible.value = false;
  }
};

onMounted(() => {
  document.addEventListener("selectionchange", handleSelection);
  document.addEventListener("mousedown", handleClickOutside);
});

onUnmounted(() => {
  document.removeEventListener("selectionchange", handleSelection);
  document.removeEventListener("mousedown", handleClickOutside);
});

watch(
  () => isStreamingMessage.value,
  (streaming) => {
    nextTick(() => updatePreviewPanels(streaming ? "streaming" : "final"));
  },
  { immediate: true }
);
</script>

<template>
  <div
    ref="messageRoot"
    class="animate-in fade-in slide-in-from-bottom-2 flex duration-300"
    :class="{
      'justify-end': message.message_type === 'USER',
    }"
  >
    <div
      :class="{
        'max-w-[85%] md:max-w-2xl': message.message_type === 'USER',
        'w-full': message.message_type === 'ASSISTANT',
      }"
    >
      <div
        :class="{
          'rounded-3xl bg-zinc-100 px-4 py-3 text-zinc-900 shadow-sm dark:bg-zinc-800 dark:text-zinc-100':
            message.message_type === 'USER',
          'text-foreground': message.message_type === 'ASSISTANT',
        }"
      >
        <!-- Agent Thinking Process (if enabled and present) -->
        <ChatAgentThinking
          v-if="showAgentThinking && message.message_type === 'ASSISTANT'"
          :steps="agentSteps"
          :is-thinking="isStreamingMessage"
          :assistant-name="assistant?.name"
          :model-name="modelName"
          class="mb-1"
        />

        <!-- Edit mode for user messages -->
        <div v-if="isEditing && message.message_type === 'USER'" class="space-y-3">
          <Textarea
            v-model="editContent"
            class="min-h-[100px] w-full resize-none border-0 bg-transparent p-0 text-base focus:ring-0"
            :placeholder="t('chat.editPlaceholder')"
            @keydown.escape="cancelEdit"
            @keydown.meta.enter="saveEdit"
            @keydown.ctrl.enter="saveEdit"
          />
          <div class="flex items-center justify-end gap-2">
            <Button variant="ghost" size="sm" @click="cancelEdit" :disabled="editSaving">
              <X class="mr-1 h-3.5 w-3.5" />
              {{ t("common.cancel") }}
            </Button>
            <Button size="sm" @click="saveEdit" :disabled="editSaving || !editContent.trim()">
              <Loader2 v-if="editSaving" class="mr-1 h-3.5 w-3.5 animate-spin" />
              {{ t("chat.saveAndRegenerate") }}
            </Button>
          </div>
        </div>

        <!-- Normal content display -->
        <article
          v-else
          class="markdown-content prose prose-zinc dark:prose-invert prose-p:leading-7 prose-p:my-3 prose-headings:mt-6 prose-headings:mb-3 prose-li:my-1 prose-ul:my-3 prose-ol:my-3 prose-pre:my-0 prose-pre:bg-transparent prose-code:before:content-none prose-code:after:content-none prose-code:bg-muted prose-code:px-1.5 prose-code:py-0.5 prose-code:rounded-md prose-code:text-[0.9em] prose-code:font-normal max-w-none"
          v-html="renderedContent"
          @click="handleMarkdownClick"
        ></article>

        <!-- Render media attachments if present -->
        <div v-if="hasRenderableImages" class="mt-3 space-y-2">
          <div
            v-for="image in message.message_type === 'USER' ? userImages : assistantImages"
            :key="image.id"
            class="overflow-hidden rounded-lg border border-gray-200 dark:border-gray-700"
          >
            <img
              :src="image.url"
              :alt="image.alt || 'Image'"
              class="h-auto max-w-full cursor-zoom-in transition hover:opacity-90"
              loading="lazy"
              :title="t('chat.imagePreviewHint')"
              @click="openImagePreview(image)"
            />
          </div>
        </div>

        <!-- Citations -->
        <div v-if="displayCitations.length" class="mt-5 space-y-2">
          <div class="text-muted-foreground text-xs font-medium tracking-wide uppercase">
            Citations
          </div>
          <div class="flex flex-wrap gap-2">
            <button
              v-for="(citation, idx) in displayCitations"
              :key="citation.index || idx"
              type="button"
              class="border-border/60 bg-muted/30 hover:bg-muted hover:border-border inline-flex items-center gap-1.5 rounded-xl border px-3 py-1.5 text-xs shadow-sm transition-all duration-200"
              @click="previewCitation(citation)"
            >
              <span class="font-medium"
                >[{{ citation.index || idx + 1 }}]
                {{ citation.display_name || citation.title || "Source" }}</span
              >
              <!-- Excel/CSV: Sheet and Row info -->
              <span
                v-if="
                  citation.sheet ||
                  citation.metadata?.sheet ||
                  citation.row_number ||
                  citation.metadata?.row_number
                "
                class="text-muted-foreground"
              >
                {{ citation.sheet || citation.metadata?.sheet || "Sheet" }} · Row
                {{ citation.row_number || citation.metadata?.row_number || "?" }}
              </span>
              <!-- PDF/Document: Page number -->
              <span
                v-else-if="
                  citation.page_number ||
                  citation.metadata?.page_number ||
                  citation.metadata?.page_start
                "
                class="text-muted-foreground flex items-center gap-1"
              >
                <svg class="h-3 w-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path
                    stroke-linecap="round"
                    stroke-linejoin="round"
                    stroke-width="2"
                    d="M7 21h10a2 2 0 002-2V9.414a1 1 0 00-.293-.707l-5.414-5.414A1 1 0 0012.586 3H7a2 2 0 00-2 2v14a2 2 0 002 2z"
                  />
                </svg>
                Page
                {{
                  citation.page_number ||
                  citation.metadata?.page_number ||
                  citation.metadata?.page_start
                }}
                <span
                  v-if="
                    citation.metadata?.page_end &&
                    citation.metadata?.page_end !==
                      (citation.page_number ||
                        citation.metadata?.page_number ||
                        citation.metadata?.page_start)
                  "
                >
                  - {{ citation.metadata.page_end }}
                </span>
                <!-- Section info if available -->
                <span
                  v-if="citation.section || citation.metadata?.section"
                  class="ml-1 border-l border-current/30 pl-1"
                >
                  {{ citation.section || citation.metadata?.section }}
                </span>
              </span>
              <!-- Fallback: snippet preview -->
              <span
                v-else-if="citation.snippet"
                class="text-muted-foreground max-w-[220px] truncate"
                :title="citation.snippet"
              >
                {{ citation.snippet }}
              </span>
              <!-- Fallback: URL -->
              <span
                v-else-if="citation.source_url || citation.url"
                class="text-muted-foreground max-w-[220px] truncate"
                :title="citation.source_url || citation.url"
              >
                {{ citation.source_url || citation.url }}
              </span>
            </button>
          </div>
          <div v-if="previewLoading" class="text-muted-foreground text-xs">Loading preview…</div>
        </div>

        <!-- Follow-up questions -->
        <div v-if="showFollowupQuestions" class="mt-5 space-y-3">
          <div class="text-muted-foreground text-xs font-medium tracking-wide uppercase">
            {{ t("chat.followups.title") }}
          </div>
          <div class="flex flex-wrap gap-2">
            <button
              v-for="(q, idx) in displayedFollowupQuestions"
              :key="`${message.id}-followup-${idx}`"
              type="button"
              class="border-border/60 bg-muted/30 hover:bg-muted hover:border-border inline-flex items-center rounded-xl border px-3.5 py-2 text-sm shadow-sm transition-all duration-200"
              @click="handleFollowupClick(q)"
            >
              {{ q }}
            </button>
          </div>
        </div>
      </div>

      <!-- Toolbar for user message (outside bubble, right aligned) -->
      <div
        v-if="!isStreamingMessage && message.message_type === 'USER'"
        class="mt-1.5 flex items-center justify-end gap-1"
      >
        <!-- Edited indicator -->
        <span
          v-if="wasEdited"
          class="text-muted-foreground/60 mr-1 text-xs"
          :title="message.edited_at ? new Date(message.edited_at).toLocaleString() : ''"
        >
          {{ t("chat.edited") }}
        </span>

        <!-- Edit button -->
        <Button
          @click="startEdit"
          class="text-muted-foreground/60 hover:text-foreground hover:bg-muted/50 h-7 w-7 rounded-lg p-0 transition-all"
          :title="t('chat.editMessage')"
          variant="ghost"
          :disabled="isEditing"
        >
          <Pencil class="h-3.5 w-3.5" />
        </Button>

        <!-- Copy button -->
        <Button
          @click="copyMessage"
          class="text-muted-foreground/60 hover:text-foreground hover:bg-muted/50 h-7 w-7 rounded-lg p-0 transition-all"
          :title="t('chat.copyContent')"
          variant="ghost"
        >
          <Check v-if="copySuccess" class="h-3.5 w-3.5 text-emerald-500" />
          <Copy v-else class="h-3.5 w-3.5" />
        </Button>
      </div>

      <!-- Toolbar -->
      <div
        v-if="!isStreamingMessage && message.message_type === 'ASSISTANT'"
        class="text-muted-foreground mt-1 flex items-center gap-1"
      >
        <Button
          @click="copyMessage"
          class="text-muted-foreground/70 hover:text-foreground hover:bg-muted/50 h-8 w-8 rounded-lg p-0 transition-all"
          :title="t('chat.copyContent')"
          variant="ghost"
        >
          <Check v-if="copySuccess" class="h-4 w-4 text-emerald-500" />
          <Copy v-else class="h-4 w-4" />
        </Button>

        <Button
          v-if="showMessageFeedbackButtons"
          @click="openFeedbackDialog('UP')"
          :disabled="feedbackSubmitting"
          :class="[
            'h-8 w-8 rounded-lg p-0 transition-all',
            feedbackSubmittedRating === 'UP'
              ? 'bg-emerald-500/10 text-emerald-500 hover:bg-emerald-500/15'
              : 'text-muted-foreground/70 hover:text-foreground hover:bg-muted/50',
          ]"
          :title="t('chat.feedback.thumbsUp')"
          variant="ghost"
        >
          <ThumbsUp class="h-4 w-4" />
        </Button>

        <Button
          v-if="showMessageFeedbackButtons"
          @click="openFeedbackDialog('DOWN')"
          :disabled="feedbackSubmitting"
          :class="[
            'h-8 w-8 rounded-lg p-0 transition-all',
            feedbackSubmittedRating === 'DOWN'
              ? 'bg-rose-500/10 text-rose-500 hover:bg-rose-500/15'
              : 'text-muted-foreground/70 hover:text-foreground hover:bg-muted/50',
          ]"
          :title="t('chat.feedback.thumbsDown')"
          variant="ghost"
        >
          <ThumbsDown class="h-4 w-4" />
        </Button>

        <Button
          v-if="showMessageStats && messageStats"
          @click="statsDialogOpen = true"
          class="text-muted-foreground/70 hover:text-foreground hover:bg-muted/50 h-8 w-8 rounded-lg p-0 transition-all"
          title="Message stats"
          variant="ghost"
        >
          <Info class="h-4 w-4" />
        </Button>

        <Button
          v-if="enableShare && message.message_type === 'ASSISTANT'"
          @click="handleShare"
          class="text-muted-foreground/70 hover:text-foreground hover:bg-muted/50 h-8 w-8 rounded-lg p-0 transition-all"
          :title="t('chat.share.titleMessage')"
          variant="ghost"
        >
          <Share class="h-4 w-4" />
        </Button>
      </div>
    </div>
  </div>

  <!-- Feedback -->
  <Dialog v-model:open="feedbackDialogOpen">
    <DialogContent class="sm:max-w-[520px]">
      <DialogHeader class="pb-2">
        <DialogTitle>
          {{ feedbackRating === "UP" ? t("chat.feedback.titleUp") : t("chat.feedback.titleDown") }}
        </DialogTitle>
        <DialogDescription>
          {{ t("chat.feedback.description") }}
        </DialogDescription>
      </DialogHeader>

      <div class="space-y-4">
        <div class="space-y-2">
          <div class="text-sm font-medium">
            {{ t("chat.feedback.quickOptions") }}
          </div>
          <div class="flex flex-wrap gap-2">
            <button
              v-for="reason in availableFeedbackReasons"
              :key="reason"
              type="button"
              @click="toggleFeedbackReason(reason)"
              :class="[
                'inline-flex items-center rounded-full border px-3 py-1 text-sm transition',
                feedbackReasons.includes(reason)
                  ? 'bg-primary text-primary-foreground border-primary'
                  : 'bg-muted/20 hover:bg-muted',
              ]"
            >
              {{ reason }}
            </button>
          </div>
        </div>

        <div class="space-y-2">
          <div class="flex items-center justify-between">
            <div class="text-sm font-medium">
              {{ t("chat.feedback.detailsLabel") }}
            </div>
            <div class="text-muted-foreground text-xs">
              {{ feedbackComment.length }} / {{ FEEDBACK_COMMENT_MAX_CHARS }}
            </div>
          </div>
          <Textarea
            v-model="feedbackComment"
            :placeholder="t('chat.feedback.detailsPlaceholder')"
            :maxlength="FEEDBACK_COMMENT_MAX_CHARS"
            class="min-h-[120px]"
          />
          <div class="text-muted-foreground text-xs">
            {{ t("chat.feedback.privacyHint") }}
          </div>
        </div>
      </div>

      <DialogFooter class="gap-2 sm:gap-0">
        <Button
          type="button"
          variant="outline"
          :disabled="feedbackSubmitting"
          @click="feedbackDialogOpen = false"
        >
          {{ t("common.cancel") }}
        </Button>
        <Button type="button" :disabled="feedbackSubmitting" @click="submitFeedback">
          <Loader2 v-if="feedbackSubmitting" class="mr-2 h-4 w-4 animate-spin" />
          {{ t("chat.feedback.submit") }}
        </Button>
      </DialogFooter>
    </DialogContent>
  </Dialog>

  <Dialog v-model:open="statsDialogOpen">
    <DialogContent class="sm:max-w-[425px]">
      <DialogHeader>
        <DialogTitle>Message Statistics</DialogTitle>
        <DialogDescription> Token usage and execution time for this message </DialogDescription>
      </DialogHeader>
      <div class="grid gap-4 py-4">
        <div class="grid grid-cols-2 items-center gap-4">
          <span class="text-sm font-medium">Input Tokens</span>
          <span class="text-sm">{{ messageStats?.inputTokens }}</span>
        </div>
        <div class="grid grid-cols-2 items-center gap-4">
          <span class="text-sm font-medium">Output Tokens</span>
          <span class="text-sm">{{ messageStats?.outputTokens }}</span>
        </div>
        <div class="grid grid-cols-2 items-center gap-4 border-t pt-2">
          <span class="text-sm font-bold">Total Tokens</span>
          <span class="text-sm font-bold">{{ messageStats?.totalTokens }}</span>
        </div>
        <div v-if="messageStats?.timeMs" class="grid grid-cols-2 items-center gap-4 border-t pt-2">
          <span class="text-sm font-medium">Execution Time</span>
          <span class="text-sm">{{ messageStats?.timeMs }} ms</span>
        </div>
      </div>
    </DialogContent>
  </Dialog>

  <Dialog v-model:open="imagePreviewOpen">
    <DialogContent class="max-h-[90vh] sm:max-w-[90vw]">
      <DialogHeader class="pb-2">
        <DialogTitle>{{ t("chat.imagePreviewTitle") }}</DialogTitle>
      </DialogHeader>
      <div class="max-h-[70vh] overflow-auto">
        <img
          v-if="previewImage"
          :src="previewImage.url"
          :alt="previewImage.alt || t('chat.imagePreviewTitle')"
          class="h-auto w-full rounded-md"
        />
      </div>
    </DialogContent>
  </Dialog>

  <!-- Citation Preview (PDF Page, Excel Row, or Text Snippet) -->
  <Dialog v-model:open="previewOpen">
    <DialogContent class="sm:max-w-[800px]">
      <DialogHeader class="pb-2">
        <DialogTitle class="flex items-center gap-2">
          <span
            v-if="previewData?.metadata?.file_type"
            class="bg-primary/10 text-primary rounded px-2 py-0.5 text-xs font-medium uppercase"
          >
            {{ previewData.metadata.file_type }}
          </span>
          {{
            previewData?.type === "pdf-page"
              ? previewData?.title || "PDF Source"
              : previewData?.type === "text" || previewData?.type === "chunk"
                ? previewData?.title || "Source Content"
                : "Row preview"
          }}
        </DialogTitle>
        <DialogDescription v-if="previewData?.metadata?.score" class="text-xs">
          Relevance: {{ (previewData.metadata.score * 100).toFixed(0) }}%
          <span v-if="previewData.metadata.page_number" class="ml-2">
            · Citation from page {{ previewData.metadata.page_number }}
          </span>
        </DialogDescription>
      </DialogHeader>

      <div v-if="previewData" class="flex-1 overflow-hidden">
        <!-- PDF Page Image Preview (NotebookLM-style) -->
        <template v-if="previewData.type === 'pdf-page'">
          <div class="max-h-[70vh] space-y-3 overflow-y-auto">
            <div class="flex items-center justify-between">
              <div
                v-if="previewData.metadata"
                class="text-muted-foreground flex flex-wrap items-center gap-2 text-xs"
              >
                <span
                  v-if="previewData.metadata.page_number"
                  class="bg-primary/10 text-primary rounded-full px-2 py-0.5 font-medium"
                >
                  Page {{ previewData.metadata.page_number }}
                </span>
              </div>
              <!-- Download PDF button -->
              <a
                v-if="previewData.pdfDownloadUrl"
                :href="previewData.pdfDownloadUrl"
                target="_blank"
                class="bg-primary/10 text-primary hover:bg-primary/20 inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-medium transition-colors"
              >
                <svg class="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path
                    stroke-linecap="round"
                    stroke-linejoin="round"
                    stroke-width="2"
                    d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"
                  />
                </svg>
                Download PDF
              </a>
            </div>
            <!-- Actual PDF Page Image -->
            <div class="bg-muted/20 overflow-hidden rounded-lg border shadow-sm">
              <img
                :src="previewData.imageUrl"
                :alt="`Page ${previewData.metadata?.page_number || 1}`"
                class="h-auto w-full"
                loading="lazy"
                @error="handlePdfImageError"
              />
            </div>
            <!-- Also show text snippet below the image for context -->
            <div v-if="previewData.snippet" class="border-t pt-3">
              <p class="text-muted-foreground mb-2 text-xs font-medium uppercase">Extracted Text</p>
              <div class="bg-muted/30 rounded-lg border p-3">
                <p class="text-muted-foreground text-sm leading-relaxed whitespace-pre-wrap">
                  {{ previewData.snippet }}
                </p>
              </div>
            </div>
          </div>
        </template>

        <!-- Chunk preview (full content from chunk endpoint) -->
        <template v-else-if="previewData.type === 'chunk'">
          <div class="max-h-[70vh] space-y-3 overflow-y-auto">
            <div
              v-if="previewData.metadata"
              class="text-muted-foreground flex flex-wrap items-center gap-2 text-xs"
            >
              <span
                v-if="previewData.metadata.file_type"
                class="bg-secondary rounded-full px-2 py-0.5 font-medium uppercase"
              >
                {{ previewData.metadata.file_type }}
              </span>
              <span
                v-if="previewData.metadata.page_number"
                class="bg-primary/10 text-primary rounded-full px-2 py-0.5 font-medium"
              >
                Page {{ previewData.metadata.page_number }}
              </span>
              <span v-if="previewData.metadata.sheet" class="flex items-center gap-1">
                <svg class="h-3 w-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path
                    stroke-linecap="round"
                    stroke-linejoin="round"
                    stroke-width="2"
                    d="M3 10h18M3 14h18m-9-4v8m-7 0h14a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z"
                  />
                </svg>
                {{ previewData.metadata.sheet }}
              </span>
              <span v-if="previewData.metadata.row_number">
                Row {{ previewData.metadata.row_number }}
              </span>
              <span v-if="previewData.metadata.section" class="border-l border-current/30 pl-2">
                {{ previewData.metadata.section }}
              </span>
              <span v-if="previewData.metadata.chunk_index !== undefined" class="opacity-60">
                Chunk {{ previewData.metadata.chunk_index + 1 }}
              </span>
            </div>
            <div class="bg-muted/30 rounded-lg border p-4">
              <p class="text-sm leading-relaxed whitespace-pre-wrap">
                {{ previewData.content }}
              </p>
            </div>
          </div>
        </template>

        <!-- Text/Document snippet preview -->
        <template v-else-if="previewData.type === 'text'">
          <div class="max-h-[70vh] space-y-3 overflow-y-auto">
            <div
              v-if="previewData.metadata"
              class="text-muted-foreground flex flex-wrap gap-2 text-xs"
            >
              <span v-if="previewData.metadata.chunk_index !== undefined">
                Chunk {{ previewData.metadata.chunk_index + 1 }}
              </span>
            </div>
            <div class="bg-muted/30 rounded-lg border p-4">
              <p class="text-sm leading-relaxed whitespace-pre-wrap">
                {{ previewData.content }}
              </p>
            </div>
          </div>
        </template>

        <!-- Excel/CSV row preview -->
        <template v-else>
          <div class="max-h-[70vh] space-y-3 overflow-y-auto">
            <div class="text-muted-foreground text-sm">
              {{ previewData.sheet }} · Row {{ previewData.row_number }}
            </div>
            <div class="bg-muted/30 rounded-lg border p-3">
              <dl class="grid grid-cols-2 gap-3 text-sm">
                <template v-for="(value, key) in previewData.row" :key="key">
                  <dt class="text-muted-foreground">{{ key }}</dt>
                  <dd class="font-medium break-words whitespace-normal">
                    {{ value ?? "—" }}
                  </dd>
                </template>
              </dl>
            </div>
          </div>
        </template>
      </div>
      <div v-else class="text-muted-foreground text-sm">No preview available.</div>
    </DialogContent>
  </Dialog>

  <!-- Selection Menu -->
  <div
    v-if="selectionMenuVisible"
    class="selection-menu bg-popover text-popover-foreground animate-in fade-in zoom-in fixed z-50 flex items-center gap-1 rounded-md border px-2 py-1 shadow-md duration-200"
    :style="{
      top: `${selectionMenuPosition.top}px`,
      left: `${selectionMenuPosition.left}px`,
      transform: 'translateX(-50%)',
    }"
  >
    <button
      @click="handleQuote"
      class="hover:bg-accent hover:text-accent-foreground flex items-center gap-1 rounded px-2 py-1 text-xs font-medium transition-colors"
    >
      <Quote class="h-3 w-3" />
      {{ t("chat.quote") }}
    </button>
  </div>
</template>

<style scoped>
.markdown-content > *:first-child {
  margin-top: 0 !important;
}

.markdown-content > *:last-child {
  margin-bottom: 0 !important;
}

.citation-marker {
  cursor: pointer;
  font-weight: 600;
  color: var(--primary);
  transition: opacity 0.15s ease;
}

.citation-marker:hover {
  opacity: 0.8;
  text-decoration: underline;
}

/* Smooth animations for message appearance */
.animate-in {
  animation-fill-mode: both;
}

/* Better inline code styling */
.markdown-content :deep(code:not(pre code)) {
  background: hsl(var(--muted));
  padding: 0.125rem 0.375rem;
  border-radius: 0.375rem;
  font-size: 0.875em;
  font-weight: 500;
}
</style>
