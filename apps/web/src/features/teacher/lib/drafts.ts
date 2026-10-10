import { useCallback, useEffect, useState } from "react";

/**
 * Drafts live in sessionStorage: they survive a refresh in this tab and go
 * away with it. The key always includes the signed-in user, so one account's
 * draft is never offered to another, and every access is guarded because
 * storage can be unavailable (private mode, blocked site data).
 */

const PREFIX = "utask.draft.";

export function draftKey(userId: string, ...parts: string[]): string {
  return `${PREFIX}${userId}.${parts.join(".")}`;
}

export function readDraft(key: string): string {
  try {
    return sessionStorage.getItem(key) ?? "";
  } catch {
    return "";
  }
}

export function writeDraft(key: string, value: string): void {
  try {
    if (value === "") sessionStorage.removeItem(key);
    else sessionStorage.setItem(key, value);
  } catch {
    // Storage unavailable: the draft just stays in memory for this page.
  }
}

/** Forget every draft in this tab (explicit sign-out on a shared device). */
export function clearAllDrafts(): void {
  try {
    for (const key of Object.keys(sessionStorage)) {
      if (key.startsWith(PREFIX)) sessionStorage.removeItem(key);
    }
  } catch {
    // Nothing to clear if storage is unavailable.
  }
}

/** Text state backed by a draft key; changing the key loads that key's draft. */
export function useDraft(key: string): [string, (value: string) => void, () => void] {
  const [value, setValue] = useState(() => readDraft(key));

  useEffect(() => {
    setValue(readDraft(key));
  }, [key]);

  const update = useCallback(
    (next: string) => {
      setValue(next);
      writeDraft(key, next);
    },
    [key],
  );
  const clear = useCallback(() => update(""), [update]);
  return [value, update, clear];
}
