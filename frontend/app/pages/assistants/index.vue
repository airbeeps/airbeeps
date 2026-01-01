<script setup lang="ts">
import { computed, ref } from "vue";
import { Card, CardContent, CardHeader, CardTitle, CardFooter } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import {
  Search,
  LayoutGrid,
  Database,
  Code,
  PenTool,
  BarChart3,
  Palette,
  GraduationCap,
  Zap,
  MoreHorizontal,
  Sparkles,
  Plus,
  User,
  Edit,
  Copy,
  Pin,
  PinOff,
  ChevronLeft,
  ChevronRight,
} from "lucide-vue-next";
import type { Assistant } from "~/types/api";
import { useSidebar } from "@/components/ui/sidebar";
import { useUserStore } from "~/stores/user";
import { useConfigStore } from "~/stores/config";
import { toast } from "vue-sonner";

const { t } = useI18n();
const requestUrl = useRequestURL();
const origin = requestUrl.origin;

definePageMeta({
  keepalive: true,
});

// Force rebuild for hydration fix
useHead({
  title: t("pageTitle.assistants"),
});

if (import.meta.server) {
  useSeoMeta({
    description: () => t("assistants.description"),
  });
}

const { isMobile } = useSidebar();

const runtimeConfig = useRuntimeConfig();
const userStore = useUserStore();
const configStore = useConfigStore();
const currentUser = computed(() => userStore.currentUser);

// Config
const allowCreate = ref(true);
onMounted(async () => {
  const config = await configStore.getConfig();
  const val = config.allow_user_create_assistants;
  // Robustly handle various truthy/falsy values
  allowCreate.value = String(val).toLowerCase() !== "false";
});

const showCreateButton = computed(() => {
  return !!(currentUser.value?.is_superuser && allowCreate.value);
});

// Filter state
const selectedMode = ref<string | undefined>(undefined);
const scope = ref<string | undefined>(undefined);
const searchQuery = ref("");

const modeOptions = [
  { value: "GENERAL", label: "General", icon: Sparkles },
  { value: "RAG", label: "RAG", icon: Database },
];

// Build query parameters
const queryParams = computed(() => {
  const params: Record<string, string> = {
    sort_by: "usage_count",
    order: "desc",
  };
  if (selectedMode.value) {
    params.mode = selectedMode.value;
  }
  if (scope.value) {
    params.scope = scope.value;
  }
  if (searchQuery.value) {
    params.search = searchQuery.value;
  }
  return params;
});

const {
  data: assistants,
  pending,
  error,
  refresh,
} = await useAPI<Assistant[]>("/v1/assistants", {
  query: queryParams,
});

// Fetch pinned assistants separately for the top section
const { data: pinnedAssistants, refresh: refreshPinned } = await useAPI<Assistant[]>(
  "/v1/assistants",
  {
    query: { scope: "pinned", limit: 100 },
    immediate: false,
  }
);

if (currentUser.value) {
  await refreshPinned();
}

const assistantList = computed(() => assistants.value ?? []);
const pinnedAssistantList = computed(() => pinnedAssistants.value ?? []);

// Use localized assistant list
const localizedAssistants = useLocalizedAssistants(assistantList);
const localizedPinnedAssistants = useLocalizedAssistants(pinnedAssistantList);

const capabilityLabelKeys: Record<string, string> = {
  chat: "assistants.capabilities.chat",
  completion: "assistants.capabilities.completion",
  embedding: "assistants.capabilities.embedding",
  vision: "assistants.capabilities.vision",
  audio: "assistants.capabilities.audio",
  function_calling: "assistants.capabilities.function_calling",
  tool_use: "assistants.capabilities.tool_use",
  code: "assistants.capabilities.code",
  image_generation: "assistants.capabilities.image_generation",
};

const capabilityColorClasses: Record<string, string> = {
  chat: "bg-stone-100 text-stone-800 border-stone-200",
  completion: "bg-amber-50 text-amber-700 border-amber-200",
  embedding: "bg-yellow-50 text-yellow-700 border-yellow-200",
  vision: "bg-orange-100 text-orange-900 border-orange-300",
  audio: "bg-amber-200 text-amber-900 border-amber-300",
  function_calling: "bg-orange-100 text-orange-800 border-orange-200",
  tool_use: "bg-amber-100 text-amber-800 border-amber-200",
  code: "bg-yellow-100 text-yellow-800 border-yellow-200",
  image_generation: "bg-emerald-50 text-emerald-800 border-emerald-200",
};

