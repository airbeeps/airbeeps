import { defineNuxtPlugin } from "#app";
import { useConfigStore } from "~/stores/config";

export default defineNuxtPlugin(() => {
  const configStore = useConfigStore();

  if (!configStore.isLoaded) {
    // Don't block app mount on config fetch (especially when backend is down)
    configStore.loadConfig();
  }
});
