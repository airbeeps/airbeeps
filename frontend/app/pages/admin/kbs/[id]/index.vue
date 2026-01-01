<script setup lang="ts">
import { ref, h, onMounted, onUnmounted, computed, watch } from "vue";
import { Badge } from "~/components/ui/badge";
import { Button } from "~/components/ui/button";
import { Progress } from "~/components/ui/progress";
import {
  FileText,
  Upload,
  Trash2,
  Split,
  ChevronLeft,
  ChevronRight,
  ChevronDown,
  ChevronUp,
  RefreshCw,
  Clock,
  CheckCircle,
  XCircle,
  Loader2,
  Settings2,
  X,
  Database,
  Layers,
  Cpu,
  FileStack,
  AlertTriangle,
} from "lucide-vue-next";
import type { ColumnDef, SortingState, PaginationState } from "@tanstack/vue-table";
import type { ActionConfig } from "~/components/model-view/DataTable.vue";
import DocIcon from "~/components/file-type-icon/Doc.vue";
import PdfIcon from "~/components/file-type-icon/Pdf.vue";
import MdIcon from "~/components/file-type-icon/Md.vue";
import TxtIcon from "~/components/file-type-icon/Txt.vue";
import XlsIcon from "~/components/file-type-icon/Xls.vue";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "~/components/ui/dialog";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "~/components/ui/sheet";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "~/components/ui/alert-dialog";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "~/components/ui/collapsible";
import DataTable from "~/components/model-view/DataTable.vue";
import FileUploadToKB from "~/components/admin/FileUploadToKB.vue";
import { toast } from "vue-sonner";
import type { KnowledgeBase, Document } from "~/types/api";

const { $api } = useNuxtApp();
const config = useRuntimeConfig();
const { t } = useI18n();

// Get route parameters
const route = useRoute();
const router = useRouter();
const kbId = route.params.id as string;

// Page metadata
definePageMeta({
  breadcrumb: "admin.pages.knowledgeBases.detail.breadcrumb",
  layout: "admin",
});

// State
const showUploadSheet = ref(false);
const knowledgeBase = ref<KnowledgeBase | null>(null);
const documentsKey = ref(0);
const loading = ref(false);
const deleteLoading = ref(false);
const showDeleteDialog = ref(false);
const documentToDelete = ref<Document | null>(null);
const showKbDetails = ref(false);

// Chunk-related state
const showChunksDialog = ref(false);
const chunksLoading = ref(false);
const currentDocument = ref<Document | null>(null);
const chunks = ref<any[]>([]);
const chunksTotal = ref(0);
const chunksPage = ref(1);
const chunksPageSize = ref(50);

// =====================================================
// Real-time Ingestion Jobs with SSE
// =====================================================
interface ActiveIngestionJob {
  id: string;
  original_filename: string;
  status: string;
  stage: string | null;
  progress: number;
  total_items: number | null;
  processed_items: number | null;
  error_message: string | null;
  created_at: string;
  updated_at: string;
  eventSource: EventSource | null;
  lastSeq: number;
}

const activeJobs = ref<ActiveIngestionJob[]>([]);
const jobsLoading = ref(false);

// Load ingestion jobs for this KB
const loadIngestionJobs = async () => {
  jobsLoading.value = true;
  try {
    const response: any[] = await $api(
      `/v1/admin/rag/ingestion-jobs?knowledge_base_id=${kbId}&limit=20`
    );

    // Close existing SSE connections
    activeJobs.value.forEach((job) => {
      if (job.eventSource) {
        job.eventSource.close();
      }
    });

    // Update jobs list
    activeJobs.value = (response || []).map((job) => ({
      ...job,
      eventSource: null,
      lastSeq: 0,
    }));

    // Start SSE for running jobs
    activeJobs.value
      .filter((j) => j.status === "RUNNING" || j.status === "PENDING")
      .forEach((job) => startJobSSE(job));
  } catch (error) {
    console.error("Failed to load ingestion jobs:", error);
  } finally {
    jobsLoading.value = false;
  }
};

