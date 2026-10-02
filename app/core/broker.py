from faststream.rabbit import RabbitBroker
from faststream.rabbit.schemas import Channel

from app.core.config import get_settings

settings = get_settings()

broker = RabbitBroker(
    settings.rabbitmq_url,
    default_channel=Channel(prefetch_count=settings.consumer_prefetch_count),
)