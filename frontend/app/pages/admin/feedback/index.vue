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
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "~/components/ui/dialog";
import {
  ThumbsUp,
  ThumbsDown,
  Search,
  RefreshCw,
  ChevronLeft,
  ChevronRight,
  MessageSquare,
  User,
  Bot,
  Trash2,
  Eye,
} from "lucide-vue-next";
import DateRangeFilter from "~/components/admin/DateRangeFilter.vue";

interface Feedback {
  id: string;
  message_id: string;
  conversation_id: string;
  assistant_id: string;
  user_id: string;
  rating: "UP" | "DOWN";
  reasons: string[];
  comment: string | null;
  extra_data: Record<string, any>;
  created_at: string;
  updated_at: string;
  user_email: string | null;
  user_name: string | null;
  assistant_name: string | null;
  message_content: string | null;
}

interface FeedbackStats {
  total_feedback: number;
  thumbs_up: number;
  thumbs_down: number;
  period_days: number;
  feedback_by_rating: Record<string, number>;
  top_reasons: { reason: string; count: number }[];
  feedback_by_assistant: {
    assistant_id: string;
    assistant_name: string;
    total: number;
    thumbs_up: number;
    thumbs_down: number;
  }[];
}

interface Assistant {
  id: string;
  name: string;
}

const { t } = useI18n();
const { $api } = useNuxtApp();

definePageMeta({
  breadcrumb: "admin.feedback.title",
  layout: "admin",
});

// State
const loading = ref(false);
const feedbacks = ref<Feedback[]>([]);
const total = ref(0);
const offset = ref(0);
const limit = ref(25);
const stats = ref<FeedbackStats | null>(null);
const assistants = ref<Assistant[]>([]);
const selectedFeedback = ref<Feedback | null>(null);
const detailDialogOpen = ref(false);
const deleteDialogOpen = ref(false);
const feedbackToDelete = ref<Feedback | null>(null);
const deleting = ref(false);

// Filters
const search = ref("");
const selectedRating = ref<string>("all");
const selectedAssistant = ref<string>("all");
const startDate = ref<string>("");
const endDate = ref<string>("");

// Rating options
const ratingOptions = [
  { value: "all", label: "All Ratings" },
  { value: "UP", label: "Thumbs Up" },
  { value: "DOWN", label: "Thumbs Down" },
];

// Computed
const currentPage = computed(() => Math.floor(offset.value / limit.value) + 1);
const totalPages = computed(() => Math.ceil(total.value / limit.value));
const hasNextPage = computed(() => offset.value + limit.value < total.value);
const hasPrevPage = computed(() => offset.value > 0);

const satisfactionRate = computed(() => {
  if (!stats.value || stats.value.total_feedback === 0) return 0;
  return Math.round((stats.value.thumbs_up / stats.value.total_feedback) * 100);
});

// Methods
const fetchFeedback = async () => {
  loading.value = true;
  try {
    const params = new URLSearchParams();
    params.set("offset", offset.value.toString());
    params.set("limit", limit.value.toString());

    if (search.value) params.set("search", search.value);
    if (selectedRating.value && selectedRating.value !== "all")
      params.set("rating", selectedRating.value);
    if (selectedAssistant.value && selectedAssistant.value !== "all")
      params.set("assistant_id", selectedAssistant.value);
    if (startDate.value) params.set("start_date", startDate.value);
    if (endDate.value) params.set("end_date", endDate.value);

    const response = await $api<{ items: Feedback[]; total: number }>(
      `/v1/admin/feedback?${params.toString()}`
    );

    feedbacks.value = response.items || [];
    total.value = response.total || 0;
  } catch (error) {
    console.error("Failed to fetch feedback:", error);
  } finally {
    loading.value = false;
  }
};

const fetchStats = async () => {
  try {
    const response = await $api<FeedbackStats>(`/v1/admin/feedback/stats?days=30`);
    stats.value = response;
  } catch (error) {
    console.error("Failed to fetch feedback stats:", error);
  }
};

