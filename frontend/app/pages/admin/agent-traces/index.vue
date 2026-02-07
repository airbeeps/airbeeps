<script setup lang="ts">
import { ref, computed, onMounted, watch } from "vue";
import {
  RefreshCw,
  Activity,
  CheckCircle,
  XCircle,
  Clock,
  DollarSign,
  Save,
  Trash2,
  Filter,
  ExternalLink,
  AlertCircle,
  TrendingUp,
  TrendingDown,
  Bookmark,
  BookmarkCheck,
  Download,
} from "lucide-vue-next";
import { useExport } from "~/composables/useExport";
import { Button } from "~/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "~/components/ui/card";
import { Badge } from "~/components/ui/badge";
import { Input } from "~/components/ui/input";
import { Label } from "~/components/ui/label";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "~/components/ui/table";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "~/components/ui/dropdown-menu";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "~/components/ui/select";
import { toast } from "vue-sonner";

const { t } = useI18n();
const router = useRouter();
const route = useRoute();
const { exportCSV, exporting } = useExport();

definePageMeta({
  breadcrumb: "Agent Traces",
  layout: "admin",
});

interface Trace {
  id: string;
  trace_id: string;
  span_id: string;
  span_name: string;
  span_kind: string;
  user_id?: string;
  assistant_id?: string;
  conversation_id?: string;
  start_time: string;
  end_time: string;
  latency_ms: number;
  tokens_used?: number;
  cost_usd?: number;
  success: boolean;
  status_code: string;
  created_at: string;
}

interface TraceStats {
  total_traces: number;
  success_count: number;
  success_rate: number;
  avg_latency_ms: number;
  total_cost_usd: number;
  total_tokens: number;
}

interface SavedFilter {
  id: string;
  name: string;
  filters: {
    span_name: string;
    success: boolean | null;
    assistant_id: string;
    time_range: string;
  };
}

// State
const traces = ref<Trace[]>([]);
const stats = ref<TraceStats | null>(null);
const loading = ref(true);
const total = ref(0);
const page = ref(1);
const limit = ref(50);

// Saved filters (stored in localStorage)
const savedFilters = ref<SavedFilter[]>([]);
const filterName = ref("");

// Filters
const filters = ref({
  span_name: "",
  success: null as boolean | null,
  assistant_id: "",
  time_range: "24h" as "1h" | "24h" | "7d" | "30d" | "all",
});

// Load saved filters from localStorage
const loadSavedFilters = () => {
  try {
    const stored = localStorage.getItem("trace_saved_filters");
    if (stored) {
      savedFilters.value = JSON.parse(stored);
    }
  } catch (e) {
    console.error("Failed to load saved filters:", e);
  }
};

// Save filter
const saveCurrentFilter = () => {
  if (!filterName.value.trim()) {
    toast.error("Please enter a filter name");
    return;
  }

  const newFilter: SavedFilter = {
    id: Date.now().toString(),
    name: filterName.value.trim(),
    filters: { ...filters.value },
  };

  savedFilters.value.push(newFilter);
  localStorage.setItem("trace_saved_filters", JSON.stringify(savedFilters.value));
  filterName.value = "";
  toast.success("Filter saved");
};

// Apply saved filter
const applySavedFilter = (filter: SavedFilter) => {
  filters.value = { ...filter.filters };
  page.value = 1;
  loadTraces();
};

// Delete saved filter
const deleteSavedFilter = (id: string) => {
  savedFilters.value = savedFilters.value.filter((f) => f.id !== id);
  localStorage.setItem("trace_saved_filters", JSON.stringify(savedFilters.value));
  toast.success("Filter deleted");
};

// Get time range date
const getTimeRangeDate = (range: string): Date | null => {
  const now = new Date();
  switch (range) {
    case "1h":
      return new Date(now.getTime() - 60 * 60 * 1000);
    case "24h":
      return new Date(now.getTime() - 24 * 60 * 60 * 1000);
    case "7d":
      return new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000);
    case "30d":
      return new Date(now.getTime() - 30 * 24 * 60 * 60 * 1000);
    default:
      return null;
  }
};

