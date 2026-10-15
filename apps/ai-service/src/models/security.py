"""Identity đã xác minh; credential không xuất hiện trong repr/prompt."""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Principal:
    user_id: str
    bearer: str = field(repr=False)
