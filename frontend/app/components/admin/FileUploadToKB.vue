<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch, computed } from "vue";
import { Upload, Trash2, Info, X, RefreshCw, CheckCircle, XCircle, Loader2 } from "lucide-vue-next";
import { Button } from "~/components/ui/button";
import { Label } from "~/components/ui/label";
import { Checkbox } from "~/components/ui/checkbox";
import { Progress } from "~/components/ui/progress";
import { Badge } from "~/components/ui/badge";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "~/components/ui/tooltip";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "~/components/ui/select";
import { toast } from "vue-sonner";
import type { KnowledgeBase } from "~/types/api";

const { $api } = useNuxtApp();
const config = useRuntimeConfig();
const { t } = useI18n();

interface IngestionJob {
  jobId: string;
  fileName: string;
  status: "pending" | "running" | "succeeded" | "failed" | "canceled";
  stage: string | null;
  progress: number;
  totalItems: number | null;
  processedItems: number | null;
  error: string | null;
  eventSource: EventSource | null;
  lastSeq: number; // Track last event seq for reconnection
  reconnectAttempts: number; // Track reconnection attempts
}

interface Props {
  defaultKnowledgeBaseId?: string;
}

const props = withDefaults(defineProps<Props>(), {
  defaultKnowledgeBaseId: "",
});

const emit = defineEmits<{
  "upload-complete": [];
}>();

// State
const selectedKbId = ref(props.defaultKnowledgeBaseId);
const selectedFiles = ref<File[]>([]);
const uploading = ref(false);
const ingestionJobs = ref<IngestionJob[]>([]);
const knowledgeBases = ref<KnowledgeBase[]>([]);
const fileInput = ref<HTMLInputElement>();
const isDragging = ref(false);
const cleanData = ref(true);
const dropHintId = "file-upload-dropzone";

// Profile state
interface IngestionProfile {
  id: string;
  name: string;
  is_default: boolean;
  is_builtin: boolean;
}
const profiles = ref<IngestionProfile[]>([]);
const selectedProfileId = ref<string>("");
const showProfileSelect = ref(false);

// Watch props changes
watch(
  () => props.defaultKnowledgeBaseId,
  (newId) => {
    selectedKbId.value = newId;
  },
  { immediate: true }
);

// Cleanup on unmount
onUnmounted(() => {
  // Close all SSE connections
  ingestionJobs.value.forEach((job) => {
    if (job.eventSource) {
      job.eventSource.close();
    }
  });
});

// File selection
const handleFileSelect = (event: Event) => {
  const target = event.target as HTMLInputElement;
  if (target.files) {
    const newFiles = Array.from(target.files);
    selectedFiles.value.push(...newFiles);
  }
};

// Drag and drop support
const addDroppedFiles = (fileList: FileList) => {
  const files = Array.from(fileList);
  if (!files.length) return;
  selectedFiles.value.push(...files);
};

const handleDragOver = (event: DragEvent) => {
  event.preventDefault();
};

const handleDragEnter = (event: DragEvent) => {
  event.preventDefault();
  isDragging.value = true;
};

const handleDragLeave = (event: DragEvent) => {
  event.preventDefault();
  isDragging.value = false;
};

const handleDrop = (event: DragEvent) => {
  event.preventDefault();
  isDragging.value = false;
  if (event.dataTransfer?.files) {
    addDroppedFiles(event.dataTransfer.files);
  }
};

// Remove file
const removeFile = (index: number) => {
  selectedFiles.value.splice(index, 1);
};

const selectedFilesWithMeta = computed(() =>
  selectedFiles.value.map((file) => ({
    name: file.name,
    size: file.size,
    type: file.type || file.name.split(".").pop() || "",
  }))
);

const formatSize = (bytes: number) => {
  if (!bytes) return "0 B";
  const units = ["B", "KB", "MB", "GB"];
  const i = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
  const size = bytes / Math.pow(1024, i);
  return `${size.toFixed(size >= 10 ? 0 : 1)} ${units[i]}`;
};

// Load knowledge base list
const loadKnowledgeBases = async () => {
  try {
    const response = (await $api("/v1/admin/rag/knowledge-bases")) as any;
    knowledgeBases.value = response.items || response || [];
  } catch (error) {
    toast.error(t("components.fileUpload.loadKnowledgeBasesFailed"));
  }
};

