from faststream import FastStream

from app.consumer.handlers import processor
from app.core.broker import broker
from app.core.config import get_settings
from app.core.db import engine, session_factory
from app.core.topology import declare_topology
from app.outbox.relay import OutboxRelay

settings = get_settings()

app = FastStream(broker)

relay = OutboxRelay(
    broker,
    session_factory,
    poll_interval=settings.outbox_poll_interval_seconds,
    batch_size=settings.outbox_batch_size,
)


@app.on_startup
async def setup_topology() -> None:
    await declare_topology(broker)


@app.after_startup
async def start_relay() -> None:
    relay.start()


@app.on_shutdown
async def stop_relay() -> None:
    await relay.stop()


@app.after_shutdown
async def close_resources() -> None:
    await processor.aclose()
    await engine.dispose()