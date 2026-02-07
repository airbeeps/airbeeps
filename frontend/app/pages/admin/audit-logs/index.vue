<script setup lang="ts">
import { ref, computed, onMounted } from "vue";
import { Badge } from "~/components/ui/badge";
import { Button } from "~/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "~/components/ui/card";
import { Input } from "~/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "~/components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "~/components/ui/table";
import {
  History,
  Search,
  Filter,
  RefreshCw,
  ChevronLeft,
  ChevronRight,
  FileText,
  User,
  Settings,
  Trash2,
  Plus,
  Pencil,
  Download,
  Upload,
  LogIn,
  LogOut,
  Key,
  Shield,
  AlertCircle,
} from "lucide-vue-next";
import DateRangeFilter from "~/components/admin/DateRangeFilter.vue";

interface AuditLog {
  id: string;
  user_id: string | null;
  user_email: string | null;
  action: string;
  entity_type: string;
  entity_id: string | null;
  entity_name: string | null;
  description: string | null;
  changes: Record<string, any> | null;
  ip_address: string | null;
  created_at: string;
}

interface AuditStats {
  total_logs: number;
  period_days: number;
  actions_by_type: Record<string, number>;
  actions_by_entity: Record<string, number>;
}

const { t } = useI18n();
const { $api } = useNuxtApp();

definePageMeta({
  breadcrumb: "Audit Logs",
  layout: "admin",
});

// State
const loading = ref(false);
const logs = ref<AuditLog[]>([]);
const total = ref(0);
const offset = ref(0);
const limit = ref(25);
const stats = ref<AuditStats | null>(null);

// Filters
const search = ref("");
const selectedAction = ref<string>("");
const selectedEntityType = ref<string>("");
const startDate = ref<string>("");
const endDate = ref<string>("");

// Available filter options
const actionOptions = [
  { value: "", label: "All Actions" },
  { value: "create", label: "Create" },
  { value: "update", label: "Update" },
  { value: "delete", label: "Delete" },
  { value: "bulk_delete", label: "Bulk Delete" },
  { value: "export", label: "Export" },
  { value: "import", label: "Import" },
  { value: "login", label: "Login" },
  { value: "logout", label: "Logout" },
  { value: "password_change", label: "Password Change" },
  { value: "role_change", label: "Role Change" },
  { value: "status_change", label: "Status Change" },
  { value: "config_change", label: "Config Change" },
];

const entityTypeOptions = ref([{ value: "", label: "All Entity Types" }]);

// Action icons and colors
const actionConfig: Record<string, { icon: any; color: string }> = {
  create: { icon: Plus, color: "bg-green-100 text-green-700" },
  update: { icon: Pencil, color: "bg-blue-100 text-blue-700" },
  delete: { icon: Trash2, color: "bg-red-100 text-red-700" },
  bulk_delete: { icon: Trash2, color: "bg-red-100 text-red-700" },
  export: { icon: Download, color: "bg-purple-100 text-purple-700" },
  import: { icon: Upload, color: "bg-purple-100 text-purple-700" },
  login: { icon: LogIn, color: "bg-gray-100 text-gray-700" },
  logout: { icon: LogOut, color: "bg-gray-100 text-gray-700" },
  password_change: { icon: Key, color: "bg-yellow-100 text-yellow-700" },
  role_change: { icon: Shield, color: "bg-orange-100 text-orange-700" },
  status_change: { icon: AlertCircle, color: "bg-cyan-100 text-cyan-700" },
  config_change: { icon: Settings, color: "bg-indigo-100 text-indigo-700" },
};

// Computed
const currentPage = computed(() => Math.floor(offset.value / limit.value) + 1);
const totalPages = computed(() => Math.ceil(total.value / limit.value));
const hasNextPage = computed(() => offset.value + limit.value < total.value);
const hasPrevPage = computed(() => offset.value > 0);

// Methods
const fetchLogs = async () => {
  loading.value = true;
  try {
    const params = new URLSearchParams();
    params.set("offset", offset.value.toString());
    params.set("limit", limit.value.toString());

    if (search.value) params.set("search", search.value);
    if (selectedAction.value) params.set("action", selectedAction.value);
    if (selectedEntityType.value) params.set("entity_type", selectedEntityType.value);
    if (startDate.value) params.set("start_date", startDate.value);
    if (endDate.value) params.set("end_date", endDate.value);

    const response = await $api<{ items: AuditLog[]; total: number }>(
      `/v1/admin/audit-logs?${params.toString()}`
    );

    logs.value = response.items || [];
    total.value = response.total || 0;
  } catch (error) {
    console.error("Failed to fetch audit logs:", error);
  } finally {
    loading.value = false;
  }
};

