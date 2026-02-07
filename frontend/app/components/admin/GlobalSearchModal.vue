<script setup lang="ts">
import { ref, computed, watch, onMounted, onUnmounted } from "vue";
import { useDebounceFn } from "@vueuse/core";
import {
  Search,
  Bot,
  Brain,
  Database,
  Users,
  MessageSquare,
  Loader2,
  ArrowRight,
  Command,
} from "lucide-vue-next";
import { Dialog, DialogContent } from "~/components/ui/dialog";
import { Input } from "~/components/ui/input";
import { Badge } from "~/components/ui/badge";

const { $api } = useNuxtApp();
const router = useRouter();
const { t } = useI18n();

// State
const open = defineModel<boolean>("open", { default: false });
const query = ref("");
const loading = ref(false);
const activeIndex = ref(0);

interface SearchResult {
  id: string;
  type: "assistant" | "model" | "kb" | "user" | "conversation";
  title: string;
  subtitle?: string;
  url: string;
}

interface SearchResults {
  assistants: SearchResult[];
  models: SearchResult[];
  kbs: SearchResult[];
  users: SearchResult[];
  conversations: SearchResult[];
}

const results = ref<SearchResults>({
  assistants: [],
  models: [],
  kbs: [],
  users: [],
  conversations: [],
});

// Flatten results for keyboard navigation
const flatResults = computed(() => {
  const flat: SearchResult[] = [];
  if (results.value.assistants.length) flat.push(...results.value.assistants);
  if (results.value.models.length) flat.push(...results.value.models);
  if (results.value.kbs.length) flat.push(...results.value.kbs);
  if (results.value.users.length) flat.push(...results.value.users);
  if (results.value.conversations.length) flat.push(...results.value.conversations);
  return flat;
});

const hasResults = computed(() => flatResults.value.length > 0);

// Type configuration
const typeConfig = {
  assistant: { icon: Bot, label: "Assistants", color: "bg-blue-500/10 text-blue-600" },
  model: { icon: Brain, label: "Models", color: "bg-purple-500/10 text-purple-600" },
  kb: { icon: Database, label: "Knowledge Bases", color: "bg-green-500/10 text-green-600" },
  user: { icon: Users, label: "Users", color: "bg-orange-500/10 text-orange-600" },
  conversation: {
    icon: MessageSquare,
    label: "Conversations",
    color: "bg-gray-500/10 text-gray-600",
  },
};

// Perform search
const doSearch = useDebounceFn(async () => {
  if (!query.value.trim()) {
    results.value = { assistants: [], models: [], kbs: [], users: [], conversations: [] };
    return;
  }

  loading.value = true;
  activeIndex.value = 0;

  try {
    // Search all entities in parallel
    const [assistantsRes, modelsRes, kbsRes, usersRes, conversationsRes] = await Promise.all([
      $api(`/v1/admin/assistants?search=${encodeURIComponent(query.value)}&size=5`).catch(() => ({
        items: [],
      })),
      $api(`/v1/admin/all-models?search=${encodeURIComponent(query.value)}`).catch(() => []),
      $api(`/v1/admin/rag/knowledge-bases?search=${encodeURIComponent(query.value)}&size=5`).catch(
        () => ({ items: [] })
      ),
      $api(`/v1/admin/users?search=${encodeURIComponent(query.value)}&size=5`).catch(() => ({
        items: [],
      })),
      $api(`/v1/admin/conversations?search=${encodeURIComponent(query.value)}&size=5`).catch(
        () => ({ items: [] })
      ),
    ]);

    results.value = {
      assistants: ((assistantsRes as any).items || []).slice(0, 5).map((a: any) => ({
        id: a.id,
        type: "assistant",
        title: a.name,
        subtitle: a.mode === "RAG" ? "RAG Mode" : "General",
        url: `/admin/assistants/${a.id}`,
      })),
      models: (Array.isArray(modelsRes) ? modelsRes : []).slice(0, 5).map((m: any) => ({
        id: m.id,
        type: "model",
        title: m.display_name || m.name,
        subtitle: m.provider?.name,
        url: `/admin/models`,
      })),
      kbs: ((kbsRes as any).items || []).slice(0, 5).map((kb: any) => ({
        id: kb.id,
        type: "kb",
        title: kb.name,
        subtitle: `${kb.document_count || 0} documents`,
        url: `/admin/kbs/${kb.id}`,
      })),
      users: ((usersRes as any).items || []).slice(0, 5).map((u: any) => ({
        id: u.id,
        type: "user",
        title: u.name || u.email,
        subtitle: u.email,
        url: `/admin/users/${u.id}`,
      })),
      conversations: ((conversationsRes as any).items || []).slice(0, 5).map((c: any) => ({
        id: c.id,
        type: "conversation",
        title: c.title || "Untitled Conversation",
        subtitle: `${c.message_count || 0} messages`,
        url: `/admin/conversations`,
      })),
    };
  } catch (error) {
    console.error("Search failed:", error);
  } finally {
    loading.value = false;
  }
}, 300);

// Watch query changes
watch(query, () => {
  doSearch();
});

// Navigate to result
const navigateTo = (result: SearchResult) => {
  open.value = false;
  query.value = "";
  router.push(result.url);
};

// Keyboard navigation
const handleKeydown = (e: KeyboardEvent) => {
  if (!hasResults.value) return;

  switch (e.key) {
    case "ArrowDown":
      e.preventDefault();
      activeIndex.value = Math.min(activeIndex.value + 1, flatResults.value.length - 1);
      break;
    case "ArrowUp":
      e.preventDefault();
      activeIndex.value = Math.max(activeIndex.value - 1, 0);
      break;
    case "Enter":
      e.preventDefault();
      if (flatResults.value[activeIndex.value]) {
        navigateTo(flatResults.value[activeIndex.value]);
      }
      break;
  }
};

