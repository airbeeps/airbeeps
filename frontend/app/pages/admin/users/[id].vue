<script setup lang="ts">
import { toast } from "vue-sonner";

const { t } = useI18n();

definePageMeta({
  breadcrumb: "admin.pages.users.detail.breadcrumb",
  layout: "admin",
});

const route = useRoute();
const userId = route.params.id as string;

// Load user info
const { data: user, refresh: refreshUser } = await useAPI(`/v1/admin/users/${userId}`);

// Format date
const formatDate = (date: string | null) => {
  if (!date) return "-";
  return new Date(date).toLocaleString();
};
</script>

<template>
  <div class="container mx-auto space-y-6 py-6">
    <!-- Back button -->
    <div class="flex items-center gap-4">
      <Button variant="outline" @click="$router.back()">
        <Icon name="lucide:arrow-left" class="mr-2 h-4 w-4" />
        {{ t("common.back") }}
      </Button>
      <h1 class="text-3xl font-bold">
        {{ t("admin.pages.users.detail.title") }}
      </h1>
    </div>

    <!-- User basic info card -->
    <Card v-if="user">
      <CardHeader>
        <CardTitle>{{ t("admin.pages.users.detail.basicInfo") }}</CardTitle>
      </CardHeader>
      <CardContent>
        <div class="grid grid-cols-2 gap-4 md:grid-cols-4">
          <div>
            <div class="text-muted-foreground text-sm">
              {{ t("admin.pages.users.detail.email") }}
            </div>
            <div class="font-medium">{{ user.email }}</div>
          </div>
          <div>
            <div class="text-muted-foreground text-sm">
              {{ t("admin.pages.users.detail.name") }}
            </div>
            <div class="font-medium">{{ user.name || "-" }}</div>
          </div>
          <div>
            <div class="text-muted-foreground text-sm">
              {{ t("admin.pages.users.detail.status") }}
            </div>
            <div class="mt-1 flex gap-2">
              <Badge v-if="user.is_active" variant="default">{{
                t("admin.pages.users.detail.active")
              }}</Badge>
              <Badge v-else variant="secondary">{{ t("admin.pages.users.detail.inactive") }}</Badge>
              <Badge v-if="user.is_verified" variant="default">{{
                t("admin.pages.users.detail.verified")
              }}</Badge>
            </div>
          </div>
          <div>
            <div class="text-muted-foreground text-sm">
              {{ t("admin.pages.users.detail.role") }}
            </div>
            <div class="mt-1">
              <Badge v-if="user.is_superuser" variant="destructive">{{
                t("admin.pages.users.detail.admin")
              }}</Badge>
              <span v-else class="text-muted-foreground">{{
                t("admin.pages.users.detail.user")
              }}</span>
            </div>
          </div>
        </div>
      </CardContent>
    </Card>
  </div>
</template>
