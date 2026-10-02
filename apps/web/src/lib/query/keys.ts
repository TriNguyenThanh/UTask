/**
 * Session-scoped cache keys. Auth session caching lives in AuthProvider;
 * feature slices add their own key namespaces here as they are rebuilt.
 */
export const authKeys = {
  all: ["auth"] as const,
  session: ["auth", "session"] as const,
};