// Start SSE stream for a job
const startJobSSE = (job: ActiveIngestionJob) => {
  const apiBase = config.public.apiBase || "";
  const url = `${apiBase}/v1/admin/rag/ingestion-jobs/${job.id}/events`;

  if (job.eventSource) {
    job.eventSource.close();
  }

  const eventSource = new EventSource(url, { withCredentials: true });
  job.eventSource = eventSource;

  eventSource.addEventListener("heartbeat", (event: any) => {
    try {
      const data = JSON.parse(event.data);
      job.status = data.status || job.status;
      job.stage = data.stage;
      job.progress = data.progress || 0;
      job.total_items = data.total_items;
      job.processed_items = data.processed_items;
    } catch (e) {}
  });

  eventSource.addEventListener("progress", (event: any) => {
    try {
      const data = JSON.parse(event.data);
      const payload = data.data || data;
      if (payload.total_items != null) job.total_items = payload.total_items;
      if (payload.processed_items != null) job.processed_items = payload.processed_items;
      if (payload.progress != null) job.progress = payload.progress;
      if (payload.stage) job.stage = payload.stage;
    } catch (e) {}
  });

  eventSource.addEventListener("completed", (event: any) => {
    job.status = "SUCCEEDED";
    job.progress = 100;
    job.stage = null;
    eventSource.close();
    job.eventSource = null;
    // Refresh documents list
    loadData();
  });

  eventSource.addEventListener("error", (event: any) => {
    try {
      const data = JSON.parse(event.data);
      job.status = "FAILED";
      job.error_message = data.data?.error || data.error || "Unknown error";
      job.stage = null;
    } catch (e) {}
    eventSource.close();
    job.eventSource = null;
  });

  eventSource.addEventListener("canceled", () => {
    job.status = "CANCELED";
    job.stage = null;
    eventSource.close();
    job.eventSource = null;
  });

  eventSource.addEventListener("done", () => {
    eventSource.close();
    job.eventSource = null;
  });

  eventSource.onerror = () => {
    eventSource.close();
    job.eventSource = null;
  };
};

// Clean up SSE connections on unmount
onUnmounted(() => {
  activeJobs.value.forEach((job) => {
    if (job.eventSource) {
      job.eventSource.close();
    }
  });
});

// Computed values
const runningJobsCount = computed(
  () => activeJobs.value.filter((j) => j.status === "RUNNING" || j.status === "PENDING").length
);

const hasActiveJobs = computed(() => runningJobsCount.value > 0);

// Get stage display text
const getStageText = (stage: string | null): string => {
  if (!stage) return "";
  const stageMap: Record<string, string> = {
    PARSING: "Parsing...",
    CHUNKING: "Chunking...",
    EMBEDDING: "Embedding...",
    UPSERTING: "Saving...",
    CANCELING: "Canceling...",
  };
  return stageMap[stage] || stage;
};

// Get status icon component
const getStatusIcon = (status: string) => {
  switch (status) {
    case "SUCCEEDED":
      return CheckCircle;
    case "FAILED":
    case "CANCELED":
      return XCircle;
    case "RUNNING":
      return Loader2;
    default:
      return Clock;
  }
};

// Get status color class
const getStatusColor = (status: string): string => {
  switch (status) {
    case "SUCCEEDED":
      return "text-green-600";
    case "FAILED":
    case "CANCELED":
      return "text-destructive";
    case "RUNNING":
      return "text-primary";
    default:
      return "text-muted-foreground";
  }
};

// Load knowledge base info
const loadKnowledgeBase = async () => {
  loading.value = true;
  try {
    const response: any = await $api(`/v1/admin/rag/knowledge-bases/${kbId}`);
    knowledgeBase.value = response as KnowledgeBase;
  } catch (error) {
    toast.error(t("admin.pages.knowledgeBases.detail.loadFailed"));
    router.push("/admin/kbs");
  } finally {
    loading.value = false;
  }
};

