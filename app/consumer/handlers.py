from app.core.broker import broker
from app.core.config import get_settings
from app.core.db import session_factory
from app.core.topology import NEW_QUEUE, PAYMENTS_EXCHANGE
from app.schemas.events import PaymentCreatedEvent
from app.services.gateway import PaymentGateway
from app.services.processing import PaymentProcessor
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
async def handle_new_payment(event: PaymentCreatedEvent) -> None:
    await processor.process(event.payment_id)