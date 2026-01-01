<script setup lang="ts">
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Activity, Clock, Zap, BarChart3 } from "lucide-vue-next";
import type { AnalyticsStatsResponse } from "~/types/api";

definePageMeta({
  layout: "admin",
  breadcrumb: "Analytics",
});

const { t } = useI18n();
const { data: stats, status } = await useAPI<AnalyticsStatsResponse>(
  "/api/v1/admin/analytics/stats"
);

const formatNumber = (num: number) => new Intl.NumberFormat("en-US").format(num);

// Simple helper to calculate bar height percentage
const getBarHeight = (value: number, max: number) => {
  if (max === 0) return 0;
  return Math.max(4, (value / max) * 100);
};

const maxTokens = computed(() => {
  if (!stats.value?.daily_tokens) return 0;
  return Math.max(
    ...stats.value.daily_tokens.map(
      (d) => (d["Input Tokens"] as number) + (d["Output Tokens"] as number)
    )
  );
});

const maxRequests = computed(() => {
  if (!stats.value?.daily_requests) return 0;
  return Math.max(...stats.value.daily_requests.map((d) => d.value));
});
</script>

<template>
  <div class="flex flex-1 flex-col gap-4 p-4">
    <div v-if="status === 'pending'" class="flex h-96 items-center justify-center">
      {{ t("common.loading") }}
    </div>

    <div v-else-if="stats" class="space-y-6">
      <!-- Summary Cards -->
      <div class="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <Card>
          <CardHeader class="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle class="text-sm font-medium">Total Tokens</CardTitle>
            <Zap class="h-4 w-4 text-amber-500" />
          </CardHeader>
          <CardContent>
            <div class="text-2xl font-bold">
              {{ formatNumber(stats.total_input_tokens + stats.total_output_tokens) }}
            </div>
            <p class="text-muted-foreground text-xs">
              {{ formatNumber(stats.total_input_tokens) }} in /
              {{ formatNumber(stats.total_output_tokens) }} out
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader class="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle class="text-sm font-medium">Total Requests</CardTitle>
            <Activity class="h-4 w-4 text-blue-500" />
          </CardHeader>
          <CardContent>
            <div class="text-2xl font-bold">{{ formatNumber(stats.total_requests) }}</div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader class="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle class="text-sm font-medium">Avg Latency</CardTitle>
            <Clock class="h-4 w-4 text-green-500" />
          </CardHeader>
          <CardContent>
            <div class="text-2xl font-bold">{{ stats.avg_execution_time_ms }} ms</div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader class="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle class="text-sm font-medium">Total Time</CardTitle>
            <Clock class="h-4 w-4 text-purple-500" />
          </CardHeader>
          <CardContent>
            <div class="text-2xl font-bold">
              {{ (stats.total_execution_time_ms / 1000 / 60).toFixed(1) }} min
            </div>
          </CardContent>
        </Card>
      </div>

      <!-- Charts -->
      <div class="grid gap-4 md:grid-cols-2">
        <!-- Token Usage Chart -->
        <Card class="col-span-1">
          <CardHeader>
            <CardTitle>Daily Token Usage (30 Days)</CardTitle>
            <CardDescription>Input vs Output tokens</CardDescription>
          </CardHeader>
          <CardContent>
            <div class="flex h-[200px] items-end gap-1 pt-4">
              <div
                v-for="(day, i) in stats.daily_tokens"
                :key="i"
                class="group relative flex flex-1 flex-col justify-end gap-0.5"
              >
                <div
                  class="w-full rounded-t-sm bg-amber-500/80"
                  :style="{ height: getBarHeight(day['Output Tokens'] as number, maxTokens) + '%' }"
                ></div>
                <div
                  class="w-full rounded-b-sm bg-amber-500/30"
                  :style="{ height: getBarHeight(day['Input Tokens'] as number, maxTokens) + '%' }"
                ></div>

                <!-- Tooltip -->
                <div
                  class="bg-popover text-popover-foreground absolute bottom-full left-1/2 z-10 mb-2 hidden -translate-x-1/2 rounded border p-2 text-xs whitespace-nowrap shadow-md group-hover:block"
                >
                  <div class="font-bold">{{ day.date }}</div>
                  <div>Input: {{ day["Input Tokens"] }}</div>
                  <div>Output: {{ day["Output Tokens"] }}</div>
                </div>
              </div>
            </div>
          </CardContent>
        </Card>

        <!-- Requests Chart -->
        <Card class="col-span-1">
          <CardHeader>
            <CardTitle>Daily Requests (30 Days)</CardTitle>
            <CardDescription>Number of assistant responses</CardDescription>
          </CardHeader>
          <CardContent>
            <div class="flex h-[200px] items-end gap-1 pt-4">
              <div
                v-for="(day, i) in stats.daily_requests"
                :key="i"
                class="group relative flex-1 rounded-sm bg-blue-500/50 transition-colors hover:bg-blue-500/80"
                :style="{ height: getBarHeight(day.value, maxRequests) + '%' }"
              >
                <!-- Tooltip -->
                <div
                  class="bg-popover text-popover-foreground absolute bottom-full left-1/2 z-10 mb-2 hidden -translate-x-1/2 rounded border p-2 text-xs whitespace-nowrap shadow-md group-hover:block"
                >
                  <div class="font-bold">{{ day.name }}</div>
                  <div>Requests: {{ day.value }}</div>
                </div>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  </div>
</template>
