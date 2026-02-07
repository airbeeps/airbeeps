<script setup lang="ts">
import { computed, h, ref, onMounted } from "vue";
import { Badge } from "~/components/ui/badge";
import { Button } from "~/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "~/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "~/components/ui/dialog";
import { Alert, AlertDescription } from "~/components/ui/alert";
import { Separator } from "~/components/ui/separator";
import {
  Server,
  RefreshCw,
  CheckCircle2,
  XCircle,
  AlertCircle,
  Settings2,
  ExternalLink,
  Copy,
  Power,
  PowerOff,
  Wrench,
  GitBranch,
  FileText,
  HardDrive,
  MessageSquare,
  Search,
  Database,
  Folder,
} from "lucide-vue-next";
import { toast } from "vue-sonner";
import type { ModelViewConfig } from "~/components/model-view/ModelView.vue";

const { t } = useI18n();
const { $api } = useNuxtApp();

definePageMeta({
  breadcrumb: "MCP Servers",
  layout: "admin",
});

// Health status state
const healthData = ref<Record<string, MCPServerHealthResponse>>({});
const loadingHealth = ref(false);
const selectedServer = ref<MCPServer | null>(null);
const showSetupDialog = ref(false);
const setupData = ref<MCPServerEnvCheckResponse | null>(null);
const loadingSetup = ref(false);

// Icon mapping for server types
const serverIcons: Record<string, any> = {
  github: GitBranch,
  notion: FileText,
  "google-drive": HardDrive,
  slack: MessageSquare,
  "brave-search": Search,
  sqlite: Database,
  filesystem: Folder,
};

// Category colors
const categoryColors: Record<string, string> = {
  developer: "bg-purple-100 text-purple-800 dark:bg-purple-900 dark:text-purple-200",
  productivity: "bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200",
  communication: "bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200",
  search: "bg-orange-100 text-orange-800 dark:bg-orange-900 dark:text-orange-200",
  database: "bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-200",
  system: "bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200",
};

// Fetch all health statuses
const fetchHealthStatus = async () => {
  loadingHealth.value = true;
  try {
    const results = await $api<MCPServerHealthResponse[]>("/v1/admin/mcp-servers/health/all", {
      method: "GET",
    });
    if (results) {
      healthData.value = {};
      results.forEach((h) => {
        healthData.value[h.server_id] = h;
      });
    }
  } catch (e: any) {
    console.error("Failed to fetch health status:", e);
  } finally {
    loadingHealth.value = false;
  }
};

// Open setup wizard
const openSetupWizard = async (server: MCPServer) => {
  selectedServer.value = server;
  showSetupDialog.value = true;
  loadingSetup.value = true;

  try {
    const data = await $api<MCPServerEnvCheckResponse>(
      `/v1/admin/mcp-servers/${server.id}/env-check`,
      {
        method: "GET",
      }
    );
    setupData.value = data;
  } catch (e: any) {
    toast.error("Failed to check environment variables");
  } finally {
    loadingSetup.value = false;
  }
};

// Copy to clipboard
const copyToClipboard = (text: string) => {
  navigator.clipboard.writeText(text);
  toast.success("Copied to clipboard");
};

// Handle row actions
const handleServerRowAction = async (action: any, row: MCPServer) => {
  try {
    if (action.key === "setup") {
      await openSetupWizard(row);
      return;
    }

    if (action.key === "test") {
      toast.info("Testing connection...");
      const result = await $api<MCPServerTestResponse>(`/v1/admin/mcp-servers/${row.id}/test`, {
        method: "POST",
      });
      if (result?.success) {
        toast.success(`Connected! Found ${result.tools_count} tools (${result.latency_ms}ms)`);
      } else {
        toast.error(result?.message || "Connection failed");
      }
      await fetchHealthStatus();
      return;
    }

    if (action.key === "activate") {
      const result = await $api<any>(`/v1/admin/mcp-servers/${row.id}/activate`, {
        method: "POST",
      });
      if (result?.success) {
        toast.success(`${row.name} activated`);
      } else {
        toast.error(result?.message || "Activation failed");
      }
      await fetchHealthStatus();
      return;
    }

    if (action.key === "deactivate") {
      const result = await $api<any>(`/v1/admin/mcp-servers/${row.id}/deactivate`, {
        method: "POST",
      });
      if (result?.success) {
        toast.success(`${row.name} deactivated`);
      }
      await fetchHealthStatus();
      return;
    }
  } catch (e: any) {
    toast.error(e?.data?.detail || e?.message || "Action failed");
  }
};

