<script setup lang="ts">
import { computed, h, ref } from "vue";
import { Badge } from "~/components/ui/badge";
import { PlugZap, Search, Copy } from "lucide-vue-next";
import { toast } from "vue-sonner";
import type { ModelViewConfig } from "~/components/model-view/ModelView.vue";
import type { Provider } from "~/types/api";

const { t } = useI18n();
const { $api } = useNuxtApp();

definePageMeta({
  breadcrumb: "admin.pages.modelProviders.breadcrumb",
  layout: "admin",
});

type ProviderTemplate = {
  id: string;
  display_name: string;
  description?: string;
  website?: string;
  api_base_url: string;
  interface_type: string;
  litellm_provider?: string | null;
};

const { data: providerTemplates } = useAPI<ProviderTemplate[]>("/v1/admin/provider-templates", {
  server: false,
});

const providerTemplateMap = computed(() => {
  const map: Record<string, ProviderTemplate> = {};
  (providerTemplates.value ?? []).forEach((p) => {
    map[p.id] = p;
  });
  return map;
});

const providerTemplateOptions = computed(() =>
  (providerTemplates.value ?? []).map((p) => ({
    label: p.display_name,
    value: p.id,
  }))
);

const lastAppliedTemplateId = ref<string | null>(null);

const handleProviderRowAction = async (action: any, row: Provider) => {
  try {
    if (action.key === "test-connection") {
      const res = await $api(`/v1/admin/providers/${row.id}/test-connection`, {
        method: "POST",
      });
      if (res?.ok) {
        toast.success(t("admin.pages.modelProviders.actions.testConnectionSuccess"));
      } else {
        // Display the error message from backend
        const errorMsg =
          res?.message ||
          res?.detail ||
          t("admin.pages.modelProviders.actions.testConnectionFailed");
        toast.error(errorMsg);
      }
      return;
    }

    if (action.key === "discover-models") {
      const models = await $api<string[]>(`/v1/admin/providers/${row.id}/discover-models`, {
        method: "GET",
      });
      toast.success(
        t("admin.pages.modelProviders.actions.discoverModelsSuccess", {
          count: (models ?? []).length,
        })
      );
      return;
    }
  } catch (e: any) {
    toast.error(e?.data?.detail || e?.message || t("common.error"));
  }
};

