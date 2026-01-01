import { defineStore } from "pinia";

type DirtySources = Record<string, true>;

export const useUnsavedChangesStore = defineStore("unsavedChanges", () => {
  const dirtySources = ref<DirtySources>({});

  const isDirty = computed(() => Object.keys(dirtySources.value).length > 0);

  const setDirty = (sourceId: string, dirty: boolean) => {
    if (!sourceId) return;
    if (dirty) {
      dirtySources.value[sourceId] = true;
    } else {
      // eslint-disable-next-line @typescript-eslint/no-dynamic-delete
      delete dirtySources.value[sourceId];
    }
  };

  const clearAll = () => {
    dirtySources.value = {};
  };

  return {
    dirtySources,
    isDirty,
    setDirty,
    clearAll,
  };
});
