/**
 * MSW mock layer runs when explicitly enabled via VITE_ENABLE_MOCKS.
 *
 * Works in both dev and production builds so the mock demo can be deployed
 * (e.g. Vercel) while no backend services exist yet. Never enabled by
 * default: absent or "false" disables mocking entirely.
 */
export async function enableMocking() {
  if (import.meta.env.VITE_ENABLE_MOCKS !== "true") {
    return;
  }

  // Browser-only MSW export resolves to null in Node, so static import cannot work.
  const { worker } = await import("@/mocks/browser");
  await worker.start({
    onUnhandledFrame: "bypass",
    serviceWorker: { url: "/mockServiceWorker.js" },
  });
}