// Load traces
const loadTraces = async () => {
  loading.value = true;
  try {
    const { $api } = useNuxtApp();
    const params = new URLSearchParams();
    params.append("limit", String(limit.value));
    params.append("offset", String((page.value - 1) * limit.value));

    if (filters.value.span_name) {
      params.append("span_name", filters.value.span_name);
    }
    if (filters.value.success !== null) {
      params.append("success", String(filters.value.success));
    }
    if (filters.value.assistant_id) {
      params.append("assistant_id", filters.value.assistant_id);
    }

    const startDate = getTimeRangeDate(filters.value.time_range);
    if (startDate) {
      params.append("start_date", startDate.toISOString());
    }

    const response = await $api(`/v1/admin/traces?${params.toString()}`);
    const data = response as { items: Trace[]; total: number };
    traces.value = data.items;
    total.value = data.total;
  } catch (error) {
    console.error("Failed to load traces:", error);
    toast.error("Failed to load traces");
  } finally {
    loading.value = false;
  }
};

// Load stats
const loadStats = async () => {
  try {
    const { $api } = useNuxtApp();
    const params = new URLSearchParams();
    const startDate = getTimeRangeDate(filters.value.time_range);
    if (startDate) {
      params.append("start_date", startDate.toISOString());
    }
    const response = await $api(`/v1/admin/traces/stats?${params.toString()}`);
    stats.value = response as TraceStats;
  } catch (error) {
    console.error("Failed to load stats:", error);
  }
};

// Format date
const formatDate = (dateStr: string) => {
  return new Date(dateStr).toLocaleString();
};

// Format relative time
const formatRelativeTime = (dateStr: string) => {
  const date = new Date(dateStr);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMins = Math.floor(diffMs / 60000);
  const diffHours = Math.floor(diffMs / 3600000);
  const diffDays = Math.floor(diffMs / 86400000);

  if (diffMins < 1) return "just now";
  if (diffMins < 60) return `${diffMins}m ago`;
  if (diffHours < 24) return `${diffHours}h ago`;
  return `${diffDays}d ago`;
};

