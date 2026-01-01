import { isPublicRoute } from "~/utils/publicRoutes";

export default defineNuxtRouteMiddleware(async (to) => {
  const routeInfo = { name: to.name?.toString() };
  const isPublic = isPublicRoute(routeInfo);

  const userStore = useUserStore();
  const backendStore = useBackendStore();
  const signInRoute = { path: "/sign-in", query: { redirect: to.fullPath } };

  if (to.path === "/") {
    return navigateTo("/chat");
  }

  // If backend is offline, don't block navigation with auth checks.
  // A global overlay will guide the user to start the backend.
  if (backendStore.isOffline) {
    return;
  }

  if (!isPublic && !userStore.user && !userStore.loading) {
    const isLoggedIn = await userStore.fetchUser();

    if (userStore.verificationRequired) {
      return navigateTo("/verify-email");
    }

    if (!isLoggedIn && !isPublic) {
      return navigateTo(signInRoute);
    }
  }

  if (isPublic) {
    return;
  }

  if (userStore.loading || userStore.user) {
    return;
  }

  return navigateTo(signInRoute);
});
