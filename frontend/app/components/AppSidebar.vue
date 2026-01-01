<script setup lang="ts">
import { computed } from "vue";
import { SquarePen, ChevronsRight } from "lucide-vue-next";
import { Button } from "~/components/ui/button";
import { useSidebar } from "~/components/ui/sidebar";
// when the route is /chatwith/:id, active the menu item
const route = useRoute();
const isActive = computed(() => {
  return route.path.startsWith("/chat") || route.path.startsWith("/assistants");
});

const runtimeConfig = useRuntimeConfig();
const userStore = useUserStore();
const unsavedChangesStore = useUnsavedChangesStore();
const { state, toggleSidebar } = useSidebar();
const isCollapsed = computed(() => state.value === "collapsed");

const handleSignIn = () => navigateTo("/sign-in");
const handleSignUp = () => navigateTo("/sign-up");

const handleLogoClick = async () => {
  if (unsavedChangesStore.isDirty && process.client) {
    const ok = window.confirm("You have unsaved changes. Leave this page and go to Chat?");
    if (!ok) return;
    unsavedChangesStore.clearAll();
  }
  await navigateTo("/chat");
};
</script>

<template>
  <Sidebar collapsible="icon">
    <SidebarHeader>
      <SidebarMenuButton
        size="lg"
        class="data-[state=open]:bg-sidebar-accent data-[state=open]:text-sidebar-accent-foreground"
        @click="handleLogoClick"
      >
        <div
          class="text-sidebar-primary-foreground flex aspect-square size-8 items-center justify-center rounded-lg"
        >
          <img src="/logo.png" alt="Logo" />
        </div>
        <div class="grid flex-1 text-left text-sm leading-tight">
          <span class="truncate font-bold">
            {{ runtimeConfig.public.appName }}
          </span>
          <span class="text-sidebar-foreground/70 truncate text-xs"> Chat </span>
        </div>
      </SidebarMenuButton>
      <SidebarMenu>
        <SidebarMenuItem>
          <SidebarMenuButton as-child :is-active="isActive">
            <NuxtLink to="/chat">
              <SquarePen />
              <span>{{ $t("nav.newChat") }}</span>
            </NuxtLink>
          </SidebarMenuButton>
        </SidebarMenuItem>
      </SidebarMenu>
    </SidebarHeader>
    <SidebarContent>
      <ClientOnly>
        <NavHistoryList v-if="userStore.user" />
      </ClientOnly>
    </SidebarContent>
    <SidebarFooter>
      <ClientOnly>
        <template v-if="!userStore.user">
          <div class="space-y-2 p-2">
            <Button class="w-full" @click="handleSignIn">
              {{ $t("auth.signIn") }}
            </Button>
            <Button variant="outline" class="w-full" @click="handleSignUp">
              {{ $t("auth.signUp") }}
            </Button>
          </div>
        </template>
      </ClientOnly>
      <div v-if="isCollapsed" class="mt-2 flex justify-center">
        <Button variant="ghost" size="icon" :title="$t('nav.expandSidebar')" @click="toggleSidebar">
          <ChevronsRight class="size-4" />
          <span class="sr-only">{{ $t("nav.expandSidebar") }}</span>
        </Button>
      </div>
    </SidebarFooter>
    <SidebarRail />
  </Sidebar>
</template>
