<script setup lang="ts">
import { ref, onMounted, computed } from "vue";
import {
  BarChart3,
  TrendingUp,
  FlaskConical,
  Plus,
  Edit,
  Trash2,
  RefreshCw,
  Play,
  Pause,
  CheckCircle,
  XCircle,
  Target,
  DollarSign,
  Clock,
  Users,
} from "lucide-vue-next";
import { Button } from "~/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "~/components/ui/card";
import { Badge } from "~/components/ui/badge";
import { Input } from "~/components/ui/input";
import { Textarea } from "~/components/ui/textarea";
import { Label } from "~/components/ui/label";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "~/components/ui/tabs";
import { Progress } from "~/components/ui/progress";
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
  breadcrumb: "Model Analytics",
  layout: "admin",
});

// Types
interface ModelStats {
  model_id: string;
  model_name: string;
  total_requests: number;
  successful_requests: number;
  failed_requests: number;
  success_rate: number;
  total_tokens: number;
  total_cost_usd: number;
  avg_latency_ms: number;
  unique_users: number;
  feedback_score: number | null;
}

interface Experiment {
  id: string;
  name: string;
  description?: string;
  status: string;
  model_a_id: string;
  model_a_name: string;
  model_b_id: string;
  model_b_name: string;
  traffic_split_percent: number;
  assistant_id?: string;
  start_date?: string;
  end_date?: string;
  min_sample_size: number;
  assignments_count: number;
  created_at?: string;
}

interface ExperimentResults {
  experiment_id: string;
  experiment_name: string;
  status: string;
  variant_a: ModelStats;
  variant_b: ModelStats;
  sample_size_a: number;
  sample_size_b: number;
  is_statistically_significant: boolean;
  confidence_level: number;
  winner: string | null;
  recommendation: string;
}

interface ModelOption {
  id: string;
  name: string;
}

// State
const modelStats = ref<ModelStats[]>([]);
const experiments = ref<Experiment[]>([]);
const models = ref<ModelOption[]>([]);
const loading = ref(true);
const activeTab = ref("overview");

// Dialog state
const showExperimentDialog = ref(false);
const showResultsDialog = ref(false);
const editingExperiment = ref<Experiment | null>(null);
const viewingResults = ref<ExperimentResults | null>(null);
const resultsLoading = ref(false);

// Form state
const experimentForm = ref({
  name: "",
  description: "",
  model_a_id: "",
  model_b_id: "",
  traffic_split_percent: 50,
  min_sample_size: 100,
});

// Computed
const statusBadge = (status: string) => {
  switch (status) {
    case "ACTIVE":
      return { variant: "default" as const, icon: Play };
    case "PAUSED":
      return { variant: "secondary" as const, icon: Pause };
    case "COMPLETED":
      return { variant: "outline" as const, icon: CheckCircle };
    default:
      return { variant: "secondary" as const, icon: null };
  }
};

// Load data
const loadData = async () => {
  loading.value = true;
  try {
    const { $api } = useNuxtApp();
    const [stats, exps, modelList] = await Promise.all([
      $api("/v1/analytics/models?days=30"),
      $api("/v1/admin/analytics/experiments"),
      $api("/v1/admin/models"),
    ]);
    modelStats.value = stats as ModelStats[];
    experiments.value = exps as Experiment[];
    models.value = (modelList as any[]).map((m) => ({
      id: m.id,
      name: m.display_name || m.name,
    }));
  } catch (error) {
    console.error("Failed to load data:", error);
    toast.error("Failed to load analytics data");
  } finally {
    loading.value = false;
  }
};

// Open experiment dialog
const openExperimentDialog = (experiment?: Experiment) => {
  if (experiment) {
    editingExperiment.value = experiment;
    experimentForm.value = {
      name: experiment.name,
      description: experiment.description || "",
      model_a_id: experiment.model_a_id,
      model_b_id: experiment.model_b_id,
      traffic_split_percent: experiment.traffic_split_percent,
      min_sample_size: experiment.min_sample_size,
    };
  } else {
    editingExperiment.value = null;
    experimentForm.value = {
      name: "",
      description: "",
      model_a_id: "",
      model_b_id: "",
      traffic_split_percent: 50,
      min_sample_size: 100,
    };
  }
  showExperimentDialog.value = true;
};

