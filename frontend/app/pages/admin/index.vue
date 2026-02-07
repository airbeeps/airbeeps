<script setup lang="ts">
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { Button } from "@/components/ui/button";
import { Users, MessageSquare, Zap, Plus, Database, Activity, ArrowRight } from "lucide-vue-next";

const { t } = useI18n();
const router = useRouter();

definePageMeta({
  layout: "admin",
  breadcrumb: "admin.pages.dashboard.breadcrumb",
});

interface ChartDataPoint {
  name: string;
  value: number;
}

interface DashboardStats {
  overview: {
    total_users: number;
    total_token_usage: number;
    total_conversations: number;
    total_documents: number;
  };
  recent_users: {
    name: string;
    email: string;
    avatar_url?: string;
    created_at: string;
  }[];
  top_assistants: {
    name: string;
    count: number;
  }[];
}

const { data: stats, status } = await useAPI<DashboardStats>("/api/v1/admin/dashboard/stats");

const userGrowthConfig = {
  value: { label: "New Users", color: "hsl(var(--primary))" },
};

const modelDistConfig = {
  value: { label: "Usage", color: "hsl(var(--chart-2))" },
};

// Formatters
const formatNumber = (num: number) => new Intl.NumberFormat("en-US").format(num);
const formatDate = (dateStr: string) => new Date(dateStr).toLocaleDateString();
</script>

<template>
  <div class="flex flex-1 flex-col gap-4 p-4">
    <div v-if="status === 'pending'" class="flex h-96 items-center justify-center">
      {{ t("common.loading") }}
    </div>
    <div v-else-if="stats" class="space-y-4">
      <!-- Quick Actions -->
      <Card class="border-dashed">
        <CardHeader class="pb-3">
          <CardTitle class="text-base font-medium">Quick Actions</CardTitle>
        </CardHeader>
        <CardContent>
          <div class="flex flex-wrap gap-2">
            <Button variant="outline" size="sm" @click="router.push('/admin/assistants/create')">
              <Plus class="mr-2 h-4 w-4" />
              New Assistant
            </Button>
            <Button variant="outline" size="sm" @click="router.push('/admin/kbs')">
              <Database class="mr-2 h-4 w-4" />
              Add Knowledge Base
            </Button>
            <Button variant="outline" size="sm" @click="router.push('/admin/agent-traces')">
              <Activity class="mr-2 h-4 w-4" />
              View Traces
            </Button>
            <Button variant="outline" size="sm" @click="router.push('/admin/system-health')">
              <ArrowRight class="mr-2 h-4 w-4" />
              System Health
            </Button>
          </div>
        </CardContent>
      </Card>

      <!-- Overview Cards -->
      <div class="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
        <Card>
          <CardHeader class="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle class="text-sm font-medium">{{
              t("admin.pages.dashboard.totalUsers")
            }}</CardTitle>
            <div class="rounded-full bg-blue-100/50 p-2 dark:bg-blue-900/20">
              <Users class="h-4 w-4 text-blue-600 dark:text-blue-400" />
            </div>
          </CardHeader>
          <CardContent>
            <div class="text-2xl font-bold">{{ formatNumber(stats.overview.total_users) }}</div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader class="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle class="text-sm font-medium">{{
              t("admin.pages.dashboard.conversations")
            }}</CardTitle>
            <div class="rounded-full bg-green-100/50 p-2 dark:bg-green-900/20">
              <MessageSquare class="h-4 w-4 text-green-600 dark:text-green-400" />
            </div>
          </CardHeader>
          <CardContent>
            <div class="text-2xl font-bold">
              {{ formatNumber(stats.overview.total_conversations) }}
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader class="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle class="text-sm font-medium">{{
              t("admin.pages.dashboard.documents")
            }}</CardTitle>
            <div class="rounded-full bg-amber-100/50 p-2 dark:bg-amber-900/20">
              <Zap class="h-4 w-4 text-amber-600 dark:text-amber-400" />
            </div>
          </CardHeader>
          <CardContent>
            <div class="text-2xl font-bold">{{ formatNumber(stats.overview.total_documents) }}</div>
          </CardContent>
        </Card>
      </div>

      <!-- Lists -->
      <div class="grid gap-4 md:grid-cols-2 lg:grid-cols-7">
        <Card class="col-span-4">
          <CardHeader>
            <CardTitle>{{ t("admin.pages.dashboard.recentUsers") }}</CardTitle>
            <CardDescription>{{ t("admin.pages.dashboard.recentUsersDesc") }}</CardDescription>
          </CardHeader>
          <CardContent>
            <div class="space-y-8">
              <div v-for="user in stats.recent_users" :key="user.email" class="flex items-center">
                <Avatar class="h-9 w-9">
                  <AvatarImage :src="user.avatar_url || ''" :alt="user.name" />
                  <AvatarFallback>{{
                    user.name?.substring(0, 2).toUpperCase() || "U"
                  }}</AvatarFallback>
                </Avatar>
                <div class="ml-4 space-y-1">
                  <p class="text-sm leading-none font-medium">
                    {{ user.name || t("admin.pages.dashboard.unnamed") }}
                  </p>
                  <p class="text-muted-foreground text-sm">{{ user.email }}</p>
                </div>
                <div class="text-muted-foreground ml-auto text-xs font-medium">
                  {{ formatDate(user.created_at) }}
                </div>
              </div>
            </div>
          </CardContent>
        </Card>
        <Card class="col-span-3">
          <CardHeader>
            <CardTitle>{{ t("admin.pages.dashboard.topAssistants") }}</CardTitle>
            <CardDescription>{{ t("admin.pages.dashboard.topAssistantsDesc") }}</CardDescription>
          </CardHeader>
          <CardContent>
            <div class="space-y-8">
              <div
                v-for="(assistant, index) in stats.top_assistants"
                :key="assistant.name"
                class="flex items-center"
              >
                <div class="bg-muted flex h-9 w-9 items-center justify-center rounded-full">
                  {{ index + 1 }}
                </div>
                <div class="ml-4 space-y-1">
                  <p class="text-sm leading-none font-medium">{{ assistant.name }}</p>
                  <p class="text-muted-foreground text-sm">
                    {{ t("admin.pages.dashboard.conversationsCount", { count: assistant.count }) }}
                  </p>
                </div>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  </div>
</template>

<style scoped></style>
