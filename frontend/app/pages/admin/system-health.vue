<script setup lang="ts">
import { ref, computed, onMounted } from "vue";
import {
  RefreshCw,
  Activity,
  AlertTriangle,
  CheckCircle,
  XCircle,
  Clock,
  DollarSign,
  Zap,
  TrendingUp,
  TrendingDown,
  Server,
  ExternalLink,
  AlertCircle,
} from "lucide-vue-next";
import { Button } from "~/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "~/components/ui/card";
import { Badge } from "~/components/ui/badge";
import { Progress } from "~/components/ui/progress";
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
import { toast } from "vue-sonner";

const { t } = useI18n();
const router = useRouter();

definePageMeta({
  breadcrumb: "System Health",
  layout: "admin",
});

interface TraceStats {
  total_traces: number;
  success_count: number;
  success_rate: number;
  avg_latency_ms: number;
  total_cost_usd: number;
  total_tokens: number;
}

interface CostPeriod {
  period: string;
  total_cost_usd: number;
  total_tokens: number;
  trace_count: number;
}

interface CostAnalytics {
  periods: CostPeriod[];
  total_cost_usd: number;
  total_tokens: number;
  start_date: string;
  end_date: string;
  group_by: string;
}

interface ToolAnalytics {
  tools: Array<{
    tool_name: string;
    call_count: number;
    success_rate: number;
    avg_latency_ms: number;
  }>;
  total_tool_calls: number;
}

interface FailedTrace {
  id: string;
  span_name: string;
  error_message?: string;
  latency_ms: number;
  start_time: string;
  assistant_id?: string;
}

// State
const loading = ref(true);
const stats = ref<TraceStats | null>(null);
const costAnalytics = ref<CostAnalytics | null>(null);
const toolAnalytics = ref<ToolAnalytics | null>(null);
const failedTraces = ref<FailedTrace[]>([]);
const timeRange = ref<"24h" | "7d" | "30d">("7d");

// Get time range date
const getTimeRangeDate = (range: string): Date => {
  const now = new Date();
  switch (range) {
    case "24h":
      return new Date(now.getTime() - 24 * 60 * 60 * 1000);
    case "7d":
      return new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000);
    case "30d":
      return new Date(now.getTime() - 30 * 24 * 60 * 60 * 1000);
    default:
      return new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000);
  }
};

// Load all data
const loadData = async () => {
  loading.value = true;
  try {
    const { $api } = useNuxtApp();
    const startDate = getTimeRangeDate(timeRange.value);
    const params = `start_date=${startDate.toISOString()}`;

    // Load all in parallel
    const [statsRes, costRes, toolRes, failedRes] = await Promise.all([
      $api(`/v1/admin/traces/stats?${params}`) as Promise<TraceStats>,
      $api(`/v1/admin/traces/analytics/cost?${params}&group_by=day`) as Promise<CostAnalytics>,
      $api(`/v1/admin/traces/analytics/tools?${params}`) as Promise<ToolAnalytics>,
      $api(`/v1/admin/traces?success=false&limit=10&${params}`) as Promise<{
        items: FailedTrace[];
        total: number;
      }>,
    ]);

    stats.value = statsRes;
    costAnalytics.value = costRes;
    toolAnalytics.value = toolRes;
    failedTraces.value = failedRes.items;
  } catch (error) {
    console.error("Failed to load health data:", error);
    toast.error("Failed to load system health data");
  } finally {
    loading.value = false;
  }
};

