import asyncio
import logging
from contextlib import suppress

from faststream.rabbit import RabbitBroker
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.topology import NEW_QUEUE_NAME, PAYMENTS_EXCHANGE
from app.models import OutboxEvent

logger = logging.getLogger(__name__)

ERROR_BACKOFF_SECONDS = 5.0


class OutboxRelay:
    """Читает неопубликованные события из outbox и публикует их в RabbitMQ."""

    def __init__(
        self,
        broker: RabbitBroker,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        poll_interval: float,
        batch_size: int,
    ) -> None:
        self._broker = broker
        self._session_factory = session_factory
        self._poll_interval = poll_interval
        self._batch_size = batch_size
        self._task: asyncio.Task[None] | None = None

    def start(self) -> None:
        self._task = asyncio.create_task(self._run(), name="outbox-relay")

    async def stop(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        with suppress(asyncio.CancelledError):
            await self._task
        self._task = None

    async def _run(self) -> None:
        while True:
            try:
                published = await self.publish_pending()
            except Exception:
                logger.exception("Outbox relay failed, retrying in %.0fs", ERROR_BACKOFF_SECONDS)
                await asyncio.sleep(ERROR_BACKOFF_SECONDS)
                continue
            if published < self._batch_size:
                await asyncio.sleep(self._poll_interval)

    async def publish_pending(self) -> int:
        async with self._session_factory() as session:
            result = await session.scalars(
                select(OutboxEvent)
                .where(OutboxEvent.published_at.is_(None))
                .order_by(OutboxEvent.id)
                .limit(self._batch_size)
                .with_for_update(skip_locked=True)
            )
            events = result.all()

            published = 0
            try:
                for event in events:
                    await self._broker.publish(
                        event.payload,
                        exchange=PAYMENTS_EXCHANGE,
                        routing_key=NEW_QUEUE_NAME,
                        persist=True,
                        message_id=str(event.id),
                    )
                    event.published_at = func.now()
                    published += 1
            finally:
                # Фиксируем то, что уже ушло в брокер, даже если следующая публикация упала
                await session.commit()
            return published