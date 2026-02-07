<script setup lang="ts">
import { ref, computed, onMounted } from "vue";
import {
  Plus,
  Trash2,
  RefreshCw,
  CheckCircle,
  XCircle,
  Server,
  ExternalLink,
} from "lucide-vue-next";
import { Button } from "~/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "~/components/ui/card";
import { Input } from "~/components/ui/input";
import { Label } from "~/components/ui/label";
import { Textarea } from "~/components/ui/textarea";
import { Badge } from "~/components/ui/badge";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "~/components/ui/dialog";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "~/components/ui/alert-dialog";
import { toast } from "vue-sonner";

const { t } = useI18n();

definePageMeta({
  breadcrumb: "MCP Servers",
  layout: "admin",
});

interface MCPServer {
  id: string;
  name: string;
  description?: string;
  transport_type: string;
  connection_params: Record<string, any>;
  status: "ACTIVE" | "INACTIVE" | "ERROR";
  created_at: string;
  updated_at: string;
}

interface MCPTool {
  name: string;
  description: string;
}

// State
const servers = ref<MCPServer[]>([]);
const loading = ref(true);
const testingServer = ref<string | null>(null);
const serverTools = ref<Record<string, MCPTool[]>>({});
const expandedServer = ref<string | null>(null);

// Dialog state
const showCreateDialog = ref(false);
const createLoading = ref(false);
const newServer = ref({
  name: "",
  description: "",
  transport_type: "stdio",
  connection_params: "{}",
});

// Load servers
const loadServers = async () => {
  loading.value = true;
  try {
    const { $api } = useNuxtApp();
    const response = await $api("/v1/admin/mcp-servers");
    servers.value = response as MCPServer[];
  } catch (error) {
    console.error("Failed to load MCP servers:", error);
    toast.error("Failed to load MCP servers");
  } finally {
    loading.value = false;
  }
};

// Test server connection
const testServer = async (serverId: string) => {
  testingServer.value = serverId;
  try {
    const { $api } = useNuxtApp();
    await $api(`/v1/admin/mcp-servers/${serverId}/test`, { method: "POST" });
    toast.success("Connection successful");
  } catch (error: any) {
    toast.error(error?.message || "Connection failed");
  } finally {
    testingServer.value = null;
  }
};

// Load tools for a server
const loadServerTools = async (serverName: string) => {
  if (serverTools.value[serverName]) return;
  try {
    const { $api } = useNuxtApp();
    const response = await $api(`/v1/admin/mcp-servers/${serverName}/tools`);
    serverTools.value[serverName] = (response as any).tools || [];
  } catch (error) {
    console.error(`Failed to load tools for ${serverName}:`, error);
  }
};

// Toggle expand server
const toggleExpand = async (server: MCPServer) => {
  if (expandedServer.value === server.id) {
    expandedServer.value = null;
  } else {
    expandedServer.value = server.id;
    await loadServerTools(server.name);
  }
};

// Create server
const createServer = async () => {
  createLoading.value = true;
  try {
    let params: Record<string, any>;
    try {
      params = JSON.parse(newServer.value.connection_params);
    } catch {
      toast.error("Invalid JSON in connection params");
      return;
    }

    const { $api } = useNuxtApp();
    await $api("/v1/admin/mcp-servers", {
      method: "POST",
      body: {
        name: newServer.value.name,
        description: newServer.value.description,
        transport_type: newServer.value.transport_type,
        connection_params: params,
      },
    });
    toast.success("MCP server created");
    showCreateDialog.value = false;
    newServer.value = {
      name: "",
      description: "",
      transport_type: "stdio",
      connection_params: "{}",
    };
    await loadServers();
  } catch (error: any) {
    toast.error(error?.message || "Failed to create server");
  } finally {
    createLoading.value = false;
  }
};

// Delete server
const deleteServer = async (serverId: string) => {
  try {
    const { $api } = useNuxtApp();
    await $api(`/v1/admin/mcp-servers/${serverId}`, { method: "DELETE" });
    toast.success("MCP server deleted");
    await loadServers();
  } catch (error: any) {
    toast.error(error?.message || "Failed to delete server");
  }
};

