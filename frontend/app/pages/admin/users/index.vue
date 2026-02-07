<script setup lang="ts">
import { computed, h } from "vue";
import { Badge } from "~/components/ui/badge";
import { Button } from "~/components/ui/button";
import type { ModelViewConfig } from "~/components/model-view/ModelView.vue";
import type { User } from "~/types/api";

definePageMeta({
  breadcrumb: "admin.pages.users.breadcrumb",
  layout: "admin",
});

const { t } = useI18n();

useHead({
  title: t("pageTitle.adminUsers"),
});

const userConfig = computed(
  (): ModelViewConfig<User> => ({
    title: t("admin.pages.users.title"),
    description: t("admin.pages.users.description"),
    apiEndpoint: "/v1/admin/users",
    apiEndpoints: {
      updateMethod: "PATCH",
    },

    columns: [
      {
        accessorKey: "email",
        header: t("admin.pages.users.email"),
        cell: (ctx) => {
          const value = ctx.getValue() as string;
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
        accessorKey: "name",
        header: t("admin.pages.users.name"),
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
      // Balance removed (legacy billing UI)
      {
        accessorKey: "is_active",
        header: t("admin.pages.users.status"),
        cell: (ctx) => {
          const isActive = ctx.getValue() as boolean;
          const isVerified = ctx.row.original.is_verified;

          return h("div", { class: "flex gap-2" }, [
            h(
              Badge,
              {
                variant: isActive ? "default" : "secondary",
              },
              () => (isActive ? t("admin.pages.users.active") : t("admin.pages.users.inactive"))
            ),
            isVerified &&
              h(
                Badge,
                {
                  variant: "default",
                },
                () => t("admin.pages.users.verified")
              ),
          ]);
        },
      },
      {
        accessorKey: "is_superuser",
        header: t("admin.pages.users.roles"),
        cell: (ctx) => {
          const isSuperuser = ctx.getValue() as boolean;
          const role = ctx.row.original.role as string | null;

          if (isSuperuser) {
            return h(Badge, { variant: "destructive" }, () => t("admin.roles.superuser"));
          }

          if (role) {
            const roleConfig: Record<
              string,
              { variant: "default" | "secondary" | "outline"; label: string }
            > = {
              admin: { variant: "default", label: t("admin.roles.admin") },
              editor: { variant: "secondary", label: t("admin.roles.editor") },
              viewer: { variant: "outline", label: t("admin.roles.viewer") },
            };
            const config = roleConfig[role] || { variant: "outline", label: role };
            return h(Badge, { variant: config.variant }, () => config.label);
          }

          return h("span", { class: "text-muted-foreground" }, t("admin.pages.users.user"));
        },
      },
      {
        accessorKey: "created_at",
        header: t("admin.pages.users.createdAt"),
        cell: (ctx) => {
          const value = ctx.getValue() as string;
          return new Date(value).toLocaleString();
        },
      },
    ],

    formFields: [
      {
        name: "email",
        label: t("admin.pages.users.email"),
        type: "email",
        required: true,
        disabled: true, // Email usually cannot be changed easily or requires verification
      },
      {
        name: "name",
        label: t("admin.pages.users.name"),
        type: "text",
      },
      {
        name: "is_active",
        label: t("admin.pages.users.active"),
        type: "switch",
      },
      {
        name: "is_verified",
        label: t("admin.pages.users.verified"),
        type: "switch",
      },
      {
        name: "is_superuser",
        label: t("admin.pages.users.isAdmin"),
        type: "switch",
      },
      {
        name: "role",
        label: t("admin.pages.users.role"),
        type: "select",
        options: [
          { label: t("admin.roles.viewer"), value: "viewer" },
          { label: t("admin.roles.editor"), value: "editor" },
          { label: t("admin.roles.admin"), value: "admin" },
        ],
      },
    ],

    filters: {
      is_active: {
        type: "select",
        label: t("admin.pages.users.filterActive"),
        options: [
          { label: t("admin.pages.users.active"), value: "true" },
          { label: t("admin.pages.users.inactive"), value: "false" },
        ],
      },
      is_verified: {
        type: "select",
        label: t("admin.pages.users.filterVerified"),
        options: [
          { label: t("admin.pages.users.verified"), value: "true" },
          { label: t("admin.pages.users.unverified"), value: "false" },
        ],
      },
      is_superuser: {
        type: "select",
        label: t("admin.pages.users.filterAdmin"),
        options: [
          { label: t("admin.pages.users.isAdmin"), value: "true" },
          { label: t("admin.pages.users.notAdmin"), value: "false" },
        ],
      },
      role: {
        type: "select",
        label: t("admin.pages.users.filterRole"),
        options: [
          { label: t("admin.roles.admin"), value: "admin" },
          { label: t("admin.roles.editor"), value: "editor" },
          { label: t("admin.roles.viewer"), value: "viewer" },
        ],
      },
    },

    detailFields: [
      { name: "id", label: "ID" },
      { name: "email", label: t("admin.pages.users.email") },
      { name: "name", label: t("admin.pages.users.name") },
      { name: "avatar_url", label: t("admin.pages.users.avatarUrl") },
      {
        name: "is_active",
        label: t("admin.pages.users.active"),
        type: "boolean",
      },
      {
        name: "is_verified",
        label: t("admin.pages.users.verified"),
        type: "boolean",
      },
      {
        name: "is_superuser",
        label: t("admin.pages.users.isAdmin"),
        type: "boolean",
      },
      {
        name: "role",
        label: t("admin.pages.users.role"),
        type: "text",
      },
      {
        name: "created_at",
        label: t("admin.pages.users.createdAt"),
        type: "datetime",
      },
    ],

    canCreate: false, // Usually users register themselves
    canDelete: true,
    canEdit: true,
    showFilters: true,
    selectable: true,
  })
);
</script>

<template>
  <ModelView :config="userConfig">
    <template #actions>
      <!-- Custom actions can be added here -->
    </template>
  </ModelView>
</template>
