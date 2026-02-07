<script setup lang="ts">
import {
  Plus,
  Edit,
  Eye,
  Languages,
  Bot,
  Brain,
  Database,
  Activity,
  Sparkles,
  Download,
  CheckCircle,
  XCircle,
  Trash2,
} from "lucide-vue-next";
import { computed, h, ref, onMounted, watch } from "vue";
import type { ColumnDef, SortingState, PaginationState } from "@tanstack/vue-table";
import { Badge } from "~/components/ui/badge";
import { Button } from "~/components/ui/button";
import { Avatar, AvatarFallback, AvatarImage } from "~/components/ui/avatar";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "~/components/ui/tooltip";
import DataTable, {
  type FilterConfig,
  type ActionConfig,
} from "~/components/model-view/DataTable.vue";
import { useModelViewAPI } from "~/composables/useModelViewAPI";
import { useExport } from "~/composables/useExport";
import { toast } from "vue-sonner";
import type { Assistant, Model } from "~/types/api";

const { t } = useI18n();

//Page metadata
definePageMeta({
  breadcrumb: "admin.pages.assistants.breadcrumb",
  layout: "admin",
});

const router = useRouter();
const { $api } = useNuxtApp();
const { exportCSV, exportJSON, exporting } = useExport();

// Bulk action state
const selectedRows = ref<Assistant[]>([]);

// Fetch model list
const { data: models } = useAPI<Model[]>("/v1/admin/all-models?capabilities=chat", {
  server: false,
});

const modelOptions = computed(() =>
  (models.value ?? []).map((m) => ({ label: m.display_name, value: m.id }))
);

// Initialize API
const api = useModelViewAPI<Assistant>("/v1/admin/assistants");

// State management
const data = ref<Assistant[]>([]);
const totalCount = ref(0);
const loading = ref(false);

// Query parameters
const searchQuery = ref("");
const filters = ref<Record<string, any>>({});
const defaultSorting: SortingState = [{ id: "updated_at", desc: true }];
const sorting = ref<SortingState>([...defaultSorting]);
const pagination = ref<PaginationState>({
  pageIndex: 0,
  pageSize: 10,
});

// Table column config
const tableColumns = computed((): ColumnDef<Assistant>[] => [
  {
    accessorKey: "name",
    header: t("admin.pages.assistants.columns.name"),
    cell: (context) => {
      const row = context.row.original;
      return h("div", { class: "flex items-center gap-2" }, [
        h(Avatar, { class: "w-8 h-8" }, () => [h(AvatarImage, { src: row.avatar_url || "" })]),
        h(
          "button",
          {
            class:
              "text-primary font-medium cursor-pointer text-left focus:outline-none focus:ring-2 focus:ring-primary/40 rounded-full bg-muted/30 hover:bg-muted/60 hover:underline px-2 py-0.5 transition-colors",
            onClick: () => router.push(`/admin/assistants/${row.id}`),
          },
          row.name
        ),
      ]);
    },
  },
  {
    accessorKey: "model.display_name",
    header: t("admin.pages.assistants.columns.model"),
  },
  {
    id: "features",
    header: "Features",
    cell: (context) => {
      const row = context.row.original;
      const badges = [];

      // Mode badge
      if (row.mode === "RAG") {
        badges.push(
          h(Badge, { variant: "default", class: "gap-1 text-xs", title: "RAG Mode" }, () => [
            h(Database, { class: "h-3 w-3" }),
            "RAG",
          ])
        );
      }

      // Agent badge
      if (row.enable_agent) {
        badges.push(
          h(Badge, { variant: "secondary", class: "gap-1 text-xs", title: "Agent Enabled" }, () => [
            h(Sparkles, { class: "h-3 w-3" }),
            "Agent",
          ])
        );
      }

      // Memory badge
      if (row.enable_memory) {
        badges.push(
          h(Badge, { variant: "outline", class: "gap-1 text-xs", title: "Memory Enabled" }, () => [
            h(Brain, { class: "h-3 w-3" }),
            "Memory",
          ])
        );
      }

      if (badges.length === 0) {
        badges.push(h(Badge, { variant: "secondary", class: "text-xs" }, () => "General"));
      }

      return h("div", { class: "flex flex-wrap gap-1" }, badges);
    },
  },
  {
    accessorKey: "status",
    header: t("admin.pages.assistants.columns.status"),
    cell: (context) => {
      const value = context.getValue() as string;
      const statusConfig = {
        ACTIVE: { key: "active", variant: "default" as const, icon: null },
        INACTIVE: { key: "inactive", variant: "secondary" as const, icon: null },
        DRAFT: { key: "draft", variant: "outline" as const, icon: null },
      };
      const config = statusConfig[value as keyof typeof statusConfig] || {
        key: value.toLowerCase(),
        variant: "secondary" as const,
        icon: null,
      };
      return h(Badge, { variant: config.variant }, () =>
        t(`admin.pages.assistants.status.${config.key}`)
      );
    },
  },
  {
    accessorKey: "created_at",
    header: t("admin.pages.assistants.columns.createdAt"),
    cell: (context) => {
      const value = context.getValue() as string;
      return new Date(value).toLocaleDateString();
    },
  },
]);