// Activate/Deactivate server
const toggleServerStatus = async (server: MCPServer) => {
  const action = server.status === "ACTIVE" ? "deactivate" : "activate";
  try {
    const { $api } = useNuxtApp();
    await $api(`/v1/admin/mcp-servers/${server.id}/${action}`, { method: "POST" });
    toast.success(`Server ${action}d`);
    await loadServers();
  } catch (error: any) {
    toast.error(error?.message || `Failed to ${action} server`);
  }
};

onMounted(() => {
  loadServers();
});
</script>

<template>
  <div class="container mx-auto space-y-6 py-6">
    <!-- Header -->
    <div class="flex items-center justify-between">
      <div>
        <h1 class="text-2xl font-bold">MCP Servers</h1>
        <p class="text-muted-foreground">
          Manage Model Context Protocol servers that provide tools to agents
        </p>
      </div>
      <div class="flex gap-2">
        <Button variant="outline" @click="loadServers" :disabled="loading">
          <RefreshCw class="mr-2 h-4 w-4" :class="{ 'animate-spin': loading }" />
          Refresh
        </Button>
        <Dialog v-model:open="showCreateDialog">
          <DialogTrigger as-child>
            <Button>
              <Plus class="mr-2 h-4 w-4" />
              Add Server
            </Button>
          </DialogTrigger>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Add MCP Server</DialogTitle>
              <DialogDescription>
                Configure a new MCP server to provide tools to agents
              </DialogDescription>
            </DialogHeader>
            <div class="space-y-4 py-4">
              <div class="space-y-2">
                <Label for="server-name">Name</Label>
                <Input id="server-name" v-model="newServer.name" placeholder="e.g., brave-search" />
              </div>
              <div class="space-y-2">
                <Label for="server-description">Description</Label>
                <Input
                  id="server-description"
                  v-model="newServer.description"
                  placeholder="Optional description"
                />
              </div>
              <div class="space-y-2">
                <Label for="transport-type">Transport Type</Label>
                <select
                  id="transport-type"
                  v-model="newServer.transport_type"
                  class="border-input bg-background ring-offset-background placeholder:text-muted-foreground focus-visible:ring-ring flex h-10 w-full rounded-md border px-3 py-2 text-sm focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:outline-none"
                >
                  <option value="stdio">stdio (subprocess)</option>
                  <option value="sse">SSE (HTTP)</option>
                </select>
              </div>
              <div class="space-y-2">
                <Label for="connection-params">Connection Params (JSON)</Label>
                <Textarea
                  id="connection-params"
                  v-model="newServer.connection_params"
                  :rows="4"
                  class="font-mono text-xs"
                  placeholder='{"command": "npx", "args": ["-y", "@modelcontextprotocol/server-brave-search"]}'
                />
              </div>
            </div>
            <DialogFooter>
              <Button variant="outline" @click="showCreateDialog = false">Cancel</Button>
              <Button @click="createServer" :disabled="createLoading || !newServer.name">
                Create
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </div>
    </div>

    <!-- Loading state -->
    <div v-if="loading" class="flex justify-center py-12">
      <div class="border-primary h-8 w-8 animate-spin rounded-full border-b-2"></div>
    </div>

    <!-- Empty state -->
    <Card v-else-if="servers.length === 0" class="py-12">
      <CardContent class="text-center">
        <Server class="text-muted-foreground mx-auto mb-4 h-12 w-12" />
        <h3 class="text-lg font-medium">No MCP Servers</h3>
        <p class="text-muted-foreground mb-4">
          Add an MCP server to enable additional tools for your agents.
        </p>
        <Button @click="showCreateDialog = true" class="mb-6">
          <Plus class="mr-2 h-4 w-4" />
          Add Server
        </Button>

        <!-- What is MCP explanation -->
        <div class="bg-muted/30 mx-auto max-w-lg rounded-lg border p-4 text-left">
          <h4 class="mb-2 text-sm font-medium">What is MCP?</h4>
          <p class="text-muted-foreground mb-3 text-sm">
            The <strong>Model Context Protocol (MCP)</strong> is an open standard that allows AI
            assistants to connect to external tools and data sources. MCP servers can provide:
          </p>
          <ul class="text-muted-foreground list-inside list-disc space-y-1 text-sm">
            <li>Web search capabilities (Brave, Google, etc.)</li>
            <li>File system access</li>
            <li>Database queries</li>
            <li>API integrations</li>
            <li>Custom tools for your specific use case</li>
          </ul>
          <p class="text-muted-foreground mt-3 text-xs">
            Learn more at
            <a
              href="https://modelcontextprotocol.io"
              target="_blank"
              class="text-primary hover:underline"
              >modelcontextprotocol.io</a
            >
          </p>
        </div>
      </CardContent>
    </Card>

    <!-- Server list -->
    <div v-else class="space-y-4">
      <Card v-for="server in servers" :key="server.id">
        <CardHeader class="cursor-pointer" @click="toggleExpand(server)">
          <div class="flex items-center justify-between">
            <div class="flex items-center gap-3">
              <Server class="h-5 w-5" />
              <div>
                <CardTitle class="text-lg">{{ server.name }}</CardTitle>
                <CardDescription v-if="server.description">
                  {{ server.description }}
                </CardDescription>
              </div>
            </div>
            <div class="flex items-center gap-2">
              <Badge :variant="server.status === 'ACTIVE' ? 'default' : 'secondary'">
                {{ server.status }}
              </Badge>
              <Badge variant="outline">{{ server.transport_type }}</Badge>
            </div>
          </div>
        </CardHeader>
        <CardContent v-if="expandedServer === server.id">
          <div class="space-y-4">
            <!-- Connection params -->
            <div class="bg-muted rounded-md p-3">
              <div class="mb-2 text-sm font-medium">Connection Parameters</div>
              <pre class="text-xs">{{ JSON.stringify(server.connection_params, null, 2) }}</pre>
            </div>

            <!-- Tools list -->
            <div v-if="serverTools[server.name]?.length">
              <div class="mb-2 text-sm font-medium">Available Tools</div>
              <div class="grid grid-cols-2 gap-2 md:grid-cols-3">
                <div
                  v-for="tool in serverTools[server.name]"
                  :key="tool.name"
                  class="rounded-md border p-2"
                >
                  <div class="text-sm font-medium">{{ tool.name }}</div>
                  <div class="text-muted-foreground text-xs">{{ tool.description }}</div>
                </div>
              </div>
            </div>

            <!-- Actions -->
            <div class="flex gap-2 border-t pt-4">
              <Button
                variant="outline"
                size="sm"
                @click.stop="testServer(server.id)"
                :disabled="testingServer === server.id"
              >
                <RefreshCw
                  class="mr-2 h-4 w-4"
                  :class="{ 'animate-spin': testingServer === server.id }"
                />
                Test Connection
              </Button>
              <Button variant="outline" size="sm" @click.stop="toggleServerStatus(server)">
                {{ server.status === "ACTIVE" ? "Deactivate" : "Activate" }}
              </Button>
              <AlertDialog>
                <AlertDialogTrigger as-child>
                  <Button variant="destructive" size="sm" @click.stop>
                    <Trash2 class="mr-2 h-4 w-4" />
                    Delete
                  </Button>
                </AlertDialogTrigger>
                <AlertDialogContent>
                  <AlertDialogHeader>
                    <AlertDialogTitle>Delete MCP Server?</AlertDialogTitle>
                    <AlertDialogDescription>
                      This will remove the server "{{ server.name }}" and its tools will no longer
                      be available to agents.
                    </AlertDialogDescription>
                  </AlertDialogHeader>
                  <AlertDialogFooter>
                    <AlertDialogCancel>Cancel</AlertDialogCancel>
                    <AlertDialogAction @click="deleteServer(server.id)">Delete</AlertDialogAction>
                  </AlertDialogFooter>
                </AlertDialogContent>
              </AlertDialog>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  </div>
</template>
