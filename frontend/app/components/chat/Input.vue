<script setup lang="ts">
import {
  ArrowUp,
  Image as ImageIcon,
  Camera,
  X,
  Loader2,
  AlertTriangle,
  Globe,
} from "lucide-vue-next";
import type { ImageAttachment } from "~/composables/useStreamingChat";

type AttachmentStatus = "uploading" | "ready" | "error";

type AttachmentItem = ImageAttachment & {
  dataUrl?: string;
  status: AttachmentStatus;
  errorMessage?: string;
};

interface Props {
  modelValue: string;
  placeholder?: string;
  disabled?: boolean;
  sendDisabled?: boolean;
  supportsVision?: boolean; // Whether the model supports image input
  cameraCapture?: "environment" | "user" | "any";
  showWebSearchToggle?: boolean; // Whether to show the web search toggle
  webSearchEnabled?: boolean; // Current state of web search
}

interface Emits {
  (e: "update:modelValue", value: string): void;
  (e: "send", images?: ImageAttachment[]): void;
  (e: "keydown", event: KeyboardEvent): void;
  (e: "update:webSearchEnabled", value: boolean): void;
}

const props = withDefaults(defineProps<Props>(), {
  disabled: false,
  sendDisabled: false,
  supportsVision: false,
  cameraCapture: "environment",
  showWebSearchToggle: false,
  webSearchEnabled: false,
});

const emit = defineEmits<Emits>();

const { $api } = useNuxtApp();
const { showError } = useNotifications();
const { t } = useI18n();
const textareaRef = ref<HTMLTextAreaElement>();
const fileInputRef = ref<HTMLInputElement>();
const cameraInputRef = ref<HTMLInputElement>();
const attachedImages = ref<AttachmentItem[]>([]);
const isDragActive = ref(false);
const dragCounter = ref(0);
const captureAttribute = computed(() =>
  props.cameraCapture !== "any" ? props.cameraCapture : undefined
);
const placeholderText = computed(() => props.placeholder || t("chat.input.placeholder"));
const MAX_IMAGE_SIZE_MB = 5;
const MAX_IMAGE_SIZE = MAX_IMAGE_SIZE_MB * 1024 * 1024;

const pendingUploadsCount = computed(
  () => attachedImages.value.filter((img) => img.status === "uploading").length
);
const hasPendingUploads = computed(() => pendingUploadsCount.value > 0);
const erroredAttachments = computed(() =>
  attachedImages.value.filter((img) => img.status === "error")
);
const readyAttachments = computed(() =>
  attachedImages.value.filter((img) => img.status === "ready" && (img.url || img.dataUrl))
);

const buildSendPayload = (): ImageAttachment[] | undefined => {
  if (!readyAttachments.value.length) {
    return undefined;
  }

  return readyAttachments.value.map(({ id, url, alt, mimeType, size, fileKey }) => ({
    id,
    url,
    alt,
    mimeType,
    size,
    fileKey,
  }));
};

const resetAttachments = () => {
  attachedImages.value = [];
};

const handleKeyPress = (event: KeyboardEvent) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    if (!props.sendDisabled) {
      if (hasPendingUploads.value) {
        showError(t("chat.input.pendingUploads"));
        return;
      }
      const payload = buildSendPayload();
      emit("send", payload);
      resetAttachments();
    }
  }
  emit("keydown", event);
};

const handleInput = (event: Event) => {
  const target = event.target as HTMLTextAreaElement;
  emit("update:modelValue", target.value);
};

const handleSend = () => {
  if (hasPendingUploads.value) {
    showError(t("chat.input.pendingUploads"));
    return;
  }
  const payload = buildSendPayload();
  emit("send", payload);
  resetAttachments();
};

const handleFileSelect = () => {
  fileInputRef.value?.click();
};

const handleCameraCapture = () => {
  cameraInputRef.value?.click();
};

const uploadImageFile = async (file: File, attachmentId: string) => {
  try {
    const formData = new FormData();
    formData.append("file", file);
    formData.append("file_type", "image");

    const response = await $api<{ url: string; id: string; file_path?: string; fileKey?: string }>(
      "/v1/files/upload",
      {
        method: "POST",
        body: formData,
      }
    );

    const image = attachedImages.value.find((img) => img.id === attachmentId);
    if (image) {
      image.url = response.url;
      image.fileKey = response.file_path || response.fileKey;
      image.status = "ready";
    }
  } catch (error) {
    showError(t("chat.input.uploadFailed", { name: file.name }));
    const image = attachedImages.value.find((img) => img.id === attachmentId);
    if (image) {
      image.status = "error";
      image.errorMessage = t("chat.input.imageErrorMessage", { name: file.name });
    }
  }
};

