<script setup lang="ts">
import { ref, onMounted } from "vue";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "~/components/ui/card";
import { Badge } from "~/components/ui/badge";
import { Shield, Edit, Eye, Crown } from "lucide-vue-next";

const { t } = useI18n();
const { $api } = useNuxtApp();

definePageMeta({
  breadcrumb: "Roles",
  layout: "admin",
});

interface Role {
  id: string;
  name: string;
  description: string;
}

interface RoleStats {
  total_users: number;
  by_role: Record<string, number>;
}

const roles = ref<Role[]>([]);
const stats = ref<RoleStats | null>(null);
const loading = ref(false);

const roleIcons: Record<string, any> = {
  admin: Shield,
  editor: Edit,
  viewer: Eye,
};

const roleColors: Record<string, string> = {
  admin: "bg-red-100 text-red-700 dark:bg-red-900 dark:text-red-300",
  editor: "bg-blue-100 text-blue-700 dark:bg-blue-900 dark:text-blue-300",
  viewer: "bg-gray-100 text-gray-700 dark:bg-gray-900 dark:text-gray-300",
};

const fetchRoles = async () => {
  loading.value = true;
  try {
    const response = await $api<{ roles: Role[] }>(`/v1/admin/users/roles/available`);
    roles.value = response.roles || [];
  } catch (error) {
    console.error("Failed to fetch roles:", error);
  } finally {
    loading.value = false;
  }
};

const fetchStats = async () => {
  try {
    const response = await $api<RoleStats>(`/v1/admin/users/stats/summary`);
    stats.value = response;
  } catch (error) {
    console.error("Failed to fetch user stats:", error);
  }
};

onMounted(() => {
  fetchRoles();
  fetchStats();
});
</script>

<template>
  <div class="container mx-auto space-y-6 p-6">
    <!-- Header -->
    <div>
      <h1 class="text-2xl font-bold">{{ t("admin.roles.title") }}</h1>
      <p class="text-muted-foreground">{{ t("admin.roles.description") }}</p>
    </div>

    <!-- Superuser Info -->
    <Card class="border-amber-200 bg-amber-50 dark:border-amber-800 dark:bg-amber-950/20">
      <CardHeader>
        <CardTitle class="flex items-center gap-2 text-amber-800 dark:text-amber-200">
          <Crown class="h-5 w-5" />
          {{ t("admin.roles.superuser") }}
        </CardTitle>
        <CardDescription class="text-amber-700 dark:text-amber-300">
          {{ t("admin.roles.superuserDescription") }}
        </CardDescription>
      </CardHeader>
      <CardContent>
        <p class="text-sm text-amber-700 dark:text-amber-300">
          Superusers have complete system access and bypass all role restrictions. This status is
          managed separately via the "Admin" toggle on user profiles.
        </p>
      </CardContent>
    </Card>

    <!-- Role Cards -->
    <div class="grid gap-4 md:grid-cols-3">
      <Card v-for="role in roles" :key="role.id" class="relative">
        <CardHeader>
          <CardTitle class="flex items-center gap-2">
            <component
              :is="roleIcons[role.id] || Shield"
              :class="['h-5 w-5', roleColors[role.id]]"
            />
            {{ role.name }}
          </CardTitle>
          <CardDescription>{{ role.description }}</CardDescription>
        </CardHeader>
        <CardContent>
          <div class="flex items-center justify-between">
            <Badge :class="roleColors[role.id]">
              {{ role.id }}
            </Badge>
            <div v-if="stats?.by_role" class="text-muted-foreground text-sm">
              {{ (stats.by_role[role.id] || 0).toLocaleString() }}
              {{ t("admin.pages.users.userList") }}
            </div>
          </div>
        </CardContent>
      </Card>
    </div>

    <!-- Permissions Matrix -->
    <Card>
      <CardHeader>
        <CardTitle>{{ t("admin.roles.permissionsMatrix") || "Permissions Matrix" }}</CardTitle>
        <CardDescription> Overview of what each role can do in the admin panel </CardDescription>
      </CardHeader>
      <CardContent>
        <div class="overflow-x-auto">
          <table class="w-full text-sm">
            <thead>
              <tr class="border-b">
                <th class="py-3 text-left font-medium">Permission</th>
                <th class="py-3 text-center font-medium">Viewer</th>
                <th class="py-3 text-center font-medium">Editor</th>
                <th class="py-3 text-center font-medium">Admin</th>
              </tr>
            </thead>
            <tbody class="divide-y">
              <tr>
                <td class="py-3">View dashboard and statistics</td>
                <td class="py-3 text-center text-green-600">✓</td>
                <td class="py-3 text-center text-green-600">✓</td>
                <td class="py-3 text-center text-green-600">✓</td>
              </tr>
              <tr>
                <td class="py-3">View assistants and settings</td>
                <td class="py-3 text-center text-green-600">✓</td>
                <td class="py-3 text-center text-green-600">✓</td>
                <td class="py-3 text-center text-green-600">✓</td>
              </tr>
              <tr>
                <td class="py-3">Create and edit assistants</td>
                <td class="text-muted-foreground py-3 text-center">—</td>
                <td class="py-3 text-center text-green-600">✓</td>
                <td class="py-3 text-center text-green-600">✓</td>
              </tr>
              <tr>
                <td class="py-3">Manage knowledge bases</td>
                <td class="text-muted-foreground py-3 text-center">—</td>
                <td class="py-3 text-center text-green-600">✓</td>
                <td class="py-3 text-center text-green-600">✓</td>
              </tr>
              <tr>
                <td class="py-3">Delete assistants and content</td>
                <td class="text-muted-foreground py-3 text-center">—</td>
                <td class="text-muted-foreground py-3 text-center">—</td>
                <td class="py-3 text-center text-green-600">✓</td>
              </tr>
              <tr>
                <td class="py-3">Manage users and roles</td>
                <td class="text-muted-foreground py-3 text-center">—</td>
                <td class="text-muted-foreground py-3 text-center">—</td>
                <td class="py-3 text-center text-green-600">✓</td>
              </tr>
              <tr>
                <td class="py-3">System configuration</td>
                <td class="text-muted-foreground py-3 text-center">—</td>
                <td class="text-muted-foreground py-3 text-center">—</td>
                <td class="py-3 text-center text-green-600">✓</td>
              </tr>
              <tr>
                <td class="py-3">View audit logs</td>
                <td class="text-muted-foreground py-3 text-center">—</td>
                <td class="text-muted-foreground py-3 text-center">—</td>
                <td class="py-3 text-center text-green-600">✓</td>
              </tr>
            </tbody>
          </table>
        </div>
      </CardContent>
    </Card>
  </div>
</template>
