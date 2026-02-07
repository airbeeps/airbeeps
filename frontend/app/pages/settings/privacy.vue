<script setup lang="ts">
import { ref, onMounted, computed } from "vue";
import {
  Shield,
  Download,
  Trash2,
  RefreshCw,
  CheckCircle,
  XCircle,
  Layers,
  Users,
  Zap,
} from "lucide-vue-next";
import { Button } from "~/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "~/components/ui/card";
import { Switch } from "~/components/ui/switch";
import { Label } from "~/components/ui/label";
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
  breadcrumb: "Privacy Settings",
  layout: "default",
  middleware: ["auth"],
});

interface ConsentStatus {
  has_consent: boolean;
  consent_date?: string;
  allowed_memory_types?: string[];
}

interface MemoryStats {
  total_memories: number;
  by_type: Record<string, number>;
  oldest_memory?: string;
  newest_memory?: string;
}

interface CompactionStats {
  total_compactions: number;
  total_memories_merged: number;
  by_strategy: Record<string, { count: number; memories_merged: number }>;
  last_compaction?: string;
}

interface SharedPool {
  id: string;
  name: string;
  description?: string;
  pool_type: string;
  access_level: string;
  owner_id: string;
  memory_count?: number;
  member_count?: number;
}

// State
const consentStatus = ref<ConsentStatus | null>(null);
const memoryStats = ref<MemoryStats | null>(null);
const compactionStats = ref<CompactionStats | null>(null);
const sharedPools = ref<SharedPool[]>([]);
const loading = ref(true);
const actionLoading = ref(false);
const compactionLoading = ref(false);
const selectedCompactionStrategy = ref("HYBRID");

// Load consent status
const loadConsentStatus = async () => {
  loading.value = true;
  try {
    const { $api } = useNuxtApp();
    const response = await $api("/v1/memory/consent");
    consentStatus.value = response as ConsentStatus;
  } catch (error) {
    console.error("Failed to load consent status:", error);
  } finally {
    loading.value = false;
  }
};

// Load memory stats
const loadMemoryStats = async () => {
  try {
    const { $api } = useNuxtApp();
    const response = await $api("/v1/memory/stats");
    memoryStats.value = response as MemoryStats;
  } catch (error) {
    console.error("Failed to load memory stats:", error);
  }
};

// Load compaction stats
const loadCompactionStats = async () => {
  try {
    const { $api } = useNuxtApp();
    const response = await $api("/v1/memory/compact/stats");
    compactionStats.value = response as CompactionStats;
  } catch (error) {
    console.error("Failed to load compaction stats:", error);
  }
};

// Load shared pools
const loadSharedPools = async () => {
  try {
    const { $api } = useNuxtApp();
    const response = await $api("/v1/memory/pools");
    sharedPools.value = response as SharedPool[];
  } catch (error) {
    console.error("Failed to load shared pools:", error);
  }
};

// Run compaction
const runCompaction = async () => {
  compactionLoading.value = true;
  try {
    const { $api } = useNuxtApp();
    const response = await $api("/v1/memory/compact", {
      method: "POST",
      body: { strategy: selectedCompactionStrategy.value },
    });
    const result = response as { compacted: boolean; memories_merged?: number };
    if (result.compacted) {
      toast.success(`Compaction complete. ${result.memories_merged || 0} memories merged.`);
    } else {
      toast.info("No memories needed compaction.");
    }
    await loadMemoryStats();
    await loadCompactionStats();
  } catch (error: any) {
    toast.error(error?.message || "Failed to run compaction");
  } finally {
    compactionLoading.value = false;
  }
};

// Grant consent
const grantConsent = async () => {
  actionLoading.value = true;
  try {
    const { $api } = useNuxtApp();
    await $api("/v1/memory/consent", { method: "POST" });
    toast.success("Memory consent granted");
    await loadConsentStatus();
  } catch (error: any) {
    toast.error(error?.message || "Failed to grant consent");
  } finally {
    actionLoading.value = false;
  }
};

// Revoke consent
const revokeConsent = async () => {
  actionLoading.value = true;
  try {
    const { $api } = useNuxtApp();
    await $api("/v1/memory/consent", { method: "DELETE" });
    toast.success("Memory consent revoked");
    await loadConsentStatus();
    await loadMemoryStats();
  } catch (error: any) {
    toast.error(error?.message || "Failed to revoke consent");
  } finally {
    actionLoading.value = false;
  }
};