const getCapabilityLabel = (capability: string) => {
  const key = capabilityLabelKeys[capability];
  return key ? t(key) : capability;
};

const getCapabilityClass = (capability: string) => {
  return capabilityColorClasses[capability] || "bg-orange-50 text-orange-700 border-orange-200";
};

const handleEdit = async (assistant: Assistant, event: Event) => {
  event.stopPropagation();
  await navigateTo(`/assistants/${assistant.id}/edit`);
};

const handleCopy = async (assistant: Assistant, event: Event) => {
  event.stopPropagation();
  await navigateTo(`/assistants/create?source_id=${assistant.id}`);
};

const handlePin = async (assistant: Assistant, event: Event) => {
  event.stopPropagation();
  if (!currentUser.value) {
    toast.error(t("auth.loginRequired"));
    return;
  }

  const { $api } = useNuxtApp();
  const isPinned = assistant.is_pinned;

  // Optimistic update helper
  const updateListState = (
    list: Ref<Assistant[] | null | undefined>,
    id: string,
    pinned: boolean
  ) => {
    if (!list.value) return;
    const item = list.value.find((a) => a.id === id);
    if (item) {
      item.is_pinned = pinned;
    }
  };

  // Optimistically update both lists
  updateListState(assistants, assistant.id, !isPinned);
  updateListState(pinnedAssistants, assistant.id, !isPinned);

  try {
    if (isPinned) {
      await $api(`/v1/assistants/${assistant.id}/pin`, { method: "DELETE" });
      toast.success(t("assistants.unpinned"));
    } else {
      await $api(`/v1/assistants/${assistant.id}/pin`, { method: "POST" });
      toast.success(t("assistants.pinned"));
    }

    // Refresh pinned list to ensure it's up to date (especially for adding new pins)
    refreshPinned();

    // If we are in pinned scope and unpinned, refresh the main list
    if (scope.value === "pinned" && isPinned) {
      refresh();
    }
  } catch {
    toast.error(t("common.error"));
    // Revert on error
    updateListState(assistants, assistant.id, isPinned);
    updateListState(pinnedAssistants, assistant.id, isPinned);
  }
};

const handleModeSelect = (m: string | undefined) => {
  selectedMode.value = m;
  scope.value = undefined;
};

const handleScopeSelect = (s: string) => {
  scope.value = s;
  selectedMode.value = undefined;
};

// Scroll handling
const scrollContainer = ref<HTMLElement | null>(null);
const showLeftArrow = ref(false);
const showRightArrow = ref(false);

const checkScroll = () => {
  if (!scrollContainer.value) return;
  const { scrollLeft, scrollWidth, clientWidth } = scrollContainer.value;
  showLeftArrow.value = scrollLeft > 0;
  showRightArrow.value = Math.ceil(scrollLeft + clientWidth) < scrollWidth;
};

const scroll = (direction: "left" | "right") => {
  if (!scrollContainer.value) return;
  const scrollAmount = 300;
  const newScrollLeft =
    direction === "left"
      ? scrollContainer.value.scrollLeft - scrollAmount
      : scrollContainer.value.scrollLeft + scrollAmount;

  scrollContainer.value.scrollTo({
    left: newScrollLeft,
    behavior: "smooth",
  });
};

onMounted(() => {
  checkScroll();
  setTimeout(checkScroll, 100);
  window.addEventListener("resize", checkScroll);
});

onUnmounted(() => {
  window.removeEventListener("resize", checkScroll);
});
</script>

