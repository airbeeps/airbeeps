<script setup lang="ts">
import { ref, computed, onMounted } from "vue";
import {
  ArrowLeft,
  CheckCircle,
  XCircle,
  Clock,
  DollarSign,
  ChevronRight,
  ChevronDown,
  Play,
  Copy,
  ExternalLink,
  AlertTriangle,
  Eye,
  EyeOff,
} from "lucide-vue-next";
import { Button } from "~/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "~/components/ui/card";
import { Badge } from "~/components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "~/components/ui/tabs";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "~/components/ui/collapsible";
import { toast } from "vue-sonner";

const { t } = useI18n();
const route = useRoute();
const router = useRouter();

definePageMeta({
  breadcrumb: "Trace Detail",
  layout: "admin",
});

interface TraceSpan {
  id: string;
  trace_id: string;
  span_id: string;
  parent_span_id: string | null;
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
  attributes?: Record<string, any>;
  events?: Array<{ name: string; timestamp: number; attributes: Record<string, any> }>;
  error_message?: string;
  created_at: string;
}

interface SpanTreeNode extends TraceSpan {
  children: SpanTreeNode[];
  depth: number;
  offsetPercent: number;
  widthPercent: number;
}

// State
const trace = ref<TraceSpan | null>(null);
const allSpans = ref<TraceSpan[]>([]);
const loading = ref(true);
const expandedSpans = ref<Set<string>>(new Set());
const selectedSpan = ref<TraceSpan | null>(null);
const showRedacted = ref(true);

// Load trace details
const loadTrace = async () => {
  loading.value = true;
  try {
    const { $api } = useNuxtApp();
    const traceId = route.params.id as string;

    // Get single trace first
    const response = (await $api(`/v1/admin/traces/${traceId}`)) as TraceSpan;
    trace.value = response;

    // Get all spans in this trace (by OTel trace_id)
    if (response.trace_id) {
      const spansResponse = (await $api(
        `/v1/admin/traces/otel/${response.trace_id}`
      )) as TraceSpan[];
      allSpans.value = spansResponse;
      // Expand root spans by default
      spansResponse
        .filter((s) => !s.parent_span_id)
        .forEach((s) => expandedSpans.value.add(s.span_id));
      // Select the root span
      selectedSpan.value = spansResponse.find((s) => !s.parent_span_id) || spansResponse[0] || null;
    } else {
      allSpans.value = [response];
      selectedSpan.value = response;
    }
  } catch (error) {
    console.error("Failed to load trace:", error);
    toast.error("Failed to load trace details");
  } finally {
    loading.value = false;
  }
};

// Build span tree
const spanTree = computed<SpanTreeNode[]>(() => {
  if (!allSpans.value.length) return [];

  const spanMap = new Map<string, SpanTreeNode>();
  const rootSpans: SpanTreeNode[] = [];

  // Calculate time bounds
  const minTime = Math.min(...allSpans.value.map((s) => new Date(s.start_time).getTime()));
  const maxTime = Math.max(...allSpans.value.map((s) => new Date(s.end_time).getTime()));
  const totalDuration = maxTime - minTime || 1;

  // Create nodes with timing info
  allSpans.value.forEach((span) => {
    const startMs = new Date(span.start_time).getTime();
    const endMs = new Date(span.end_time).getTime();

    spanMap.set(span.span_id, {
      ...span,
      children: [],
      depth: 0,
      offsetPercent: ((startMs - minTime) / totalDuration) * 100,
      widthPercent: Math.max(2, ((endMs - startMs) / totalDuration) * 100),
    });
  });

  // Build tree structure
  spanMap.forEach((node) => {
    if (node.parent_span_id && spanMap.has(node.parent_span_id)) {
      const parent = spanMap.get(node.parent_span_id)!;
      parent.children.push(node);
      node.depth = parent.depth + 1;
    } else {
      rootSpans.push(node);
    }
  });

  // Sort children by start time
  const sortChildren = (nodes: SpanTreeNode[]) => {
    nodes.sort((a, b) => new Date(a.start_time).getTime() - new Date(b.start_time).getTime());
    nodes.forEach((n) => sortChildren(n.children));
  };
  sortChildren(rootSpans);

  return rootSpans;
});