// Save experiment
const saveExperiment = async () => {
  try {
    const { $api } = useNuxtApp();

    if (editingExperiment.value) {
      await $api(`/v1/admin/analytics/experiments/${editingExperiment.value.id}`, {
        method: "PATCH",
        body: experimentForm.value,
      });
      toast.success("Experiment updated");
    } else {
      await $api("/v1/admin/analytics/experiments", {
        method: "POST",
        body: experimentForm.value,
      });
      toast.success("Experiment created");
    }

    showExperimentDialog.value = false;
    await loadData();
  } catch (error: any) {
    toast.error(error?.message || "Failed to save experiment");
  }
};

// Update experiment status
const updateExperimentStatus = async (experiment: Experiment, status: string) => {
  try {
    const { $api } = useNuxtApp();
    await $api(`/v1/admin/analytics/experiments/${experiment.id}`, {
      method: "PATCH",
      body: { status },
    });
    toast.success(`Experiment ${status.toLowerCase()}`);
    await loadData();
  } catch (error: any) {
    toast.error(error?.message || "Failed to update experiment");
  }
};

// Delete experiment
const deleteExperiment = async (id: string) => {
  try {
    const { $api } = useNuxtApp();
    await $api(`/v1/admin/analytics/experiments/${id}`, { method: "DELETE" });
    toast.success("Experiment deleted");
    await loadData();
  } catch (error: any) {
    toast.error(error?.message || "Failed to delete experiment");
  }
};

// View experiment results
const viewExperimentResults = async (experiment: Experiment) => {
  resultsLoading.value = true;
  viewingResults.value = null;
  showResultsDialog.value = true;

  try {
    const { $api } = useNuxtApp();
    const results = await $api(`/v1/admin/analytics/experiments/${experiment.id}/results`);
    viewingResults.value = results as ExperimentResults;
  } catch (error: any) {
    toast.error(error?.message || "Failed to load results");
  } finally {
    resultsLoading.value = false;
  }
};

// Format helpers
const formatCost = (value: number) => `$${value.toFixed(4)}`;
const formatLatency = (ms: number) =>
  ms < 1000 ? `${ms.toFixed(0)}ms` : `${(ms / 1000).toFixed(2)}s`;
const formatPercent = (value: number) => `${(value * 100).toFixed(1)}%`;
const formatNumber = (value: number) => value.toLocaleString();

onMounted(() => {
  loadData();
});
</script>