<template>
  <div class="absolute inset-0 flex flex-col overflow-hidden rounded-[inherit]">
    <AppHeader></AppHeader>
    <div class="mx-auto flex w-full max-w-[1600px] flex-1 flex-col overflow-y-auto px-4 py-6">
      <!-- Pinned Section -->
      <div
        v-if="!selectedMode && !scope && !searchQuery && localizedPinnedAssistants.length > 0"
        class="bg-muted/20 border-border/50 mb-8 flex-shrink-0 rounded-2xl border p-6"
      >
        <h2 class="text-primary mb-4 flex items-center gap-2 text-lg font-semibold">
          <Pin class="h-4 w-4" />
          {{ t("assistants.pinned") }}
        </h2>
        <div class="grid gap-6 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          <Card
            v-for="assistant in localizedPinnedAssistants"
            :key="assistant.id"
            :class="[
              'group bg-background relative cursor-pointer transition-all hover:scale-[1.02] hover:shadow-md',
              assistant.status === 'DRAFT' ? 'cursor-not-allowed opacity-60' : '',
            ]"
          >
            <CardHeader>
              <div class="flex min-w-0 items-center gap-3">
                <Avatar class="size-10 flex-shrink-0">
                  <AvatarImage
                    v-if="assistant.avatar_url"
                    :src="assistant.avatar_url"
                    :alt="assistant.name"
                  />
                  <AvatarFallback>
                    {{ assistant.name.charAt(0).toUpperCase() }}
                  </AvatarFallback>
                </Avatar>
                <div class="flex min-w-0 flex-col">
                  <CardTitle class="truncate text-base leading-tight font-medium">
                    <NuxtLink
                      v-if="assistant.status !== 'DRAFT'"
                      :to="`/chatwith/${assistant.id}`"
                      custom
                      v-slot="{ href, navigate }"
                    >
                      <a :href="`${origin}${href}`" @click="navigate" class="focus:outline-none">
                        <span class="absolute inset-0" aria-hidden="true"></span>
                        {{ assistant.name }}
                      </a>
                    </NuxtLink>
                    <span v-else>{{ assistant.name }}</span>
                  </CardTitle>
                  <div
                    v-if="assistant.model"
                    class="text-muted-foreground mt-1 flex items-center gap-1 truncate text-xs"
                  >
                    <Sparkles class="h-3 w-3 opacity-70" />
                    {{ assistant.model.name }}
                  </div>
                </div>
              </div>
            </CardHeader>
            <CardContent>
              <div class="mb-4 flex flex-wrap gap-1" v-if="assistant.model?.capabilities?.length">
                <Badge
                  v-for="cap in assistant.model.capabilities"
                  :key="cap"
                  variant="outline"
                  :class="['h-5 px-1 py-0 text-[10px]', getCapabilityClass(cap)]"
                >
                  {{ getCapabilityLabel(cap) }}
                </Badge>
              </div>
              <p class="text-muted-foreground line-clamp-3 text-sm">{{ assistant.description }}</p>
            </CardContent>
            <CardFooter class="relative z-10 flex justify-start gap-1 px-6 pt-0 pb-4">
              <Button
                v-if="currentUser"
                variant="ghost"
                size="icon"
                class="text-muted-foreground hover:text-primary h-8 w-8"
                @click="(e: MouseEvent) => handlePin(assistant, e)"
                :title="assistant.is_pinned ? t('assistants.unpin') : t('assistants.pin')"
              >
                <PinOff v-if="assistant.is_pinned" class="h-4 w-4 fill-current" />
                <Pin v-else class="h-4 w-4" />
              </Button>
              <Button
                v-if="currentUser && assistant.owner_id === currentUser.id"
                variant="ghost"
                size="icon"
                class="text-muted-foreground hover:text-primary h-8 w-8"
                @click="(e: MouseEvent) => handleEdit(assistant, e)"
              >
                <Edit class="h-4 w-4" />
              </Button>
              <Button
                v-if="currentUser && assistant.owner_id !== currentUser.id"
                variant="ghost"
                size="icon"
                class="text-muted-foreground hover:text-primary h-8 w-8"
                @click="(e: MouseEvent) => handleCopy(assistant, e)"
                :title="t('assistants.copy')"
              >
                <Copy class="h-4 w-4" />
              </Button>
            </CardFooter>
          </Card>
        </div>
      </div>

      <!-- Top area: title, search, category -->
      <div class="mb-4 flex-shrink-0 space-y-6">
        <div class="flex flex-col justify-between gap-4 md:flex-row md:items-center">
          <h1 class="text-2xl font-bold">
            {{ selectedMode ? (selectedMode === "RAG" ? "RAG" : "General") : "All Assistants" }}
          </h1>
          <div class="flex w-full items-center gap-2 md:w-auto">
            <div class="relative w-full max-w-sm">
              <Search class="text-muted-foreground absolute top-2.5 left-2 h-4 w-4" />
              <Input
                v-model="searchQuery"
                :placeholder="$t('assistants.searchPlaceholder')"
                class="pl-8"
              />
            </div>
            <Button v-if="showCreateButton" @click="navigateTo('/assistants/create')">
              <Plus class="mr-2 h-4 w-4" />
              {{ t("assistants.create") }}
            </Button>
          </div>
        </div>

        <!-- Horizontal category bar -->
        <div class="group relative">
          <div
            v-if="showLeftArrow"
            class="from-background via-background absolute top-0 bottom-2 left-0 z-10 flex items-center bg-gradient-to-r to-transparent pr-6"
          >
            <Button
              variant="outline"
              size="icon"
              class="h-8 w-8 rounded-full shadow-sm"
              @click="scroll('left')"
            >
              <ChevronLeft class="h-4 w-4" />
            </Button>
          </div>

          <div
            ref="scrollContainer"
            class="flex w-full max-w-full items-center gap-2 overflow-x-auto scroll-smooth pb-2 [-ms-overflow-style:'none'] [scrollbar-width:'none'] [&::-webkit-scrollbar]:hidden"
            @scroll="checkScroll"
          >
            <Button
              variant="ghost"
              :class="[
                'h-9 flex-shrink-0 rounded-full px-4 transition-all',
                !selectedMode && !scope
                  ? 'bg-primary text-primary-foreground hover:bg-primary/90 hover:text-primary-foreground'
                  : 'bg-muted/50 text-muted-foreground hover:bg-muted hover:text-foreground',
              ]"
              @click="handleModeSelect(undefined)"
            >
              <LayoutGrid class="mr-2 h-4 w-4" />
              All
            </Button>

            <Button
              variant="ghost"
              :class="[
                'h-9 flex-shrink-0 rounded-full px-4 transition-all',
                scope === 'mine'
                  ? 'bg-primary text-primary-foreground hover:bg-primary/90 hover:text-primary-foreground'
                  : 'bg-muted/50 text-muted-foreground hover:bg-muted hover:text-foreground',
              ]"
              @click="handleScopeSelect('mine')"
            >
              <User class="mr-2 h-4 w-4" />
              {{ t("assistants.myAssistants") }}
            </Button>

            <Button
              v-for="opt in modeOptions"
              :key="opt.value"
              variant="ghost"
              :class="[
                'h-9 flex-shrink-0 rounded-full px-4 transition-all',
                selectedMode === opt.value
                  ? 'bg-primary text-primary-foreground hover:bg-primary/90 hover:text-primary-foreground'
                  : 'bg-muted/50 text-muted-foreground hover:bg-muted hover:text-foreground',
              ]"
              @click="handleModeSelect(opt.value)"
            >
              <component :is="opt.icon" class="mr-2 h-4 w-4" />
              {{ opt.label }}
            </Button>
          </div>

          <div
            v-if="showRightArrow"
            class="from-background via-background absolute top-0 right-0 bottom-2 z-10 flex items-center bg-gradient-to-l to-transparent pl-6"
          >
            <Button
              variant="outline"
              size="icon"
              class="h-8 w-8 rounded-full shadow-sm"
              @click="scroll('right')"
            >
              <ChevronRight class="h-4 w-4" />
            </Button>
          </div>
        </div>
      </div>

      <!-- List content area -->
      <div class="pr-2 pb-4">
        <div v-if="pending" class="flex justify-center py-12">
          <div class="border-primary h-8 w-8 animate-spin rounded-full border-b-2"></div>
        </div>

        <div v-else-if="error" class="py-12 text-center">
          <p class="text-destructive mb-4">{{ $t("assistants.failedToLoad") }}</p>
          <Button @click="refresh" variant="outline">{{ $t("assistants.tryAgain") }}</Button>
        </div>

        <div v-else-if="!assistants || assistants.length === 0" class="py-12 text-center">
          <div class="mb-4">
            <svg
              class="text-muted-foreground mx-auto h-16 w-16"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                stroke-linecap="round"
                stroke-linejoin="round"
                stroke-width="1"
                d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z"
              />
            </svg>
          </div>
          <h3 class="mb-2 text-lg font-semibold">{{ $t("assistants.noAssistants") }}</h3>
          <p class="text-muted-foreground">{{ $t("assistants.noAssistantsDescription") }}</p>
        </div>

        <div v-else class="grid gap-6 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          <Card
            v-for="assistant in localizedAssistants"
            :key="assistant.id"
            :class="[
              'group relative cursor-pointer transition-all hover:scale-[1.02] hover:shadow-md',
              assistant.status === 'DRAFT' ? 'cursor-not-allowed opacity-60' : '',
            ]"
          >
            <CardHeader>
              <div class="flex min-w-0 items-center gap-3">
                <Avatar class="size-10 flex-shrink-0">
                  <AvatarImage
                    v-if="assistant.avatar_url"
                    :src="assistant.avatar_url"
                    :alt="assistant.name"
                  />
                  <AvatarFallback>
                    {{ assistant.name.charAt(0).toUpperCase() }}
                  </AvatarFallback>
                </Avatar>
                <div class="flex min-w-0 flex-col">
                  <CardTitle class="truncate text-base leading-tight font-medium">
                    <NuxtLink
                      v-if="assistant.status !== 'DRAFT'"
                      :to="`/chatwith/${assistant.id}`"
                      custom
                      v-slot="{ href, navigate }"
                    >
                      <a :href="`${origin}${href}`" @click="navigate" class="focus:outline-none">
                        <span class="absolute inset-0" aria-hidden="true"></span>
                        {{ assistant.name }}
                      </a>
                    </NuxtLink>
                    <span v-else>{{ assistant.name }}</span>
                  </CardTitle>
                  <div
                    v-if="assistant.model"
                    class="text-muted-foreground mt-1 flex items-center gap-1 truncate text-xs"
                  >
                    <Sparkles class="h-3 w-3 opacity-70" />
                    {{ assistant.model.name }}
                  </div>
                </div>
              </div>
            </CardHeader>
            <CardContent>
              <div class="mb-4 flex flex-wrap gap-1" v-if="assistant.model?.capabilities?.length">
                <Badge
                  v-for="cap in assistant.model.capabilities"
                  :key="cap"
                  variant="outline"
                  :class="['h-5 px-1 py-0 text-[10px]', getCapabilityClass(cap)]"
                >
                  {{ getCapabilityLabel(cap) }}
                </Badge>
              </div>
              <p class="text-muted-foreground line-clamp-3 text-sm">{{ assistant.description }}</p>
            </CardContent>
            <CardFooter class="relative z-10 flex justify-start gap-1 px-6 pt-0 pb-4">
              <Button
                v-if="currentUser"
                variant="ghost"
                size="icon"
                class="text-muted-foreground hover:text-primary h-8 w-8"
                @click="(e: MouseEvent) => handlePin(assistant, e)"
                :title="assistant.is_pinned ? t('assistants.unpin') : t('assistants.pin')"
              >
                <PinOff v-if="assistant.is_pinned" class="h-4 w-4 fill-current" />
                <Pin v-else class="h-4 w-4" />
              </Button>
              <Button
                v-if="currentUser && assistant.owner_id === currentUser.id"
                variant="ghost"
                size="icon"
                class="text-muted-foreground hover:text-primary h-8 w-8"
                @click="(e: MouseEvent) => handleEdit(assistant, e)"
              >
                <Edit class="h-4 w-4" />
              </Button>
              <Button
                v-if="currentUser && assistant.owner_id !== currentUser.id"
                variant="ghost"
                size="icon"
                class="text-muted-foreground hover:text-primary h-8 w-8"
                @click="(e: MouseEvent) => handleCopy(assistant, e)"
                :title="t('assistants.copy')"
              >
                <Copy class="h-4 w-4" />
              </Button>
            </CardFooter>
          </Card>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped></style>
