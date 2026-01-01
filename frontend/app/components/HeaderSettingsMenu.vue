<script setup lang="ts">
import { CircleUser, LogOut, MonitorCog, Settings } from "lucide-vue-next";

const userStore = useUserStore();
const { t } = useI18n();

const settingsDialogOpen = ref(false);

const openSettings = () => {
  settingsDialogOpen.value = true;
};

const goToAdmin = () => navigateTo("/admin");

const handleLogout = async () => {
  await userStore.logout();
  await navigateTo("/sign-in");
};
</script>

<template>
  <DropdownMenu>
    <DropdownMenuTrigger as-child>
      <Button
        variant="ghost"
        size="icon"
        class="text-foreground bg-muted hover:bg-muted/90 hover:text-foreground h-11 w-11 rounded-lg transition-colors"
        :title="t('nav.settings')"
      >
        <Settings class="text-foreground/90 h-6 w-6" />
      </Button>
    </DropdownMenuTrigger>
    <DropdownMenuContent align="end" class="w-64 rounded-lg">
      <DropdownMenuLabel class="p-0 font-normal">
        <div class="flex items-center gap-2 px-1 py-1.5 text-left text-sm">
          <Avatar class="h-9 w-9 rounded-lg">
            <AvatarImage :src="userStore.user?.avatar_url || ''" :alt="t('nav.avatar')" />
            <AvatarFallback class="rounded-lg">
              <CircleUser />
            </AvatarFallback>
          </Avatar>
          <div class="grid flex-1 text-left text-sm leading-tight">
            <span class="truncate font-semibold">
              {{ userStore.user?.name || t("nav.mysteriousUser") }}
            </span>
            <span class="truncate text-xs">{{ userStore.user?.email }}</span>
          </div>
        </div>
      </DropdownMenuLabel>
      <DropdownMenuSeparator />
      <DropdownMenuItem @click="openSettings">
        <Settings class="h-4 w-4" />
        {{ t("nav.settings") }}
      </DropdownMenuItem>
      <DropdownMenuItem v-if="userStore.user?.is_superuser" @click="goToAdmin">
        <MonitorCog class="h-4 w-4" />
        {{ t("nav.adminPanel") }}
      </DropdownMenuItem>
      <DropdownMenuSeparator />
      <DropdownMenuItem @click="handleLogout">
        <LogOut class="h-4 w-4" />
        {{ t("common.logout") }}
      </DropdownMenuItem>
    </DropdownMenuContent>
  </DropdownMenu>

  <SettingsDialog v-model:open="settingsDialogOpen" />
</template>
