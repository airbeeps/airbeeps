<script setup lang="ts">
import { ref, computed, onMounted } from "vue";
import { useRouter, useRoute } from "vue-router";
import { ArrowLeft, Edit, Trash2, MessageSquare, Copy, Settings, Languages } from "lucide-vue-next";
import { Button } from "~/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "~/components/ui/card";
import { Badge } from "~/components/ui/badge";
import { Avatar, AvatarFallback, AvatarImage } from "~/components/ui/avatar";
import { Separator } from "~/components/ui/separator";
import { Label } from "~/components/ui/label";
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
import type { Assistant } from "~/types/api";

const { t } = useI18n();

// Page metadata
definePageMeta({
  breadcrumb: "admin.pages.assistants.detail.breadcrumb",
  layout: "admin",
});

const router = useRouter();
const route = useRoute();
const assistantId = route.params.id as string;

// State management
const loading = ref(false);
const deleteLoading = ref(false);
const assistant = ref<Assistant | null>(null);

// Computed properties
const statusConfig = computed(() => {
  if (!assistant.value) return null;

  switch (assistant.value.status) {
    case "ACTIVE":
      return {
        label: t("admin.pages.assistants.detail.status.active"),
        variant: "default" as const,
        color: "text-green-600",
      };
    case "INACTIVE":
      return {
        label: t("admin.pages.assistants.detail.status.inactive"),
        variant: "secondary" as const,
        color: "text-gray-500",
      };
    case "DRAFT":
      return {
        label: t("admin.pages.assistants.detail.status.draft"),
        variant: "outline" as const,
        color: "text-orange-600",
      };
    default:
      return {
        label: t("admin.pages.assistants.detail.status.unknown"),
        variant: "secondary" as const,
        color: "text-gray-500",
      };
  }
});

const modeLabel = computed(() => {
  const mode = (assistant.value as any)?.mode || "GENERAL";
  return mode === "RAG" ? "RAG" : "General";
});

// Load assistant data
const loadAssistant = async () => {
  loading.value = true;
  try {
    const { $api } = useNuxtApp();
    const response = await $api(`/v1/admin/assistants/${assistantId}`);
    assistant.value = response;
  } catch (error) {
    console.error("Failed to load assistant data:", error);
    toast.error(t("admin.pages.assistants.detail.loadFailed"));
    router.push("/admin/assistants");
  } finally {
    loading.value = false;
  }
};

// Delete assistant
const deleteAssistant = async () => {
  deleteLoading.value = true;
  try {
    const { $api } = useNuxtApp();
    await $api(`/v1/admin/assistants/${assistantId}`, {
      method: "DELETE",
    });

    toast.success(t("admin.pages.assistants.detail.deleteSuccess"));
    router.push("/admin/assistants");
  } catch (error) {
    console.error("Delete failed:", error);
    toast.error(t("admin.pages.assistants.detail.deleteFailed"));
  } finally {
    deleteLoading.value = false;
  }
};

// Copy assistant ID
const copyAssistantId = () => {
  if (assistant.value) {
    navigator.clipboard.writeText(assistant.value.id);
    toast.success(t("admin.pages.assistants.detail.idCopied"));
  }
};

// Navigation actions
const handleEdit = () => {
  router.push(`/admin/assistants/${assistantId}/edit`);
};

const handleBack = () => {
  router.push("/admin/assistants");
};

const handleChat = () => {
  router.push(`/chatwith/${assistantId}`);
};

// Page initialization
onMounted(() => {
  loadAssistant();
});
</script>

