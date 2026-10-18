import { generateKeyBetween } from "fractional-indexing";

/**
 * A rank strictly between two neighbours. `null` means "no neighbour on that
 * side" (start or end of the list). Returns `null` when the neighbours are
 * not in order, which would make any key invalid.
 */
export function rankBetween(before: string | null, after: string | null): string | null {
  if (before !== null && after !== null && before >= after) return null;
  try {
    return generateKeyBetween(before, after);
  } catch {
    return null;
  }
}

/** Orders issues the way every list on the board does: by rank, key as tie-break. */
export function compareByRank(a: { rank: string; key: string }, b: { rank: string; key: string }): number {
  if (a.rank === b.rank) return a.key.localeCompare(b.key);
  return a.rank < b.rank ? -1 : 1;
}