// Row action config
const rowActions = computed((): ActionConfig[] => [
  {
    key: "view",
    label: t("admin.pages.assistants.actions.view"),
    icon: Eye,
  },
  {
    key: "edit",
    label: t("admin.pages.assistants.actions.edit"),
    icon: Edit,
  },
  {
    key: "traces",
    label: "View Traces",
    icon: Activity,
  },
  {
    key: "translations",
    label: t("admin.pages.assistants.actions.translations"),
    icon: Languages,
  },
  {
    key: "exportConfig",
    label: t("admin.export.json"),
    icon: Download,
  },
]);

// Bulk actions config
const bulkActions = computed((): ActionConfig[] => [
  {
    key: "activate",
    label: t("admin.bulkActions.activate"),
    icon: CheckCircle,
  },
  {
    key: "deactivate",
    label: t("admin.bulkActions.deactivate"),
    icon: XCircle,
  },
  {
    key: "exportCSV",
    label: t("admin.export.csv"),
    icon: Download,
  },
  {
    key: "delete",
    label: t("admin.bulkActions.delete"),
    icon: Trash2,
    variant: "destructive",
  },
]);

// Filter config
const filterConfig = computed(
  (): Record<string, FilterConfig> => ({
    model: {
      type: "select",
      label: t("admin.pages.assistants.filters.model"),
      placeholder: t("admin.pages.assistants.filters.modelPlaceholder"),
      options: modelOptions.value,
    },
    mode: {
      type: "select",
      label: "Mode",
      placeholder: "Select mode",
      options: [
        { label: "General", value: "GENERAL" },
        { label: "RAG", value: "RAG" },
      ],
    },
    enable_agent: {
      type: "select",
      label: "Agent Mode",
      placeholder: "Any",
      options: [
        { label: "Enabled", value: "true" },
        { label: "Disabled", value: "false" },
      ],
    },
    status: {
      type: "select",
      label: t("admin.pages.assistants.filters.status"),
      placeholder: t("admin.pages.assistants.filters.statusPlaceholder"),
      options: [
        { label: t("admin.pages.assistants.status.active"), value: "ACTIVE" },
        {
          label: t("admin.pages.assistants.status.inactive"),
          value: "INACTIVE",
        },
        { label: t("admin.pages.assistants.status.draft"), value: "DRAFT" },
      ],
    },
    created_at: {
      type: "daterange",
      label: t("admin.pages.assistants.filters.createdAt"),
    },
  })
);

// API methods
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
    toast.error(t("admin.pages.assistants.loadDataFailed"));
  } finally {
    loading.value = false;
  }
};

// Event handler methods
const handleSearch = (query: string) => {
  searchQuery.value = query;
  pagination.value.pageIndex = 0;
  loadData();
};

