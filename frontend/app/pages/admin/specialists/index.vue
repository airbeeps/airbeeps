<script setup lang="ts">
import { ref, onMounted, computed } from "vue";
import {
  Users,
  Plus,
  Edit,
  Trash2,
  RefreshCw,
  Route,
  ChevronDown,
  BarChart3,
  Play,
  CheckCircle,
  XCircle,
  Zap,
} from "lucide-vue-next";
import { Button } from "~/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "~/components/ui/card";
import { Badge } from "~/components/ui/badge";
import { Input } from "~/components/ui/input";
import { Textarea } from "~/components/ui/textarea";
import { Switch } from "~/components/ui/switch";
import { Label } from "~/components/ui/label";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "~/components/ui/tabs";
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
  breadcrumb: "Specialist Management",
  layout: "admin",
});

// Types
interface BuiltInSpecialist {
  type: string;
  name: string;
  tools: string[];
  max_iterations: number;
  cost_limit_usd: number;
  can_handoff_to: string[];
  priority_keywords: string[];
}

interface CustomSpecialist {
  id: string;
  name: string;
  display_name: string;
  description?: string;
  tools: string[];
  system_prompt_suffix: string;
  max_iterations: number;
  cost_limit_usd: number;
  can_handoff_to: string[];
  priority_keywords: string[];
  is_enabled: boolean;
  created_at?: string;
}

interface RoutingRule {
  id: string;
  specialist_name: string;
  custom_specialist_id?: string;
  rule_type: string;
  rule_value: string;
  priority: number;
  description?: string;
  is_enabled: boolean;
  created_at?: string;
}

interface SpecialistAnalytics {
  specialist_name: string;
  total_invocations: number;
  success_rate: number;
  avg_cost_usd: number;
  avg_duration_ms: number;
  avg_iterations: number;
  total_handoffs_from: number;
  total_handoffs_to: number;
  top_tools: Record<string, number>;
}

// State
const builtInSpecialists = ref<BuiltInSpecialist[]>([]);
const customSpecialists = ref<CustomSpecialist[]>([]);
const routingRules = ref<RoutingRule[]>([]);
const analytics = ref<SpecialistAnalytics[]>([]);
const loading = ref(true);
const activeTab = ref("built-in");

// Dialog state
const showSpecialistDialog = ref(false);
const showRuleDialog = ref(false);
const showTestDialog = ref(false);
const editingSpecialist = ref<CustomSpecialist | null>(null);
const editingRule = ref<RoutingRule | null>(null);

// Form state
const specialistForm = ref({
  name: "",
  display_name: "",
  description: "",
  tools: "",
  system_prompt_suffix: "",
  max_iterations: 5,
  cost_limit_usd: 0.25,
  can_handoff_to: "",
  priority_keywords: "",
});

const ruleForm = ref({
  specialist_name: "",
  rule_type: "KEYWORD",
  rule_value: "",
  priority: 0,
  description: "",
  is_enabled: true,
});

const testInput = ref("");
const testResult = ref<any>(null);
const testLoading = ref(false);

// All specialist names for dropdowns
const allSpecialistNames = computed(() => {
  const names = builtInSpecialists.value.map((s) => s.type);
  customSpecialists.value.forEach((s) => {
    if (!names.includes(s.name)) names.push(s.name);
  });
  return names;
});

// Load data
const loadData = async () => {
  loading.value = true;
  try {
    const { $api } = useNuxtApp();
    const [builtIn, custom, rules, stats] = await Promise.all([
      $api("/v1/multiagent/specialists"),
      $api("/v1/admin/multiagent/specialist-types?include_disabled=true"),
      $api("/v1/admin/multiagent/routing-rules?include_disabled=true"),
      $api("/v1/admin/multiagent/analytics/specialists?days=30"),
    ]);
    builtInSpecialists.value = builtIn as BuiltInSpecialist[];
    customSpecialists.value = custom as CustomSpecialist[];
    routingRules.value = rules as RoutingRule[];
    analytics.value = stats as SpecialistAnalytics[];
  } catch (error) {
    console.error("Failed to load data:", error);
    toast.error("Failed to load specialist data");
  } finally {
    loading.value = false;
  }
};