const fetchStats = async () => {
  try {
    const response = await $api<AuditStats>(`/v1/admin/audit-logs/stats?days=30`);
    stats.value = response;
  } catch (error) {
    console.error("Failed to fetch audit stats:", error);
  }
};

const fetchEntityTypes = async () => {
  try {
    const response = await $api<{ entity_types: string[] }>(`/v1/admin/audit-logs/entity-types`);
    entityTypeOptions.value = [
      { value: "", label: "All Entity Types" },
      ...response.entity_types.map((type) => ({
        value: type,
        label: type.charAt(0).toUpperCase() + type.slice(1).replace(/_/g, " "),
      })),
    ];
  } catch (error) {
    console.error("Failed to fetch entity types:", error);
  }
};

const handleSearch = () => {
  offset.value = 0;
  fetchLogs();
};

const handleFilterChange = () => {
  offset.value = 0;
  fetchLogs();
};

const handleDateRangeChange = (range: { start: string; end: string }) => {
  startDate.value = range.start;
  endDate.value = range.end;
  offset.value = 0;
  fetchLogs();
};

const nextPage = () => {
  if (hasNextPage.value) {
    offset.value += limit.value;
    fetchLogs();
  }
};

const prevPage = () => {
  if (hasPrevPage.value) {
    offset.value = Math.max(0, offset.value - limit.value);
    fetchLogs();
  }
};

const formatDate = (dateStr: string) => {
  return new Date(dateStr).toLocaleString();
};

const getActionIcon = (action: string) => {
  return actionConfig[action]?.icon || FileText;
};

const getActionColor = (action: string) => {
  return actionConfig[action]?.color || "bg-gray-100 text-gray-700";
};

// Initialize
onMounted(() => {
  fetchLogs();
  fetchStats();
  fetchEntityTypes();
});
</script>

