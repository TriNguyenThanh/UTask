export interface Neighbours {
  previousTaskId: string | null;
  nextTaskId: string | null;
}

export interface RankedId {
  id: string;
  rank: number;
}

/**
 * Hàng xóm liền kề để gửi cho `PATCH /tasks/{id}/transition/`.
 *
 * Server tính vị trí trên cột đầy đủ của state đích (kể cả subtask và task ngoài sprint đang hiện),
 * và trả 409 nếu hai neighbour không liền kề nhau trong cột đó. Vì vậy `column` phải là danh sách id
 * đầy đủ lấy từ server (đã bỏ chính task đang chuyển, theo `sort_order`), còn `siblings` là các
 * thẻ client đang có trong state đích, dùng để suy ra "đặt sau thẻ nào" từ `rank` lạc quan.
 *
 * - Không có `rank` (chuyển cột từ menu): cuối cột.
 * - Có `rank`: ngay sau thẻ gần nhất có rank nhỏ hơn; không có thì ngay trước thẻ gần nhất có rank lớn hơn.
 * - Thẻ tham chiếu không còn trong `column` (dữ liệu cũ): cuối cột.
 */
export function planNeighbours(
  column: readonly string[],
  siblings: readonly RankedId[],
  rank: number | undefined,
): Neighbours {
  const atEnd: Neighbours = { previousTaskId: column.at(-1) ?? null, nextTaskId: null };
  if (rank === undefined) return atEnd;

  const inColumn = siblings.filter((sibling) => column.includes(sibling.id));
  const after = inColumn.filter((s) => s.rank < rank).sort((a, b) => b.rank - a.rank)[0];
  if (after) {
    const index = column.indexOf(after.id);
    return { previousTaskId: after.id, nextTaskId: column[index + 1] ?? null };
  }
  const before = inColumn.filter((s) => s.rank > rank).sort((a, b) => a.rank - b.rank)[0];
  if (before) {
    const index = column.indexOf(before.id);
    return { previousTaskId: column[index - 1] ?? null, nextTaskId: before.id };
  }
  return atEnd;
}
