/**
 * Numeric sort-order helpers (D2).
 * `rank` is a plain `number`; `rankBetween` returns the midpoint.
 */

/**
 * A rank strictly between two neighbours. `null` means "no neighbour on that
 * side" (start or end of the list).
 * - both null → 1
 * - no before → after - 1
 * - no after → before + 1
 * Returns `null` when `before >= after` or the midpoint is not strictly
 * between the two (float exhausted).
 */
export function rankBetween(before: number | null, after: number | null): number | null {
  if (before === null && after === null) return 1;
  if (before === null) return after! - 1;
  if (after === null) return before + 1;
  if (before >= after) return null;
  const mid = (before + after) / 2;
  if (mid <= before || mid >= after) return null; // float exhausted
  return mid;
}

/** Orders issues the way every list on the board does: by rank, key as tie-break. */
export function compareByRank(a: { rank: number; key: string }, b: { rank: number; key: string }): number {
  if (a.rank !== b.rank) return a.rank - b.rank;
  return a.key.localeCompare(b.key);
}