// Flatten tree for rendering
const flattenedSpans = computed<SpanTreeNode[]>(() => {
  const result: SpanTreeNode[] = [];

  const traverse = (nodes: SpanTreeNode[]) => {
    nodes.forEach((node) => {
      result.push(node);
      if (expandedSpans.value.has(node.span_id)) {
        traverse(node.children);
      }
    });
  };

  traverse(spanTree.value);
  return result;
});

// Toggle span expansion
const toggleSpan = (spanId: string) => {
  if (expandedSpans.value.has(spanId)) {
    expandedSpans.value.delete(spanId);
  } else {
    expandedSpans.value.add(spanId);
  }
};

// Select span for detail view
const selectSpan = (span: TraceSpan) => {
  selectedSpan.value = span;
};

// Format date
const formatDate = (dateStr: string) => {
  return new Date(dateStr).toLocaleString();
};

// Format latency
const formatLatency = (ms: number) => {
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(2)}s`;
};

// Get span type badge color
const getSpanBadgeVariant = (spanName: string) => {
  if (spanName.startsWith("tool_")) return "default";
  if (spanName.startsWith("agent_")) return "secondary";
  if (spanName.includes("llm") || spanName.includes("completion")) return "outline";
  return "secondary";
};

// Copy to clipboard
const copyToClipboard = async (text: string) => {
  try {
    await navigator.clipboard.writeText(text);
    toast.success("Copied to clipboard");
  } catch {
    toast.error("Failed to copy");
  }
};

// Format JSON for display
const formatJson = (obj: any): string => {
  try {
    return JSON.stringify(obj, null, 2);
  } catch {
    return String(obj);
  }
};

// Check if value looks redacted
const isRedacted = (value: any): boolean => {
  if (typeof value === "string") {
    return value.includes("[REDACTED");
  }
  return false;
};

// Get tool input/output from attributes
const toolData = computed(() => {
  if (!selectedSpan.value?.attributes) return null;
  const attrs = selectedSpan.value.attributes;
  return {
    input: attrs["tool.input"] || attrs["llm.prompt"] || attrs["input"],
    output: attrs["tool.output"] || attrs["llm.response"] || attrs["output"],
    model: attrs["llm.model"],
    tokens: {
      prompt: attrs["llm.prompt_tokens"],
      completion: attrs["llm.completion_tokens"],
      total: attrs["llm.total_tokens"],
    },
  };
});

onMounted(() => {
  loadTrace();
});
</script>

<template>
  <div class="container mx-auto space-y-6 py-6">
    <!-- Header -->
    <div class="flex items-center gap-4">
      <Button variant="ghost" size="icon" @click="router.back()">
        <ArrowLeft class="h-5 w-5" />
      </Button>
      <div class="flex-1">
        <h1 class="text-2xl font-bold">Trace Detail</h1>
        <p v-if="trace" class="text-muted-foreground font-mono text-sm">
          {{ trace.trace_id }}
        </p>
      </div>
      <div class="flex items-center gap-2">
        <Button variant="outline" size="sm" @click="showRedacted = !showRedacted">
          <Eye v-if="showRedacted" class="mr-2 h-4 w-4" />
          <EyeOff v-else class="mr-2 h-4 w-4" />
          {{ showRedacted ? "Show Redacted" : "Hide Redacted" }}
        </Button>
      </div>
    </div>

    <!-- Loading state -->
    <div v-if="loading" class="flex justify-center py-12">
      <div class="border-primary h-8 w-8 animate-spin rounded-full border-b-2"></div>
    </div>

    <template v-else-if="trace">
      <!-- Summary Cards -->
      <div class="grid gap-4 md:grid-cols-5">
        <Card>
          <CardHeader class="pb-2">
            <CardDescription>Status</CardDescription>
          </CardHeader>
          <CardContent>
            <div class="flex items-center gap-2">
              <CheckCircle v-if="trace.success" class="h-5 w-5 text-green-500" />
              <XCircle v-else class="h-5 w-5 text-red-500" />
              <span class="font-medium">{{ trace.success ? "Success" : "Failed" }}</span>
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader class="pb-2">
            <CardDescription>Duration</CardDescription>
          </CardHeader>
          <CardContent>
            <div class="flex items-center gap-2">
              <Clock class="h-5 w-5 text-blue-500" />
              <span class="text-xl font-bold">{{ formatLatency(trace.latency_ms) }}</span>
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader class="pb-2">
            <CardDescription>Spans</CardDescription>
          </CardHeader>
          <CardContent>
            <span class="text-xl font-bold">{{ allSpans.length }}</span>
          </CardContent>
        </Card>
        <Card>
          <CardHeader class="pb-2">
            <CardDescription>Tokens</CardDescription>
          </CardHeader>
          <CardContent>
            <span class="text-xl font-bold">
              {{ allSpans.reduce((sum, s) => sum + (s.tokens_used || 0), 0).toLocaleString() }}
            </span>
          </CardContent>
        </Card>
        <Card>
          <CardHeader class="pb-2">
            <CardDescription>Cost</CardDescription>
          </CardHeader>
          <CardContent>
            <div class="flex items-center gap-1">
              <DollarSign class="h-4 w-4" />
              <span class="text-xl font-bold">
                {{ allSpans.reduce((sum, s) => sum + (s.cost_usd || 0), 0).toFixed(4) }}
              </span>
            </div>
          </CardContent>
        </Card>
      </div>

      <!-- Error Alert -->
      <Card v-if="trace.error_message" class="border-destructive">
        <CardHeader class="pb-2">
          <div class="flex items-center gap-2">
            <AlertTriangle class="text-destructive h-5 w-5" />
            <CardTitle class="text-destructive">Error</CardTitle>
          </div>
        </CardHeader>
        <CardContent>
          <pre class="text-destructive text-sm whitespace-pre-wrap">{{ trace.error_message }}</pre>
        </CardContent>
      </Card>

      <!-- Main Content -->
      <div class="grid gap-6 lg:grid-cols-2">
        <!-- Left: Span Tree / Waterfall -->
        <Card>
          <CardHeader>
            <CardTitle>Trace Timeline</CardTitle>
            <CardDescription>Click a span to view details</CardDescription>
          </CardHeader>
          <CardContent>
            <div class="space-y-1">
              <div
                v-for="span in flattenedSpans"
                :key="span.id"
                class="group cursor-pointer"
                @click="selectSpan(span)"
              >
                <div
                  class="hover:bg-muted flex items-center gap-2 rounded-md p-2 transition-colors"
                  :class="{ 'bg-muted': selectedSpan?.id === span.id }"
                  :style="{ paddingLeft: `${span.depth * 20 + 8}px` }"
                >
                  <!-- Expand/Collapse -->
                  <button
                    v-if="span.children.length > 0"
                    class="text-muted-foreground hover:text-foreground shrink-0"
                    @click.stop="toggleSpan(span.span_id)"
                  >
                    <ChevronDown v-if="expandedSpans.has(span.span_id)" class="h-4 w-4" />
                    <ChevronRight v-else class="h-4 w-4" />
                  </button>
                  <div v-else class="w-4"></div>

                  <!-- Status icon -->
                  <CheckCircle v-if="span.success" class="h-4 w-4 shrink-0 text-green-500" />
                  <XCircle v-else class="h-4 w-4 shrink-0 text-red-500" />

                  <!-- Span name -->
                  <div class="min-w-0 flex-1">
                    <div class="flex items-center gap-2">
                      <Badge :variant="getSpanBadgeVariant(span.span_name)" class="text-xs">
                        {{ span.span_kind }}
                      </Badge>
                      <span class="truncate text-sm font-medium">{{ span.span_name }}</span>
                    </div>
                  </div>

                  <!-- Latency -->
                  <span class="text-muted-foreground shrink-0 text-xs">
                    {{ formatLatency(span.latency_ms) }}
                  </span>
                </div>

                <!-- Timing bar (waterfall) -->
                <div class="relative ml-8 h-2">
                  <div class="bg-muted absolute inset-0 rounded-full opacity-50"></div>
                  <div
                    class="absolute top-0 h-full rounded-full"
                    :class="span.success ? 'bg-primary' : 'bg-destructive'"
                    :style="{
                      left: `${span.offsetPercent}%`,
                      width: `${span.widthPercent}%`,
                    }"
                  ></div>
                </div>
              </div>
            </div>
          </CardContent>
        </Card>

        <!-- Right: Span Details -->
        <Card v-if="selectedSpan">
          <CardHeader>
            <div class="flex items-center justify-between">
              <div>
                <CardTitle class="flex items-center gap-2">
                  {{ selectedSpan.span_name }}
                  <CheckCircle v-if="selectedSpan.success" class="h-5 w-5 text-green-500" />
                  <XCircle v-else class="h-5 w-5 text-red-500" />
                </CardTitle>
                <CardDescription>
                  {{ formatDate(selectedSpan.start_time) }} -
                  {{ formatLatency(selectedSpan.latency_ms) }}
                </CardDescription>
              </div>
              <Button variant="ghost" size="icon" @click="copyToClipboard(selectedSpan.span_id)">
                <Copy class="h-4 w-4" />
              </Button>
            </div>
          </CardHeader>
          <CardContent>
            <Tabs default-value="details" class="w-full">
              <TabsList class="grid w-full grid-cols-3">
                <TabsTrigger value="details">Details</TabsTrigger>
                <TabsTrigger value="io">Input/Output</TabsTrigger>
                <TabsTrigger value="events">Events</TabsTrigger>
              </TabsList>

              <!-- Details Tab -->
              <TabsContent value="details" class="space-y-4">
                <div class="grid gap-3">
                  <div class="flex justify-between border-b py-2">
                    <span class="text-muted-foreground">Span ID</span>
                    <code class="text-xs">{{ selectedSpan.span_id }}</code>
                  </div>
                  <div
                    v-if="selectedSpan.parent_span_id"
                    class="flex justify-between border-b py-2"
                  >
                    <span class="text-muted-foreground">Parent Span</span>
                    <code class="text-xs">{{ selectedSpan.parent_span_id }}</code>
                  </div>
                  <div class="flex justify-between border-b py-2">
                    <span class="text-muted-foreground">Kind</span>
                    <Badge variant="outline">{{ selectedSpan.span_kind }}</Badge>
                  </div>
                  <div class="flex justify-between border-b py-2">
                    <span class="text-muted-foreground">Status</span>
                    <Badge :variant="selectedSpan.success ? 'default' : 'destructive'">
                      {{ selectedSpan.status_code }}
                    </Badge>
                  </div>
                  <div v-if="selectedSpan.tokens_used" class="flex justify-between border-b py-2">
                    <span class="text-muted-foreground">Tokens</span>
                    <span>{{ selectedSpan.tokens_used.toLocaleString() }}</span>
                  </div>
                  <div v-if="selectedSpan.cost_usd" class="flex justify-between border-b py-2">
                    <span class="text-muted-foreground">Cost</span>
                    <span>${{ selectedSpan.cost_usd.toFixed(4) }}</span>
                  </div>
                  <div v-if="selectedSpan.assistant_id" class="flex justify-between border-b py-2">
                    <span class="text-muted-foreground">Assistant</span>
                    <NuxtLink
                      :to="`/admin/assistants/${selectedSpan.assistant_id}`"
                      class="text-primary flex items-center gap-1 hover:underline"
                    >
                      View <ExternalLink class="h-3 w-3" />
                    </NuxtLink>
                  </div>
                  <div
                    v-if="selectedSpan.conversation_id"
                    class="flex justify-between border-b py-2"
                  >
                    <span class="text-muted-foreground">Conversation</span>
                    <code class="text-xs">{{ selectedSpan.conversation_id }}</code>
                  </div>
                </div>

                <!-- Error message -->
                <div v-if="selectedSpan.error_message" class="space-y-2">
                  <h4 class="text-destructive font-medium">Error Message</h4>
                  <pre
                    class="bg-destructive/10 text-destructive rounded-md p-3 text-sm whitespace-pre-wrap"
                    >{{ selectedSpan.error_message }}</pre
                  >
                </div>
              </TabsContent>

              <!-- Input/Output Tab -->
              <TabsContent value="io" class="space-y-4">
                <template v-if="toolData">
                  <!-- Model info -->
                  <div v-if="toolData.model" class="mb-4">
                    <Badge variant="outline">{{ toolData.model }}</Badge>
                    <span v-if="toolData.tokens.total" class="text-muted-foreground ml-2 text-sm">
                      {{ toolData.tokens.prompt }} prompt +
                      {{ toolData.tokens.completion }} completion
                    </span>
                  </div>

                  <!-- Input -->
                  <div v-if="toolData.input" class="space-y-2">
                    <div class="flex items-center justify-between">
                      <h4 class="font-medium">Input</h4>
                      <Button
                        variant="ghost"
                        size="sm"
                        @click="copyToClipboard(formatJson(toolData.input))"
                      >
                        <Copy class="mr-1 h-3 w-3" /> Copy
                      </Button>
                    </div>
                    <pre
                      class="bg-muted max-h-[200px] overflow-auto rounded-md p-3 text-sm"
                      :class="{ 'opacity-50': !showRedacted && isRedacted(toolData.input) }"
                      >{{ formatJson(toolData.input) }}</pre
                    >
                  </div>

                  <!-- Output -->
                  <div v-if="toolData.output" class="space-y-2">
                    <div class="flex items-center justify-between">
                      <h4 class="font-medium">Output</h4>
                      <Button
                        variant="ghost"
                        size="sm"
                        @click="copyToClipboard(formatJson(toolData.output))"
                      >
                        <Copy class="mr-1 h-3 w-3" /> Copy
                      </Button>
                    </div>
                    <pre
                      class="bg-muted max-h-[200px] overflow-auto rounded-md p-3 text-sm"
                      :class="{ 'opacity-50': !showRedacted && isRedacted(toolData.output) }"
                      >{{ formatJson(toolData.output) }}</pre
                    >
                  </div>
                </template>

                <!-- All attributes -->
                <div v-if="selectedSpan.attributes" class="space-y-2">
                  <h4 class="font-medium">All Attributes</h4>
                  <pre class="bg-muted max-h-[300px] overflow-auto rounded-md p-3 text-sm">{{
                    formatJson(selectedSpan.attributes)
                  }}</pre>
                </div>

                <div
                  v-if="!toolData?.input && !toolData?.output && !selectedSpan.attributes"
                  class="text-muted-foreground py-8 text-center"
                >
                  No input/output data available for this span.
                </div>
              </TabsContent>

              <!-- Events Tab -->
              <TabsContent value="events" class="space-y-4">
                <div v-if="selectedSpan.events?.length" class="space-y-3">
                  <div
                    v-for="(event, idx) in selectedSpan.events"
                    :key="idx"
                    class="border-primary/50 border-l-2 pl-4"
                  >
                    <div class="flex items-center justify-between">
                      <span class="font-medium">{{ event.name }}</span>
                      <span class="text-muted-foreground text-xs">
                        {{
                          event.timestamp
                            ? new Date(event.timestamp * 1000).toLocaleTimeString()
                            : ""
                        }}
                      </span>
                    </div>
                    <pre
                      v-if="Object.keys(event.attributes || {}).length"
                      class="bg-muted mt-2 rounded-md p-2 text-xs"
                      >{{ formatJson(event.attributes) }}</pre
                    >
                  </div>
                </div>
                <div v-else class="text-muted-foreground py-8 text-center">
                  No events recorded for this span.
                </div>
              </TabsContent>
            </Tabs>
          </CardContent>
        </Card>
      </div>

      <!-- Context Links -->
      <Card v-if="trace.assistant_id || trace.conversation_id || trace.user_id">
        <CardHeader>
          <CardTitle>Related Resources</CardTitle>
        </CardHeader>
        <CardContent>
          <div class="flex flex-wrap gap-3">
            <Button v-if="trace.assistant_id" variant="outline" as-child>
              <NuxtLink :to="`/admin/assistants/${trace.assistant_id}`">
                View Assistant
                <ExternalLink class="ml-2 h-4 w-4" />
              </NuxtLink>
            </Button>
            <Button v-if="trace.user_id" variant="outline" as-child>
              <NuxtLink :to="`/admin/users/${trace.user_id}`">
                View User
                <ExternalLink class="ml-2 h-4 w-4" />
              </NuxtLink>
            </Button>
            <Button
              v-if="trace.conversation_id"
              variant="outline"
              @click="copyToClipboard(trace.conversation_id!)"
            >
              Copy Conversation ID
              <Copy class="ml-2 h-4 w-4" />
            </Button>
          </div>
        </CardContent>
      </Card>
    </template>
  </div>
</template>