<template>
  <div class="container mx-auto space-y-6 py-6">
    <!-- Header -->
    <div class="flex items-center justify-between">
      <div>
        <h1 class="text-2xl font-bold">Model Analytics & A/B Testing</h1>
        <p class="text-muted-foreground">Monitor model performance and run experiments</p>
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
          <TabsTrigger value="overview">
            <BarChart3 class="mr-2 h-4 w-4" />
            Overview
          </TabsTrigger>
          <TabsTrigger value="experiments">
            <FlaskConical class="mr-2 h-4 w-4" />
            A/B Experiments
          </TabsTrigger>
        </TabsList>

        <!-- Overview Tab -->
        <TabsContent value="overview">
          <div v-if="modelStats.length === 0" class="py-12 text-center">
            <BarChart3 class="text-muted-foreground mx-auto mb-4 h-12 w-12" />
            <h3 class="text-lg font-medium">No Usage Data</h3>
            <p class="text-muted-foreground">
              Model usage statistics will appear here once models are used.
            </p>
          </div>

          <div v-else class="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
            <Card v-for="stat in modelStats" :key="stat.model_id">
              <CardHeader>
                <CardTitle class="text-lg">{{ stat.model_name }}</CardTitle>
                <CardDescription>Last 30 days</CardDescription>
              </CardHeader>
              <CardContent class="space-y-4">
                <div class="grid grid-cols-2 gap-4">
                  <div class="flex items-center gap-2">
                    <Target class="text-muted-foreground h-4 w-4" />
                    <div>
                      <div class="text-xl font-bold">{{ formatNumber(stat.total_requests) }}</div>
                      <div class="text-muted-foreground text-xs">Requests</div>
                    </div>
                  </div>
                  <div class="flex items-center gap-2">
                    <CheckCircle class="text-muted-foreground h-4 w-4" />
                    <div>
                      <div class="text-xl font-bold">{{ formatPercent(stat.success_rate) }}</div>
                      <div class="text-muted-foreground text-xs">Success Rate</div>
                    </div>
                  </div>
                  <div class="flex items-center gap-2">
                    <DollarSign class="text-muted-foreground h-4 w-4" />
                    <div>
                      <div class="text-xl font-bold">{{ formatCost(stat.total_cost_usd) }}</div>
                      <div class="text-muted-foreground text-xs">Total Cost</div>
                    </div>
                  </div>
                  <div class="flex items-center gap-2">
                    <Clock class="text-muted-foreground h-4 w-4" />
                    <div>
                      <div class="text-xl font-bold">{{ formatLatency(stat.avg_latency_ms) }}</div>
                      <div class="text-muted-foreground text-xs">Avg Latency</div>
                    </div>
                  </div>
                </div>
                <div v-if="stat.feedback_score !== null">
                  <div class="text-muted-foreground mb-1 text-sm">Quality Score</div>
                  <div class="flex items-center gap-2">
                    <Progress :model-value="stat.feedback_score * 100" class="flex-1" />
                    <span class="text-sm font-medium">{{
                      formatPercent(stat.feedback_score)
                    }}</span>
                  </div>
                </div>
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        <!-- Experiments Tab -->
        <TabsContent value="experiments">
          <div class="mb-4 flex justify-end">
            <Button @click="openExperimentDialog()">
              <Plus class="mr-2 h-4 w-4" />
              Create Experiment
            </Button>
          </div>

          <div v-if="experiments.length === 0" class="py-12 text-center">
            <FlaskConical class="text-muted-foreground mx-auto mb-4 h-12 w-12" />
            <h3 class="text-lg font-medium">No Experiments</h3>
            <p class="text-muted-foreground">
              Create an A/B experiment to compare model performance.
            </p>
          </div>

          <div v-else class="space-y-4">
            <Card v-for="exp in experiments" :key="exp.id">
              <CardContent class="py-4">
                <div class="flex items-center justify-between">
                  <div class="flex-1">
                    <div class="mb-1 flex items-center gap-2">
                      <h3 class="text-lg font-semibold">{{ exp.name }}</h3>
                      <Badge :variant="statusBadge(exp.status).variant">
                        <component
                          v-if="statusBadge(exp.status).icon"
                          :is="statusBadge(exp.status).icon"
                          class="mr-1 h-3 w-3"
                        />
                        {{ exp.status }}
                      </Badge>
                    </div>
                    <p v-if="exp.description" class="text-muted-foreground mb-2 text-sm">
                      {{ exp.description }}
                    </p>
                    <div class="flex flex-wrap gap-4 text-sm">
                      <div>
                        <span class="text-muted-foreground">Variant A:</span>
                        <span class="ml-1 font-medium">{{ exp.model_a_name }}</span>
                        <span class="text-muted-foreground ml-1"
                          >({{ exp.traffic_split_percent }}%)</span
                        >
                      </div>
                      <div>
                        <span class="text-muted-foreground">Variant B:</span>
                        <span class="ml-1 font-medium">{{ exp.model_b_name }}</span>
                        <span class="text-muted-foreground ml-1"
                          >({{ 100 - exp.traffic_split_percent }}%)</span
                        >
                      </div>
                      <div>
                        <span class="text-muted-foreground">Assignments:</span>
                        <span class="ml-1 font-medium">{{ exp.assignments_count }}</span>
                        <span class="text-muted-foreground ml-1"
                          >/ {{ exp.min_sample_size }} min</span
                        >
                      </div>
                    </div>
                  </div>
                  <div class="flex items-center gap-2">
                    <Button
                      v-if="exp.status === 'DRAFT'"
                      variant="outline"
                      size="sm"
                      @click="updateExperimentStatus(exp, 'ACTIVE')"
                    >
                      <Play class="mr-2 h-4 w-4" /> Start
                    </Button>
                    <Button
                      v-if="exp.status === 'ACTIVE'"
                      variant="outline"
                      size="sm"
                      @click="updateExperimentStatus(exp, 'PAUSED')"
                    >
                      <Pause class="mr-2 h-4 w-4" /> Pause
                    </Button>
                    <Button
                      v-if="exp.status === 'PAUSED'"
                      variant="outline"
                      size="sm"
                      @click="updateExperimentStatus(exp, 'ACTIVE')"
                    >
                      <Play class="mr-2 h-4 w-4" /> Resume
                    </Button>
                    <Button variant="outline" size="sm" @click="viewExperimentResults(exp)">
                      <TrendingUp class="mr-2 h-4 w-4" /> Results
                    </Button>
                    <Button variant="ghost" size="sm" @click="openExperimentDialog(exp)">
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
                          <AlertDialogTitle>Delete Experiment?</AlertDialogTitle>
                          <AlertDialogDescription>
                            This will permanently delete "{{ exp.name }}" and all associated data.
                          </AlertDialogDescription>
                        </AlertDialogHeader>
                        <AlertDialogFooter>
                          <AlertDialogCancel>Cancel</AlertDialogCancel>
                          <AlertDialogAction @click="deleteExperiment(exp.id)"
                            >Delete</AlertDialogAction
                          >
                        </AlertDialogFooter>
                      </AlertDialogContent>
                    </AlertDialog>
                  </div>
                </div>
              </CardContent>
            </Card>
          </div>
        </TabsContent>
      </Tabs>
    </template>

    <!-- Experiment Dialog -->
    <Dialog v-model:open="showExperimentDialog">
      <DialogContent class="max-w-lg">
        <DialogHeader>
          <DialogTitle>
            {{ editingExperiment ? "Edit Experiment" : "Create A/B Experiment" }}
          </DialogTitle>
          <DialogDescription> Compare two models to find the best performer. </DialogDescription>
        </DialogHeader>
        <div class="grid gap-4 py-4">
          <div class="space-y-2">
            <Label>Experiment Name</Label>
            <Input v-model="experimentForm.name" placeholder="GPT-4 vs Claude comparison" />
          </div>
          <div class="space-y-2">
            <Label>Description</Label>
            <Textarea
              v-model="experimentForm.description"
              :rows="2"
              placeholder="Compare response quality..."
            />
          </div>
          <div class="grid grid-cols-2 gap-4">
            <div class="space-y-2">
              <Label>Variant A (Model)</Label>
              <Select v-model="experimentForm.model_a_id">
                <SelectTrigger>
                  <SelectValue placeholder="Select model" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem v-for="m in models" :key="m.id" :value="m.id">
                    {{ m.name }}
                  </SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div class="space-y-2">
              <Label>Variant B (Model)</Label>
              <Select v-model="experimentForm.model_b_id">
                <SelectTrigger>
                  <SelectValue placeholder="Select model" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem v-for="m in models" :key="m.id" :value="m.id">
                    {{ m.name }}
                  </SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
          <div class="grid grid-cols-2 gap-4">
            <div class="space-y-2">
              <Label>Traffic Split (% to A)</Label>
              <Input
                v-model.number="experimentForm.traffic_split_percent"
                type="number"
                min="0"
                max="100"
              />
            </div>
            <div class="space-y-2">
              <Label>Min Sample Size</Label>
              <Input v-model.number="experimentForm.min_sample_size" type="number" min="10" />
            </div>
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" @click="showExperimentDialog = false">Cancel</Button>
          <Button @click="saveExperiment">Save</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>

    <!-- Results Dialog -->
    <Dialog v-model:open="showResultsDialog">
      <DialogContent class="max-w-3xl">
        <DialogHeader>
          <DialogTitle>Experiment Results</DialogTitle>
          <DialogDescription v-if="viewingResults">
            {{ viewingResults.experiment_name }}
          </DialogDescription>
        </DialogHeader>
        <div v-if="resultsLoading" class="flex justify-center py-12">
          <div class="border-primary h-8 w-8 animate-spin rounded-full border-b-2"></div>
        </div>
        <div v-else-if="viewingResults" class="space-y-6 py-4">
          <!-- Summary -->
          <Card :class="viewingResults.is_statistically_significant ? 'border-green-500' : ''">
            <CardContent class="py-4">
              <div class="flex items-center justify-between">
                <div>
                  <div class="text-lg font-semibold">
                    {{
                      viewingResults.is_statistically_significant
                        ? "Statistically Significant"
                        : "Not Yet Significant"
                    }}
                  </div>
                  <div class="text-muted-foreground text-sm">
                    Confidence: {{ formatPercent(viewingResults.confidence_level) }}
                  </div>
                </div>
                <div v-if="viewingResults.winner" class="text-right">
                  <Badge variant="default" class="text-lg">
                    Winner: Variant {{ viewingResults.winner }}
                  </Badge>
                </div>
              </div>
              <p class="text-muted-foreground mt-2 text-sm">
                {{ viewingResults.recommendation }}
              </p>
            </CardContent>
          </Card>

          <!-- Comparison -->
          <div class="grid grid-cols-2 gap-4">
            <Card>
              <CardHeader>
                <CardTitle class="text-base"
                  >Variant A: {{ viewingResults.variant_a.model_name }}</CardTitle
                >
                <CardDescription>{{ viewingResults.sample_size_a }} users</CardDescription>
              </CardHeader>
              <CardContent class="space-y-2">
                <div class="flex justify-between">
                  <span class="text-muted-foreground">Success Rate</span>
                  <span class="font-medium">{{
                    formatPercent(viewingResults.variant_a.success_rate)
                  }}</span>
                </div>
                <div class="flex justify-between">
                  <span class="text-muted-foreground">Avg Latency</span>
                  <span class="font-medium">{{
                    formatLatency(viewingResults.variant_a.avg_latency_ms)
                  }}</span>
                </div>
                <div class="flex justify-between">
                  <span class="text-muted-foreground">Avg Cost</span>
                  <span class="font-medium">{{
                    formatCost(
                      viewingResults.variant_a.total_cost_usd /
                        viewingResults.variant_a.total_requests || 0
                    )
                  }}</span>
                </div>
                <div v-if="viewingResults.variant_a.feedback_score" class="flex justify-between">
                  <span class="text-muted-foreground">Quality Score</span>
                  <span class="font-medium">{{
                    formatPercent(viewingResults.variant_a.feedback_score)
                  }}</span>
                </div>
              </CardContent>
            </Card>
            <Card>
              <CardHeader>
                <CardTitle class="text-base"
                  >Variant B: {{ viewingResults.variant_b.model_name }}</CardTitle
                >
                <CardDescription>{{ viewingResults.sample_size_b }} users</CardDescription>
              </CardHeader>
              <CardContent class="space-y-2">
                <div class="flex justify-between">
                  <span class="text-muted-foreground">Success Rate</span>
                  <span class="font-medium">{{
                    formatPercent(viewingResults.variant_b.success_rate)
                  }}</span>
                </div>
                <div class="flex justify-between">
                  <span class="text-muted-foreground">Avg Latency</span>
                  <span class="font-medium">{{
                    formatLatency(viewingResults.variant_b.avg_latency_ms)
                  }}</span>
                </div>
                <div class="flex justify-between">
                  <span class="text-muted-foreground">Avg Cost</span>
                  <span class="font-medium">{{
                    formatCost(
                      viewingResults.variant_b.total_cost_usd /
                        viewingResults.variant_b.total_requests || 0
                    )
                  }}</span>
                </div>
                <div v-if="viewingResults.variant_b.feedback_score" class="flex justify-between">
                  <span class="text-muted-foreground">Quality Score</span>
                  <span class="font-medium">{{
                    formatPercent(viewingResults.variant_b.feedback_score)
                  }}</span>
                </div>
              </CardContent>
            </Card>
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" @click="showResultsDialog = false">Close</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  </div>
</template>