const reindexLoading = ref(false);
const handleReindex = async () => {
  if (!knowledgeBase.value) return;
  reindexLoading.value = true;
  try {
    await $api(`/v1/admin/rag/knowledge-bases/${kbId}/reindex`, {
      method: "POST",
    });
    toast.success(t("admin.pages.knowledgeBases.detail.reindexSuccess") || "Reindex started");
    await loadKnowledgeBase();
  } catch (error) {
    toast.error(t("admin.pages.knowledgeBases.detail.reindexFailed") || "Reindex failed");
  } finally {
    reindexLoading.value = false;
  }
};

// Initialize API
const api = useModelViewAPI<Document>(`/v1/admin/rag/knowledge-bases/${kbId}/documents`, {
  update: "/v1/admin/rag/documents",
  delete: "/v1/admin/rag/documents",
});

// State management
const data = ref<Document[]>([]);
const totalCount = ref(0);

// Query parameters
const searchQuery = ref("");
const filters = ref<Record<string, any>>({});
const sorting = ref<SortingState>([]);
const pagination = ref<PaginationState>({
  pageIndex: 0,
  pageSize: 20,
});

const loadData = async () => {
  loading.value = true;
  try {
    const params = {
      page: pagination.value.pageIndex + 1,
      size: pagination.value.pageSize,
      search: searchQuery.value || undefined,
      sort_by: sorting.value[0]?.id,
      sort_desc: sorting.value[0]?.desc,
      ...filters.value,
    };

    const response = await api.getList(params);
    data.value = response.items;
    totalCount.value = response.total;
  } catch (error) {
    toast.error(t("admin.pages.knowledgeBases.detail.loadDataFailed"));
  } finally {
    loading.value = false;
  }
};

const tableColumns: ColumnDef<Document>[] = [
  {
    accessorKey: "title",
    header: t("admin.pages.knowledgeBases.detail.columns.title"),
    cell: (context) => {
      const row = context.row.original;

      const getFileIcon = (fileType: string) => {
        const type = fileType?.toLowerCase();
        switch (type) {
          case "pdf":
            return PdfIcon;
          case "doc":
          case "docx":
            return DocIcon;
          case "md":
          case "markdown":
            return MdIcon;
          case "txt":
            return TxtIcon;
          case "xls":
          case "xlsx":
            return XlsIcon;
          default:
            return FileText;
        }
      };

      const IconComponent = getFileIcon(row.file_type);

      return h("div", { class: "flex items-center" }, [
        h(IconComponent, { class: "size-8 mr-2 shrink-0" }),
        h("span", { class: "truncate" }, row.title),
      ]);
    },
  },
  {
    accessorKey: "file_size",
    header: t("admin.pages.knowledgeBases.detail.columns.size"),
    cell: (context) => {
      const size = context.getValue() as number;
      if (!size) return "-";

      if (size < 1024) return `${size} B`;
      if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
      return `${(size / (1024 * 1024)).toFixed(1)} MB`;
    },
  },
  {
    accessorKey: "file_type",
    header: t("admin.pages.knowledgeBases.detail.columns.type"),
    cell: (context) => {
      const type = context.getValue() as string;
      return h(Badge, { variant: "secondary", class: "uppercase" }, () => type || "—");
    },
  },
  {
    accessorKey: "status",
    header: t("admin.pages.knowledgeBases.detail.columns.status"),
    cell: (context) => {
      const status = context.getValue() as string;
      const variants = {
        INDEXING: "secondary",
        ACTIVE: "default",
        FAILED: "destructive",
      } as const;

      const labels = {
        INDEXING: "Indexing",
        ACTIVE: "Active",
        FAILED: "Failed",
      } as const;

      return h(
        Badge,
        {
          variant: variants[status as keyof typeof variants] || "secondary",
        },
        () => labels[status as keyof typeof labels] || status
      );
    },
  },
  {
    accessorKey: "created_at",
    header: t("admin.pages.knowledgeBases.detail.columns.createdAt"),
    cell: (context) => {
      const date = new Date(context.getValue() as string);
      return date.toLocaleDateString();
    },
  },
];

const rowActions: ActionConfig[] = [
  {
    key: "view-chunks",
    label: t("admin.pages.knowledgeBases.detail.viewChunks"),
    icon: Split,
  },
  {
    key: "delete",
    label: t("admin.pages.knowledgeBases.detail.delete"),
    icon: Trash2,
    variant: "destructive",
  },
];

