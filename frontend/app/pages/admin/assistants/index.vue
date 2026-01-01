<script setup lang="ts">
import { Plus, Edit, Eye, Languages } from "lucide-vue-next";
import { computed, h, ref, onMounted, watch } from "vue";
import type { ColumnDef, SortingState, PaginationState } from "@tanstack/vue-table";
import { Badge } from "~/components/ui/badge";
import { Button } from "~/components/ui/button";
import { Avatar, AvatarFallback, AvatarImage } from "~/components/ui/avatar";
import DataTable, {
  type FilterConfig,
  type ActionConfig,
} from "~/components/model-view/DataTable.vue";
import { useModelViewAPI } from "~/composables/useModelViewAPI";
import { toast } from "vue-sonner";
import type { Assistant, Model } from "~/types/api";

const { t } = useI18n();

//Page metadata
definePageMeta({
  breadcrumb: "admin.pages.assistants.breadcrumb",
  layout: "admin",
});

const router = useRouter();

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
    accessorKey: "mode",
    header: "Mode",
    cell: (context) => {
      const value = (context.getValue() as string) || "GENERAL";
      const label = value === "RAG" ? "RAG" : "General";
      return h(Badge, { variant: value === "RAG" ? "default" : "secondary" }, () => label);
    },
  },
  {
    accessorKey: "status",
    header: t("admin.pages.assistants.columns.status"),
    cell: (context) => {
      const value = context.getValue() as string;
      const statusConfig = {
        ACTIVE: { key: "active", variant: "default" as const },
        INACTIVE: { key: "inactive", variant: "secondary" as const },
        DRAFT: { key: "draft", variant: "outline" as const },
      };
      const config = statusConfig[value as keyof typeof statusConfig] || {
        key: value.toLowerCase(),
        variant: "secondary" as const,
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
    key: "translations",
    label: t("admin.pages.assistants.actions.translations"),
    icon: Languages,
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

const handleRowAction = (action: ActionConfig, row: Assistant) => {
  switch (action.key) {
    case "view":
      router.push(`/admin/assistants/${row.id}`);
      break;
    case "edit":
      router.push(`/admin/assistants/${row.id}/edit`);
      break;
    case "translations":
      router.push(`/admin/assistants/${row.id}/translations`);
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
      :selectable="false"
      :can-create="false"
      :show-filters="true"
      :filters="filterConfig"
      :row-actions="rowActions"
      :bulk-actions="[]"
      :initial-page-size="10"
      :initial-sorting="defaultSorting"
      :empty-message="t('admin.pages.assistants.emptyMessage')"
      @refresh="handleRefresh"
      @search="handleSearch"
      @filter="handleFilter"
      @sort="handleSort"
      @paginate="handlePaginate"
      @row-action="handleRowAction"
    />
  </div>
</template>