const processFile = (file: File) => {
  if (!file.type.startsWith("image/")) {
    showError(t("chat.input.fileNotImage", { name: file.name }));
    return;
  }

  if (file.size > MAX_IMAGE_SIZE) {
    showError(t("chat.input.fileTooLarge", { name: file.name, max: `${MAX_IMAGE_SIZE_MB}MB` }));
    return;
  }

  const reader = new FileReader();
  reader.onload = async (e) => {
    const dataUrl = e.target?.result as string;
    const imageId = `img-${Date.now()}-${Math.random()}`;

    attachedImages.value.push({
      id: imageId,
      dataUrl,
      alt: file.name,
      mimeType: file.type,
      size: file.size,
      status: "uploading",
    });

    await uploadImageFile(file, imageId);
  };
  reader.readAsDataURL(file);
};

const processFiles = (files: FileList | File[] | Iterable<File>) => {
  const list = Array.isArray(files) ? files : Array.from(files as Iterable<File>);
  for (const file of list) {
    processFile(file);
  }
};

const processFileList = (files: FileList | null) => {
  if (files && files.length > 0) {
    processFiles(files);
  }
};

const handleFileChange = (event: Event) => {
  const target = event.target as HTMLInputElement;
  processFileList(target.files);
  target.value = "";
};

const handleCameraChange = (event: Event) => {
  const target = event.target as HTMLInputElement;
  processFileList(target.files);
  target.value = "";
};

const handlePaste = (event: ClipboardEvent) => {
  if (!props.supportsVision) return;
  const items = event.clipboardData?.items;
  if (!items || items.length === 0) return;

  const imageFiles: File[] = [];
  for (const item of items) {
    if (item.kind === "file") {
      const file = item.getAsFile();
      if (file && file.type.startsWith("image/")) {
        imageFiles.push(file);
      }
    }
  }

  if (imageFiles.length > 0) {
    const textData = event.clipboardData?.getData("text");
    if (!textData) {
      event.preventDefault();
    }
    processFiles(imageFiles);
  }
};

const handleDragEnter = (event: DragEvent) => {
  if (!props.supportsVision) return;
  const hasFiles =
    event.dataTransfer?.types && Array.from(event.dataTransfer.types).includes("Files");
  if (!hasFiles) return;
  event.preventDefault();
  dragCounter.value += 1;
  isDragActive.value = true;
};

const handleDragOver = (event: DragEvent) => {
  if (!props.supportsVision) return;
  const hasFiles =
    event.dataTransfer?.types && Array.from(event.dataTransfer.types).includes("Files");
  if (!hasFiles) return;
  event.preventDefault();
  event.dataTransfer.dropEffect = "copy";
};

const handleDragLeave = (event: DragEvent) => {
  if (!props.supportsVision) return;
  if (dragCounter.value > 0) {
    dragCounter.value -= 1;
  }
  if (dragCounter.value === 0) {
    isDragActive.value = false;
  }
};

const handleDrop = (event: DragEvent) => {
  if (!props.supportsVision) return;
  event.preventDefault();
  dragCounter.value = 0;
  isDragActive.value = false;
  const files = event.dataTransfer?.files;
  if (files && files.length > 0) {
    processFiles(files);
  }
};

const removeImage = (id: string) => {
  attachedImages.value = attachedImages.value.filter((img) => img.id !== id);
};

// Auto-resize textarea
const adjustTextareaHeight = () => {
  if (textareaRef.value) {
    textareaRef.value.style.height = "auto";
    const newHeight = Math.min(textareaRef.value.scrollHeight, 192);
    textareaRef.value.style.height = newHeight + "px";
  }
};

watch(
  () => props.modelValue,
  () => {
    nextTick(() => adjustTextareaHeight());
  }
);

onMounted(() => {
  adjustTextareaHeight();
  // Auto-focus on the textarea when component mounts
  nextTick(() => {
    textareaRef.value?.focus();
  });
});

const toggleWebSearch = () => {
  emit("update:webSearchEnabled", !props.webSearchEnabled);
};

defineExpose({
  focus: () => textareaRef.value?.focus(),
});
</script>