// Provider configuration
const providerConfig = computed(
  (): ModelViewConfig<Provider> => ({
    title: t("admin.pages.modelProviders.title"),
    description: t("admin.pages.modelProviders.description"),
    apiEndpoint: "/v1/admin/providers",
    onFormChange: ({ formData, mode, setValues }) => {
      if (mode !== "create") return;
      const tplId = (formData?.template_id as string) || "";
      if (!tplId) {
        lastAppliedTemplateId.value = null;
        return;
      }
      if (tplId === lastAppliedTemplateId.value) return;
      const tpl = providerTemplateMap.value[tplId];
      if (!tpl || !setValues) return;

      setValues({
        template_id: tpl.id,
        name: tpl.id,
        display_name: tpl.display_name,
        description: tpl.description ?? "",
        website: tpl.website ?? "",
        api_base_url: tpl.api_base_url,
        interface_type: tpl.interface_type,
        litellm_provider: tpl.litellm_provider ?? "",
      });
      lastAppliedTemplateId.value = tplId;
    },
    customActions: [
      {
        key: "test-connection",
        label: t("admin.pages.modelProviders.actions.testConnection"),
        icon: h(PlugZap, { class: "h-4 w-4" }),
        variant: "default" as const,
      },
      {
        key: "discover-models",
        label: t("admin.pages.modelProviders.actions.discoverModels"),
        icon: h(Search, { class: "h-4 w-4" }),
        variant: "secondary" as const,
      },
    ],

    columns: [
      {
        accessorKey: "display_name",
        header: t("admin.pages.modelProviders.columns.displayName"),
        cell: (ctx) => {
          const value = ctx.getValue() as string;
          if (!value) return "-";
          return h(
            "button",
            {
              class:
                "text-primary font-medium cursor-pointer text-left focus:outline-none focus:ring-2 focus:ring-primary/40 rounded-full bg-muted/30 hover:bg-muted/60 hover:underline px-2 py-0.5 transition-colors",
              onClick: () =>
                ctx.table.options.meta?.triggerRowAction?.(
                  { key: "view", label: "view" },
                  ctx.row.original
                ),
            },
            value
          );
        },
      },
      {
        accessorKey: "api_base_url",
        header: t("admin.pages.modelProviders.fields.apiBaseUrl"),
        cell: (context) => {
          const value = context.getValue() as string;
          if (!value) return "-";
          return h("div", { class: "flex items-center gap-2" }, [
            h(
              "span",
              { class: "truncate max-w-[200px]", title: value },
              value.length > 30 ? value.substring(0, 30) + "..." : value
            ),
            h(
              "button",
              {
                class:
                  "text-muted-foreground hover:text-foreground p-1 rounded hover:bg-muted transition-colors",
                title: t("common.copy"),
                onClick: (e: Event) => {
                  e.stopPropagation();
                  navigator.clipboard.writeText(value);
                  toast.success(t("common.copied"));
                },
              },
              h(Copy, { class: "h-3 w-3" })
            ),
          ]);
        },
      },
      {
        accessorKey: "status",
        header: t("admin.pages.modelProviders.columns.status"),
        cell: (context) => {
          const value = context.getValue() as string;
          // Based on status
          const variant =
            value === "ACTIVE" ? "default" : value === "MAINTENANCE" ? "outline" : "secondary";
          const statusKey =
            value === "ACTIVE" ? "active" : value === "MAINTENANCE" ? "maintenance" : "inactive";
          return h(Badge, { variant }, () => t(`admin.pages.modelProviders.status.${statusKey}`));
        },
      },
      {
        accessorKey: "created_at",
        header: t("admin.pages.modelProviders.columns.createdAt"),
        cell: (context) => {
          const value = context.getValue() as string;
          return new Date(value).toLocaleDateString();
        },
      },
    ],

    detailFields: [
      {
        name: "name",
        label: t("admin.pages.modelProviders.fields.providerId"),
        type: "text",
      },
      {
        name: "display_name",
        label: t("admin.pages.modelProviders.fields.displayName"),
        type: "text",
      },
      {
        name: "description",
        label: t("admin.pages.modelProviders.fields.description"),
        type: "textarea",
      },
      {
        name: "website",
        label: t("admin.pages.modelProviders.fields.website"),
        type: "text",
      },
      {
        name: "api_base_url",
        label: t("admin.pages.modelProviders.fields.apiBaseUrl"),
        type: "text",
      },
      {
        name: "interface_type",
        label: t("admin.pages.modelProviders.fields.interfaceType"),
        type: "text",
      },
      {
        name: "litellm_provider",
        label: t("admin.pages.modelProviders.fields.litellmProvider"),
        type: "text",
      },
      {
        name: "status",
        label: t("admin.pages.modelProviders.fields.statusLabel"),
        type: "text",
      },
      {
        name: "created_at",
        label: t("admin.pages.modelProviders.columns.createdAt"),
        type: "datetime",
      },
    ],

    formFields: [
      {
        name: "template_id",
        label: t("admin.pages.modelProviders.fields.providerTemplate"),
        type: "select",
        required: false,
        options: providerTemplateOptions.value,
        placeholder: t("admin.pages.modelProviders.fields.providerTemplatePlaceholder"),
        help: t("admin.pages.modelProviders.fields.providerTemplateHelp"),
      },
      {
        name: "name",
        label: t("admin.pages.modelProviders.fields.providerId"),
        type: "text",
        required: true,
        placeholder: t("admin.pages.modelProviders.fields.providerIdPlaceholder"),
        htmlName: "provider_id",
        autocomplete: "off",
      },
      {
        name: "display_name",
        label: t("admin.pages.modelProviders.fields.displayName"),
        type: "text",
        required: true,
        placeholder: t("admin.pages.modelProviders.fields.displayNamePlaceholder"),
      },
      {
        name: "description",
        label: t("admin.pages.modelProviders.fields.description"),
        type: "textarea",
        placeholder: t("admin.pages.modelProviders.fields.descriptionPlaceholder"),
      },
      {
        name: "website",
        label: t("admin.pages.modelProviders.fields.website"),
        type: "text",
        placeholder: "https://example.com",
      },
      {
        name: "api_base_url",
        label: t("admin.pages.modelProviders.fields.apiBaseUrl"),
        type: "text",
        placeholder: "https://api.example.com/v1",
      },
      {
        name: "api_key",
        label: t("admin.pages.modelProviders.fields.apiKey"),
        type: "password",
        required: false,
        placeholder: t("admin.pages.modelProviders.fields.apiKeyPlaceholder"),
        help:
          t("admin.pages.modelProviders.fields.apiKeyPlaceholder") +
          " (not required for local HuggingFace embeddings)",
        htmlName: "provider_api_key",
        autocomplete: "new-password",
      },
      {
        name: "interface_type",
        label: t("admin.pages.modelProviders.fields.interfaceType"),
        type: "select",
        required: true,
        options: [
          { label: "Anthropic", value: "ANTHROPIC" },
          { label: "DashScope", value: "DASHSCOPE" },
          { label: "Google", value: "GOOGLE" },
          { label: "OpenAI", value: "OPENAI" },
          { label: "xAI", value: "XAI" },
          { label: "HuggingFace (local embeddings)", value: "HUGGINGFACE" },
        ],
        defaultValue: "OPENAI",
      },
      {
        name: "litellm_provider",
        label: t("admin.pages.modelProviders.fields.litellmProvider"),
        type: "text",
        required: false,
        placeholder: t("admin.pages.modelProviders.fields.litellmProviderPlaceholder"),
        help: t("admin.pages.modelProviders.fields.litellmProviderHelp"),
      },
      {
        name: "status",
        label: t("admin.pages.modelProviders.fields.statusLabel"),
        type: "select",
        required: true,
        options: [
          { label: t("admin.pages.modelProviders.status.active"), value: "ACTIVE" },
          { label: t("admin.pages.modelProviders.status.inactive"), value: "INACTIVE" },
          { label: t("admin.pages.modelProviders.status.maintenance"), value: "MAINTENANCE" },
        ],
        defaultValue: "ACTIVE",
      },
    ],
  })
);
</script>

<template>
  <ModelView :config="providerConfig" @row-action="handleProviderRowAction" />
</template>
