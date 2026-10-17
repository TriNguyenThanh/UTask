/**
 * Board and backlog writes (drag, move menu, blocked flag) only exist on the
 * Demo MSW layer: Project Service has no code and no contract yet. Against a
 * real backend the board stays read-only, so no button can pretend to save.
 *
 * Read at call time, not at import time, so tests can stub the environment.
 */
export function demoWritesEnabled(): boolean {
  return import.meta.env.VITE_ENABLE_MOCKS === "true";
}