const bulkActions: ActionConfig[] = [
  {
    key: "bulk-delete",
    label: t("common.delete") || "Delete",
    icon: Trash2,
    variant: "destructive",
  },
];

// Handle file upload complete
const handleUploadComplete = async () => {
  documentsKey.value++;
  await Promise.all([loadData(), loadIngestionJobs()]);
};

// Handle upload sheet close
const handleUploadSheetClose = async (open: boolean) => {
  showUploadSheet.value = open;
  if (!open) {
    // Refresh data when sheet closes
    await Promise.all([loadData(), loadIngestionJobs()]);
  }
};

// Handle document actions
const resetDeleteDialog = () => {
  showDeleteDialog.value = false;
  documentToDelete.value = null;
};

const handleDocumentAction = (action: ActionConfig, row: Document) => {
  switch (action.key) {
    case "view-chunks":
      openChunksDialog(row);
      break;
    case "delete":
      documentToDelete.value = row;
      showDeleteDialog.value = true;
      break;
  }
};

const handleBulkAction = async (action: ActionConfig, rows: Document[]) => {
  if (action.key === "bulk-delete") {
    try {
      const ids = rows.map((r) => r.id);
      await $api(`/v1/admin/rag/knowledge-bases/${kbId}/documents`, {
        method: "DELETE",
        body: { ids },
      });
      toast.success(t("admin.pages.knowledgeBases.detail.deleteConfirm.success"));
      documentsKey.value++;
      await loadData();
    } catch (error) {
      toast.error(t("admin.pages.knowledgeBases.detail.deleteConfirm.failed"));
    }
  }
};

const confirmDeleteDocument = async () => {
  if (!documentToDelete.value) return;

  deleteLoading.value = true;
  try {
    await api.remove(documentToDelete.value.id);
    toast.success(t("admin.pages.knowledgeBases.detail.deleteConfirm.success"));
    resetDeleteDialog();
    loadData();
  } catch (error) {
    toast.error(t("admin.pages.knowledgeBases.detail.deleteConfirm.failed"));
  } finally {
    deleteLoading.value = false;
  }
};

// Event handler methods
const handleSearch = (query: string) => {
  searchQuery.value = query;
  pagination.value.pageIndex = 0;
  loadData();
};

const handleFilter = (filterValues: Record<string, any>) => {
  filters.value = filterValues;
  pagination.value.pageIndex = 0;
  loadData();
};

const handleSort = (sortingState: SortingState) => {
  sorting.value = sortingState;
  loadData();
};

const handlePaginate = (paginationState: PaginationState) => {
  pagination.value = paginationState;
  loadData();
};

const handleRefresh = () => {
  loadData();
  loadIngestionJobs();
};

const handleDeleteDialogOpenChange = (open: boolean) => {
  showDeleteDialog.value = open;
};

// Get document chunks
const loadDocumentChunks = async (documentId: string, page: number = 1) => {
  chunksLoading.value = true;
  try {
    const response: any = await $api(
      `/v1/admin/rag/documents/${documentId}/chunks?page=${page}&size=${chunksPageSize.value}`
    );
    chunks.value = response.items || [];
    chunksTotal.value = response.total || 0;
    chunksPage.value = page;
  } catch (error) {
    toast.error(t("admin.pages.knowledgeBases.detail.chunks.loadFailed"));
  } finally {
    chunksLoading.value = false;
  }
};

// Open chunk dialog
const openChunksDialog = (document: Document) => {
  currentDocument.value = document;
  showChunksDialog.value = true;
  chunksPage.value = 1;
  loadDocumentChunks(document.id, 1);
};

// Close chunk dialog
const closeChunksDialog = () => {
  showChunksDialog.value = false;
  currentDocument.value = null;
  chunks.value = [];
  chunksTotal.value = 0;
  chunksPage.value = 1;
};

// Pagination handling
const totalPages = computed(() => Math.ceil(chunksTotal.value / chunksPageSize.value));
const canGoPrevious = computed(() => chunksPage.value > 1);
const canGoNext = computed(() => chunksPage.value < totalPages.value);

