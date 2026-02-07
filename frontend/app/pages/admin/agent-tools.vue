<script setup lang="ts">
import { ref, computed, onMounted } from "vue";
import {
  RefreshCw,
  Wrench,
  Shield,
  ShieldAlert,
  ShieldOff,
  Play,
  Search,
  Filter,
} from "lucide-vue-next";
import { Button } from "~/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "~/components/ui/card";
import { Badge } from "~/components/ui/badge";
import { Input } from "~/components/ui/input";
import { Textarea } from "~/components/ui/textarea";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "~/components/ui/dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "~/components/ui/select";
import { toast } from "vue-sonner";

const { t } = useI18n();

definePageMeta({
  breadcrumb: "Agent Tools",
  layout: "admin",
});

interface Tool {
  name: string;
  description: string;
  security_level?: "safe" | "moderate" | "dangerous";
  source?: "local" | "mcp";
  parameters?: Record<string, any>;
}

// State
const tools = ref<Tool[]>([]);
const loading = ref(true);

// Filter state
const searchQuery = ref("");
const securityFilter = ref<string>("all");
const sourceFilter = ref<string>("all");

// Filtered tools
const filteredTools = computed(() => {
  return tools.value.filter((tool) => {
    // Search filter
    const matchesSearch =
      searchQuery.value === "" ||
      tool.name.toLowerCase().includes(searchQuery.value.toLowerCase()) ||
      tool.description.toLowerCase().includes(searchQuery.value.toLowerCase());

    // Security filter
    const matchesSecurity =
      securityFilter.value === "all" || (tool.security_level || "safe") === securityFilter.value;

    // Source filter
    const matchesSource =
      sourceFilter.value === "all" || (tool.source || "local") === sourceFilter.value;

    return matchesSearch && matchesSecurity && matchesSource;
  });
});

// Tool counts by category
const toolCounts = computed(() => ({
  safe: tools.value.filter((t) => (t.security_level || "safe") === "safe").length,
  moderate: tools.value.filter((t) => t.security_level === "moderate").length,
  dangerous: tools.value.filter((t) => t.security_level === "dangerous").length,
  local: tools.value.filter((t) => (t.source || "local") === "local").length,
  mcp: tools.value.filter((t) => t.source === "mcp").length,
}));

// Test dialog
const showTestDialog = ref(false);
const testingTool = ref<Tool | null>(null);
const testInput = ref("{}");
const testResult = ref<string | null>(null);
const testLoading = ref(false);

// Security level colors
const securityBadge = (level?: string) => {
  switch (level) {
    case "dangerous":
      return { variant: "destructive" as const, icon: ShieldOff };
    case "moderate":
      return { variant: "warning" as const, icon: ShieldAlert };
    default:
      return { variant: "secondary" as const, icon: Shield };
  }
};

// Load tools
const loadTools = async () => {
  loading.value = true;
  try {
    const { $api } = useNuxtApp();
    const response = await $api("/v1/admin/tools");
    const data = response as { local_tools: Tool[]; mcp_tools?: Tool[] };
    // Combine local and MCP tools
    const localTools = (data.local_tools || []).map((t) => ({ ...t, source: "local" as const }));
    const mcpTools = (data.mcp_tools || []).map((t) => ({ ...t, source: "mcp" as const }));
    tools.value = [...localTools, ...mcpTools];
  } catch (error) {
    console.error("Failed to load tools:", error);
    toast.error("Failed to load tools");
  } finally {
    loading.value = false;
  }
};

// Open test dialog
const openTestDialog = (tool: Tool) => {
  testingTool.value = tool;
  testInput.value = "{}";
  testResult.value = null;
  showTestDialog.value = true;
};

// Test tool
const testTool = async () => {
  if (!testingTool.value) return;
  testLoading.value = true;
  testResult.value = null;
  try {
    let input: Record<string, any>;
    try {
      input = JSON.parse(testInput.value);
    } catch {
      toast.error("Invalid JSON input");
      return;
    }

    const { $api } = useNuxtApp();
    const response = await $api(`/v1/admin/tools/${testingTool.value.name}/test`, {
      method: "POST",
      body: { input },
    });
    testResult.value = JSON.stringify(response, null, 2);
  } catch (error: any) {
    testResult.value = `Error: ${error?.message || "Tool execution failed"}`;
  } finally {
    testLoading.value = false;
  }
};

onMounted(() => {
  loadTools();
});
</script>

