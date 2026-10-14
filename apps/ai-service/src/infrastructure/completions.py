"""API listener: NOTIFY đánh thức, inbox PostgreSQL phục hồi khi mất tín hiệu."""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from contextlib import aclosing

from psycopg import AsyncConnection
from sqlalchemy.engine import make_url

from .repositories import COMPLETION_CHANNEL

logger = logging.getLogger(__name__)


class CompletionListener:
    def __init__(
        self,
        database_url: str,
        accept: Callable[[], Awaitable[int]],
        *,
        reconcile_seconds: float = 5,
    ):
        self.dsn = (
            make_url(database_url)
            .set(drivername="postgresql")
            .render_as_string(hide_password=False)
        )
        self.accept = accept
        self.reconcile_seconds = reconcile_seconds

    async def run(self) -> None:
        while True:
            try:
                async with await AsyncConnection.connect(
                    self.dsn, autocommit=True, connect_timeout=3
                ) as connection:
                    await connection.execute(f"LISTEN {COMPLETION_CHANNEL}")
                    # LISTEN trước khi đọc inbox để không có cửa sổ bỏ lỡ completion.
                    while True:
                        while await self.accept():
                            await asyncio.sleep(0)
                        async with aclosing(
                            connection.notifies(timeout=self.reconcile_seconds, stop_after=1)
                        ) as notifications:
                            async for _ in notifications:
                                break
            except Exception:
                # Không log exception/DSN/payload vì có thể chứa credential/result.
                logger.warning("Completion listener tạm lỗi; sẽ kết nối và đọc lại inbox")
                await asyncio.sleep(self.reconcile_seconds)