const goToPreviousPage = () => {
  if (canGoPrevious.value && currentDocument.value) {
    loadDocumentChunks(currentDocument.value.id, chunksPage.value - 1);
  }
};

const goToNextPage = () => {
  if (canGoNext.value && currentDocument.value) {
    loadDocumentChunks(currentDocument.value.id, chunksPage.value + 1);
  }
};

// Lifecycle
onMounted(async () => {
  await Promise.all([loadKnowledgeBase(), loadData(), loadIngestionJobs()]);
});
</script>

<template>
  <div class="flex h-full flex-col">
    <!-- Compact Header Bar -->
    <div class="from-background to-muted/30 border-b bg-gradient-to-r px-1 py-3">
      <div class="flex items-center justify-between gap-4">
        <!-- KB Name & Quick Info -->
        <div class="flex min-w-0 items-center gap-3">
          <div
            class="bg-primary/10 text-primary flex h-10 w-10 shrink-0 items-center justify-center rounded-lg"
          >
            <Database class="h-5 w-5" />
          </div>
          <div class="min-w-0">
            <div class="flex items-center gap-2">
              <h1 class="truncate text-lg font-semibold">{{ knowledgeBase?.name || "..." }}</h1>
              <Badge v-if="knowledgeBase?.status" variant="outline" class="shrink-0">
                {{ knowledgeBase.status }}
              </Badge>
              <Badge v-if="knowledgeBase?.reindex_required" variant="destructive" class="shrink-0">
                <AlertTriangle class="mr-1 h-3 w-3" />
                Reindex needed
              </Badge>
            </div>
            <div class="text-muted-foreground flex items-center gap-3 text-xs">
              <span class="flex items-center gap-1">
                <Cpu class="h-3 w-3" />
                {{ knowledgeBase?.embedding_model_name || "No model" }}
              </span>
              <span class="flex items-center gap-1">
                <Layers class="h-3 w-3" />
                {{ knowledgeBase?.chunk_size || 0 }} / {{ knowledgeBase?.chunk_overlap || 0 }}
              </span>
              <span class="flex items-center gap-1">
                <FileStack class="h-3 w-3" />
                {{ totalCount }} docs
              </span>
            </div>
          </div>
        </div>

        <!-- Actions -->
        <div class="flex shrink-0 items-center gap-2">
          <!-- Active Jobs Indicator -->
          <Button
            v-if="activeJobs.length > 0"
            variant="outline"
            size="sm"
            class="relative"
            @click="showUploadSheet = true"
          >
            <Loader2 v-if="hasActiveJobs" class="mr-2 h-4 w-4 animate-spin" />
            <Clock v-else class="mr-2 h-4 w-4" />
            {{ activeJobs.length }} Jobs
            <span v-if="hasActiveJobs" class="absolute -top-1 -right-1 flex h-3 w-3">
              <span
                class="bg-primary absolute inline-flex h-full w-full animate-ping rounded-full opacity-75"
              ></span>
              <span class="bg-primary relative inline-flex h-3 w-3 rounded-full"></span>
            </span>
          </Button>

          <Button variant="outline" size="sm" @click="router.push(`/admin/kbs/${kbId}/profiles`)">
            <Settings2 class="mr-2 h-4 w-4" />
            Profiles
          </Button>

          <Button
            v-if="knowledgeBase?.reindex_required"
            size="sm"
            variant="destructive"
            @click="handleReindex"
            :disabled="reindexLoading"
          >
            <RefreshCw class="mr-2 h-4 w-4" :class="{ 'animate-spin': reindexLoading }" />
            Reindex
          </Button>

          <Button size="sm" @click="showUploadSheet = true">
            <Upload class="mr-2 h-4 w-4" />
            Upload
          </Button>
        </div>
      </div>

      <!-- Expandable Details -->
      <Collapsible v-model:open="showKbDetails" class="mt-2">
        <CollapsibleTrigger asChild>
          <Button variant="ghost" size="sm" class="text-muted-foreground h-6 px-2 text-xs">
            <component :is="showKbDetails ? ChevronUp : ChevronDown" class="mr-1 h-3 w-3" />
            {{ showKbDetails ? "Hide details" : "Show details" }}
          </Button>
        </CollapsibleTrigger>
        <CollapsibleContent>
          <div class="bg-muted/30 mt-2 rounded-lg border p-3">
            <div class="grid gap-4 text-sm sm:grid-cols-2 lg:grid-cols-4">
              <div>
                <span class="text-muted-foreground text-xs">Description</span>
                <p class="mt-0.5">{{ knowledgeBase?.description || "No description" }}</p>
              </div>
              <div>
                <span class="text-muted-foreground text-xs">Embedding Model</span>
                <p class="mt-0.5 font-medium">
                  {{ knowledgeBase?.embedding_model_name || "Not configured" }}
                </p>
              </div>
              <div>
                <span class="text-muted-foreground text-xs">Chunk Settings</span>
                <p class="mt-0.5">
                  Size: {{ knowledgeBase?.chunk_size }}, Overlap: {{ knowledgeBase?.chunk_overlap }}
                </p>
              </div>
              <div>
                <span class="text-muted-foreground text-xs">Last Updated</span>
                <p class="mt-0.5">
                  {{
                    knowledgeBase?.updated_at
                      ? new Date(knowledgeBase.updated_at).toLocaleString()
                      : "—"
                  }}
                </p>
              </div>
            </div>
          </div>
        </CollapsibleContent>
      </Collapsible>
    </div>

    <!-- Documents Table (Main Content) -->
    <div class="flex-1 overflow-hidden p-1">
      <DataTable
        :key="documentsKey"
        :data="data"
        :columns="tableColumns"
        :total-count="totalCount"
        :loading="loading"
        :selectable="true"
        :can-create="false"
        :show-filters="true"
        :bulk-actions="bulkActions"
        :row-actions="rowActions"
        :empty-message="t('admin.pages.knowledgeBases.detail.noDocuments')"
        @refresh="handleRefresh"
        @search="handleSearch"
        @filter="handleFilter"
        @sort="handleSort"
        @paginate="handlePaginate"
        @row-action="handleDocumentAction"
        @bulk-action="handleBulkAction"
      />
    </div>

    <!-- Upload & Jobs Sheet (Slide-out Panel) -->
    <Sheet :open="showUploadSheet" @update:open="handleUploadSheetClose">
      <SheetContent class="flex w-full flex-col sm:max-w-lg">
        <SheetHeader>
          <SheetTitle>Upload Documents</SheetTitle>
          <SheetDescription> Add documents to {{ knowledgeBase?.name }} </SheetDescription>
        </SheetHeader>

        <div class="flex-1 overflow-y-auto py-4">
          <!-- Upload Component -->
          <FileUploadToKB
            :default-knowledge-base-id="kbId"
            @upload-complete="handleUploadComplete"
          />

          <!-- Recent Jobs -->
          <div v-if="activeJobs.length > 0" class="mt-6 border-t pt-4">
            <div class="mb-3 flex items-center justify-between">
              <h4 class="text-sm font-medium">Recent Jobs</h4>
              <Button variant="ghost" size="sm" @click="loadIngestionJobs" :disabled="jobsLoading">
                <RefreshCw class="h-4 w-4" :class="{ 'animate-spin': jobsLoading }" />
              </Button>
            </div>

            <div class="space-y-2">
              <div
                v-for="job in activeJobs"
                :key="job.id"
                class="bg-muted/30 rounded-lg border p-3"
              >
                <div class="flex items-center gap-2">
                  <component
                    :is="getStatusIcon(job.status)"
                    class="h-4 w-4 shrink-0"
                    :class="[
                      getStatusColor(job.status),
                      { 'animate-spin': job.status === 'RUNNING' },
                    ]"
                  />
                  <span class="min-w-0 flex-1 truncate text-sm font-medium">
                    {{ job.original_filename }}
                  </span>
                  <Badge variant="outline" class="shrink-0 text-xs">
                    {{ job.status.toLowerCase() }}
                  </Badge>
                </div>

                <!-- Progress -->
                <div v-if="job.status === 'RUNNING'" class="mt-2 space-y-1">
                  <div class="text-muted-foreground flex justify-between text-xs">
                    <span>{{ getStageText(job.stage) }}</span>
                    <span>{{ job.progress }}%</span>
                  </div>
                  <Progress :model-value="job.progress" class="h-1.5" />
                </div>

                <!-- Error -->
                <div v-if="job.error_message" class="text-destructive mt-2 text-xs">
                  {{ job.error_message }}
                </div>

                <!-- Timestamp -->
                <div v-if="job.status === 'SUCCEEDED'" class="text-muted-foreground mt-1 text-xs">
                  Completed {{ new Date(job.updated_at).toLocaleString() }}
                </div>
              </div>
            </div>
          </div>
        </div>
      </SheetContent>
    </Sheet>

    <!-- Delete Confirmation Dialog -->
    <AlertDialog :open="showDeleteDialog" @update:open="handleDeleteDialogOpenChange">
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>{{
            t("admin.pages.knowledgeBases.detail.deleteConfirm.title")
          }}</AlertDialogTitle>
          <AlertDialogDescription>
            {{
              t("admin.pages.knowledgeBases.detail.deleteConfirm.description", {
                title: documentToDelete?.title,
              })
            }}
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>{{ t("common.cancel") }}</AlertDialogCancel>
          <AlertDialogAction
            class="bg-destructive hover:bg-destructive/90"
            :disabled="deleteLoading"
            @click="confirmDeleteDocument"
          >
            {{ deleteLoading ? t("common.deleting") : t("common.confirmDelete") }}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>

    <!-- Chunks Dialog -->
    <Dialog
      :open="showChunksDialog"
      @update:open="
        (open) => {
          if (!open) closeChunksDialog();
        }
      "
    >
      <DialogContent class="max-h-[80vh] max-w-4xl grid-rows-[auto_minmax(0,1fr)_auto] p-0">
        <DialogHeader class="p-6 pb-0">
          <DialogTitle>{{ t("admin.pages.knowledgeBases.detail.chunks.title") }}</DialogTitle>
          <DialogDescription>
            {{
              t("admin.pages.knowledgeBases.detail.chunks.description", {
                title: currentDocument?.title,
                count: chunksTotal,
              })
            }}
          </DialogDescription>
        </DialogHeader>
        <div class="flex-1 gap-4 overflow-y-auto px-6 py-4">
          <div v-if="chunksLoading" class="flex items-center justify-center py-8">
            <Loader2 class="text-muted-foreground h-6 w-6 animate-spin" />
          </div>
          <div v-else-if="chunks.length === 0" class="flex items-center justify-center py-8">
            <div class="text-muted-foreground">
              {{ t("admin.pages.knowledgeBases.detail.chunks.empty") }}
            </div>
          </div>
          <div v-else class="space-y-3">
            <div
              v-for="(chunk, index) in chunks"
              :key="chunk.id || index"
              class="bg-muted/30 rounded-lg border p-4"
            >
              <div class="mb-2 flex items-center justify-between">
                <span class="text-sm font-medium"
                  >Chunk {{ (chunksPage - 1) * chunksPageSize + index + 1 }}</span
                >
                <span class="text-muted-foreground text-xs">
                  {{ chunk.content?.length || 0 }} chars
                </span>
              </div>
              <p class="text-sm whitespace-pre-wrap">{{ chunk.content }}</p>
            </div>
          </div>
        </div>
        <DialogFooter class="border-t p-4">
          <div class="flex w-full items-center justify-between">
            <div class="text-muted-foreground text-sm">
              Page {{ chunksPage }} of {{ totalPages }} ({{ chunksTotal }} chunks)
            </div>
            <div class="flex items-center gap-2">
              <Button
                variant="outline"
                size="sm"
                :disabled="!canGoPrevious || chunksLoading"
                @click="goToPreviousPage"
              >
                <ChevronLeft class="h-4 w-4" />
              </Button>
              <Button
                variant="outline"
                size="sm"
                :disabled="!canGoNext || chunksLoading"
                @click="goToNextPage"
              >
                <ChevronRight class="h-4 w-4" />
              </Button>
            </div>
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  </div>
</template>