const fetchAssistants = async () => {
  try {
    const response = await $api<{ items: Assistant[] }>(`/v1/admin/assistants?size=100`);
    assistants.value = response.items || [];
  } catch (error) {
    console.error("Failed to fetch assistants:", error);
  }
};

const handleSearch = () => {
  offset.value = 0;
  fetchFeedback();
};

const handleFilterChange = () => {
  offset.value = 0;
  fetchFeedback();
};

const handleDateRangeChange = (range: { start: string; end: string }) => {
  startDate.value = range.start;
  endDate.value = range.end;
  offset.value = 0;
  fetchFeedback();
};

const nextPage = () => {
  if (hasNextPage.value) {
    offset.value += limit.value;
    fetchFeedback();
  }
};

const prevPage = () => {
  if (hasPrevPage.value) {
    offset.value = Math.max(0, offset.value - limit.value);
    fetchFeedback();
  }
};

const formatDate = (dateStr: string) => {
  return new Date(dateStr).toLocaleString();
};

const viewFeedback = (feedback: Feedback) => {
  selectedFeedback.value = feedback;
  detailDialogOpen.value = true;
};

const confirmDelete = (feedback: Feedback) => {
  feedbackToDelete.value = feedback;
  deleteDialogOpen.value = true;
};

const deleteFeedback = async () => {
  if (!feedbackToDelete.value) return;

  deleting.value = true;
  try {
    await $api(`/v1/admin/feedback/${feedbackToDelete.value.id}`, {
      method: "DELETE",
    });
    deleteDialogOpen.value = false;
    feedbackToDelete.value = null;
    await fetchFeedback();
    await fetchStats();
  } catch (error) {
    console.error("Failed to delete feedback:", error);
  } finally {
    deleting.value = false;
  }
};

// Initialize
onMounted(() => {
  fetchFeedback();
  fetchStats();
  fetchAssistants();
});
</script>

