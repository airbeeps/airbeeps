export default defineNuxtPlugin(() => {
  const colorMode = useColorMode();

  const applyScheme = (mode: string) => {
    if (process.server) return;
    const root = document.documentElement;
    const scheme = mode === "dark" ? "dark" : "light";

    root.classList.remove("dark", "light");
    root.classList.add(scheme);
    root.style.colorScheme = scheme;
  };

  watch(
    () => colorMode.value,
    (mode) => applyScheme(mode),
    { immediate: true }
  );
});