// Load profiles for selected KB
const loadProfiles = async () => {
  if (!selectedKbId.value) {
    profiles.value = [];
    selectedProfileId.value = "";
    return;
  }

  try {
    const response = (await $api(
      `/v1/admin/rag/knowledge-bases/${selectedKbId.value}/ingestion-profiles`
    )) as IngestionProfile[];
    profiles.value = response || [];

    // Auto-select default profile
    const defaultProfile = profiles.value.find((p) => p.is_default);
    if (defaultProfile) {
      selectedProfileId.value = defaultProfile.id;
    } else if (profiles.value.length > 0) {
      selectedProfileId.value = profiles.value[0].id;
    } else {
      selectedProfileId.value = "";
    }

    showProfileSelect.value = profiles.value.length > 0;
  } catch (error) {
    profiles.value = [];
  }
};

// Watch KB selection to load profiles
watch(selectedKbId, () => {
  loadProfiles();
});

// Get stage display text
const getStageText = (stage: string | null): string => {
  if (!stage) return "";
  const stageMap: Record<string, string> = {
    PARSING: "Parsing file...",
    CHUNKING: "Creating chunks...",
    EMBEDDING: "Generating embeddings...",
    UPSERTING: "Saving to vector store...",
    CANCELING: "Canceling...",
  };
  return stageMap[stage] || stage;
};

// Get status badge variant
const getStatusVariant = (status: string): "default" | "secondary" | "destructive" | "outline" => {
  switch (status) {
    case "succeeded":
      return "default";
    case "failed":
    case "canceled":
      return "destructive";
    case "running":
      return "secondary";
    default:
      return "outline";
  }
};

// Start SSE stream for a job with reconnection support
const startJobEventStream = (job: IngestionJob, reconnect: boolean = false) => {
  const apiBase = config.public.apiBase || "";
  // Include last_event_id for reconnection (query param since EventSource doesn't support custom headers)
  const lastSeqParam = reconnect && job.lastSeq > 0 ? `?last_event_id=${job.lastSeq}` : "";
  const url = `${apiBase}/v1/admin/rag/ingestion-jobs/${job.jobId}/events${lastSeqParam}`;

  // Close existing connection if any
  if (job.eventSource) {
    job.eventSource.close();
  }

  const eventSource = new EventSource(url, { withCredentials: true });
  job.eventSource = eventSource;

  eventSource.onopen = () => {
    job.reconnectAttempts = 0; // Reset on successful connection
  };

  // Generic message handler to track seq
  eventSource.onmessage = (event) => {
    // Extract seq from event id if available
    if (event.lastEventId) {
      const seq = parseInt(event.lastEventId, 10);
      if (!isNaN(seq)) {
        job.lastSeq = seq;
      }
    }
  };

  eventSource.addEventListener("heartbeat", (event) => {
    try {
      const data = JSON.parse(event.data);
      job.status = data.status?.toLowerCase() || job.status;
      job.stage = data.stage;
      job.progress = data.progress || 0;
      job.totalItems = data.total_items;
      job.processedItems = data.processed_items;
    } catch (e) {
      // Parse error silently ignored
    }
  });

  eventSource.addEventListener("stage_change", (event: any) => {
    try {
      const data = JSON.parse(event.data);
      job.stage = data.data?.stage || data.stage;
      job.progress = data.data?.progress || data.progress || job.progress;
      // Track seq from event
      if (data.seq) job.lastSeq = data.seq;
    } catch (e) {
      // Parse error silently ignored
    }
  });

  eventSource.addEventListener("progress", (event: any) => {
    try {
      const data = JSON.parse(event.data);
      const payload = data.data || data;

      // Track seq from event
      if (data.seq) job.lastSeq = data.seq;

      // Update counters/progress when present
      if (payload.total_items != null) job.totalItems = payload.total_items;
      if (payload.processed_items != null) job.processedItems = payload.processed_items;
      if (payload.progress != null) job.progress = payload.progress;
      if (payload.stage) job.stage = payload.stage;

      // Back-compat: older payload might include total_chunks
      if (payload.total_chunks != null) job.totalItems = payload.total_chunks;
    } catch (e) {
      // Parse error silently ignored
    }
  });

  eventSource.addEventListener("completed", (event: any) => {
    try {
      const data = JSON.parse(event.data);
      job.status = "succeeded";
      job.progress = 100;
      job.stage = null;
      if (data.seq) job.lastSeq = data.seq;
      toast.success(`'${job.fileName}' ingested successfully`);
      emit("upload-complete");
    } catch (e) {
      // Parse error silently ignored
    }
    eventSource.close();
    job.eventSource = null;
  });

  eventSource.addEventListener("error", (event: any) => {
    try {
      const data = JSON.parse(event.data);
      job.status = "failed";
      job.error = data.data?.error || data.error || "Unknown error";
      job.stage = null;
      if (data.seq) job.lastSeq = data.seq;
    } catch (e) {
      // SSE connection error, not a job error event
    }
    eventSource.close();
    job.eventSource = null;
  });

  eventSource.addEventListener("canceled", (event: any) => {
    try {
      const data = JSON.parse(event.data);
      if (data.seq) job.lastSeq = data.seq;
    } catch (e) {}
    job.status = "canceled";
    job.stage = null;
    eventSource.close();
    job.eventSource = null;
  });

  eventSource.addEventListener("done", () => {
    eventSource.close();
    job.eventSource = null;
  });

  eventSource.onerror = (error) => {
    eventSource.close();
    job.eventSource = null;

    // Auto-reconnect if job is still running and we haven't exceeded retry limit
    const MAX_RECONNECT_ATTEMPTS = 5;
    const RECONNECT_DELAY_MS = 2000;

    if (job.status === "running" && job.reconnectAttempts < MAX_RECONNECT_ATTEMPTS) {
      job.reconnectAttempts++;
      setTimeout(() => {
        if (job.status === "running") {
          startJobEventStream(job, true); // Reconnect with last_seq
        }
      }, RECONNECT_DELAY_MS * job.reconnectAttempts);
    }
  };
};