<template>
  <div class="container mx-auto space-y-6 p-6">
    <!-- Header -->
    <div class="flex items-center justify-between">
      <div>
        <h1 class="text-2xl font-bold">{{ t("admin.auditLogs.title") }}</h1>
        <p class="text-muted-foreground">{{ t("admin.auditLogs.description") }}</p>
      </div>
      <Button variant="outline" size="sm" @click="fetchLogs" :disabled="loading">
        <RefreshCw :class="['mr-2 h-4 w-4', loading && 'animate-spin']" />
        {{ t("common.refresh") }}
      </Button>
    </div>

    <!-- Stats Cards -->
    <div v-if="stats" class="grid gap-4 md:grid-cols-4">
      <Card>
        <CardHeader class="pb-2">
          <CardDescription>{{ t("admin.auditLogs.stats.totalLogs") }}</CardDescription>
          <CardTitle class="text-3xl">{{ stats.total_logs.toLocaleString() }}</CardTitle>
        </CardHeader>
        <CardContent>
          <p class="text-muted-foreground text-xs">
            {{ t("admin.auditLogs.stats.lastNDays", { days: stats.period_days }) }}
          </p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader class="pb-2">
          <CardDescription>{{ t("admin.auditLogs.stats.creates") }}</CardDescription>
          <CardTitle class="text-3xl text-green-600">
            {{ (stats.actions_by_type.create || 0).toLocaleString() }}
          </CardTitle>
        </CardHeader>
      </Card>

      <Card>
        <CardHeader class="pb-2">
          <CardDescription>{{ t("admin.auditLogs.stats.updates") }}</CardDescription>
          <CardTitle class="text-3xl text-blue-600">
            {{ (stats.actions_by_type.update || 0).toLocaleString() }}
          </CardTitle>
        </CardHeader>
      </Card>

      <Card>
        <CardHeader class="pb-2">
          <CardDescription>{{ t("admin.auditLogs.stats.deletes") }}</CardDescription>
          <CardTitle class="text-3xl text-red-600">
            {{ (stats.actions_by_type.delete || 0).toLocaleString() }}
          </CardTitle>
        </CardHeader>
      </Card>
    </div>

    <!-- Filters -->
    <Card>
      <CardContent class="pt-6">
        <div class="flex flex-wrap items-center gap-4">
          <!-- Search -->
          <div class="relative min-w-[200px] flex-1">
            <Search
              class="text-muted-foreground absolute top-1/2 left-3 h-4 w-4 -translate-y-1/2"
            />
            <Input
              v-model="search"
              :placeholder="t('admin.auditLogs.searchPlaceholder')"
              class="pl-10"
              @keyup.enter="handleSearch"
            />
          </div>

          <!-- Action Filter -->
          <Select v-model="selectedAction" @update:modelValue="handleFilterChange">
            <SelectTrigger class="w-[180px]">
              <SelectValue :placeholder="t('admin.auditLogs.filterByAction')" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem v-for="opt in actionOptions" :key="opt.value" :value="opt.value">
                {{ opt.label }}
              </SelectItem>
            </SelectContent>
          </Select>

          <!-- Entity Type Filter -->
          <Select v-model="selectedEntityType" @update:modelValue="handleFilterChange">
            <SelectTrigger class="w-[180px]">
              <SelectValue :placeholder="t('admin.auditLogs.filterByEntity')" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem v-for="opt in entityTypeOptions" :key="opt.value" :value="opt.value">
                {{ opt.label }}
              </SelectItem>
            </SelectContent>
          </Select>

          <!-- Date Range -->
          <DateRangeFilter @change="handleDateRangeChange" />
        </div>
      </CardContent>
    </Card>

    <!-- Table -->
    <Card>
      <CardContent class="pt-6">
        <div class="rounded-md border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead class="w-[180px]">{{ t("admin.auditLogs.table.timestamp") }}</TableHead>
                <TableHead>{{ t("admin.auditLogs.table.user") }}</TableHead>
                <TableHead class="w-[140px]">{{ t("admin.auditLogs.table.action") }}</TableHead>
                <TableHead>{{ t("admin.auditLogs.table.entity") }}</TableHead>
                <TableHead>{{ t("admin.auditLogs.table.description") }}</TableHead>
                <TableHead class="w-[120px]">{{ t("admin.auditLogs.table.ip") }}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              <TableRow v-if="loading">
                <TableCell colspan="6" class="py-8 text-center">
                  <RefreshCw class="text-muted-foreground mx-auto h-6 w-6 animate-spin" />
                </TableCell>
              </TableRow>
              <TableRow v-else-if="logs.length === 0">
                <TableCell colspan="6" class="text-muted-foreground py-8 text-center">
                  <History class="mx-auto mb-2 h-12 w-12 opacity-50" />
                  <p>{{ t("admin.auditLogs.noLogs") }}</p>
                </TableCell>
              </TableRow>
              <TableRow v-for="log in logs" :key="log.id">
                <TableCell class="font-mono text-xs">
                  {{ formatDate(log.created_at) }}
                </TableCell>
                <TableCell>
                  <div class="flex items-center gap-2">
                    <User class="text-muted-foreground h-4 w-4" />
                    <span class="max-w-[150px] truncate" :title="log.user_email || 'Unknown'">
                      {{ log.user_email || t("admin.auditLogs.unknownUser") }}
                    </span>
                  </div>
                </TableCell>
                <TableCell>
                  <Badge :class="getActionColor(log.action)" class="gap-1">
                    <component :is="getActionIcon(log.action)" class="h-3 w-3" />
                    {{ log.action }}
                  </Badge>
                </TableCell>
                <TableCell>
                  <div>
                    <span class="font-medium">{{ log.entity_type }}</span>
                    <span v-if="log.entity_name" class="text-muted-foreground ml-1">
                      ({{ log.entity_name }})
                    </span>
                  </div>
                  <div v-if="log.entity_id" class="text-muted-foreground font-mono text-xs">
                    {{ log.entity_id }}
                  </div>
                </TableCell>
                <TableCell class="max-w-[250px]">
                  <span class="block truncate" :title="log.description || ''">
                    {{ log.description || "-" }}
                  </span>
                </TableCell>
                <TableCell class="text-muted-foreground font-mono text-xs">
                  {{ log.ip_address || "-" }}
                </TableCell>
              </TableRow>
            </TableBody>
          </Table>
        </div>

        <!-- Pagination -->
        <div class="mt-4 flex items-center justify-between">
          <p class="text-muted-foreground text-sm">
            {{ t("common.showing") }} {{ offset + 1 }}-{{ Math.min(offset + limit, total) }}
            {{ t("common.of") }} {{ total.toLocaleString() }}
          </p>
          <div class="flex items-center gap-2">
            <Button variant="outline" size="sm" :disabled="!hasPrevPage" @click="prevPage">
              <ChevronLeft class="h-4 w-4" />
            </Button>
            <span class="text-sm">
              {{ t("admin.auditLogs.page") }} {{ currentPage }} / {{ totalPages }}
            </span>
            <Button variant="outline" size="sm" :disabled="!hasNextPage" @click="nextPage">
              <ChevronRight class="h-4 w-4" />
            </Button>
          </div>
        </div>
      </CardContent>
    </Card>
  </div>
</template>
