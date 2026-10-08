"""Budget dùng chung giữa application và workflow, không phụ thuộc SDK."""

from typing import Literal, Protocol

BudgetKind = Literal["model", "tool", "output"]


class Charge(Protocol):
    async def __call__(self, kind: BudgetKind, limit: int, amount: int = 1) -> int:
        """Trừ budget nguyên tử và trả phần còn lại; lỗi khi không được thực thi."""
        ...
