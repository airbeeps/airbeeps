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
  Workflow,
  UserCog,
  Sliders,
} from "lucide-vue-next";

const route = useRoute();
const router = useRouter();
const runtimeConfig = useRuntimeConfig();
const unsavedChangesStore = useUnsavedChangesStore();
const enableOAuthProviders = computed(() => !!runtimeConfig.public.enableOAuthProviders);

const modelsOpen = ref(false);
const ragOpen = ref(false);
const userManagementOpen = ref(false);

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
    </SidebarHeader>
    <SidebarContent>
      <SidebarGroup>
        <SidebarGroupContent>
          <SidebarMenu>
            <Collapsible :default-open="true" class="group/collapsible">
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
                      <SidebarMenuSubButton as-child :is-active="route.path === '/admin/analytics'">
                        <NuxtLink to="/admin/analytics">
                          <span>Analytics</span>
                        </NuxtLink>
                      </SidebarMenuSubButton>
                    </SidebarMenuSubItem>
                  </SidebarMenuSub>
                </CollapsibleContent>
              </SidebarMenuItem>
            </Collapsible>

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
                  </SidebarMenuSub>
                </CollapsibleContent>
              </SidebarMenuItem>
            </Collapsible>

            <Collapsible v-model:open="ragOpen" class="group/collapsible">
              <SidebarMenuItem>
                <CollapsibleTrigger as-child>
                  <SidebarMenuButton tooltip="RAG">
                    <Workflow />
                    <span>RAG</span>
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
                          (route.path.startsWith('/admin/assistants') &&
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
                        :is-active="route.path === '/admin/assistants/settings'"
                      >
                        <NuxtLink to="/admin/assistants/settings">
                          <Settings />
                          <span>Settings</span>
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
                  </SidebarMenuSub>
                </CollapsibleContent>
              </SidebarMenuItem>
            </Collapsible>

            <Collapsible v-model:open="userManagementOpen" class="group/collapsible">
              <SidebarMenuItem>
                <CollapsibleTrigger as-child>
                  <SidebarMenuButton tooltip="User Management">
                    <UserCog />
                    <span>User Management</span>
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
                        :is-active="route.path === '/admin/users/settings'"
                      >
                        <NuxtLink to="/admin/users/settings">
                          <Settings />
                          <span>Settings</span>
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
                  </SidebarMenuSub>
                </CollapsibleContent>
              </SidebarMenuItem>
            </Collapsible>

            <SidebarMenuItem v-if="enableOAuthProviders">
              <SidebarMenuButton
                as-child
                :is-active="route.path.startsWith('/admin/oauth-providers')"
                tooltip="OAuth Providers"
              >
                <NuxtLink to="/admin/oauth-providers">
                  <Key />
                  <span>{{ $t("admin.sidebar.oauthProviders") }}</span>
                </NuxtLink>
              </SidebarMenuButton>
            </SidebarMenuItem>

            <SidebarMenuItem>
              <SidebarMenuButton
                as-child
                :is-active="route.path.startsWith('/admin/system-config')"
                tooltip="System Config"
              >
                <NuxtLink to="/admin/system-config">
                  <Settings />
                  <span>{{ $t("admin.sidebar.systemConfig") }}</span>
                </NuxtLink>
              </SidebarMenuButton>
            </SidebarMenuItem>
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
  </Sidebar>
</template>