const handleFilter = (filterValues: Record<string, any>) => {
  filters.value = { ...filterValues };
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

// Bulk status update
const bulkUpdateStatus = async (rows: Assistant[], status: "ACTIVE" | "INACTIVE") => {
  try {
    await Promise.all(
      rows.map((row) =>
        $api(`/v1/admin/assistants/${row.id}`, {
          method: "PATCH",
          body: { status },
        })
      )
    );
    toast.success(t("admin.bulkActions.statusUpdated", { count: rows.length }));
    loadData();
  } catch (error) {
    toast.error(t("admin.bulkActions.statusUpdateFailed"));
  }
};

// Bulk delete
const bulkDelete = async (rows: Assistant[]) => {
  if (
    !confirm(
      t("components.modelView.deleteConfirmMultiple", { count: rows.length, title: "Assistants" })
    )
  ) {
    return;
  }
  try {
    await Promise.all(rows.map((row) => api.remove(row.id)));
    toast.success(t("components.modelView.deleteSuccess", { title: "Assistants" }));
    loadData();
  } catch (error) {
    toast.error(t("components.modelView.deleteFailed"));
  }
};

// Export selected as CSV
const handleExportCSV = async (rows: Assistant[]) => {
  const columns = [
    { key: "id", label: "ID" },
    { key: "name", label: "Name" },
    { key: "status", label: "Status" },
    { key: "mode", label: "Mode" },
    { key: "enable_agent", label: "Agent Enabled" },
    { key: "created_at", label: "Created At" },
  ];
  await exportCSV(rows, { filename: `assistants_${Date.now()}.csv`, columns });
  toast.success(t("admin.export.success"));
};

// Export single config as JSON
const handleExportConfig = async (row: Assistant) => {
  const { exportConfig } = useExport();
  // Clean up the config for export
  const config = {
    name: row.name,
    description: row.description,
    mode: row.mode,
    status: row.status,
    system_prompt: row.system_prompt,
    enable_agent: row.enable_agent,
    enable_memory: row.enable_memory,
    agent_max_iterations: row.agent_max_iterations,
    agent_token_budget: row.agent_token_budget,
    agent_cost_limit: row.agent_cost_limit,
    agent_reflection_threshold: row.agent_reflection_threshold,
    generate_follow_up_questions: row.generate_follow_up_questions,
    // Model reference by ID
    model_id: row.model_id,
    // KB IDs if any
    knowledge_base_ids: row.knowledge_base_ids || [],
  };
  await exportConfig(config, { filename: `assistant_${row.name.replace(/\s+/g, "_")}.json` });
  toast.success(t("admin.export.success"));
};

// Handle bulk action
const handleBulkAction = (action: ActionConfig, rows: Assistant[]) => {
  switch (action.key) {
    case "activate":
      bulkUpdateStatus(rows, "ACTIVE");
      break;
    case "deactivate":
      bulkUpdateStatus(rows, "INACTIVE");
      break;
    case "exportCSV":
      handleExportCSV(rows);
      break;
    case "delete":
      bulkDelete(rows);
      break;
  }
};

const handleRowAction = (action: ActionConfig, row: Assistant) => {
  switch (action.key) {
    case "view":
      router.push(`/admin/assistants/${row.id}`);
      break;
    case "edit":
      router.push(`/admin/assistants/${row.id}/edit`);
      break;
    case "traces":
      router.push(`/admin/agent-traces?assistant_id=${row.id}`);
      break;
    case "translations":
      router.push(`/admin/assistants/${row.id}/translations`);
      break;
    case "exportConfig":
      handleExportConfig(row);
      break;
  }
};

const handleCreate = () => {
  router.push("/admin/assistants/create");
};

const handleRefresh = () => {
  loadData();
};

// Watch route changes, reload data
watch(
  () => router.currentRoute.value.path,
  () => {
    if (router.currentRoute.value.path === "/admin/assistants") {
      loadData();
    }
  }
);
</script>

<template>
  <div class="space-y-6">
    <!-- Header -->
    <div class="flex items-center justify-between">
      <div>
        <h1 class="text-2xl font-bold">
          {{ t("admin.pages.assistants.title") }}
        </h1>
        <p class="text-muted-foreground">
          {{ t("admin.pages.assistants.description") }}
        </p>
      </div>
      <Button @click="handleCreate" data-testid="create-assistant-btn">
        <Plus class="mr-2 h-4 w-4" />
        {{ t("admin.pages.assistants.createButton") }}
      </Button>
    </div>

    <!-- DataTable -->
    <DataTable
      :data="data"
      :columns="tableColumns"
      :total-count="totalCount"
      :loading="loading"
      :selectable="true"
      :can-create="false"
      :show-filters="true"
      :filters="filterConfig"
      :row-actions="rowActions"
      :bulk-actions="bulkActions"
      :initial-page-size="10"
      :initial-sorting="defaultSorting"
      :empty-message="t('admin.pages.assistants.emptyMessage')"
      @refresh="handleRefresh"
      @search="handleSearch"
      @filter="handleFilter"
      @sort="handleSort"
      @paginate="handlePaginate"
      @row-action="handleRowAction"
      @bulk-action="handleBulkAction"
    />
  </div>
</template>
