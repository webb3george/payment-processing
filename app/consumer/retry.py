from faststream.rabbit import RabbitBroker, RabbitMessage

from app.core.topology import (
    DLQ_NAME,
    DLX_EXCHANGE,
    PAYMENTS_EXCHANGE,
    RETRY_DELAYS_MS,
    RETRY_QUEUES,
)
from app.schemas.events import PaymentCreatedEvent

ATTEMPT_HEADER = "x-attempt"
ERROR_TYPE_HEADER = "x-error-type"
ERROR_HEADER = "x-error"
MAX_ERROR_LENGTH = 500


def get_attempt(message: RabbitMessage) -> int:
    """Номер текущей попытки: 1 для сообщения, пришедшего из outbox."""
    try:
        return int(message.headers.get(ATTEMPT_HEADER, 1))
    except (TypeError, ValueError):
        return 1


async def schedule_retry(
    broker: RabbitBroker,
    event: PaymentCreatedEvent,
    message: RabbitMessage,
    *,
    attempt: int,
) -> int:
    """Кладёт событие в retry-очередь. Возвращает задержку в секундах."""
    index = attempt - 1
    await broker.publish(
        event.model_dump(mode="json"),
        exchange=PAYMENTS_EXCHANGE,
        routing_key=RETRY_QUEUES[index].name,
        headers={ATTEMPT_HEADER: attempt + 1},
        persist=True,
        message_id=message.message_id,
    )
    return RETRY_DELAYS_MS[index] // 1000


async def send_to_dead_letter(
    broker: RabbitBroker,
    event: PaymentCreatedEvent,
    message: RabbitMessage,
    *,
    attempt: int,
    error: Exception,
) -> None:
    """Кладёт событие в DLQ вместе с причиной ошибки."""
    await broker.publish(
        event.model_dump(mode="json"),
        exchange=DLX_EXCHANGE,
        routing_key=DLQ_NAME,
        headers={
            ATTEMPT_HEADER: attempt,
            ERROR_TYPE_HEADER: type(error).__name__,
            ERROR_HEADER: str(error)[:MAX_ERROR_LENGTH],
        },
        persist=True,
        message_id=message.message_id,
    )