// Get status badge variant
const getStatusBadge = (serverId: string, isActive: boolean) => {
  const health = healthData.value[serverId];
  if (!isActive) {
    return { variant: "secondary" as const, label: "Inactive", icon: PowerOff };
  }
  if (!health) {
    return { variant: "outline" as const, label: "Unknown", icon: AlertCircle };
  }
  if (health.is_healthy) {
    return { variant: "default" as const, label: "Healthy", icon: CheckCircle2 };
  }
  if (health.status === "unconfigured") {
    return { variant: "outline" as const, label: "Unconfigured", icon: Settings2 };
  }
  return { variant: "destructive" as const, label: "Unhealthy", icon: XCircle };
};

// Get server icon
const getServerIcon = (server: MCPServer) => {
  const iconName = server.extra_data?.icon || server.name;
  return serverIcons[iconName] || Server;
};

// MCP Server config for ModelView
const mcpServerConfig = computed(
  (): ModelViewConfig<MCPServer> => ({
    title: "MCP Servers",
    description:
      "Manage Model Context Protocol servers for extending agent capabilities with external tools and data sources.",
    apiEndpoint: "/v1/admin/mcp-servers",
    customActions: [
      {
        key: "setup",
        label: "Setup Wizard",
        icon: h(Settings2, { class: "h-4 w-4" }),
        variant: "outline" as const,
      },
      {
        key: "test",
        label: "Test Connection",
        icon: h(RefreshCw, { class: "h-4 w-4" }),
        variant: "secondary" as const,
        visible: (row: any) => row.is_active,
      },
      {
        key: "activate",
        label: "Activate",
        icon: h(Power, { class: "h-4 w-4" }),
        variant: "default" as const,
        visible: (row: any) => !row.is_active,
      },
      {
        key: "deactivate",
        label: "Deactivate",
        icon: h(PowerOff, { class: "h-4 w-4" }),
        variant: "outline" as const,
        visible: (row: any) => row.is_active,
      },
    ],

    columns: [
      {
        accessorKey: "name",
        header: "Server",
        cell: (ctx) => {
          const row = ctx.row.original as MCPServer;
          const displayName = row.extra_data?.display_name || row.name;
          const Icon = getServerIcon(row);
          const category = row.extra_data?.category || "system";
          const categoryClass = categoryColors[category] || categoryColors.system;

          return h("div", { class: "flex items-center gap-3" }, [
            h("div", { class: "flex h-10 w-10 items-center justify-center rounded-lg bg-muted" }, [
              h(Icon, { class: "h-5 w-5 text-muted-foreground" }),
            ]),
            h("div", { class: "flex flex-col" }, [
              h(
                "button",
                {
                  class: "text-primary font-medium cursor-pointer text-left hover:underline",
                  onClick: () =>
                    ctx.table.options.meta?.triggerRowAction?.({ key: "view", label: "view" }, row),
                },
                displayName
              ),
              h("span", { class: "text-xs text-muted-foreground" }, row.name),
            ]),
          ]);
        },
      },
      {
        accessorKey: "description",
        header: "Description",
        cell: (ctx) => {
          const value = ctx.getValue() as string;
          if (!value) return "-";
          const truncated = value.length > 60 ? value.substring(0, 60) + "..." : value;
          return h("span", { class: "text-sm text-muted-foreground", title: value }, truncated);
        },
      },
      {
        accessorKey: "extra_data.category",
        header: "Category",
        cell: (ctx) => {
          const row = ctx.row.original as MCPServer;
          const category = row.extra_data?.category || "system";
          const categoryClass = categoryColors[category] || categoryColors.system;
          return h(
            "span",
            {
              class: `inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${categoryClass}`,
            },
            category.charAt(0).toUpperCase() + category.slice(1)
          );
        },
      },
      {
        accessorKey: "is_active",
        header: "Status",
        cell: (ctx) => {
          const row = ctx.row.original as MCPServer;
          const status = getStatusBadge(row.id, row.is_active);
          const health = healthData.value[row.id];
          const toolsInfo = health?.tools_count != null ? ` (${health.tools_count} tools)` : "";

          return h("div", { class: "flex flex-col gap-1" }, [
            h(
              Badge,
              { variant: status.variant, class: "inline-flex items-center gap-1 w-fit" },
              () => [h(status.icon, { class: "h-3 w-3" }), status.label + toolsInfo]
            ),
            health?.last_check_ms != null
              ? h(
                  "span",
                  { class: "text-xs text-muted-foreground" },
                  `${health.last_check_ms}ms latency`
                )
              : null,
          ]);
        },
      },
      {
        accessorKey: "server_type",
        header: "Type",
        cell: (ctx) => {
          const value = ctx.getValue() as string;
          return h(Badge, { variant: "outline" }, () => value);
        },
      },
    ],

    detailFields: [
      { name: "name", label: "Server Name", type: "text" },
      { name: "description", label: "Description", type: "textarea" },
      { name: "server_type", label: "Server Type", type: "text" },
      { name: "is_active", label: "Active", type: "text" },
      { name: "created_at", label: "Created", type: "datetime" },
      { name: "updated_at", label: "Updated", type: "datetime" },
    ],

    formFields: [
      {
        name: "name",
        label: "Server Name",
        type: "text",
        required: true,
        placeholder: "e.g., github, notion",
        help: "Unique identifier for this MCP server",
      },
      {
        name: "description",
        label: "Description",
        type: "textarea",
        placeholder: "What does this server do?",
      },
      {
        name: "server_type",
        label: "Server Type",
        type: "select",
        required: true,
        options: [
          { label: "STDIO (subprocess)", value: "STDIO" },
          { label: "SSE (Server-Sent Events)", value: "SSE" },
          { label: "HTTP", value: "HTTP" },
        ],
        defaultValue: "STDIO",
      },
      {
        name: "connection_config.command",
        label: "Command",
        type: "text",
        placeholder: "npx",
        help: "Command to execute (for STDIO)",
      },
      {
        name: "is_active",
        label: "Active",
        type: "checkbox",
        defaultValue: false,
      },
    ],
  })
);

