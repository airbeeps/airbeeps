<script setup lang="ts">
import {
  Bot,
  ArrowLeft,
  Building,
  Brain,
  Database,
  MessageSquare,
  Users,
  Key,
  Settings,
  LayoutDashboard,
  ChevronRight,
  UserCog,
  Sliders,
  Wrench,
  Server,
  Activity,
  Sparkles,
  BarChart3,
  Users2,
  Search,
  ThumbsUp,
} from "lucide-vue-next";
import GlobalSearchModal from "~/components/admin/GlobalSearchModal.vue";

// Global search state
const searchOpen = ref(false);

const route = useRoute();
const router = useRouter();
const runtimeConfig = useRuntimeConfig();
const unsavedChangesStore = useUnsavedChangesStore();
const enableOAuthProviders = computed(() => !!runtimeConfig.public.enableOAuthProviders);

// Section collapse states
const dashboardOpen = ref(true);
const assistantsOpen = ref(false);
const modelsOpen = ref(false);
const agentsOpen = ref(false);
const userManagementOpen = ref(false);
const settingsOpen = ref(false);

// Auto-expand sections based on current route
watchEffect(() => {
  const path = route.path;
  if (
    path.startsWith("/admin/assistants") ||
    path.startsWith("/admin/kbs") ||
    path.startsWith("/admin/assistant-defaults")
  ) {
    assistantsOpen.value = true;
  }
  if (path.startsWith("/admin/model") || path === "/admin/models") {
    modelsOpen.value = true;
  }
  if (
    path.startsWith("/admin/agent") ||
    path.startsWith("/admin/mcp") ||
    path.startsWith("/admin/specialist")
  ) {
    agentsOpen.value = true;
  }
  if (
    path.startsWith("/admin/users") ||
    path.startsWith("/admin/conversations") ||
    path.startsWith("/admin/users/roles") ||
    path.startsWith("/admin/feedback")
  ) {
    userManagementOpen.value = true;
  }
  if (
    path.startsWith("/admin/system-config") ||
    path.startsWith("/admin/oauth") ||
    path.startsWith("/admin/audit-logs")
  ) {
    settingsOpen.value = true;
  }
});

const handleLogoClick = async () => {
  if (unsavedChangesStore.isDirty && process.client) {
    const ok = window.confirm("You have unsaved changes. Leave this page and go to Chat?");
    if (!ok) return;
    unsavedChangesStore.clearAll();
  }
  await navigateTo("/chat");
};