<template>
  <div class="container mx-auto space-y-6 py-6">
    <div class="flex items-center justify-between">
      <div class="flex items-center gap-4">
        <Button variant="ghost" size="sm" @click="handleBack">
          <ArrowLeft class="mr-2 h-4 w-4" />
          {{ t("admin.back") }}
        </Button>
        <div>
          <h1 class="text-2xl font-bold">
            {{ t("admin.pages.assistants.detail.title") }}
          </h1>
          <p class="text-muted-foreground">
            {{
              assistant?.name
                ? t("admin.pages.assistants.detail.viewing", {
                    name: assistant.name,
                  })
                : t("common.loading")
            }}
          </p>
        </div>
      </div>

      <div class="flex items-center gap-2">
        <Button variant="outline" size="sm" @click="handleChat" :disabled="loading">
          <MessageSquare class="mr-2 h-4 w-4" />
          {{ t("admin.pages.assistants.detail.testChat") }}
        </Button>
        <Button
          variant="outline"
          size="sm"
          @click="router.push(`/admin/assistants/${assistantId}/translations`)"
          :disabled="loading"
        >
          <Languages class="mr-2 h-4 w-4" />
          {{ t("admin.pages.assistants.actions.translations") }}
        </Button>
        <Button variant="outline" size="sm" @click="handleEdit" :disabled="loading">
          <Edit class="mr-2 h-4 w-4" />
          {{ t("admin.edit") }}
        </Button>

        <AlertDialog>
          <AlertDialogTrigger as-child>
            <Button variant="destructive" size="sm" :disabled="loading">
              <Trash2 class="mr-2 h-4 w-4" />
              {{ t("admin.delete") }}
            </Button>
          </AlertDialogTrigger>
          <AlertDialogContent>
            <AlertDialogHeader>
              <AlertDialogTitle>{{ t("admin.pages.assistants.delete.title") }}</AlertDialogTitle>
              <AlertDialogDescription>
                {{
                  t("admin.pages.assistants.delete.description", {
                    name: assistant?.name,
                  })
                }}
              </AlertDialogDescription>
            </AlertDialogHeader>
            <AlertDialogFooter>
              <AlertDialogCancel>{{ t("admin.cancel") }}</AlertDialogCancel>
              <AlertDialogAction
                @click="deleteAssistant"
                :disabled="deleteLoading"
                class="bg-destructive text-destructive-foreground hover:bg-destructive/90"
              >
                {{ t("admin.pages.assistants.delete.confirm") }}
              </AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>
      </div>
    </div>

    <div v-if="loading" class="flex justify-center py-12">
      <div class="border-primary h-8 w-8 animate-spin rounded-full border-b-2"></div>
    </div>

    <div v-else-if="assistant" class="grid grid-cols-1 gap-4 lg:grid-cols-3">
      <div class="space-y-4 lg:col-span-2">
        <Card>
          <CardHeader>
            <div class="flex items-start gap-4">
              <Avatar class="h-16 w-16">
                <AvatarImage :src="assistant.avatar_url || ''" />
                <AvatarFallback>{{ assistant.name.charAt(0).toUpperCase() }}</AvatarFallback>
              </Avatar>
              <div class="flex-1">
                <div class="mb-2 flex items-center gap-3">
                  <CardTitle class="text-xl">{{ assistant.name }}</CardTitle>
                  <Badge v-if="statusConfig" :variant="statusConfig.variant">
                    {{ statusConfig.label }}
                  </Badge>
                  <Badge v-if="assistant.is_public" variant="outline">
                    {{ t("admin.public") }}
                  </Badge>
                </div>
                <CardDescription class="text-base">
                  {{ assistant.description }}
                </CardDescription>

                <div class="mt-4 flex flex-wrap gap-2">
                  <Badge variant="secondary" class="text-xs">
                    {{ modeLabel }}
                  </Badge>
                </div>
              </div>
            </div>
          </CardHeader>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle class="flex items-center gap-2">
              <Settings class="h-5 w-5" />
              {{ t("admin.pages.assistants.create.modelConfig.systemPromptLabel") }}
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div class="bg-muted rounded-lg p-4">
              <pre class="text-sm whitespace-pre-wrap">{{ assistant.system_prompt }}</pre>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader class="pb-3">
            <CardTitle>{{ t("admin.pages.assistants.create.modelConfig.title") }}</CardTitle>
          </CardHeader>
          <CardContent>
            <div class="grid grid-cols-2 gap-3">
              <div>
                <Label class="text-muted-foreground text-sm">{{
                  t("admin.pages.assistants.create.modelConfig.modelLabel")
                }}</Label>
                <div class="font-medium">
                  {{ assistant.model?.display_name || t("admin.notSet") }}
                </div>
              </div>
              <div>
                <Label class="text-muted-foreground text-sm">{{
                  t("admin.pages.assistants.create.modelConfig.providerLabel")
                }}</Label>
                <div class="font-medium">
                  {{ assistant.model?.provider?.name || assistant.model?.provider || "-" }}
                </div>
              </div>
              <div>
                <Label class="text-muted-foreground text-sm">{{
                  t("admin.pages.assistants.create.modelConfig.temperatureLabel")
                }}</Label>
                <div class="font-medium">
                  {{ assistant.temperature ?? "-" }}
                </div>
              </div>
              <div>
                <Label class="text-muted-foreground text-sm">{{
                  t("admin.pages.assistants.create.modelConfig.maxTokensLabel")
                }}</Label>
                <div class="font-medium">{{ assistant.max_tokens ?? "-" }}</div>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      <div class="space-y-4">
        <Card>
          <CardHeader class="pb-3">
            <CardTitle class="text-lg">{{
              t("admin.pages.assistants.detail.statusInfo")
            }}</CardTitle>
          </CardHeader>
          <CardContent class="space-y-3">
            <div>
              <Label class="text-muted-foreground text-sm">{{
                t("admin.pages.assistants.create.publishSettings.statusLabel")
              }}</Label>
              <div class="mt-1 flex items-center gap-2">
                <div :class="statusConfig?.color" class="h-2 w-2 rounded-full bg-current"></div>
                <span class="font-medium">{{ statusConfig?.label }}</span>
              </div>
            </div>
            <Separator />
            <div>
              <Label class="text-muted-foreground text-sm">{{
                t("admin.pages.assistants.detail.visibility")
              }}</Label>
              <div class="mt-1 font-medium">
                {{
                  assistant.is_public
                    ? t("admin.pages.assistants.detail.visibilityPublic")
                    : t("admin.pages.assistants.detail.visibilityPrivate")
                }}
              </div>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader class="pb-3">
            <CardTitle class="text-lg">{{ t("admin.pages.assistants.detail.metadata") }}</CardTitle>
          </CardHeader>
          <CardContent class="space-y-3 text-sm">
            <div>
              <Label class="text-muted-foreground">Assistant ID</Label>
              <div class="mt-1 flex items-center gap-2">
                <code class="bg-muted rounded px-2 py-1 font-mono text-xs">{{ assistant.id }}</code>
                <Button variant="ghost" size="sm" @click="copyAssistantId">
                  <Copy class="h-3 w-3" />
                </Button>
              </div>
            </div>
            <Separator />
            <div>
              <Label class="text-muted-foreground">{{
                t("admin.pages.assistants.detail.createdAt")
              }}</Label>
              <div class="mt-1">
                {{ new Date(assistant.created_at).toLocaleString() }}
              </div>
            </div>
            <div>
              <Label class="text-muted-foreground">{{
                t("admin.pages.assistants.detail.updatedAt")
              }}</Label>
              <div class="mt-1">
                {{ new Date(assistant.updated_at).toLocaleString() }}
              </div>
            </div>
            <div v-if="assistant.owner_name || assistant.owner_id">
              <Label class="text-muted-foreground">{{
                t("admin.pages.assistants.detail.creator")
              }}</Label>
              <div class="mt-1">{{ assistant.owner_name || assistant.owner_id }}</div>
            </div>
          </CardContent>
        </Card>

        <!-- Usage Stats (Reserved) -->
        <Card>
          <CardHeader>
            <CardTitle class="text-lg">{{
              t("admin.pages.assistants.detail.usageStats")
            }}</CardTitle>
          </CardHeader>
          <CardContent class="space-y-3 text-sm">
            <div class="text-muted-foreground py-4 text-center">
              {{ t("admin.pages.assistants.detail.statsDev") }}
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  </div>
</template>