// Global keyboard shortcut (Cmd/Ctrl + K)
const handleGlobalKeydown = (e: KeyboardEvent) => {
  if ((e.metaKey || e.ctrlKey) && e.key === "k") {
    e.preventDefault();
    open.value = true;
  }
};

onMounted(() => {
  window.addEventListener("keydown", handleGlobalKeydown);
});

onUnmounted(() => {
  window.removeEventListener("keydown", handleGlobalKeydown);
});

// Reset on close
watch(open, (isOpen) => {
  if (!isOpen) {
    query.value = "";
    results.value = { assistants: [], models: [], kbs: [], users: [], conversations: [] };
    activeIndex.value = 0;
  }
});

// Render category
const renderCategory = (items: SearchResult[], type: keyof typeof typeConfig) => {
  if (!items.length) return null;
  const config = typeConfig[type];
  return { items, config, type };
};

const categories = computed(() => {
  return [
    renderCategory(results.value.assistants, "assistant"),
    renderCategory(results.value.models, "model"),
    renderCategory(results.value.kbs, "kb"),
    renderCategory(results.value.users, "user"),
    renderCategory(results.value.conversations, "conversation"),
  ].filter(Boolean);
});

// Get flat index for an item
const getFlatIndex = (item: SearchResult) => {
  return flatResults.value.findIndex((r) => r.id === item.id && r.type === item.type);
};
</script>

<template>
  <Dialog v-model:open="open">
    <DialogContent class="max-w-2xl gap-0 overflow-hidden p-0" @keydown="handleKeydown">
      <!-- Search input -->
      <div class="flex items-center border-b px-4">
        <Search class="text-muted-foreground h-5 w-5 shrink-0" />
        <Input
          v-model="query"
          :placeholder="t('admin.globalSearch.placeholder')"
          class="h-14 border-0 text-base focus-visible:ring-0 focus-visible:ring-offset-0"
          autofocus
        />
        <div class="text-muted-foreground flex items-center gap-1 text-xs">
          <kbd
            class="bg-muted pointer-events-none inline-flex h-5 items-center gap-1 rounded border px-1.5 font-mono text-[10px] font-medium opacity-100 select-none"
          >
            <Command class="h-3 w-3" />K
          </kbd>
        </div>
      </div>

      <!-- Results -->
      <div class="max-h-[400px] overflow-y-auto">
        <!-- Loading state -->
        <div v-if="loading" class="flex items-center justify-center py-8">
          <Loader2 class="text-muted-foreground h-6 w-6 animate-spin" />
        </div>

        <!-- Empty state -->
        <div v-else-if="query && !hasResults" class="text-muted-foreground py-8 text-center">
          <Search class="mx-auto mb-2 h-8 w-8 opacity-50" />
          <p>{{ t("admin.globalSearch.noResults") }}</p>
        </div>

        <!-- Initial state -->
        <div v-else-if="!query" class="text-muted-foreground py-8 text-center">
          <p class="text-sm">{{ t("admin.globalSearch.hint") }}</p>
        </div>

        <!-- Results list -->
        <div v-else class="py-2">
          <template v-for="category in categories" :key="category?.type">
            <div v-if="category" class="px-2 py-1">
              <div
                class="text-muted-foreground flex items-center gap-2 px-2 py-1.5 text-xs font-medium"
              >
                <component :is="category.config.icon" class="h-4 w-4" />
                {{ category.config.label }}
              </div>
              <div
                v-for="item in category.items"
                :key="item.id"
                class="flex cursor-pointer items-center justify-between gap-2 rounded-md px-2 py-2 transition-colors"
                :class="[
                  getFlatIndex(item) === activeIndex
                    ? 'bg-accent text-accent-foreground'
                    : 'hover:bg-muted/50',
                ]"
                @click="navigateTo(item)"
                @mouseenter="activeIndex = getFlatIndex(item)"
              >
                <div class="flex min-w-0 items-center gap-3">
                  <Badge variant="outline" :class="category.config.color" class="shrink-0">
                    <component :is="category.config.icon" class="h-3 w-3" />
                  </Badge>
                  <div class="min-w-0">
                    <div class="truncate font-medium">{{ item.title }}</div>
                    <div v-if="item.subtitle" class="text-muted-foreground truncate text-xs">
                      {{ item.subtitle }}
                    </div>
                  </div>
                </div>
                <ArrowRight class="text-muted-foreground h-4 w-4 shrink-0" />
              </div>
            </div>
          </template>
        </div>
      </div>

      <!-- Footer -->
      <div
        class="text-muted-foreground bg-muted/30 flex items-center justify-between border-t px-4 py-2 text-xs"
      >
        <div class="flex items-center gap-4">
          <span class="flex items-center gap-1">
            <kbd class="bg-background rounded border px-1.5 py-0.5">↑</kbd>
            <kbd class="bg-background rounded border px-1.5 py-0.5">↓</kbd>
            {{ t("admin.globalSearch.navigate") }}
          </span>
          <span class="flex items-center gap-1">
            <kbd class="bg-background rounded border px-1.5 py-0.5">↵</kbd>
            {{ t("admin.globalSearch.select") }}
          </span>
        </div>
        <span class="flex items-center gap-1">
          <kbd class="bg-background rounded border px-1.5 py-0.5">esc</kbd>
          {{ t("admin.globalSearch.close") }}
        </span>
      </div>
    </DialogContent>
  </Dialog>
</template>