// Upload files using new one-step ingestion job endpoint
const uploadFiles = async () => {
  if (!selectedKbId.value || selectedFiles.value.length === 0) {
    toast.error(t("components.fileUpload.selectKnowledgeBaseAndFiles"));
    return;
  }

  uploading.value = true;

  try {
    for (const file of selectedFiles.value) {
      // Create job entry
      const job: IngestionJob = {
        jobId: "",
        fileName: file.name,
        status: "pending",
        stage: null,
        progress: 0,
        totalItems: null,
        processedItems: null,
        error: null,
        eventSource: null,
        lastSeq: 0,
        reconnectAttempts: 0,
      };
      ingestionJobs.value.push(job);

      try {
        // Create FormData for one-step upload + job creation
        const formData = new FormData();
        formData.append("file", file);
        formData.append("knowledge_base_id", selectedKbId.value);
        formData.append("dedup_strategy", "replace");
        formData.append("clean_data", cleanData.value.toString());
        if (selectedProfileId.value) {
          formData.append("profile_id", selectedProfileId.value);
        }

        // Call new ingestion job endpoint
        const response: any = await $api("/v1/admin/rag/ingestion-jobs/from-upload", {
          method: "POST",
          body: formData,
        });

        job.jobId = response.job_id;
        job.status = "running";

        // Start SSE stream for this job
        startJobEventStream(job);
      } catch (error: any) {
        job.status = "failed";
        job.error = error?.message || "Failed to create ingestion job";
        toast.error(t("components.fileUpload.uploadFileFailed", { name: file.name }));
      }
    }

    // Clear selected files
    selectedFiles.value = [];
  } finally {
    uploading.value = false;
  }
};

// Cancel a job
const cancelJob = async (job: IngestionJob) => {
  if (!job.jobId || job.status !== "running") return;

  try {
    await $api(`/v1/admin/rag/ingestion-jobs/${job.jobId}/cancel`, {
      method: "POST",
    });
    // Optimistic UI while worker observes cancel_requested
    job.stage = "CANCELING";
    toast.info(`Cancellation requested for '${job.fileName}'`);
  } catch (error) {
    toast.error("Failed to cancel job");
  }
};

// Retry a failed job
const retryJob = async (job: IngestionJob) => {
  if (!job.jobId || !["failed", "canceled"].includes(job.status)) return;

  try {
    const response: any = await $api(`/v1/admin/rag/ingestion-jobs/${job.jobId}/retry`, {
      method: "POST",
    });

    // Update job with new ID
    job.jobId = response.job_id;
    job.status = "running";
    job.stage = null;
    job.progress = 0;
    job.error = null;

    // Start SSE stream for retried job
    startJobEventStream(job);

    toast.info(`Retrying '${job.fileName}'...`);
  } catch (error) {
    toast.error("Failed to retry job");
  }
};

// Remove job from list
const removeJob = (index: number) => {
  const job = ingestionJobs.value[index];
  if (job?.eventSource) {
    job.eventSource.close();
  }
  ingestionJobs.value.splice(index, 1);
};

onMounted(() => {
  loadKnowledgeBases();
});
</script>

