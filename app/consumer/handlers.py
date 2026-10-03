from faststream import Logger
from faststream.rabbit import RabbitMessage

from app.consumer.retry import get_attempt, schedule_retry, send_to_dead_letter
from app.core.broker import broker
from app.core.config import get_settings
from app.core.db import session_factory
from app.core.topology import MAX_ATTEMPTS, NEW_QUEUE, PAYMENTS_EXCHANGE
from app.schemas.events import PaymentCreatedEvent
from app.services.gateway import PaymentGateway
from app.services.processing import PaymentNotFoundError, PaymentProcessor
from app.services.webhook import WebhookSender

settings = get_settings()

processor = PaymentProcessor(
    session_factory,
    PaymentGateway(
        min_delay=settings.gateway_min_delay_seconds,
        max_delay=settings.gateway_max_delay_seconds,
        success_rate=settings.gateway_success_rate,
    ),
    WebhookSender(timeout=settings.webhook_timeout_seconds),
)


@broker.subscriber(NEW_QUEUE, PAYMENTS_EXCHANGE)
async def handle_new_payment(
    event: PaymentCreatedEvent,
    message: RabbitMessage,
    logger: Logger,
) -> None:
    attempt = get_attempt(message)
    try:
        await processor.process(event.payment_id)
    except PaymentNotFoundError as exc:
        # Повтор не поможет: платежа нет. Сразу в DLQ.
        logger.error("payment %s not found, sending to DLQ", event.payment_id)
        await send_to_dead_letter(broker, event, message, attempt=attempt, error=exc)
    except Exception as exc:
        if attempt < MAX_ATTEMPTS:
            delay = await schedule_retry(broker, event, message, attempt=attempt)
            logger.warning(
                "payment %s: attempt %d/%d failed (%r), retry in %ds",
                event.payment_id,
                attempt,
                MAX_ATTEMPTS,
                exc,
                delay,
            )
        else:
            logger.error(
                "payment %s: attempt %d/%d failed (%r), sending to DLQ",
                event.payment_id,
                attempt,
                MAX_ATTEMPTS,
                exc,
            )
            await send_to_dead_letter(broker, event, message, attempt=attempt, error=exc)