// Format latency
const formatLatency = (ms: number) => {
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(2)}s`;
};

// Get latency badge variant
const getLatencyBadge = (ms: number) => {
  if (ms < 500) return "default";
  if (ms < 2000) return "secondary";
  return "destructive";
};

// Get span type display
const getSpanTypeDisplay = (spanName: string) => {
  if (spanName.startsWith("tool_")) return { label: "Tool", variant: "default" as const };
  if (spanName.startsWith("agent_")) return { label: "Agent", variant: "secondary" as const };
  if (spanName.includes("llm") || spanName.includes("completion"))
    return { label: "LLM", variant: "outline" as const };
  return { label: spanName.split("_")[0], variant: "secondary" as const };
};

// Export traces to CSV
const handleExportCSV = async () => {
  if (!traces.value.length) {
    toast.error(t("admin.export.noData"));
    return;
  }

  const columns = [
    { key: "trace_id", label: "Trace ID" },
    { key: "span_name", label: "Span Name" },
    { key: "span_kind", label: "Span Kind" },
    { key: "success", label: "Success" },
    { key: "latency_ms", label: "Latency (ms)" },
    { key: "tokens_used", label: "Tokens" },
    { key: "cost_usd", label: "Cost (USD)" },
    { key: "start_time", label: "Start Time" },
    { key: "end_time", label: "End Time" },
    { key: "assistant_id", label: "Assistant ID" },
    { key: "user_id", label: "User ID" },
  ];

  await exportCSV(traces.value, { filename: `traces_${Date.now()}.csv`, columns });
  toast.success(t("admin.export.success"));
};

// Apply filters
const applyFilters = () => {
  page.value = 1;
  loadTraces();
  loadStats();
};

// Reset filters
const resetFilters = () => {
  filters.value = { span_name: "", success: null, assistant_id: "", time_range: "24h" };
  page.value = 1;
  loadTraces();
  loadStats();
};

// Navigate to trace detail
const viewTraceDetail = (traceId: string) => {
  router.push(`/admin/agent-traces/${traceId}`);
};

// Quick filter by status
const filterByStatus = (success: boolean) => {
  filters.value.success = success;
  applyFilters();
};

// Total pages
const totalPages = computed(() => Math.ceil(total.value / limit.value));

// Active filter count
const activeFilterCount = computed(() => {
  let count = 0;
  if (filters.value.span_name) count++;
  if (filters.value.success !== null) count++;
  if (filters.value.assistant_id) count++;
  if (filters.value.time_range !== "all") count++;
  return count;
});

// Error rate trend (mock - would need historical data)
const errorRateTrend = computed(() => {
  if (!stats.value) return null;
  // In a real implementation, compare with previous period
  return stats.value.success_rate >= 95 ? "up" : "down";
});

// Initialize filters from query params
const initFiltersFromQuery = () => {
  const query = route.query;
  if (query.assistant_id) {
    filters.value.assistant_id = String(query.assistant_id);
  }
  if (query.success !== undefined) {
    filters.value.success =
      query.success === "true" ? true : query.success === "false" ? false : null;
  }
  if (query.span_name) {
    filters.value.span_name = String(query.span_name);
  }
  if (query.time_range && ["1h", "24h", "7d", "30d", "all"].includes(String(query.time_range))) {
    filters.value.time_range = query.time_range as typeof filters.value.time_range;
  }
};

onMounted(() => {
  loadSavedFilters();
  initFiltersFromQuery();
  loadTraces();
  loadStats();
});
</script>

<template>
  <div class="container mx-auto space-y-6 py-6">
    <!-- Header -->
    <div class="flex items-center justify-between">
      <div>
        <h1 class="text-2xl font-bold">Agent Traces</h1>
        <p class="text-muted-foreground">
          View execution traces and performance metrics for agent operations
        </p>
      </div>
      <div class="flex items-center gap-2">
        <!-- Export Button -->
        <Button
          variant="outline"
          size="sm"
          @click="handleExportCSV"
          :disabled="exporting || loading"
        >
          <Download class="mr-2 h-4 w-4" />
          {{ t("admin.export.csv") }}
        </Button>

        <!-- Saved Filters Dropdown -->
        <DropdownMenu v-if="savedFilters.length > 0">
          <DropdownMenuTrigger as-child>
            <Button variant="outline" size="sm">
              <Bookmark class="mr-2 h-4 w-4" />
              Saved Filters
              <Badge variant="secondary" class="ml-2">{{ savedFilters.length }}</Badge>
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" class="w-56">
            <DropdownMenuLabel>Saved Filters</DropdownMenuLabel>
            <DropdownMenuSeparator />
            <DropdownMenuItem
              v-for="filter in savedFilters"
              :key="filter.id"
              class="flex justify-between"
            >
              <span class="flex-1 cursor-pointer" @click="applySavedFilter(filter)">
                {{ filter.name }}
              </span>
              <Button
                variant="ghost"
                size="icon"
                class="h-6 w-6"
                @click.stop="deleteSavedFilter(filter.id)"
              >
                <Trash2 class="h-3 w-3" />
              </Button>
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>

        <Button
          variant="outline"
          @click="
            loadTraces();
            loadStats();
          "
          :disabled="loading"
        >
          <RefreshCw class="mr-2 h-4 w-4" :class="{ 'animate-spin': loading }" />
          Refresh
        </Button>
      </div>
    </div>

    <!-- Stats Cards with Quick Actions -->
    <div v-if="stats" class="grid gap-4 md:grid-cols-5">
      <Card>
        <CardHeader class="pb-2">
          <CardDescription>Total Traces</CardDescription>
          <CardTitle class="text-2xl">{{ stats.total_traces.toLocaleString() }}</CardTitle>
        </CardHeader>
      </Card>
      <Card
        class="cursor-pointer transition-colors hover:border-green-500"
        @click="filterByStatus(true)"
      >
        <CardHeader class="pb-2">
          <div class="flex items-center justify-between">
            <CardDescription>Success Rate</CardDescription>
            <TrendingUp v-if="errorRateTrend === 'up'" class="h-4 w-4 text-green-500" />
            <TrendingDown v-else class="h-4 w-4 text-red-500" />
          </div>
          <CardTitle class="flex items-center gap-2 text-2xl">
            <span
              :class="
                stats.success_rate >= 95
                  ? 'text-green-600'
                  : stats.success_rate >= 80
                    ? 'text-yellow-600'
                    : 'text-red-600'
              "
            >
              {{ stats.success_rate.toFixed(1) }}%
            </span>
          </CardTitle>
        </CardHeader>
        <CardContent class="pt-0">
          <p class="text-muted-foreground text-xs">Click to view successful</p>
        </CardContent>
      </Card>
      <Card
        class="cursor-pointer transition-colors hover:border-red-500"
        @click="filterByStatus(false)"
      >
        <CardHeader class="pb-2">
          <CardDescription>Failed Traces</CardDescription>
          <CardTitle class="flex items-center gap-2 text-2xl">
            <AlertCircle
              v-if="stats.total_traces - stats.success_count > 0"
              class="h-5 w-5 text-red-500"
            />
            {{ (stats.total_traces - stats.success_count).toLocaleString() }}
          </CardTitle>
        </CardHeader>
        <CardContent class="pt-0">
          <p class="text-muted-foreground text-xs">Click to view failures</p>
        </CardContent>
      </Card>
      <Card>
        <CardHeader class="pb-2">
          <CardDescription>Avg Latency</CardDescription>
          <CardTitle class="text-2xl">
            <Badge :variant="getLatencyBadge(stats.avg_latency_ms)" class="text-base">
              {{ formatLatency(stats.avg_latency_ms) }}
            </Badge>
          </CardTitle>
        </CardHeader>
      </Card>
      <Card>
        <CardHeader class="pb-2">
          <CardDescription>Total Cost</CardDescription>
          <CardTitle class="flex items-center gap-1 text-2xl">
            <DollarSign class="h-5 w-5" />
            {{ stats.total_cost_usd.toFixed(4) }}
          </CardTitle>
        </CardHeader>
        <CardContent class="pt-0">
          <p class="text-muted-foreground text-xs">
            {{ stats.total_tokens.toLocaleString() }} tokens
          </p>
        </CardContent>
      </Card>
    </div>

    <!-- Filters -->
    <Card>
      <CardHeader class="pb-3">
        <div class="flex items-center justify-between">
          <CardTitle class="flex items-center gap-2 text-lg">
            <Filter class="h-5 w-5" />
            Filters
            <Badge v-if="activeFilterCount > 0" variant="secondary">
              {{ activeFilterCount }} active
            </Badge>
          </CardTitle>
        </div>
      </CardHeader>
      <CardContent>
        <div class="flex flex-wrap gap-4">
          <div class="space-y-2">
            <Label>Time Range</Label>
            <Select v-model="filters.time_range" @update:model-value="applyFilters">
              <SelectTrigger class="w-32">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="1h">Last Hour</SelectItem>
                <SelectItem value="24h">Last 24h</SelectItem>
                <SelectItem value="7d">Last 7 Days</SelectItem>
                <SelectItem value="30d">Last 30 Days</SelectItem>
                <SelectItem value="all">All Time</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div class="space-y-2">
            <Label>Span Name</Label>
            <Input
              v-model="filters.span_name"
              placeholder="e.g., tool_web_search"
              class="w-48"
              @keyup.enter="applyFilters"
            />
          </div>
          <div class="space-y-2">
            <Label>Status</Label>
            <Select
              :model-value="
                filters.success === null ? 'all' : filters.success ? 'success' : 'failed'
              "
              @update:model-value="
                (v: string) => {
                  filters.success = v === 'all' ? null : v === 'success';
                  applyFilters();
                }
              "
            >
              <SelectTrigger class="w-32">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All</SelectItem>
                <SelectItem value="success">Success</SelectItem>
                <SelectItem value="failed">Failed</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div class="space-y-2">
            <Label>Assistant ID</Label>
            <Input
              v-model="filters.assistant_id"
              placeholder="Filter by assistant"
              class="w-48"
              @keyup.enter="applyFilters"
            />
          </div>
          <div class="flex items-end gap-2">
            <Button @click="applyFilters">Apply</Button>
            <Button variant="outline" @click="resetFilters">Reset</Button>
          </div>
        </div>

        <!-- Save Filter -->
        <div class="mt-4 border-t pt-4">
          <div class="flex items-center gap-2">
            <Input
              v-model="filterName"
              placeholder="Filter name..."
              class="w-48"
              @keyup.enter="saveCurrentFilter"
            />
            <Button variant="outline" size="sm" @click="saveCurrentFilter">
              <Save class="mr-2 h-4 w-4" />
              Save Filter
            </Button>
          </div>
        </div>
      </CardContent>
    </Card>

    <!-- Loading state -->
    <div v-if="loading" class="flex justify-center py-12">
      <div class="border-primary h-8 w-8 animate-spin rounded-full border-b-2"></div>
    </div>

    <!-- Empty state -->
    <Card v-else-if="traces.length === 0" class="py-12 text-center">
      <CardContent>
        <Activity class="text-muted-foreground mx-auto mb-4 h-12 w-12" />
        <h3 class="text-lg font-medium">No Traces Found</h3>
        <p class="text-muted-foreground">Traces will appear here when agents execute tools.</p>
      </CardContent>
    </Card>

    <!-- Traces table -->
    <Card v-else>
      <CardContent class="pt-6">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead class="w-[60px]">Status</TableHead>
              <TableHead>Span</TableHead>
              <TableHead>Latency</TableHead>
              <TableHead>Tokens</TableHead>
              <TableHead>Cost</TableHead>
              <TableHead>Time</TableHead>
              <TableHead class="w-[80px]">Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            <TableRow
              v-for="trace in traces"
              :key="trace.id"
              class="hover:bg-muted/50 cursor-pointer transition-colors"
              @click="viewTraceDetail(trace.id)"
            >
              <TableCell>
                <div class="flex items-center gap-1">
                  <CheckCircle v-if="trace.success" class="h-5 w-5 text-green-500" />
                  <XCircle v-else class="h-5 w-5 text-red-500" />
                </div>
              </TableCell>
              <TableCell>
                <div class="flex items-center gap-2">
                  <Badge :variant="getSpanTypeDisplay(trace.span_name).variant" class="text-xs">
                    {{ getSpanTypeDisplay(trace.span_name).label }}
                  </Badge>
                  <div>
                    <div class="font-medium">{{ trace.span_name }}</div>
                    <div class="text-muted-foreground text-xs">{{ trace.span_kind }}</div>
                  </div>
                </div>
              </TableCell>
              <TableCell>
                <Badge :variant="getLatencyBadge(trace.latency_ms)">
                  <Clock class="mr-1 h-3 w-3" />
                  {{ formatLatency(trace.latency_ms) }}
                </Badge>
              </TableCell>
              <TableCell>
                <span class="tabular-nums">{{ trace.tokens_used?.toLocaleString() || "-" }}</span>
              </TableCell>
              <TableCell>
                <div v-if="trace.cost_usd" class="flex items-center gap-1 tabular-nums">
                  <DollarSign class="h-3 w-3" />
                  {{ trace.cost_usd.toFixed(4) }}
                </div>
                <span v-else class="text-muted-foreground">-</span>
              </TableCell>
              <TableCell>
                <div class="text-sm" :title="formatDate(trace.start_time)">
                  {{ formatRelativeTime(trace.start_time) }}
                </div>
              </TableCell>
              <TableCell>
                <Button variant="ghost" size="icon" @click.stop="viewTraceDetail(trace.id)">
                  <ExternalLink class="h-4 w-4" />
                </Button>
              </TableCell>
            </TableRow>
          </TableBody>
        </Table>

        <!-- Pagination -->
        <div class="mt-4 flex items-center justify-between">
          <div class="text-muted-foreground text-sm">
            Showing {{ (page - 1) * limit + 1 }} to {{ Math.min(page * limit, total) }} of
            {{ total }} traces
          </div>
          <div class="flex gap-2">
            <Button
              variant="outline"
              size="sm"
              :disabled="page === 1"
              @click="
                page--;
                loadTraces();
              "
            >
              Previous
            </Button>
            <Button
              variant="outline"
              size="sm"
              :disabled="page >= totalPages"
              @click="
                page++;
                loadTraces();
              "
            >
              Next
            </Button>
          </div>
        </div>
      </CardContent>
    </Card>
  </div>
</template>