// Open specialist dialog
const openSpecialistDialog = (specialist?: CustomSpecialist) => {
  if (specialist) {
    editingSpecialist.value = specialist;
    specialistForm.value = {
      name: specialist.name,
      display_name: specialist.display_name,
      description: specialist.description || "",
      tools: specialist.tools.join(", "),
      system_prompt_suffix: specialist.system_prompt_suffix,
      max_iterations: specialist.max_iterations,
      cost_limit_usd: specialist.cost_limit_usd,
      can_handoff_to: specialist.can_handoff_to.join(", "),
      priority_keywords: specialist.priority_keywords.join(", "),
    };
  } else {
    editingSpecialist.value = null;
    specialistForm.value = {
      name: "",
      display_name: "",
      description: "",
      tools: "",
      system_prompt_suffix: "",
      max_iterations: 5,
      cost_limit_usd: 0.25,
      can_handoff_to: "",
      priority_keywords: "",
    };
  }
  showSpecialistDialog.value = true;
};

// Save specialist
const saveSpecialist = async () => {
  try {
    const { $api } = useNuxtApp();
    const payload = {
      name: specialistForm.value.name.toUpperCase().replace(/\s+/g, "_"),
      display_name: specialistForm.value.display_name,
      description: specialistForm.value.description || null,
      tools: specialistForm.value.tools
        .split(",")
        .map((t) => t.trim())
        .filter(Boolean),
      system_prompt_suffix: specialistForm.value.system_prompt_suffix,
      max_iterations: specialistForm.value.max_iterations,
      cost_limit_usd: specialistForm.value.cost_limit_usd,
      can_handoff_to: specialistForm.value.can_handoff_to
        .split(",")
        .map((t) => t.trim())
        .filter(Boolean),
      priority_keywords: specialistForm.value.priority_keywords
        .split(",")
        .map((t) => t.trim())
        .filter(Boolean),
    };

    if (editingSpecialist.value) {
      await $api(`/v1/admin/multiagent/specialist-types/${editingSpecialist.value.id}`, {
        method: "PATCH",
        body: payload,
      });
      toast.success("Specialist updated");
    } else {
      await $api("/v1/admin/multiagent/specialist-types", {
        method: "POST",
        body: payload,
      });
      toast.success("Specialist created");
    }

    showSpecialistDialog.value = false;
    await loadData();
  } catch (error: any) {
    toast.error(error?.message || "Failed to save specialist");
  }
};

// Delete specialist
const deleteSpecialist = async (id: string) => {
  try {
    const { $api } = useNuxtApp();
    await $api(`/v1/admin/multiagent/specialist-types/${id}`, { method: "DELETE" });
    toast.success("Specialist deleted");
    await loadData();
  } catch (error: any) {
    toast.error(error?.message || "Failed to delete specialist");
  }
};

// Open rule dialog
const openRuleDialog = (rule?: RoutingRule) => {
  if (rule) {
    editingRule.value = rule;
    ruleForm.value = {
      specialist_name: rule.specialist_name,
      rule_type: rule.rule_type,
      rule_value: rule.rule_value,
      priority: rule.priority,
      description: rule.description || "",
      is_enabled: rule.is_enabled,
    };
  } else {
    editingRule.value = null;
    ruleForm.value = {
      specialist_name: "",
      rule_type: "KEYWORD",
      rule_value: "",
      priority: 0,
      description: "",
      is_enabled: true,
    };
  }
  showRuleDialog.value = true;
};

// Save rule
const saveRule = async () => {
  try {
    const { $api } = useNuxtApp();

    if (editingRule.value) {
      await $api(`/v1/admin/multiagent/routing-rules/${editingRule.value.id}`, {
        method: "PATCH",
        body: ruleForm.value,
      });
      toast.success("Rule updated");
    } else {
      await $api("/v1/admin/multiagent/routing-rules", {
        method: "POST",
        body: ruleForm.value,
      });
      toast.success("Rule created");
    }

    showRuleDialog.value = false;
    await loadData();
  } catch (error: any) {
    toast.error(error?.message || "Failed to save rule");
  }
};

// Delete rule
const deleteRule = async (id: string) => {
  try {
    const { $api } = useNuxtApp();
    await $api(`/v1/admin/multiagent/routing-rules/${id}`, { method: "DELETE" });
    toast.success("Rule deleted");
    await loadData();
  } catch (error: any) {
    toast.error(error?.message || "Failed to delete rule");
  }
};