<template>
  <div class="space-y-5">
    <!-- Header row -->
    <div class="flex flex-col gap-2">
      <div class="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div class="flex-1 space-y-2">
          <div class="flex items-center gap-2">
            <Label for="kb-select" class="text-sm font-medium">{{
              t("components.fileUpload.selectKnowledgeBase")
            }}</Label>
          </div>
          <Select v-model="selectedKbId" required>
            <SelectTrigger class="h-10">
              <SelectValue
                :placeholder="t('components.fileUpload.selectKnowledgeBasePlaceholder')"
              />
            </SelectTrigger>
            <SelectContent>
              <SelectItem v-for="kb in knowledgeBases" :key="kb.id" :value="kb.id">
                {{ kb.name }}
              </SelectItem>
            </SelectContent>
          </Select>
        </div>
        <div class="flex items-center gap-2 sm:pt-6">
          <Checkbox id="clean-data" v-model:checked="cleanData" />
          <Label for="clean-data" class="text-foreground text-sm font-medium">
            {{ t("components.fileUpload.cleanData") }}
          </Label>
          <TooltipProvider>
            <Tooltip>
              <TooltipTrigger as-child>
                <Info class="text-foreground/80 h-4 w-4 cursor-help" />
              </TooltipTrigger>
              <TooltipContent side="top" class="max-w-xs text-left">
                {{ t("components.fileUpload.cleanDataHelp") }}
              </TooltipContent>
            </Tooltip>
          </TooltipProvider>
        </div>
      </div>

      <!-- Profile Selection (for CSV/XLSX) -->
      <div v-if="showProfileSelect" class="pt-2">
        <div class="flex items-center gap-2">
          <Label for="profile-select" class="text-sm font-medium whitespace-nowrap">
            Ingestion Profile:
          </Label>
          <Select v-model="selectedProfileId" class="flex-1">
            <SelectTrigger class="h-9">
              <SelectValue placeholder="Select profile..." />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="">Auto-detect</SelectItem>
              <SelectItem v-for="profile in profiles" :key="profile.id" :value="profile.id">
                {{ profile.name }}
                <span v-if="profile.is_default" class="text-muted-foreground ml-1">(default)</span>
                <span v-if="profile.is_builtin" class="text-muted-foreground ml-1">(built-in)</span>
              </SelectItem>
            </SelectContent>
          </Select>
        </div>
      </div>
    </div>

    <!-- Dropzone -->
    <div class="space-y-2">
      <Label for="file-upload" class="text-sm font-medium">{{
        t("components.fileUpload.uploadFiles")
      }}</Label>
      <div
        :id="dropHintId"
        class="bg-muted/40 rounded-xl border-2 border-dashed p-6 text-center transition-all duration-200"
        :class="[
          isDragging
            ? 'border-primary bg-primary/5 shadow-sm'
            : 'border-border hover:border-primary/70 hover:bg-muted/60',
        ]"
        @dragover.prevent="handleDragOver"
        @dragenter.prevent="handleDragEnter"
        @dragleave.prevent="handleDragLeave"
        @drop.prevent="handleDrop"
      >
        <input
          ref="fileInput"
          type="file"
          multiple
          accept=".pdf,.txt,.md,.docx,.doc,.pptx,.xlsx,.xls,.csv"
          class="hidden"
          @change="handleFileSelect"
        />

        <div v-if="selectedFiles.length === 0" class="space-y-4">
          <div class="flex justify-center">
            <div
              class="border-primary/40 text-primary flex h-12 w-12 items-center justify-center rounded-full border border-dashed"
            >
              <Upload class="h-6 w-6" />
            </div>
          </div>
          <div class="space-y-2">
            <p class="text-muted-foreground text-sm">
              {{ t("components.fileUpload.supportedFormats") }}
            </p>
            <p class="text-muted-foreground text-xs">
              {{ t("components.fileUpload.orDragDrop") }}
            </p>
          </div>
          <div class="flex justify-center gap-2">
            <Button
              variant="outline"
              class="border-primary/70 text-primary shadow-sm"
              @click="fileInput?.click()"
            >
              {{ t("components.fileUpload.selectFiles") }}
            </Button>
          </div>
        </div>

        <div v-else class="space-y-4">
          <div class="max-h-60 space-y-2 overflow-auto pr-1">
            <div
              v-for="(file, index) in selectedFilesWithMeta"
              :key="`${file.name}-${index}`"
              class="border-border/70 bg-card flex items-center justify-between rounded-lg border px-3 py-2"
            >
              <div class="flex flex-col text-left">
                <span class="truncate text-sm font-medium">{{ file.name }}</span>
                <span class="text-muted-foreground text-xs">
                  {{ formatSize(file.size) }} · {{ file.type || "file" }}
                </span>
              </div>
              <Button variant="ghost" size="sm" @click="removeFile(index)">
                <Trash2 class="text-muted-foreground h-4 w-4" />
              </Button>
            </div>
          </div>
          <div class="flex flex-wrap items-center justify-end gap-2">
            <Button variant="outline" size="sm" @click="fileInput?.click()">
              {{ t("components.fileUpload.addMore") }}
            </Button>
            <Button
              @click="uploadFiles"
              :disabled="!selectedKbId || uploading"
              class="min-w-[140px]"
            >
              <Upload class="mr-2 h-4 w-4" v-if="!uploading" />
              <Loader2 v-else class="mr-2 h-4 w-4 animate-spin" />
              {{
                uploading
                  ? t("components.fileUpload.uploading")
                  : t("components.fileUpload.startUpload")
              }}
            </Button>
          </div>
        </div>
      </div>
    </div>

    <!-- Ingestion Jobs Progress -->
    <div v-if="ingestionJobs.length > 0" class="space-y-3">
      <h4 class="font-medium">Ingestion Jobs</h4>
      <div
        v-for="(job, index) in ingestionJobs"
        :key="job.jobId || `pending-${index}`"
        class="border-border/60 bg-card space-y-2 rounded-lg border px-4 py-3"
      >
        <!-- Header row -->
        <div class="flex items-center justify-between">
          <div class="flex min-w-0 flex-1 items-center gap-2">
            <span class="truncate text-sm font-medium">{{ job.fileName }}</span>
            <Badge :variant="getStatusVariant(job.status)" class="shrink-0 capitalize">
              {{ job.status }}
            </Badge>
          </div>
          <div class="flex shrink-0 items-center gap-1">
            <!-- Cancel button (for running jobs) -->
            <TooltipProvider v-if="job.status === 'running'">
              <Tooltip>
                <TooltipTrigger as-child>
                  <Button
                    variant="ghost"
                    size="icon"
                    class="h-7 w-7"
                    :disabled="job.stage === 'CANCELING'"
                    @click="cancelJob(job)"
                  >
                    <X class="h-4 w-4" />
                  </Button>
                </TooltipTrigger>
                <TooltipContent>Cancel</TooltipContent>
              </Tooltip>
            </TooltipProvider>

            <!-- Retry button (for failed/canceled jobs) -->
            <TooltipProvider v-if="['failed', 'canceled'].includes(job.status)">
              <Tooltip>
                <TooltipTrigger as-child>
                  <Button variant="ghost" size="icon" class="h-7 w-7" @click="retryJob(job)">
                    <RefreshCw class="h-4 w-4" />
                  </Button>
                </TooltipTrigger>
                <TooltipContent>Retry</TooltipContent>
              </Tooltip>
            </TooltipProvider>

            <!-- Remove button (for terminal states) -->
            <TooltipProvider v-if="['succeeded', 'failed', 'canceled'].includes(job.status)">
              <Tooltip>
                <TooltipTrigger as-child>
                  <Button variant="ghost" size="icon" class="h-7 w-7" @click="removeJob(index)">
                    <Trash2 class="h-4 w-4" />
                  </Button>
                </TooltipTrigger>
                <TooltipContent>Remove</TooltipContent>
              </Tooltip>
            </TooltipProvider>
          </div>
        </div>

        <!-- Progress bar (for running jobs) -->
        <div v-if="job.status === 'running'" class="space-y-1">
          <div class="text-muted-foreground flex justify-between text-xs">
            <span>{{ getStageText(job.stage) }}</span>
            <span>{{ job.progress }}%</span>
          </div>
          <Progress :model-value="job.progress" class="h-2" />
          <div v-if="job.totalItems != null" class="text-muted-foreground text-xs">
            {{ job.processedItems || 0 }} / {{ job.totalItems }} items
          </div>
        </div>

        <!-- Error message -->
        <div v-if="job.error" class="text-destructive text-sm">
          {{ job.error }}
        </div>

        <!-- Success indicator -->
        <div
          v-if="job.status === 'succeeded'"
          class="flex items-center gap-1 text-sm text-green-600"
        >
          <CheckCircle class="h-4 w-4" />
          <span>Ingestion complete</span>
        </div>
      </div>
    </div>
  </div>
</template>