const goBackToUser = () => {
  const backPath = (router.options as any)?.history?.state?.back as string | undefined;
  if (backPath && backPath.startsWith("/chat")) {
    return navigateTo(backPath);
  }
  return navigateTo("/chat");
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
          <span class="truncate text-xs">{{ $t("admin.dashboard") }}</span>
        </div>
      </SidebarMenuButton>

      <!-- Global Search Button -->
      <SidebarMenuButton
        size="sm"
        class="text-muted-foreground hover:text-foreground mt-2 justify-start gap-2"
        @click="searchOpen = true"
      >
        <Search class="h-4 w-4" />
        <span class="flex-1 text-left text-sm">{{ $t("admin.globalSearch.button") }}</span>
        <kbd
          class="bg-muted pointer-events-none inline-flex h-5 items-center gap-1 rounded border px-1.5 font-mono text-[10px] font-medium opacity-100 select-none"
        >
          ⌘K
        </kbd>
      </SidebarMenuButton>
    </SidebarHeader>
    <SidebarContent>
      <SidebarGroup>
        <SidebarGroupContent>
          <SidebarMenu>
            <!-- Dashboard Section -->
            <Collapsible v-model:open="dashboardOpen" class="group/collapsible">
              <SidebarMenuItem>
                <CollapsibleTrigger as-child>
                  <SidebarMenuButton tooltip="Dashboard">
                    <LayoutDashboard />
                    <span>Dashboard</span>
                    <ChevronRight
                      class="ml-auto transition-transform duration-200 group-data-[state=open]/collapsible:rotate-90"
                    />
                  </SidebarMenuButton>
                </CollapsibleTrigger>
                <CollapsibleContent>
                  <SidebarMenuSub>
                    <SidebarMenuSubItem>
                      <SidebarMenuSubButton as-child :is-active="route.path === '/admin'">
                        <NuxtLink to="/admin">
                          <span>Overview</span>
                        </NuxtLink>
                      </SidebarMenuSubButton>
                    </SidebarMenuSubItem>
                    <SidebarMenuSubItem>
                      <SidebarMenuSubButton
                        as-child
                        :is-active="route.path === '/admin/system-health'"
                      >
                        <NuxtLink to="/admin/system-health">
                          <Activity class="h-4 w-4" />
                          <span>System Health</span>
                        </NuxtLink>
                      </SidebarMenuSubButton>
                    </SidebarMenuSubItem>
                  </SidebarMenuSub>
                </CollapsibleContent>
              </SidebarMenuItem>
            </Collapsible>

            <!-- Assistants Section (promoted to top-level) -->
            <Collapsible v-model:open="assistantsOpen" class="group/collapsible">
              <SidebarMenuItem>
                <CollapsibleTrigger as-child>
                  <SidebarMenuButton tooltip="Assistants">
                    <Bot />
                    <span>Assistants</span>
                    <ChevronRight
                      class="ml-auto transition-transform duration-200 group-data-[state=open]/collapsible:rotate-90"
                    />
                  </SidebarMenuButton>
                </CollapsibleTrigger>
                <CollapsibleContent>
                  <SidebarMenuSub>
                    <SidebarMenuSubItem>
                      <SidebarMenuSubButton
                        as-child
                        :is-active="
                          route.path === '/admin/assistants' ||
                          (route.path.startsWith('/admin/assistants/') &&
                            !route.path.includes('/settings'))
                        "
                      >
                        <NuxtLink to="/admin/assistants">
                          <Bot />
                          <span>{{ $t("admin.sidebar.assistants") }}</span>
                        </NuxtLink>
                      </SidebarMenuSubButton>
                    </SidebarMenuSubItem>
                    <SidebarMenuSubItem>
                      <SidebarMenuSubButton
                        as-child
                        :is-active="route.path.startsWith('/admin/kbs')"
                      >
                        <NuxtLink to="/admin/kbs">
                          <Database />
                          <span>{{ $t("admin.sidebar.knowledgeBases") }}</span>
                        </NuxtLink>
                      </SidebarMenuSubButton>
                    </SidebarMenuSubItem>
                    <SidebarMenuSubItem>
                      <SidebarMenuSubButton
                        as-child
                        :is-active="route.path.startsWith('/admin/assistant-defaults')"
                      >
                        <NuxtLink to="/admin/assistant-defaults">
                          <Sliders />
                          <span>{{ $t("admin.sidebar.assistantDefaults") }}</span>
                        </NuxtLink>
                      </SidebarMenuSubButton>
                    </SidebarMenuSubItem>
                    <SidebarMenuSubItem>
                      <SidebarMenuSubButton
                        as-child
                        :is-active="route.path === '/admin/assistants/settings'"
                      >
                        <NuxtLink to="/admin/assistants/settings">
                          <Settings />
                          <span>Settings</span>
                        </NuxtLink>
                      </SidebarMenuSubButton>
                    </SidebarMenuSubItem>
                  </SidebarMenuSub>
                </CollapsibleContent>
              </SidebarMenuItem>
            </Collapsible>

            <!-- Models Section -->
            <Collapsible v-model:open="modelsOpen" class="group/collapsible">
              <SidebarMenuItem>
                <CollapsibleTrigger as-child>
                  <SidebarMenuButton tooltip="Models">
                    <Brain />
                    <span>Models</span>
                    <ChevronRight
                      class="ml-auto transition-transform duration-200 group-data-[state=open]/collapsible:rotate-90"
                    />
                  </SidebarMenuButton>
                </CollapsibleTrigger>
                <CollapsibleContent>
                  <SidebarMenuSub>
                    <SidebarMenuSubItem>
                      <SidebarMenuSubButton
                        as-child
                        :is-active="route.path === '/admin/model-providers'"
                      >
                        <NuxtLink to="/admin/model-providers">
                          <Building />
                          <span>{{ $t("admin.sidebar.modelProviders") }}</span>
                        </NuxtLink>
                      </SidebarMenuSubButton>
                    </SidebarMenuSubItem>
                    <SidebarMenuSubItem>
                      <SidebarMenuSubButton as-child :is-active="route.path === '/admin/models'">
                        <NuxtLink to="/admin/models">
                          <Brain />
                          <span>{{ $t("admin.sidebar.models") }}</span>
                        </NuxtLink>
                      </SidebarMenuSubButton>
                    </SidebarMenuSubItem>
                    <SidebarMenuSubItem>
                      <SidebarMenuSubButton
                        as-child
                        :is-active="route.path === '/admin/model-analytics'"
                      >
                        <NuxtLink to="/admin/model-analytics">
                          <BarChart3 />
                          <span>Analytics</span>
                        </NuxtLink>
                      </SidebarMenuSubButton>
                    </SidebarMenuSubItem>
                  </SidebarMenuSub>
                </CollapsibleContent>
              </SidebarMenuItem>
            </Collapsible>

            <!-- Agents Section -->
            <Collapsible v-model:open="agentsOpen" class="group/collapsible">
              <SidebarMenuItem>
                <CollapsibleTrigger as-child>
                  <SidebarMenuButton tooltip="Agents">
                    <Sparkles />
                    <span>Agents</span>
                    <ChevronRight
                      class="ml-auto transition-transform duration-200 group-data-[state=open]/collapsible:rotate-90"
                    />
                  </SidebarMenuButton>
                </CollapsibleTrigger>
                <CollapsibleContent>
                  <SidebarMenuSub>
                    <SidebarMenuSubItem>
                      <SidebarMenuSubButton
                        as-child
                        :is-active="route.path === '/admin/agent-tools'"
                      >
                        <NuxtLink to="/admin/agent-tools">
                          <Wrench />
                          <span>Tools</span>
                        </NuxtLink>
                      </SidebarMenuSubButton>
                    </SidebarMenuSubItem>
                    <SidebarMenuSubItem>
                      <SidebarMenuSubButton
                        as-child
                        :is-active="route.path.startsWith('/admin/specialists')"
                      >
                        <NuxtLink to="/admin/specialists">
                          <Users2 />
                          <span>Specialists</span>
                        </NuxtLink>
                      </SidebarMenuSubButton>
                    </SidebarMenuSubItem>
                    <SidebarMenuSubItem>
                      <SidebarMenuSubButton
                        as-child
                        :is-active="route.path.startsWith('/admin/mcp-servers')"
                      >
                        <NuxtLink to="/admin/mcp-servers">
                          <Server />
                          <span>MCP Servers</span>
                        </NuxtLink>
                      </SidebarMenuSubButton>
                    </SidebarMenuSubItem>
                    <SidebarMenuSubItem>
                      <SidebarMenuSubButton
                        as-child
                        :is-active="route.path.startsWith('/admin/agent-traces')"
                      >
                        <NuxtLink to="/admin/agent-traces">
                          <Activity />
                          <span>Traces</span>
                        </NuxtLink>
                      </SidebarMenuSubButton>
                    </SidebarMenuSubItem>
                  </SidebarMenuSub>
                </CollapsibleContent>
              </SidebarMenuItem>
            </Collapsible>

            <!-- Users Section -->
            <Collapsible v-model:open="userManagementOpen" class="group/collapsible">
              <SidebarMenuItem>
                <CollapsibleTrigger as-child>
                  <SidebarMenuButton tooltip="Users">
                    <UserCog />
                    <span>Users</span>
                    <ChevronRight
                      class="ml-auto transition-transform duration-200 group-data-[state=open]/collapsible:rotate-90"
                    />
                  </SidebarMenuButton>
                </CollapsibleTrigger>
                <CollapsibleContent>
                  <SidebarMenuSub>
                    <SidebarMenuSubItem>
                      <SidebarMenuSubButton
                        as-child
                        :is-active="
                          route.path === '/admin/users' ||
                          (route.path.startsWith('/admin/users/') &&
                            !route.path.includes('/settings'))
                        "
                      >
                        <NuxtLink to="/admin/users">
                          <Users />
                          <span>{{ $t("admin.sidebar.users") }}</span>
                        </NuxtLink>
                      </SidebarMenuSubButton>
                    </SidebarMenuSubItem>
                    <SidebarMenuSubItem>
                      <SidebarMenuSubButton
                        as-child
                        :is-active="route.path === '/admin/conversations'"
                      >
                        <NuxtLink to="/admin/conversations">
                          <MessageSquare />
                          <span>{{ $t("admin.sidebar.conversations") }}</span>
                        </NuxtLink>
                      </SidebarMenuSubButton>
                    </SidebarMenuSubItem>
                    <SidebarMenuSubItem>
                      <SidebarMenuSubButton
                        as-child
                        :is-active="route.path.startsWith('/admin/feedback')"
                      >
                        <NuxtLink to="/admin/feedback">
                          <ThumbsUp />
                          <span>{{ $t("admin.sidebar.feedback") }}</span>
                        </NuxtLink>
                      </SidebarMenuSubButton>
                    </SidebarMenuSubItem>
                    <SidebarMenuSubItem>
                      <SidebarMenuSubButton
                        as-child
                        :is-active="route.path === '/admin/users/roles'"
                      >
                        <NuxtLink to="/admin/users/roles">
                          <UserCog />
                          <span>{{ $t("admin.sidebar.roles") }}</span>
                        </NuxtLink>
                      </SidebarMenuSubButton>
                    </SidebarMenuSubItem>
                    <SidebarMenuSubItem>
                      <SidebarMenuSubButton
                        as-child
                        :is-active="route.path === '/admin/users/settings'"
                      >
                        <NuxtLink to="/admin/users/settings">
                          <Settings />
                          <span>Settings</span>
                        </NuxtLink>
                      </SidebarMenuSubButton>
                    </SidebarMenuSubItem>
                  </SidebarMenuSub>
                </CollapsibleContent>
              </SidebarMenuItem>
            </Collapsible>

            <!-- Settings Section (consolidated) -->
            <Collapsible v-model:open="settingsOpen" class="group/collapsible">
              <SidebarMenuItem>
                <CollapsibleTrigger as-child>
                  <SidebarMenuButton tooltip="Settings">
                    <Settings />
                    <span>Settings</span>
                    <ChevronRight
                      class="ml-auto transition-transform duration-200 group-data-[state=open]/collapsible:rotate-90"
                    />
                  </SidebarMenuButton>
                </CollapsibleTrigger>
                <CollapsibleContent>
                  <SidebarMenuSub>
                    <SidebarMenuSubItem>
                      <SidebarMenuSubButton
                        as-child
                        :is-active="route.path.startsWith('/admin/system-config')"
                      >
                        <NuxtLink to="/admin/system-config">
                          <Settings />
                          <span>{{ $t("admin.sidebar.systemConfig") }}</span>
                        </NuxtLink>
                      </SidebarMenuSubButton>
                    </SidebarMenuSubItem>
                    <SidebarMenuSubItem v-if="enableOAuthProviders">
                      <SidebarMenuSubButton
                        as-child
                        :is-active="route.path.startsWith('/admin/oauth-providers')"
                      >
                        <NuxtLink to="/admin/oauth-providers">
                          <Key />
                          <span>{{ $t("admin.sidebar.oauthProviders") }}</span>
                        </NuxtLink>
                      </SidebarMenuSubButton>
                    </SidebarMenuSubItem>
                    <SidebarMenuSubItem>
                      <SidebarMenuSubButton
                        as-child
                        :is-active="route.path.startsWith('/admin/audit-logs')"
                      >
                        <NuxtLink to="/admin/audit-logs">
                          <Activity />
                          <span>{{ $t("admin.sidebar.auditLogs") }}</span>
                        </NuxtLink>
                      </SidebarMenuSubButton>
                    </SidebarMenuSubItem>
                  </SidebarMenuSub>
                </CollapsibleContent>
              </SidebarMenuItem>
            </Collapsible>
          </SidebarMenu>
        </SidebarGroupContent>
      </SidebarGroup>
    </SidebarContent>
    <SidebarFooter>
      <SidebarMenuItem>
        <SidebarMenuButton
          @click="goBackToUser"
          variant="outline"
          size="lg"
          class="border-primary/50 text-primary hover:border-primary hover:text-primary data-[active=true]:bg-sidebar-accent/60 mt-1 font-semibold hover:shadow-sm"
        >
          <ArrowLeft class="shrink-0" />
          <span class="truncate">{{ $t("admin.sidebar.backToUser") }}</span>
        </SidebarMenuButton>
      </SidebarMenuItem>
      <NavUser />
    </SidebarFooter>
    <SidebarRail />

    <!-- Global Search Modal -->
    <GlobalSearchModal v-model:open="searchOpen" />
  </Sidebar>
</template>