<template>
  <div class="container mx-auto space-y-6 p-6">
    <!-- Header -->
    <div class="flex items-center justify-between">
      <div>
        <h1 class="text-2xl font-bold">{{ t("admin.feedback.title") }}</h1>
        <p class="text-muted-foreground">{{ t("admin.feedback.description") }}</p>
      </div>
      <Button
        variant="outline"
        size="sm"
        @click="
          fetchFeedback();
          fetchStats();
        "
        :disabled="loading"
      >
        <RefreshCw :class="['mr-2 h-4 w-4', loading && 'animate-spin']" />
        {{ t("common.refresh") }}
      </Button>
    </div>

    <!-- Stats Cards -->
    <div v-if="stats" class="grid gap-4 md:grid-cols-4">
      <Card>
        <CardHeader class="pb-2">
          <CardDescription>{{ t("admin.feedback.stats.total") }}</CardDescription>
          <CardTitle class="text-3xl">{{ stats.total_feedback.toLocaleString() }}</CardTitle>
        </CardHeader>
        <CardContent>
          <p class="text-muted-foreground text-xs">
            {{ t("admin.feedback.stats.lastNDays", { days: stats.period_days }) }}
          </p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader class="pb-2">
          <CardDescription>{{ t("admin.feedback.stats.thumbsUp") }}</CardDescription>
          <CardTitle class="flex items-center gap-2 text-3xl text-emerald-600">
            <ThumbsUp class="h-6 w-6" />
            {{ stats.thumbs_up.toLocaleString() }}
          </CardTitle>
        </CardHeader>
      </Card>

      <Card>
        <CardHeader class="pb-2">
          <CardDescription>{{ t("admin.feedback.stats.thumbsDown") }}</CardDescription>
          <CardTitle class="flex items-center gap-2 text-3xl text-rose-600">
            <ThumbsDown class="h-6 w-6" />
            {{ stats.thumbs_down.toLocaleString() }}
          </CardTitle>
        </CardHeader>
      </Card>

      <Card>
        <CardHeader class="pb-2">
          <CardDescription>{{ t("admin.feedback.stats.satisfaction") }}</CardDescription>
          <CardTitle
            class="text-3xl"
            :class="
              satisfactionRate >= 70
                ? 'text-emerald-600'
                : satisfactionRate >= 50
                  ? 'text-amber-600'
                  : 'text-rose-600'
            "
          >
            {{ satisfactionRate }}%
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div class="bg-muted h-2 w-full rounded-full">
            <div
              class="h-2 rounded-full transition-all"
              :class="
                satisfactionRate >= 70
                  ? 'bg-emerald-500'
                  : satisfactionRate >= 50
                    ? 'bg-amber-500'
                    : 'bg-rose-500'
              "
              :style="{ width: `${satisfactionRate}%` }"
            />
          </div>
        </CardContent>
      </Card>
    </div>

    <!-- Top Reasons Card -->
    <div v-if="stats && stats.top_reasons.length > 0" class="grid gap-4 md:grid-cols-2">
      <Card>
        <CardHeader>
          <CardTitle class="text-lg">{{ t("admin.feedback.stats.topReasons") }}</CardTitle>
        </CardHeader>
        <CardContent>
          <div class="space-y-2">
            <div
              v-for="reason in stats.top_reasons.slice(0, 5)"
              :key="reason.reason"
              class="flex items-center justify-between"
            >
              <span class="text-sm">{{ reason.reason }}</span>
              <Badge variant="secondary">{{ reason.count }}</Badge>
            </div>
          </div>
        </CardContent>
      </Card>

      <Card v-if="stats.feedback_by_assistant.length > 0">
        <CardHeader>
          <CardTitle class="text-lg">{{ t("admin.feedback.stats.byAssistant") }}</CardTitle>
        </CardHeader>
        <CardContent>
          <div class="space-y-2">
            <div
              v-for="asst in stats.feedback_by_assistant.slice(0, 5)"
              :key="asst.assistant_id"
              class="flex items-center justify-between"
            >
              <span class="max-w-[150px] truncate text-sm" :title="asst.assistant_name">{{
                asst.assistant_name
              }}</span>
              <div class="flex items-center gap-2">
                <Badge variant="outline" class="text-emerald-600">
                  <ThumbsUp class="mr-1 h-3 w-3" />{{ asst.thumbs_up }}
                </Badge>
                <Badge variant="outline" class="text-rose-600">
                  <ThumbsDown class="mr-1 h-3 w-3" />{{ asst.thumbs_down }}
                </Badge>
              </div>
            </div>
          </div>
        </CardContent>
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
              :placeholder="t('admin.feedback.searchPlaceholder')"
              class="pl-10"
              @keyup.enter="handleSearch"
            />
          </div>

          <!-- Rating Filter -->
          <Select v-model="selectedRating" @update:modelValue="handleFilterChange">
            <SelectTrigger class="w-[150px]">
              <SelectValue :placeholder="t('admin.feedback.filterByRating')" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem v-for="opt in ratingOptions" :key="opt.value" :value="opt.value">
                {{ opt.label }}
              </SelectItem>
            </SelectContent>
          </Select>

          <!-- Assistant Filter -->
          <Select v-model="selectedAssistant" @update:modelValue="handleFilterChange">
            <SelectTrigger class="w-[180px]">
              <SelectValue :placeholder="t('admin.feedback.filterByAssistant')" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">{{ t("admin.feedback.allAssistants") }}</SelectItem>
              <SelectItem v-for="asst in assistants" :key="asst.id" :value="asst.id">
                {{ asst.name }}
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
                <TableHead class="w-[180px]">{{ t("admin.feedback.table.timestamp") }}</TableHead>
                <TableHead>{{ t("admin.feedback.table.user") }}</TableHead>
                <TableHead>{{ t("admin.feedback.table.assistant") }}</TableHead>
                <TableHead class="w-[100px]">{{ t("admin.feedback.table.rating") }}</TableHead>
                <TableHead>{{ t("admin.feedback.table.reasons") }}</TableHead>
                <TableHead class="max-w-[200px]">{{ t("admin.feedback.table.comment") }}</TableHead>
                <TableHead class="w-[100px]">{{ t("common.actions") }}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              <TableRow v-if="loading">
                <TableCell colspan="7" class="py-8 text-center">
                  <RefreshCw class="text-muted-foreground mx-auto h-6 w-6 animate-spin" />
                </TableCell>
              </TableRow>
              <TableRow v-else-if="feedbacks.length === 0">
                <TableCell colspan="7" class="text-muted-foreground py-8 text-center">
                  <MessageSquare class="mx-auto mb-2 h-12 w-12 opacity-50" />
                  <p>{{ t("admin.feedback.noFeedback") }}</p>
                </TableCell>
              </TableRow>
              <TableRow v-for="fb in feedbacks" :key="fb.id">
                <TableCell class="font-mono text-xs">
                  {{ formatDate(fb.created_at) }}
                </TableCell>
                <TableCell>
                  <div class="flex items-center gap-2">
                    <User class="text-muted-foreground h-4 w-4" />
                    <span class="max-w-[150px] truncate" :title="fb.user_email || 'Unknown'">
                      {{ fb.user_email || t("admin.feedback.unknownUser") }}
                    </span>
                  </div>
                </TableCell>
                <TableCell>
                  <div class="flex items-center gap-2">
                    <Bot class="text-muted-foreground h-4 w-4" />
                    <span class="max-w-[120px] truncate" :title="fb.assistant_name || 'Unknown'">
                      {{ fb.assistant_name || t("admin.feedback.unknownAssistant") }}
                    </span>
                  </div>
                </TableCell>
                <TableCell>
                  <Badge
                    :class="
                      fb.rating === 'UP'
                        ? 'bg-emerald-100 text-emerald-700'
                        : 'bg-rose-100 text-rose-700'
                    "
                    class="gap-1"
                  >
                    <ThumbsUp v-if="fb.rating === 'UP'" class="h-3 w-3" />
                    <ThumbsDown v-else class="h-3 w-3" />
                    {{ fb.rating }}
                  </Badge>
                </TableCell>
                <TableCell>
                  <div class="flex flex-wrap gap-1">
                    <Badge
                      v-for="reason in fb.reasons.slice(0, 2)"
                      :key="reason"
                      variant="outline"
                      class="text-xs"
                    >
                      {{ reason }}
                    </Badge>
                    <Badge v-if="fb.reasons.length > 2" variant="outline" class="text-xs">
                      +{{ fb.reasons.length - 2 }}
                    </Badge>
                  </div>
                </TableCell>
                <TableCell class="max-w-[200px]">
                  <span class="block truncate text-sm" :title="fb.comment || ''">
                    {{ fb.comment || "-" }}
                  </span>
                </TableCell>
                <TableCell>
                  <div class="flex items-center gap-1">
                    <Button
                      variant="ghost"
                      size="icon"
                      @click="viewFeedback(fb)"
                      :title="t('common.view')"
                    >
                      <Eye class="h-4 w-4" />
                    </Button>
                    <Button
                      variant="ghost"
                      size="icon"
                      @click="confirmDelete(fb)"
                      :title="t('common.delete')"
                      class="text-destructive hover:text-destructive"
                    >
                      <Trash2 class="h-4 w-4" />
                    </Button>
                  </div>
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
              {{ t("admin.feedback.page") }} {{ currentPage }} / {{ totalPages }}
            </span>
            <Button variant="outline" size="sm" :disabled="!hasNextPage" @click="nextPage">
              <ChevronRight class="h-4 w-4" />
            </Button>
          </div>
        </div>
      </CardContent>
    </Card>

    <!-- Detail Dialog -->
    <Dialog v-model:open="detailDialogOpen">
      <DialogContent class="max-w-2xl">
        <DialogHeader>
          <DialogTitle>{{ t("admin.feedback.detailTitle") }}</DialogTitle>
          <DialogDescription>{{ t("admin.feedback.detailDescription") }}</DialogDescription>
        </DialogHeader>
        <div v-if="selectedFeedback" class="space-y-4">
          <div class="grid grid-cols-2 gap-4">
            <div>
              <label class="text-muted-foreground text-sm font-medium">{{
                t("admin.feedback.table.user")
              }}</label>
              <p class="mt-1">
                {{ selectedFeedback.user_email || t("admin.feedback.unknownUser") }}
              </p>
            </div>
            <div>
              <label class="text-muted-foreground text-sm font-medium">{{
                t("admin.feedback.table.assistant")
              }}</label>
              <p class="mt-1">
                {{ selectedFeedback.assistant_name || t("admin.feedback.unknownAssistant") }}
              </p>
            </div>
            <div>
              <label class="text-muted-foreground text-sm font-medium">{{
                t("admin.feedback.table.rating")
              }}</label>
              <div class="mt-1">
                <Badge
                  :class="
                    selectedFeedback.rating === 'UP'
                      ? 'bg-emerald-100 text-emerald-700'
                      : 'bg-rose-100 text-rose-700'
                  "
                  class="gap-1"
                >
                  <ThumbsUp v-if="selectedFeedback.rating === 'UP'" class="h-3 w-3" />
                  <ThumbsDown v-else class="h-3 w-3" />
                  {{
                    selectedFeedback.rating === "UP"
                      ? t("admin.feedback.thumbsUp")
                      : t("admin.feedback.thumbsDown")
                  }}
                </Badge>
              </div>
            </div>
            <div>
              <label class="text-muted-foreground text-sm font-medium">{{
                t("admin.feedback.table.timestamp")
              }}</label>
              <p class="mt-1">{{ formatDate(selectedFeedback.created_at) }}</p>
            </div>
          </div>

          <div v-if="selectedFeedback.reasons.length > 0">
            <label class="text-muted-foreground text-sm font-medium">{{
              t("admin.feedback.table.reasons")
            }}</label>
            <div class="mt-1 flex flex-wrap gap-2">
              <Badge v-for="reason in selectedFeedback.reasons" :key="reason" variant="secondary">
                {{ reason }}
              </Badge>
            </div>
          </div>

          <div v-if="selectedFeedback.comment">
            <label class="text-muted-foreground text-sm font-medium">{{
              t("admin.feedback.table.comment")
            }}</label>
            <p class="bg-muted mt-1 rounded-lg p-3 text-sm">{{ selectedFeedback.comment }}</p>
          </div>

          <div v-if="selectedFeedback.message_content">
            <label class="text-muted-foreground text-sm font-medium">{{
              t("admin.feedback.messageContent")
            }}</label>
            <p class="bg-muted mt-1 rounded-lg p-3 text-sm whitespace-pre-wrap">
              {{ selectedFeedback.message_content }}
            </p>
          </div>
        </div>
      </DialogContent>
    </Dialog>

    <!-- Delete Confirmation Dialog -->
    <Dialog v-model:open="deleteDialogOpen">
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{{ t("admin.feedback.deleteTitle") }}</DialogTitle>
          <DialogDescription>{{ t("admin.feedback.deleteDescription") }}</DialogDescription>
        </DialogHeader>
        <div class="mt-4 flex justify-end gap-2">
          <Button variant="outline" @click="deleteDialogOpen = false" :disabled="deleting">
            {{ t("common.cancel") }}
          </Button>
          <Button variant="destructive" @click="deleteFeedback" :disabled="deleting">
            <Trash2 v-if="!deleting" class="mr-2 h-4 w-4" />
            <RefreshCw v-else class="mr-2 h-4 w-4 animate-spin" />
            {{ t("common.delete") }}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  </div>
</template>