// Format latency
const formatLatency = (ms: number) => {
  if (ms < 1000) return `${Math.round(ms)}ms`;
  return `${(ms / 1000).toFixed(2)}s`;
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

// Get health status
const healthStatus = computed(() => {
  if (!stats.value) return { status: "unknown", color: "gray" };
  // Show "No Data" when there are no traces at all
  if (stats.value.total_traces === 0) return { status: "No Data", color: "gray" };
  if (stats.value.success_rate >= 99) return { status: "Excellent", color: "green" };
  if (stats.value.success_rate >= 95) return { status: "Good", color: "green" };
  if (stats.value.success_rate >= 90) return { status: "Fair", color: "yellow" };
  if (stats.value.success_rate >= 80) return { status: "Degraded", color: "orange" };
  return { status: "Critical", color: "red" };
});

// Get latency status
const latencyStatus = computed(() => {
  if (!stats.value) return { status: "unknown", color: "gray" };
  const ms = stats.value.avg_latency_ms;
  if (ms < 500) return { status: "Fast", color: "green" };
  if (ms < 1000) return { status: "Normal", color: "green" };
  if (ms < 2000) return { status: "Slow", color: "yellow" };
  return { status: "Critical", color: "red" };
});

// Cost trend (simple calculation)
const costTrend = computed(() => {
  if (!costAnalytics.value || costAnalytics.value.periods.length < 2) return null;
  const periods = costAnalytics.value.periods;
  const recent = periods.slice(-7).reduce((sum, p) => sum + p.total_cost_usd, 0);
  const earlier = periods.slice(0, 7).reduce((sum, p) => sum + p.total_cost_usd, 0);
  if (earlier === 0) return null;
  const change = ((recent - earlier) / earlier) * 100;
  return { change: change.toFixed(1), increasing: change > 0 };
});

// Max cost for bar chart
const maxCost = computed(() => {
  if (!costAnalytics.value) return 0;
  return Math.max(...costAnalytics.value.periods.map((p) => p.total_cost_usd), 0.001);
});

// Navigate to trace
const viewTrace = (id: string) => {
  router.push(`/admin/agent-traces/${id}`);
};

// Navigate to all failed traces
const viewAllFailed = () => {
  router.push("/admin/agent-traces?success=false");
};

onMounted(() => {
  loadData();
});

// Watch time range changes
watch(timeRange, () => {
  loadData();
});
</script>

<template>
  <div class="w-full space-y-6 py-6">
    <!-- Header -->
    <div class="flex items-center justify-between">
      <div>
        <h1 class="text-2xl font-bold">System Health</h1>
        <p class="text-muted-foreground">
          Monitor agent performance, costs, and system health metrics
        </p>
      </div>
      <div class="flex items-center gap-3">
        <Select v-model="timeRange">
          <SelectTrigger class="w-32">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="24h">Last 24h</SelectItem>
            <SelectItem value="7d">Last 7 Days</SelectItem>
            <SelectItem value="30d">Last 30 Days</SelectItem>
          </SelectContent>
        </Select>
        <Button variant="outline" @click="loadData" :disabled="loading">
          <RefreshCw class="mr-2 h-4 w-4" :class="{ 'animate-spin': loading }" />
          Refresh
        </Button>
      </div>
    </div>

    <!-- Loading state -->
    <div v-if="loading" class="flex justify-center py-12">
      <div class="border-primary h-8 w-8 animate-spin rounded-full border-b-2"></div>
    </div>

    <template v-else-if="stats">
      <!-- Health Overview Cards -->
      <div class="grid gap-4 md:grid-cols-4">
        <!-- Overall Health -->
        <Card
          :class="{
            'border-green-500': healthStatus.color === 'green',
            'border-yellow-500': healthStatus.color === 'yellow',
            'border-orange-500': healthStatus.color === 'orange',
            'border-red-500': healthStatus.color === 'red',
            'border-gray-400': healthStatus.color === 'gray',
          }"
        >
          <CardHeader class="pb-2">
            <CardDescription>System Health</CardDescription>
            <CardTitle class="flex items-center gap-2 text-2xl">
              <CheckCircle v-if="healthStatus.color === 'green'" class="h-6 w-6 text-green-500" />
              <AlertTriangle
                v-else-if="healthStatus.color === 'yellow' || healthStatus.color === 'orange'"
                class="h-6 w-6 text-yellow-500"
              />
              <AlertCircle
                v-else-if="healthStatus.color === 'gray'"
                class="h-6 w-6 text-gray-400"
              />
              <XCircle v-else class="h-6 w-6 text-red-500" />
              {{ healthStatus.status }}
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div v-if="stats.total_traces > 0" class="flex items-center gap-2">
              <Progress :model-value="stats.success_rate" class="flex-1" />
              <span class="text-sm font-medium">{{ stats.success_rate.toFixed(1) }}%</span>
            </div>
            <p v-else class="text-muted-foreground text-sm">No agent traces recorded yet</p>
          </CardContent>
        </Card>

        <!-- Latency -->
        <Card>
          <CardHeader class="pb-2">
            <CardDescription>Avg Response Time</CardDescription>
            <CardTitle class="flex items-center gap-2 text-2xl">
              <Clock class="h-6 w-6 text-blue-500" />
              {{ formatLatency(stats.avg_latency_ms) }}
            </CardTitle>
          </CardHeader>
          <CardContent>
            <Badge
              :variant="
                latencyStatus.color === 'green'
                  ? 'default'
                  : latencyStatus.color === 'yellow'
                    ? 'secondary'
                    : 'destructive'
              "
            >
              {{ latencyStatus.status }}
            </Badge>
          </CardContent>
        </Card>

        <!-- Total Cost -->
        <Card>
          <CardHeader class="pb-2">
            <CardDescription>Total Cost</CardDescription>
            <CardTitle class="flex items-center gap-2 text-2xl">
              <DollarSign class="h-6 w-6 text-green-600" />
              {{ stats.total_cost_usd.toFixed(2) }}
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div v-if="costTrend" class="flex items-center gap-1 text-sm">
              <TrendingUp v-if="costTrend.increasing" class="h-4 w-4 text-red-500" />
              <TrendingDown v-else class="h-4 w-4 text-green-500" />
              <span :class="costTrend.increasing ? 'text-red-500' : 'text-green-500'">
                {{ costTrend.change }}% vs previous period
              </span>
            </div>
            <span v-else class="text-muted-foreground text-sm"
              >{{ stats.total_tokens.toLocaleString() }} tokens</span
            >
          </CardContent>
        </Card>

        <!-- Error Count -->
        <Card class="cursor-pointer transition-colors hover:border-red-500" @click="viewAllFailed">
          <CardHeader class="pb-2">
            <CardDescription>Failed Traces</CardDescription>
            <CardTitle class="flex items-center gap-2 text-2xl">
              <AlertCircle
                v-if="stats.total_traces - stats.success_count > 0"
                class="h-6 w-6 text-red-500"
              />
              <CheckCircle v-else class="h-6 w-6 text-green-500" />
              {{ (stats.total_traces - stats.success_count).toLocaleString() }}
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p class="text-muted-foreground text-sm">
              of {{ stats.total_traces.toLocaleString() }} total
            </p>
          </CardContent>
        </Card>
      </div>

      <div class="grid gap-6 lg:grid-cols-2">
        <!-- Cost Over Time Chart -->
        <Card>
          <CardHeader>
            <CardTitle class="flex items-center gap-2">
              <DollarSign class="h-5 w-5" />
              Cost Trend
            </CardTitle>
            <CardDescription>Daily cost breakdown</CardDescription>
          </CardHeader>
          <CardContent>
            <div v-if="costAnalytics && costAnalytics.periods.length > 0" class="space-y-4">
              <div class="flex h-[200px] items-end gap-1">
                <div
                  v-for="(period, idx) in costAnalytics.periods"
                  :key="idx"
                  class="group relative flex-1"
                >
                  <div
                    class="w-full rounded-t-sm bg-green-500/70 transition-colors hover:bg-green-500"
                    :style="{ height: `${Math.max(4, (period.total_cost_usd / maxCost) * 100)}%` }"
                  ></div>
                  <!-- Tooltip -->
                  <div
                    class="bg-popover text-popover-foreground absolute bottom-full left-1/2 z-10 mb-2 hidden -translate-x-1/2 rounded border p-2 text-xs whitespace-nowrap shadow-md group-hover:block"
                  >
                    <div class="font-bold">{{ period.period }}</div>
                    <div>Cost: ${{ period.total_cost_usd.toFixed(4) }}</div>
                    <div>Tokens: {{ period.total_tokens.toLocaleString() }}</div>
                    <div>Traces: {{ period.trace_count }}</div>
                  </div>
                </div>
              </div>
              <div class="text-muted-foreground flex justify-between text-xs">
                <span>{{ costAnalytics.periods[0]?.period }}</span>
                <span>{{ costAnalytics.periods[costAnalytics.periods.length - 1]?.period }}</span>
              </div>
            </div>
            <div v-else class="text-muted-foreground flex h-[200px] items-center justify-center">
              No cost data available
            </div>
          </CardContent>
        </Card>

        <!-- Tool Performance -->
        <Card>
          <CardHeader>
            <CardTitle class="flex items-center gap-2">
              <Zap class="h-5 w-5" />
              Tool Performance
            </CardTitle>
            <CardDescription>Success rates and latency by tool</CardDescription>
          </CardHeader>
          <CardContent>
            <div v-if="toolAnalytics && toolAnalytics.tools.length > 0" class="space-y-3">
              <div
                v-for="tool in toolAnalytics.tools.slice(0, 6)"
                :key="tool.tool_name"
                class="flex items-center gap-3"
              >
                <div class="min-w-0 flex-1">
                  <div class="flex items-center justify-between">
                    <span class="truncate text-sm font-medium">{{ tool.tool_name }}</span>
                    <span class="text-muted-foreground text-xs">{{ tool.call_count }} calls</span>
                  </div>
                  <div class="mt-1 flex items-center gap-2">
                    <Progress :model-value="tool.success_rate" class="h-2 flex-1" />
                    <span class="w-12 text-right text-xs">{{ tool.success_rate.toFixed(0) }}%</span>
                  </div>
                </div>
                <Badge variant="outline" class="shrink-0">
                  {{ formatLatency(tool.avg_latency_ms) }}
                </Badge>
              </div>
            </div>
            <div v-else class="text-muted-foreground flex h-[200px] items-center justify-center">
              No tool data available
            </div>
          </CardContent>
        </Card>
      </div>

      <!-- Recent Failures -->
      <Card>
        <CardHeader>
          <div class="flex items-center justify-between">
            <div>
              <CardTitle class="flex items-center gap-2">
                <AlertTriangle class="h-5 w-5 text-red-500" />
                Recent Failures
              </CardTitle>
              <CardDescription>Quick access to failed traces for debugging</CardDescription>
            </div>
            <Button variant="outline" size="sm" @click="viewAllFailed">
              View All
              <ExternalLink class="ml-2 h-4 w-4" />
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          <div v-if="failedTraces.length > 0">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Span</TableHead>
                  <TableHead>Error</TableHead>
                  <TableHead>Latency</TableHead>
                  <TableHead>Time</TableHead>
                  <TableHead class="w-[60px]"></TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                <TableRow
                  v-for="trace in failedTraces"
                  :key="trace.id"
                  class="hover:bg-muted/50 cursor-pointer"
                  @click="viewTrace(trace.id)"
                >
                  <TableCell>
                    <div class="flex items-center gap-2">
                      <XCircle class="h-4 w-4 shrink-0 text-red-500" />
                      <span class="font-medium">{{ trace.span_name }}</span>
                    </div>
                  </TableCell>
                  <TableCell>
                    <span class="text-muted-foreground line-clamp-1 text-sm">
                      {{ trace.error_message || "No error message" }}
                    </span>
                  </TableCell>
                  <TableCell>
                    <Badge variant="secondary">{{ formatLatency(trace.latency_ms) }}</Badge>
                  </TableCell>
                  <TableCell>
                    <span class="text-muted-foreground text-sm">{{
                      formatRelativeTime(trace.start_time)
                    }}</span>
                  </TableCell>
                  <TableCell>
                    <Button variant="ghost" size="icon" @click.stop="viewTrace(trace.id)">
                      <ExternalLink class="h-4 w-4" />
                    </Button>
                  </TableCell>
                </TableRow>
              </TableBody>
            </Table>
          </div>
          <div v-else class="flex flex-col items-center justify-center py-12 text-center">
            <CheckCircle class="mb-4 h-12 w-12 text-green-500" />
            <h3 class="text-lg font-medium">No Recent Failures</h3>
            <p class="text-muted-foreground">All agent executions are running smoothly.</p>
          </div>
        </CardContent>
      </Card>
    </template>
  </div>
</template>
