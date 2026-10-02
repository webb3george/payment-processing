from faststream.rabbit import ExchangeType, RabbitBroker, RabbitExchange, RabbitQueue

NEW_QUEUE_NAME = "payments.new"
DLQ_NAME = "payments.dlq"

# Паузы перед 2-й и 3-й попытками, мс. Всего попыток = len(RETRY_DELAYS_MS) + 1.
RETRY_DELAYS_MS = (2_000, 4_000)

PAYMENTS_EXCHANGE = RabbitExchange("payments", type=ExchangeType.DIRECT, durable=True)
DLX_EXCHANGE = RabbitExchange("payments.dlx", type=ExchangeType.DIRECT, durable=True)

NEW_QUEUE = RabbitQueue(
    NEW_QUEUE_NAME,
    durable=True,
    arguments={
        "x-dead-letter-exchange": DLX_EXCHANGE.name,
        "x-dead-letter-routing-key": DLQ_NAME,
    },
)

DLQ_QUEUE = RabbitQueue(DLQ_NAME, durable=True)

# Очереди ожидания: без consumer'ов. Сообщение лежит до истечения TTL,
# затем RabbitMQ сам возвращает его в payments.new.
RETRY_QUEUES = tuple(
    RabbitQueue(
        f"payments.retry.{n}",
        durable=True,
        arguments={
            "x-message-ttl": delay_ms,
            "x-dead-letter-exchange": PAYMENTS_EXCHANGE.name,
            "x-dead-letter-routing-key": NEW_QUEUE_NAME,
        },
    )
    for n, delay_ms in enumerate(RETRY_DELAYS_MS, start=1)
)


async def declare_topology(broker: RabbitBroker) -> None:
    """Объявляет все обменники и очереди и привязывает их (routing key = имя очереди)."""
    await broker.connect()

    payments = await broker.declare_exchange(PAYMENTS_EXCHANGE)
    dlx = await broker.declare_exchange(DLX_EXCHANGE)

    for queue in (NEW_QUEUE, *RETRY_QUEUES):
        declared = await broker.declare_queue(queue)
        await declared.bind(payments, routing_key=declared.name)

    declared_dlq = await broker.declare_queue(DLQ_QUEUE)
    await declared_dlq.bind(dlx, routing_key=declared_dlq.name)