<template>
  <div class="w-full space-y-6 py-6">
    <!-- Header -->
    <div class="flex items-center justify-between">
      <div>
        <h1 class="text-2xl font-bold">Agent Tools</h1>
        <p class="text-muted-foreground">View and test available tools for agent execution</p>
      </div>
      <Button variant="outline" @click="loadTools" :disabled="loading">
        <RefreshCw class="mr-2 h-4 w-4" :class="{ 'animate-spin': loading }" />
        Refresh
      </Button>
    </div>

    <!-- Search and Filters -->
    <Card v-if="!loading && tools.length > 0">
      <CardContent class="pt-4">
        <div class="flex flex-wrap items-center gap-4">
          <!-- Search -->
          <div class="relative min-w-[200px] flex-1">
            <Search
              class="text-muted-foreground absolute top-1/2 left-3 h-4 w-4 -translate-y-1/2"
            />
            <Input v-model="searchQuery" placeholder="Search tools..." class="pl-9" />
          </div>

          <!-- Security Filter -->
          <div class="flex items-center gap-2">
            <Filter class="text-muted-foreground h-4 w-4" />
            <Select v-model="securityFilter">
              <SelectTrigger class="w-[140px]">
                <SelectValue placeholder="Security" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All levels</SelectItem>
                <SelectItem value="safe">
                  <div class="flex items-center gap-2">
                    <Shield class="h-3 w-3" /> Safe ({{ toolCounts.safe }})
                  </div>
                </SelectItem>
                <SelectItem value="moderate">
                  <div class="flex items-center gap-2">
                    <ShieldAlert class="h-3 w-3" /> Moderate ({{ toolCounts.moderate }})
                  </div>
                </SelectItem>
                <SelectItem value="dangerous">
                  <div class="flex items-center gap-2">
                    <ShieldOff class="h-3 w-3" /> Dangerous ({{ toolCounts.dangerous }})
                  </div>
                </SelectItem>
              </SelectContent>
            </Select>
          </div>

          <!-- Source Filter -->
          <Select v-model="sourceFilter">
            <SelectTrigger class="w-[120px]">
              <SelectValue placeholder="Source" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All sources</SelectItem>
              <SelectItem value="local">Local ({{ toolCounts.local }})</SelectItem>
              <SelectItem value="mcp">MCP ({{ toolCounts.mcp }})</SelectItem>
            </SelectContent>
          </Select>

          <!-- Results count -->
          <div class="text-muted-foreground text-sm">
            {{ filteredTools.length }} of {{ tools.length }} tools
          </div>
        </div>
      </CardContent>
    </Card>

    <!-- Loading state -->
    <div v-if="loading" class="flex justify-center py-12">
      <div class="border-primary h-8 w-8 animate-spin rounded-full border-b-2"></div>
    </div>

    <!-- Empty state -->
    <Card v-else-if="tools.length === 0" class="py-12 text-center">
      <CardContent>
        <Wrench class="text-muted-foreground mx-auto mb-4 h-12 w-12" />
        <h3 class="text-lg font-medium">No Tools Available</h3>
        <p class="text-muted-foreground mb-4">
          Tools will appear here once configured in the backend.
        </p>
        <p class="text-muted-foreground mx-auto max-w-md text-sm">
          Tools enable agents to perform actions like web searches, code execution, and file
          operations. Configure tools in your backend settings or add MCP servers to extend
          capabilities.
        </p>
      </CardContent>
    </Card>

    <!-- No results after filtering -->
    <Card v-else-if="filteredTools.length === 0" class="py-8 text-center">
      <CardContent>
        <Search class="text-muted-foreground mx-auto mb-4 h-8 w-8" />
        <h3 class="text-lg font-medium">No matching tools</h3>
        <p class="text-muted-foreground">Try adjusting your search or filter criteria.</p>
      </CardContent>
    </Card>

    <!-- Tools grid -->
    <div v-else class="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
      <Card v-for="tool in filteredTools" :key="tool.name">
        <CardHeader>
          <div class="flex items-start justify-between">
            <div class="flex items-center gap-2">
              <Wrench class="h-5 w-5" />
              <CardTitle class="text-base">{{ tool.name }}</CardTitle>
            </div>
            <div class="flex gap-1">
              <Badge variant="outline" class="text-xs">
                {{ tool.source || "local" }}
              </Badge>
              <Badge :variant="securityBadge(tool.security_level).variant" class="text-xs">
                <component :is="securityBadge(tool.security_level).icon" class="mr-1 h-3 w-3" />
                {{ tool.security_level || "safe" }}
              </Badge>
            </div>
          </div>
          <CardDescription class="mt-2">
            {{ tool.description }}
          </CardDescription>
        </CardHeader>
        <CardContent>
          <Button variant="outline" size="sm" @click="openTestDialog(tool)">
            <Play class="mr-2 h-4 w-4" />
            Test Tool
          </Button>
        </CardContent>
      </Card>
    </div>

    <!-- Test Dialog -->
    <Dialog v-model:open="showTestDialog">
      <DialogContent class="max-w-2xl">
        <DialogHeader>
          <DialogTitle>Test Tool: {{ testingTool?.name }}</DialogTitle>
          <DialogDescription>
            {{ testingTool?.description }}
          </DialogDescription>
        </DialogHeader>
        <div class="space-y-4 py-4">
          <div class="space-y-2">
            <label class="text-sm font-medium">Input (JSON)</label>
            <Textarea
              v-model="testInput"
              :rows="4"
              class="font-mono text-xs"
              placeholder='{"query": "example"}'
            />
          </div>
          <div v-if="testResult" class="space-y-2">
            <label class="text-sm font-medium">Result</label>
            <pre class="bg-muted max-h-64 overflow-auto rounded-md p-3 text-xs">{{
              testResult
            }}</pre>
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" @click="showTestDialog = false">Close</Button>
          <Button @click="testTool" :disabled="testLoading">
            <Play class="mr-2 h-4 w-4" />
            {{ testLoading ? "Running..." : "Run" }}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  </div>
</template>