onMounted(() => {
  fetchHealthStatus();
});
</script>

<template>
  <div class="space-y-6">
    <!-- Health Overview Card -->
    <Card>
      <CardHeader class="flex flex-row items-center justify-between pb-2">
        <div>
          <CardTitle class="text-lg">Server Health Overview</CardTitle>
          <CardDescription>Real-time status of all MCP servers</CardDescription>
        </div>
        <Button variant="outline" size="sm" :disabled="loadingHealth" @click="fetchHealthStatus">
          <RefreshCw :class="['mr-2 h-4 w-4', { 'animate-spin': loadingHealth }]" />
          Refresh
        </Button>
      </CardHeader>
      <CardContent>
        <div class="grid grid-cols-2 gap-4 md:grid-cols-4">
          <div class="flex items-center gap-2 rounded-lg bg-green-50 p-3 dark:bg-green-950">
            <CheckCircle2 class="h-5 w-5 text-green-600" />
            <div>
              <p class="text-sm font-medium">
                {{ Object.values(healthData).filter((h) => h.is_healthy).length }}
              </p>
              <p class="text-muted-foreground text-xs">Healthy</p>
            </div>
          </div>
          <div class="flex items-center gap-2 rounded-lg bg-red-50 p-3 dark:bg-red-950">
            <XCircle class="h-5 w-5 text-red-600" />
            <div>
              <p class="text-sm font-medium">
                {{ Object.values(healthData).filter((h) => !h.is_healthy && h.is_active).length }}
              </p>
              <p class="text-muted-foreground text-xs">Unhealthy</p>
            </div>
          </div>
          <div class="flex items-center gap-2 rounded-lg bg-yellow-50 p-3 dark:bg-yellow-950">
            <Settings2 class="h-5 w-5 text-yellow-600" />
            <div>
              <p class="text-sm font-medium">
                {{ Object.values(healthData).filter((h) => h.status === "unconfigured").length }}
              </p>
              <p class="text-muted-foreground text-xs">Needs Setup</p>
            </div>
          </div>
          <div class="flex items-center gap-2 rounded-lg bg-gray-50 p-3 dark:bg-gray-900">
            <PowerOff class="h-5 w-5 text-gray-500" />
            <div>
              <p class="text-sm font-medium">
                {{ Object.values(healthData).filter((h) => !h.is_active).length }}
              </p>
              <p class="text-muted-foreground text-xs">Inactive</p>
            </div>
          </div>
        </div>
      </CardContent>
    </Card>

    <!-- ModelView for servers -->
    <ModelView :config="mcpServerConfig" @row-action="handleServerRowAction" />

    <!-- Setup Wizard Dialog -->
    <Dialog v-model:open="showSetupDialog">
      <DialogContent class="max-w-2xl">
        <DialogHeader>
          <DialogTitle class="flex items-center gap-2">
            <component :is="getServerIcon(selectedServer!)" class="h-5 w-5" v-if="selectedServer" />
            Setup {{ selectedServer?.extra_data?.display_name || selectedServer?.name }}
          </DialogTitle>
          <DialogDescription>
            Configure the required environment variables to enable this connector.
          </DialogDescription>
        </DialogHeader>

        <div v-if="loadingSetup" class="flex items-center justify-center py-8">
          <RefreshCw class="text-muted-foreground h-6 w-6 animate-spin" />
        </div>

        <div v-else-if="setupData" class="space-y-4">
          <!-- Status Alert -->
          <Alert :variant="setupData.all_vars_set ? 'default' : 'destructive'">
            <component :is="setupData.all_vars_set ? CheckCircle2 : AlertCircle" class="h-4 w-4" />
            <AlertDescription>
              {{
                setupData.all_vars_set
                  ? "All environment variables are configured. You can activate this server."
                  : "Some environment variables are missing. Configure them before activating."
              }}
            </AlertDescription>
          </Alert>

          <!-- Environment Variables -->
          <div class="space-y-3">
            <h4 class="text-sm font-medium">Required Environment Variables</h4>
            <div
              v-for="envVar in setupData.env_vars"
              :key="envVar.name"
              class="flex items-start gap-3 rounded-lg border p-3"
            >
              <div :class="['mt-0.5', envVar.is_set ? 'text-green-600' : 'text-red-500']">
                <component :is="envVar.is_set ? CheckCircle2 : XCircle" class="h-4 w-4" />
              </div>
              <div class="min-w-0 flex-1">
                <div class="flex items-center gap-2">
                  <code class="bg-muted rounded px-1.5 py-0.5 font-mono text-sm">{{
                    envVar.name
                  }}</code>
                  <Button
                    variant="ghost"
                    size="sm"
                    class="h-6 w-6 p-0"
                    @click="copyToClipboard(envVar.name)"
                  >
                    <Copy class="h-3 w-3" />
                  </Button>
                  <Badge v-if="envVar.is_set" variant="outline" class="text-xs">
                    {{ envVar.value_preview }}
                  </Badge>
                </div>
                <p v-if="envVar.description" class="text-muted-foreground mt-1 text-sm">
                  {{ envVar.description }}
                </p>
                <a
                  v-if="envVar.docs_url"
                  :href="envVar.docs_url"
                  target="_blank"
                  rel="noopener noreferrer"
                  class="text-primary mt-1 inline-flex items-center gap-1 text-xs hover:underline"
                >
                  Documentation <ExternalLink class="h-3 w-3" />
                </a>
              </div>
            </div>
          </div>

          <Separator />

          <!-- Setup Instructions -->
          <div v-if="setupData.setup_instructions" class="space-y-2">
            <h4 class="text-sm font-medium">Setup Instructions</h4>
            <div class="bg-muted rounded-lg p-3">
              <pre class="font-mono text-sm whitespace-pre-wrap">{{
                setupData.setup_instructions
              }}</pre>
            </div>
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" @click="showSetupDialog = false">Close</Button>
          <Button
            v-if="setupData?.all_vars_set && selectedServer && !selectedServer.is_active"
            @click="
              handleServerRowAction({ key: 'activate' }, selectedServer);
              showSetupDialog = false;
            "
          >
            <Power class="mr-2 h-4 w-4" />
            Activate Server
          </Button>
          <Button
            v-if="selectedServer?.is_active"
            variant="secondary"
            @click="
              handleServerRowAction({ key: 'test' }, selectedServer);
              showSetupDialog = false;
            "
          >
            <Wrench class="mr-2 h-4 w-4" />
            Test Connection
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  </div>
</template>
