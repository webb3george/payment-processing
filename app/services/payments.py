import uuid

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import OutboxEvent, Payment
from app.outbox.events import PAYMENT_CREATED
from app.schemas.payment import PaymentCreate


async def create_payment(
    session: AsyncSession, data: PaymentCreate, idempotency_key: str
) -> Payment:
    """Создаёт платёж и событие outbox в одной транзакции.

    Если платёж с таким idempotency_key уже есть, возвращает его
    и ничего нового не пишет.
    """
    stmt = (
        pg_insert(Payment)
        .values(
            amount=data.amount,
            currency=data.currency,
            description=data.description,
            metadata_=data.metadata,
            idempotency_key=idempotency_key,
            webhook_url=str(data.webhook_url),
        )
        .on_conflict_do_nothing(index_elements=["idempotency_key"])
        .returning(Payment)
    )
    payment = (await session.execute(stmt)).scalar_one_or_none()

    if payment is None:
        existing = await session.execute(
            select(Payment).where(Payment.idempotency_key == idempotency_key)
        )
        return existing.scalar_one()

    session.add(
        OutboxEvent(event_type=PAYMENT_CREATED, payload={"payment_id": str(payment.id)})
    )
    await session.commit()
    return payment


async def get_payment(session: AsyncSession, payment_id: uuid.UUID) -> Payment | None:
    return await session.get(Payment, payment_id)