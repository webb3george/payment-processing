import asyncio
import random

from app.models import PaymentStatus


class PaymentGateway:
    """Эмуляция внешнего платёжного шлюза: задержка и случайный результат."""

    def __init__(self, *, min_delay: float, max_delay: float, success_rate: float) -> None:
        self._min_delay = min_delay
        self._max_delay = max_delay
        self._success_rate = success_rate

    async def process(self) -> PaymentStatus:
        await asyncio.sleep(random.uniform(self._min_delay, self._max_delay))
        if random.random() < self._success_rate:
            return PaymentStatus.SUCCEEDED
        return PaymentStatus.FAILED