// Export memories
const exportMemories = async () => {
  actionLoading.value = true;
  try {
    const { $api } = useNuxtApp();
    const response = await $api("/v1/memory/export");
    // Download as JSON file
    const blob = new Blob([JSON.stringify(response, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `memories-export-${new Date().toISOString().split("T")[0]}.json`;
    a.click();
    URL.revokeObjectURL(url);
    toast.success("Memories exported successfully");
  } catch (error: any) {
    toast.error(error?.message || "Failed to export memories");
  } finally {
    actionLoading.value = false;
  }
};

// Delete all memories
const deleteAllMemories = async () => {
  actionLoading.value = true;
  try {
    const { $api } = useNuxtApp();
    await $api("/v1/memory/all", { method: "DELETE" });
    toast.success("All memories deleted");
    await loadMemoryStats();
  } catch (error: any) {
    toast.error(error?.message || "Failed to delete memories");
  } finally {
    actionLoading.value = false;
  }
};

// Format date
const formatDate = (dateStr?: string) => {
  if (!dateStr) return "N/A";
  return new Date(dateStr).toLocaleDateString();
};

onMounted(() => {
  loadConsentStatus();
  loadMemoryStats();
  loadCompactionStats();
  loadSharedPools();
});
</script>

<template>
  <div class="container mx-auto max-w-2xl space-y-6 py-6">
    <!-- Header -->
    <div>
      <h1 class="text-2xl font-bold">Privacy Settings</h1>
      <p class="text-muted-foreground">Manage how AI assistants remember information about you</p>
    </div>

    <!-- Loading state -->
    <div v-if="loading" class="flex justify-center py-12">
      <div class="border-primary h-8 w-8 animate-spin rounded-full border-b-2"></div>
    </div>

    <template v-else>
      <!-- Memory Consent -->
      <Card>
        <CardHeader>
          <div class="flex items-center gap-2">
            <Shield class="h-5 w-5" />
            <CardTitle>Memory Consent</CardTitle>
          </div>
          <CardDescription>
            Control whether AI assistants can store memories about your interactions
          </CardDescription>
        </CardHeader>
        <CardContent class="space-y-4">
          <div class="flex items-center justify-between">
            <div>
              <div class="font-medium">Enable Memory Storage</div>
              <div class="text-muted-foreground text-sm">
                Allow assistants to remember information to personalize responses
              </div>
            </div>
            <div class="flex items-center gap-2">
              <span v-if="consentStatus?.has_consent" class="text-sm text-green-600">
                <CheckCircle class="mr-1 inline h-4 w-4" />
                Enabled
              </span>
              <span v-else class="text-muted-foreground text-sm">
                <XCircle class="mr-1 inline h-4 w-4" />
                Disabled
              </span>
              <Switch
                :model-value="consentStatus?.has_consent ?? false"
                @update:model-value="(v) => (v ? grantConsent() : revokeConsent())"
                :disabled="actionLoading"
              />
            </div>
          </div>
          <div v-if="consentStatus?.consent_date" class="text-muted-foreground text-sm">
            Consent granted on: {{ formatDate(consentStatus.consent_date) }}
          </div>
        </CardContent>
      </Card>

      <!-- Memory Stats -->
      <Card v-if="consentStatus?.has_consent && memoryStats">
        <CardHeader>
          <CardTitle>Your Memories</CardTitle>
          <CardDescription> Statistics about stored memories </CardDescription>
        </CardHeader>
        <CardContent class="space-y-4">
          <div class="grid grid-cols-2 gap-4">
            <div>
              <div class="text-muted-foreground text-sm">Total Memories</div>
              <div class="text-2xl font-bold">{{ memoryStats.total_memories }}</div>
            </div>
            <div>
              <div class="text-muted-foreground text-sm">Memory Types</div>
              <div class="text-2xl font-bold">
                {{ Object.keys(memoryStats.by_type || {}).length }}
              </div>
            </div>
          </div>
          <div v-if="memoryStats.by_type && Object.keys(memoryStats.by_type).length > 0">
            <div class="text-muted-foreground mb-2 text-sm">By Type</div>
            <div class="space-y-1">
              <div
                v-for="(count, type) in memoryStats.by_type"
                :key="type"
                class="flex justify-between text-sm"
              >
                <span class="capitalize">{{ type.toLowerCase() }}</span>
                <span>{{ count }}</span>
              </div>
            </div>
          </div>
        </CardContent>
      </Card>

      <!-- Memory Compaction -->
      <Card v-if="consentStatus?.has_consent">
        <CardHeader>
          <div class="flex items-center gap-2">
            <Zap class="h-5 w-5" />
            <CardTitle>Memory Optimization</CardTitle>
          </div>
          <CardDescription>
            Compact and optimize your memories to reduce storage and improve retrieval
          </CardDescription>
        </CardHeader>
        <CardContent class="space-y-4">
          <div class="flex items-center justify-between">
            <div>
              <div class="font-medium">Run Compaction</div>
              <div class="text-muted-foreground text-sm">
                Merge similar or old memories to save space
              </div>
            </div>
            <div class="flex items-center gap-2">
              <Select v-model="selectedCompactionStrategy">
                <SelectTrigger class="w-[140px]">
                  <SelectValue placeholder="Strategy" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="HYBRID">Hybrid</SelectItem>
                  <SelectItem value="AGE">By Age</SelectItem>
                  <SelectItem value="SIMILARITY">By Similarity</SelectItem>
                  <SelectItem value="IMPORTANCE">By Importance</SelectItem>
                </SelectContent>
              </Select>
              <Button variant="outline" @click="runCompaction" :disabled="compactionLoading">
                <Zap v-if="!compactionLoading" class="mr-2 h-4 w-4" />
                <RefreshCw v-else class="mr-2 h-4 w-4 animate-spin" />
                Optimize
              </Button>
            </div>
          </div>
          <div
            v-if="compactionStats && compactionStats.total_compactions > 0"
            class="border-t pt-4"
          >
            <div class="text-muted-foreground mb-2 text-sm">Compaction History</div>
            <div class="grid grid-cols-2 gap-4">
              <div>
                <div class="text-2xl font-bold">{{ compactionStats.total_compactions }}</div>
                <div class="text-muted-foreground text-xs">Total Compactions</div>
              </div>
              <div>
                <div class="text-2xl font-bold">{{ compactionStats.total_memories_merged }}</div>
                <div class="text-muted-foreground text-xs">Memories Merged</div>
              </div>
            </div>
            <div v-if="compactionStats.last_compaction" class="text-muted-foreground mt-2 text-xs">
              Last compaction: {{ formatDate(compactionStats.last_compaction) }}
            </div>
          </div>
        </CardContent>
      </Card>

      <!-- Shared Memory Pools -->
      <Card v-if="consentStatus?.has_consent">
        <CardHeader>
          <div class="flex items-center gap-2">
            <Users class="h-5 w-5" />
            <CardTitle>Shared Memory Pools</CardTitle>
          </div>
          <CardDescription>
            Collaborate by sharing memories with teams or the community
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div
            v-if="sharedPools.length === 0"
            class="text-muted-foreground py-4 text-center text-sm"
          >
            You're not a member of any shared memory pools yet.
          </div>
          <div v-else class="space-y-3">
            <div
              v-for="pool in sharedPools"
              :key="pool.id"
              class="flex items-center justify-between rounded-lg border p-3"
            >
              <div class="flex items-center gap-3">
                <Layers class="text-muted-foreground h-5 w-5" />
                <div>
                  <div class="font-medium">{{ pool.name }}</div>
                  <div class="text-muted-foreground text-xs">
                    {{ pool.pool_type }} · {{ pool.access_level }}
                  </div>
                </div>
              </div>
              <Badge variant="secondary"> {{ pool.memory_count || 0 }} memories </Badge>
            </div>
          </div>
        </CardContent>
      </Card>

      <!-- Data Rights (GDPR) -->
      <Card>
        <CardHeader>
          <CardTitle>Your Data Rights</CardTitle>
          <CardDescription>
            Exercise your rights under GDPR and other privacy regulations
          </CardDescription>
        </CardHeader>
        <CardContent class="space-y-4">
          <!-- Export -->
          <div class="flex items-center justify-between">
            <div>
              <div class="font-medium">Export Your Data</div>
              <div class="text-muted-foreground text-sm">
                Download all memories stored about you in JSON format
              </div>
            </div>
            <Button
              variant="outline"
              @click="exportMemories"
              :disabled="actionLoading || !consentStatus?.has_consent"
            >
              <Download class="mr-2 h-4 w-4" />
              Export
            </Button>
          </div>

          <!-- Delete All -->
          <div class="flex items-center justify-between border-t pt-4">
            <div>
              <div class="font-medium">Delete All Memories</div>
              <div class="text-muted-foreground text-sm">
                Permanently delete all stored memories (cannot be undone)
              </div>
            </div>
            <AlertDialog>
              <AlertDialogTrigger as-child>
                <Button variant="destructive" :disabled="actionLoading">
                  <Trash2 class="mr-2 h-4 w-4" />
                  Delete All
                </Button>
              </AlertDialogTrigger>
              <AlertDialogContent>
                <AlertDialogHeader>
                  <AlertDialogTitle>Delete All Memories?</AlertDialogTitle>
                  <AlertDialogDescription>
                    This will permanently delete all memories stored about you. This action cannot
                    be undone.
                  </AlertDialogDescription>
                </AlertDialogHeader>
                <AlertDialogFooter>
                  <AlertDialogCancel>Cancel</AlertDialogCancel>
                  <AlertDialogAction @click="deleteAllMemories"> Delete All </AlertDialogAction>
                </AlertDialogFooter>
              </AlertDialogContent>
            </AlertDialog>
          </div>
        </CardContent>
      </Card>

      <!-- Info -->
      <Card class="bg-muted/30">
        <CardContent class="pt-6">
          <div class="text-muted-foreground text-sm">
            <p class="mb-2">
              <strong>What are memories?</strong> Memories help AI assistants personalize responses
              by remembering facts, preferences, and context from your conversations.
            </p>
            <p class="mb-2">
              <strong>Your privacy:</strong> All memories are encrypted at rest and only accessible
              to you. Revoking consent stops new memories from being stored.
            </p>
            <p>
              <strong>Retention:</strong> Memories are automatically deleted after the configured
              retention period (typically 90 days of inactivity).
            </p>
          </div>
        </CardContent>
      </Card>
    </template>
  </div>
</template>