<template>
  <fieldset class="flex w-full min-w-0 flex-col">
    <div
      class="bg-card border-border/80 dark:border-border/60 focus-within:border-primary/60 hover:border-border dark:hover:border-border/80 relative z-10 flex cursor-text flex-col items-stretch rounded-2xl border-2 shadow-lg backdrop-blur-md transition-all duration-200 focus-within:shadow-xl hover:shadow-xl"
      :class="{ 'ring-primary/50 border-primary/40 ring-2': isDragActive }"
      @dragenter.prevent="handleDragEnter"
      @dragover.prevent="handleDragOver"
      @dragleave.prevent="handleDragLeave"
      @drop.prevent="handleDrop"
    >
      <!-- Image previews (compact row above input) -->
      <div v-if="attachedImages.length > 0" class="flex flex-wrap gap-2 px-3 pt-3">
        <div
          v-for="image in attachedImages"
          :key="image.id"
          class="group border-border/50 relative h-16 w-16 overflow-hidden rounded-lg border shadow-sm"
        >
          <img
            :src="image.dataUrl"
            :alt="image.alt || t('chat.input.previewAlt')"
            class="h-full w-full object-cover"
          />
          <div
            v-if="image.status === 'uploading'"
            class="bg-background/80 absolute inset-0 flex items-center justify-center backdrop-blur-sm"
          >
            <Loader2 class="text-primary h-4 w-4 animate-spin" />
          </div>
          <div
            v-else-if="image.status === 'error'"
            class="bg-destructive/80 text-destructive-foreground absolute inset-0 flex items-center justify-center px-1 text-center text-[10px] font-medium"
          >
            {{ t("chat.input.uploadFailedLabel") }}
          </div>
          <button
            @click="removeImage(image.id)"
            class="bg-foreground text-background absolute -top-1 -right-1 rounded-full p-1 opacity-0 shadow-md transition-opacity group-hover:opacity-100"
            type="button"
          >
            <X class="h-3 w-3" />
          </button>
        </div>
      </div>

      <!-- Main input area -->
      <div class="flex items-end gap-2 p-3">
        <!-- Left controls (web search + vision buttons) -->
        <div v-if="showWebSearchToggle || supportsVision" class="flex items-center gap-1 pb-0.5">
          <!-- Web search toggle -->
          <button
            v-if="showWebSearchToggle"
            @click="toggleWebSearch"
            type="button"
            :disabled="disabled"
            class="rounded-lg p-2 transition-colors disabled:opacity-50"
            :class="[
              webSearchEnabled
                ? 'bg-primary/10 text-primary hover:bg-primary/20'
                : 'hover:bg-muted text-muted-foreground',
            ]"
            :title="webSearchEnabled ? t('chat.input.webSearchOn') : t('chat.input.webSearchOff')"
          >
            <Globe class="h-5 w-5" />
          </button>
          <!-- Vision: upload button -->
          <button
            v-if="supportsVision"
            @click="handleFileSelect"
            type="button"
            :disabled="disabled"
            class="hover:bg-muted rounded-lg p-2 transition-colors disabled:opacity-50"
            :title="t('chat.input.uploadButton')"
          >
            <ImageIcon class="text-muted-foreground h-5 w-5" />
          </button>
          <!-- Vision: camera button -->
          <button
            v-if="supportsVision"
            @click="handleCameraCapture"
            type="button"
            :disabled="disabled"
            class="hover:bg-muted rounded-lg p-2 transition-colors disabled:opacity-50"
            :title="t('chat.input.cameraButton')"
          >
            <Camera class="text-muted-foreground h-5 w-5" />
          </button>
          <input
            ref="fileInputRef"
            type="file"
            accept="image/*"
            multiple
            class="hidden"
            @change="handleFileChange"
          />
          <input
            ref="cameraInputRef"
            type="file"
            accept="image/*"
            :capture="captureAttribute"
            class="hidden"
            @change="handleCameraChange"
          />
        </div>

        <!-- Textarea -->
        <div class="min-w-0 flex-1">
          <textarea
            ref="textareaRef"
            :value="modelValue"
            @input="handleInput"
            @keydown="handleKeyPress"
            @paste="handlePaste"
            :placeholder="placeholderText"
            :disabled="disabled"
            autofocus
            data-testid="chat-input"
            class="placeholder:text-muted-foreground/70 max-h-40 min-h-[24px] w-full resize-none overflow-y-auto border-0 bg-transparent py-1 text-sm leading-6 outline-none md:text-[15px]"
            rows="1"
          />
        </div>

        <!-- Send button -->
        <div class="shrink-0 pb-0.5">
          <Button
            @click="handleSend"
            :disabled="sendDisabled || hasPendingUploads"
            data-testid="send-message-btn"
            class="size-9 rounded-full shadow-sm transition-all duration-200"
            :class="{
              'bg-primary hover:bg-primary/90': !sendDisabled && !hasPendingUploads,
              'bg-muted': sendDisabled || hasPendingUploads,
            }"
          >
            <Loader2 v-if="hasPendingUploads" class="h-4 w-4 animate-spin" />
            <ArrowUp v-else class="h-4 w-4" />
          </Button>
        </div>
      </div>

      <!-- Status indicators (below input, minimal) -->
      <div v-if="hasPendingUploads || erroredAttachments.length" class="px-3 pb-2">
        <div class="text-muted-foreground flex items-center gap-2 text-xs">
          <span v-if="hasPendingUploads" class="flex items-center gap-1">
            <Loader2 class="h-3 w-3 animate-spin" />
            {{ t("chat.input.uploadingStatus", { count: pendingUploadsCount }) }}
          </span>
          <span v-if="erroredAttachments.length" class="text-destructive flex items-center gap-1">
            <AlertTriangle class="h-3 w-3" />
            {{ t("chat.input.failedStatus", { count: erroredAttachments.length }) }}
          </span>
        </div>
      </div>
    </div>
  </fieldset>
</template>