// Test routing
const testRouting = async () => {
  testLoading.value = true;
  testResult.value = null;
  try {
    const { $api } = useNuxtApp();
    const result = await $api("/v1/admin/multiagent/routing-rules/test", {
      method: "POST",
      body: { user_input: testInput.value },
    });
    testResult.value = result;
  } catch (error: any) {
    testResult.value = { error: error?.message || "Test failed" };
  } finally {
    testLoading.value = false;
  }
};

// Format percentage
const formatPercent = (value: number) => `${(value * 100).toFixed(1)}%`;

// Format duration
const formatDuration = (ms: number) => {
  if (ms < 1000) return `${ms.toFixed(0)}ms`;
  return `${(ms / 1000).toFixed(2)}s`;
};

onMounted(() => {
  loadData();
});
</script>

<template>
  <div class="container mx-auto space-y-6 py-6">
    <!-- Header -->
    <div class="flex items-center justify-between">
      <div>
        <h1 class="text-2xl font-bold">Specialist Management</h1>
        <p class="text-muted-foreground">
          Configure custom specialist types, routing rules, and view analytics
        </p>
      </div>
      <Button variant="outline" @click="loadData" :disabled="loading">
        <RefreshCw class="mr-2 h-4 w-4" :class="{ 'animate-spin': loading }" />
        Refresh
      </Button>
    </div>

    <!-- Loading state -->
    <div v-if="loading" class="flex justify-center py-12">
      <div class="border-primary h-8 w-8 animate-spin rounded-full border-b-2"></div>
    </div>

    <template v-else>
      <Tabs v-model="activeTab">
        <TabsList>
          <TabsTrigger value="built-in">
            <Users class="mr-2 h-4 w-4" />
            Built-in Types
          </TabsTrigger>
          <TabsTrigger value="custom">
            <Plus class="mr-2 h-4 w-4" />
            Custom Types
          </TabsTrigger>
          <TabsTrigger value="routing">
            <Route class="mr-2 h-4 w-4" />
            Routing Rules
          </TabsTrigger>
          <TabsTrigger value="analytics">
            <BarChart3 class="mr-2 h-4 w-4" />
            Analytics
          </TabsTrigger>
        </TabsList>

        <!-- Built-in Specialists -->
        <TabsContent value="built-in">
          <div class="grid gap-4 md:grid-cols-2">
            <Card v-for="spec in builtInSpecialists" :key="spec.type">
              <CardHeader>
                <div class="flex items-center justify-between">
                  <CardTitle class="text-lg">{{ spec.name }}</CardTitle>
                  <Badge variant="secondary">Built-in</Badge>
                </div>
                <CardDescription>{{ spec.type }}</CardDescription>
              </CardHeader>
              <CardContent class="space-y-3">
                <div class="text-sm">
                  <span class="text-muted-foreground">Tools:</span>
                  <span v-if="spec.tools.length" class="ml-2">
                    {{ spec.tools.join(", ") }}
                  </span>
                  <span v-else class="text-muted-foreground ml-2 italic">None</span>
                </div>
                <div class="grid grid-cols-2 gap-2 text-sm">
                  <div>
                    <span class="text-muted-foreground">Max iterations:</span>
                    {{ spec.max_iterations }}
                  </div>
                  <div>
                    <span class="text-muted-foreground">Cost limit:</span>
                    ${{ spec.cost_limit_usd.toFixed(2) }}
                  </div>
                </div>
                <div class="text-sm">
                  <span class="text-muted-foreground">Handoffs to:</span>
                  <span class="ml-2">{{ spec.can_handoff_to.join(", ") || "None" }}</span>
                </div>
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        <!-- Custom Specialists -->
        <TabsContent value="custom">
          <div class="mb-4 flex justify-end">
            <Button @click="openSpecialistDialog()">
              <Plus class="mr-2 h-4 w-4" />
              Add Specialist Type
            </Button>
          </div>

          <div v-if="customSpecialists.length === 0" class="py-12 text-center">
            <Users class="text-muted-foreground mx-auto mb-4 h-12 w-12" />
            <h3 class="text-lg font-medium">No Custom Specialists</h3>
            <p class="text-muted-foreground">
              Create custom specialist types to extend agent capabilities.
            </p>
          </div>

          <div v-else class="grid gap-4 md:grid-cols-2">
            <Card v-for="spec in customSpecialists" :key="spec.id">
              <CardHeader>
                <div class="flex items-center justify-between">
                  <CardTitle class="text-lg">{{ spec.display_name }}</CardTitle>
                  <div class="flex gap-2">
                    <Badge v-if="spec.is_enabled" variant="default">
                      <CheckCircle class="mr-1 h-3 w-3" /> Enabled
                    </Badge>
                    <Badge v-else variant="secondary">
                      <XCircle class="mr-1 h-3 w-3" /> Disabled
                    </Badge>
                  </div>
                </div>
                <CardDescription>{{ spec.name }}</CardDescription>
              </CardHeader>
              <CardContent class="space-y-3">
                <div v-if="spec.description" class="text-muted-foreground text-sm">
                  {{ spec.description }}
                </div>
                <div class="text-sm">
                  <span class="text-muted-foreground">Tools:</span>
                  <span class="ml-2">{{ spec.tools.join(", ") || "None" }}</span>
                </div>
                <div class="grid grid-cols-2 gap-2 text-sm">
                  <div>
                    <span class="text-muted-foreground">Max iterations:</span>
                    {{ spec.max_iterations }}
                  </div>
                  <div>
                    <span class="text-muted-foreground">Cost limit:</span>
                    ${{ spec.cost_limit_usd.toFixed(2) }}
                  </div>
                </div>
                <div class="flex gap-2">
                  <Button variant="outline" size="sm" @click="openSpecialistDialog(spec)">
                    <Edit class="mr-2 h-4 w-4" /> Edit
                  </Button>
                  <AlertDialog>
                    <AlertDialogTrigger as-child>
                      <Button variant="destructive" size="sm">
                        <Trash2 class="mr-2 h-4 w-4" /> Delete
                      </Button>
                    </AlertDialogTrigger>
                    <AlertDialogContent>
                      <AlertDialogHeader>
                        <AlertDialogTitle>Delete Specialist?</AlertDialogTitle>
                        <AlertDialogDescription>
                          This will delete "{{ spec.display_name }}" and all associated routing
                          rules.
                        </AlertDialogDescription>
                      </AlertDialogHeader>
                      <AlertDialogFooter>
                        <AlertDialogCancel>Cancel</AlertDialogCancel>
                        <AlertDialogAction @click="deleteSpecialist(spec.id)"
                          >Delete</AlertDialogAction
                        >
                      </AlertDialogFooter>
                    </AlertDialogContent>
                  </AlertDialog>
                </div>
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        <!-- Routing Rules -->
        <TabsContent value="routing">
          <div class="mb-4 flex items-center justify-between gap-4">
            <div class="flex-1">
              <Input v-model="testInput" placeholder="Test input to classify..." class="max-w-md" />
            </div>
            <div class="flex gap-2">
              <Button variant="outline" @click="testRouting" :disabled="!testInput || testLoading">
                <Play class="mr-2 h-4 w-4" />
                Test Routing
              </Button>
              <Button @click="openRuleDialog()">
                <Plus class="mr-2 h-4 w-4" />
                Add Rule
              </Button>
            </div>
          </div>

          <!-- Test result -->
          <Card v-if="testResult" class="mb-4">
            <CardContent class="py-3">
              <div v-if="testResult.matched" class="flex items-center gap-4">
                <Badge variant="default"> <CheckCircle class="mr-1 h-3 w-3" /> Matched </Badge>
                <span
                  >Specialist: <strong>{{ testResult.specialist_name }}</strong></span
                >
                <span>Type: {{ testResult.rule_type }}</span>
                <span>Confidence: {{ formatPercent(testResult.confidence) }}</span>
              </div>
              <div v-else class="flex items-center gap-4">
                <Badge variant="secondary">No Match</Badge>
                <span class="text-muted-foreground">Will fall back to LLM classification</span>
              </div>
            </CardContent>
          </Card>

          <div v-if="routingRules.length === 0" class="py-12 text-center">
            <Route class="text-muted-foreground mx-auto mb-4 h-12 w-12" />
            <h3 class="text-lg font-medium">No Routing Rules</h3>
            <p class="text-muted-foreground">
              Add routing rules to customize how requests are classified.
            </p>
          </div>

          <div v-else class="space-y-3">
            <Card v-for="rule in routingRules" :key="rule.id">
              <CardContent class="flex items-center justify-between py-3">
                <div class="flex items-center gap-4">
                  <Badge variant="outline">P{{ rule.priority }}</Badge>
                  <div>
                    <div class="font-medium">{{ rule.specialist_name }}</div>
                    <div class="text-muted-foreground text-sm">
                      {{ rule.rule_type }}: {{ rule.rule_value.substring(0, 50)
                      }}{{ rule.rule_value.length > 50 ? "..." : "" }}
                    </div>
                  </div>
                </div>
                <div class="flex items-center gap-2">
                  <Badge v-if="rule.is_enabled" variant="default">Enabled</Badge>
                  <Badge v-else variant="secondary">Disabled</Badge>
                  <Button variant="ghost" size="sm" @click="openRuleDialog(rule)">
                    <Edit class="h-4 w-4" />
                  </Button>
                  <AlertDialog>
                    <AlertDialogTrigger as-child>
                      <Button variant="ghost" size="sm">
                        <Trash2 class="h-4 w-4" />
                      </Button>
                    </AlertDialogTrigger>
                    <AlertDialogContent>
                      <AlertDialogHeader>
                        <AlertDialogTitle>Delete Rule?</AlertDialogTitle>
                        <AlertDialogDescription>
                          This routing rule will be permanently deleted.
                        </AlertDialogDescription>
                      </AlertDialogHeader>
                      <AlertDialogFooter>
                        <AlertDialogCancel>Cancel</AlertDialogCancel>
                        <AlertDialogAction @click="deleteRule(rule.id)">Delete</AlertDialogAction>
                      </AlertDialogFooter>
                    </AlertDialogContent>
                  </AlertDialog>
                </div>
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        <!-- Analytics -->
        <TabsContent value="analytics">
          <div v-if="analytics.length === 0" class="py-12 text-center">
            <BarChart3 class="text-muted-foreground mx-auto mb-4 h-12 w-12" />
            <h3 class="text-lg font-medium">No Analytics Data</h3>
            <p class="text-muted-foreground">
              Analytics will appear once specialists have been used.
            </p>
          </div>

          <div v-else class="grid gap-4 md:grid-cols-2">
            <Card v-for="stat in analytics" :key="stat.specialist_name">
              <CardHeader>
                <CardTitle class="text-lg">{{ stat.specialist_name }}</CardTitle>
                <CardDescription>Last 30 days performance</CardDescription>
              </CardHeader>
              <CardContent>
                <div class="grid grid-cols-2 gap-4">
                  <div>
                    <div class="text-2xl font-bold">{{ stat.total_invocations }}</div>
                    <div class="text-muted-foreground text-xs">Invocations</div>
                  </div>
                  <div>
                    <div class="text-2xl font-bold">{{ formatPercent(stat.success_rate) }}</div>
                    <div class="text-muted-foreground text-xs">Success Rate</div>
                  </div>
                  <div>
                    <div class="text-2xl font-bold">${{ stat.avg_cost_usd.toFixed(4) }}</div>
                    <div class="text-muted-foreground text-xs">Avg Cost</div>
                  </div>
                  <div>
                    <div class="text-2xl font-bold">{{ formatDuration(stat.avg_duration_ms) }}</div>
                    <div class="text-muted-foreground text-xs">Avg Duration</div>
                  </div>
                </div>
                <div v-if="Object.keys(stat.top_tools).length > 0" class="mt-4">
                  <div class="text-muted-foreground mb-2 text-sm">Top Tools</div>
                  <div class="flex flex-wrap gap-1">
                    <Badge v-for="(count, tool) in stat.top_tools" :key="tool" variant="outline">
                      {{ tool }}: {{ count }}
                    </Badge>
                  </div>
                </div>
              </CardContent>
            </Card>
          </div>
        </TabsContent>
      </Tabs>
    </template>

    <!-- Specialist Dialog -->
    <Dialog v-model:open="showSpecialistDialog">
      <DialogContent class="max-w-2xl">
        <DialogHeader>
          <DialogTitle>
            {{ editingSpecialist ? "Edit Specialist Type" : "Create Specialist Type" }}
          </DialogTitle>
          <DialogDescription>
            Configure a custom specialist type for agent collaboration.
          </DialogDescription>
        </DialogHeader>
        <div class="grid gap-4 py-4">
          <div class="grid grid-cols-2 gap-4">
            <div class="space-y-2">
              <Label>Name (uppercase, no spaces)</Label>
              <Input
                v-model="specialistForm.name"
                :disabled="!!editingSpecialist"
                placeholder="LEGAL_EXPERT"
              />
            </div>
            <div class="space-y-2">
              <Label>Display Name</Label>
              <Input v-model="specialistForm.display_name" placeholder="Legal Expert" />
            </div>
          </div>
          <div class="space-y-2">
            <Label>Description</Label>
            <Textarea
              v-model="specialistForm.description"
              :rows="2"
              placeholder="Expert in legal matters..."
            />
          </div>
          <div class="space-y-2">
            <Label>Tools (comma-separated)</Label>
            <Input v-model="specialistForm.tools" placeholder="knowledge_base_query, web_search" />
          </div>
          <div class="space-y-2">
            <Label>System Prompt Suffix</Label>
            <Textarea
              v-model="specialistForm.system_prompt_suffix"
              :rows="4"
              placeholder="You are a legal expert..."
            />
          </div>
          <div class="grid grid-cols-2 gap-4">
            <div class="space-y-2">
              <Label>Max Iterations</Label>
              <Input
                v-model.number="specialistForm.max_iterations"
                type="number"
                min="1"
                max="20"
              />
            </div>
            <div class="space-y-2">
              <Label>Cost Limit (USD)</Label>
              <Input
                v-model.number="specialistForm.cost_limit_usd"
                type="number"
                step="0.01"
                min="0.01"
                max="10"
              />
            </div>
          </div>
          <div class="space-y-2">
            <Label>Can Handoff To (comma-separated)</Label>
            <Input v-model="specialistForm.can_handoff_to" placeholder="GENERAL, RESEARCH" />
          </div>
          <div class="space-y-2">
            <Label>Priority Keywords (comma-separated)</Label>
            <Input
              v-model="specialistForm.priority_keywords"
              placeholder="legal, contract, lawsuit"
            />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" @click="showSpecialistDialog = false">Cancel</Button>
          <Button @click="saveSpecialist">Save</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>

    <!-- Rule Dialog -->
    <Dialog v-model:open="showRuleDialog">
      <DialogContent>
        <DialogHeader>
          <DialogTitle>
            {{ editingRule ? "Edit Routing Rule" : "Create Routing Rule" }}
          </DialogTitle>
          <DialogDescription>
            Define how user requests are routed to specialists.
          </DialogDescription>
        </DialogHeader>
        <div class="grid gap-4 py-4">
          <div class="space-y-2">
            <Label>Specialist</Label>
            <Select v-model="ruleForm.specialist_name">
              <SelectTrigger>
                <SelectValue placeholder="Select specialist" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem v-for="name in allSpecialistNames" :key="name" :value="name">
                  {{ name }}
                </SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div class="space-y-2">
            <Label>Rule Type</Label>
            <Select v-model="ruleForm.rule_type">
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="KEYWORD">Keyword Match</SelectItem>
                <SelectItem value="REGEX">Regular Expression</SelectItem>
                <SelectItem value="LLM">LLM Classification</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div class="space-y-2">
            <Label>
              {{
                ruleForm.rule_type === "KEYWORD"
                  ? "Keywords (comma-separated)"
                  : ruleForm.rule_type === "REGEX"
                    ? "Regex Pattern"
                    : "Classification Prompt"
              }}
            </Label>
            <Textarea
              v-model="ruleForm.rule_value"
              :rows="ruleForm.rule_type === 'LLM' ? 4 : 2"
              :placeholder="
                ruleForm.rule_type === 'KEYWORD'
                  ? 'legal, contract, lawsuit'
                  : ruleForm.rule_type === 'REGEX'
                    ? '\\b(legal|law|attorney)\\b'
                    : 'Classify as LEGAL if the user asks about legal matters...'
              "
            />
          </div>
          <div class="space-y-2">
            <Label>Priority (higher = checked first)</Label>
            <Input v-model.number="ruleForm.priority" type="number" min="-100" max="100" />
          </div>
          <div class="space-y-2">
            <Label>Description (optional)</Label>
            <Input v-model="ruleForm.description" placeholder="Route legal queries" />
          </div>
          <div class="flex items-center gap-2">
            <Switch v-model:checked="ruleForm.is_enabled" />
            <Label>Enabled</Label>
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" @click="showRuleDialog = false">Cancel</Button>
          <Button @click="saveRule">Save</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  </div>
</template>
