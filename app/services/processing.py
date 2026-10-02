import uuid

from sqlalchemy import func, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models import Payment, PaymentStatus
from app.schemas.webhook import WebhookPayload
from app.services.gateway import PaymentGateway
from app.services.webhook import WebhookSender


class PaymentNotFoundError(Exception):
    """Событие ссылается на платёж, которого нет в БД. Повтор не поможет."""


class PaymentProcessor:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        gateway: PaymentGateway,
        webhook_sender: WebhookSender,
    ) -> None:
        self._session_factory = session_factory
        self._gateway = gateway
        self._webhook_sender = webhook_sender

    async def process(self, payment_id: uuid.UUID) -> None:
        payment = await self._get(payment_id)

        # Эмуляция только для ещё не обработанного платежа: при повторной
        # доставке сообщения платёж не пересчитывается.
        if payment.status == PaymentStatus.PENDING:
            result = await self._gateway.process()
            await self._set_result(payment_id, result)
            payment = await self._get(payment_id)

        if payment.webhook_delivered_at is not None:
            return

        payload = WebhookPayload.model_validate(payment).model_dump(mode="json")
        await self._webhook_sender.send(payment.webhook_url, payload)
        await self._mark_webhook_delivered(payment_id)

    async def aclose(self) -> None:
        await self._webhook_sender.aclose()

    async def _get(self, payment_id: uuid.UUID) -> Payment:
        async with self._session_factory() as session:
            payment = await session.get(Payment, payment_id)
        if payment is None:
            raise PaymentNotFoundError(str(payment_id))
        return payment

    async def _set_result(self, payment_id: uuid.UUID, status: PaymentStatus) -> None:
        async with self._session_factory() as session:
            await session.execute(
                update(Payment)
                .where(Payment.id == payment_id, Payment.status == PaymentStatus.PENDING)
                .values(status=status, processed_at=func.now())
            )
            await session.commit()

    async def _mark_webhook_delivered(self, payment_id: uuid.UUID) -> None:
        async with self._session_factory() as session:
            await session.execute(
                update(Payment)
                .where(Payment.id == payment_id, Payment.webhook_delivered_at.is_(None))
                .values(webhook_delivered_at=func.now())
            )
            await session.commit()