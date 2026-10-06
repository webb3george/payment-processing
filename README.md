# Payments Service

Асинхронный микросервис обработки платежей. Принимает запросы на оплату, обрабатывает их через эмуляцию платёжного шлюза и уведомляет клиента о результате через webhook.

**Стек:** FastAPI + Pydantic v2, SQLAlchemy 2.0 (async), PostgreSQL, RabbitMQ (FastStream), Alembic, Docker Compose.

## Быстрый старт

### 1. Требования

- Git
- Docker с Docker Compose
- свободные порты `8000`, `5432`, `5672`, `15672`
- Python 3 (необязательно): нужен только для приёмника webhook из шага 5, устанавливать зависимости для него не требуется

### 2. Получение проекта

```bash
git clone https://github.com/webb3george/payment-processing.git
cd payment-processing
```

### 3. Зависимости

Отдельная установка не нужна: все зависимости ставятся внутри Docker-образа при сборке (версии зафиксированы в `uv.lock`).

API-ключ по умолчанию `change-me`. Чтобы задать свой, создай файл `.env` в корне проекта:

```
API_KEY=my-secret-key
```

Дальше в примерах используется ключ по умолчанию.

### 4. Запуск

```bash
docker compose up --build -d
```

Первая сборка занимает пару минут. Порядок старта: Postgres и RabbitMQ, затем `api` (применяет миграции), затем `consumer`. Поднимутся четыре сервиса:

| Сервис     | Назначение                                         | Адрес                                    |
|------------|----------------------------------------------------|------------------------------------------|
| `api`      | HTTP API (миграции применяются при старте)         | http://localhost:8000 (Swagger: `/docs`) |
| `consumer` | обработка платежей, отправка webhook, relay outbox | -                                        |
| `postgres` | база данных                                        | localhost:5432                           |
| `rabbitmq` | брокер сообщений (веб-интерфейс)                   | http://localhost:15672 (guest / guest)   |

Проверь, что всё готово:

```bash
docker compose ps
curl http://localhost:8000/
```

`postgres`, `rabbitmq` и `api` должны быть в статусе `healthy`, `consumer` в статусе `running`, а запрос вернёт `{"service":"Payments Service"}`. Логи: `docker compose logs -f consumer`. Регулярные строки `GET /` в логе `api` это проверка здоровья от Docker.

### 5. Проверка работы

**Терминал 1.** Запусти приёмник webhook (на Windows `python` вместо `python3`, на Linux добавь флаг `--public`):

```bash
python3 scripts/webhook_receiver.py
```

**Терминал 2.** Создай платёж:

```bash
curl -X POST http://localhost:8000/api/v1/payments \
  -H "X-API-Key: change-me" \
  -H "Idempotency-Key: order-1001" \
  -H "Content-Type: application/json" \
  -d '{
    "amount": "100.50",
    "currency": "RUB",
    "description": "Order #1001",
    "metadata": {"order_id": 1001},
    "webhook_url": "http://host.docker.internal:9000/hook"
  }'
```

Ответ `202 Accepted` со статусом `pending`. Через 2-5 секунд в терминале 1 появится webhook с итоговым статусом (`succeeded` или `failed`). Запроси платёж, подставив свой `payment_id` из ответа:

```bash
curl http://localhost:8000/api/v1/payments/<payment_id> -H "X-API-Key: change-me"
```

Статус финальный, `processed_at` заполнен. Повтори запрос создания с тем же `Idempotency-Key: order-1001`: вернётся тот же `payment_id`, новый платёж не создаётся.

Дополнительно: веб-интерфейс RabbitMQ http://localhost:15672 (guest / guest), вкладка Queues. Swagger http://localhost:8000/docs (кнопка Authorize для ключа).

### 6. Проверка retry и DLQ

Останови приёмник из терминала 1 (Ctrl+C) и создай платёж с новым ключом:

```bash
curl -X POST http://localhost:8000/api/v1/payments \
  -H "X-API-Key: change-me" \
  -H "Idempotency-Key: order-1002" \
  -H "Content-Type: application/json" \
  -d '{
    "amount": "10.00",
    "currency": "USD",
    "description": "DLQ check",
    "webhook_url": "http://host.docker.internal:9000/hook"
  }'
```

Webhook не доставляется, поэтому сервис делает 3 попытки с паузами 2 и 4 секунды. Подожди около 15 секунд и проверь:

```bash
docker compose logs consumer | grep -E "attempt|DLQ"
docker compose exec rabbitmq rabbitmqctl list_queues name messages
```

В логе видны попытки 1/3, 2/3, 3/3, а в очереди `payments.dlq` одно сообщение. Причина ошибки лежит в его заголовках `x-error-type` и `x-error` (видны в веб-интерфейсе RabbitMQ: Queues, `payments.dlq`, Get messages).

### 7. Остановка

```bash
docker compose down        # остановить и удалить контейнеры, данные сохраняются
docker compose down -v     # то же, плюс удалить данные
```

## API

Все эндпоинты требуют заголовок `X-API-Key`.

### `POST /api/v1/payments`: создание платежа

Заголовок `Idempotency-Key` обязателен. Тело запроса:

| Поле          | Описание                                    |
|---------------|---------------------------------------------|
| `amount`      | сумма, больше 0, до 2 знаков после запятой  |
| `currency`    | `RUB`, `USD` или `EUR`                      |
| `description` | описание платежа                            |
| `metadata`    | произвольный JSON (необязательно)           |
| `webhook_url` | адрес для уведомления (http или https)      |

Ответ `202 Accepted`:

```json
{
  "payment_id": "5b0d0c7e-3c1e-4a37-9d6e-0f2d6f5f7c11",
  "status": "pending",
  "created_at": "2026-10-06T12:00:00.123456Z"
}
```

Повторный запрос с тем же `Idempotency-Key` не создаёт дубль и возвращает тот же `payment_id`.

### `GET /api/v1/payments/{payment_id}`: получение платежа

Ответ `200 OK`:

```json
{
  "payment_id": "5b0d0c7e-3c1e-4a37-9d6e-0f2d6f5f7c11",
  "status": "succeeded",
  "created_at": "2026-10-06T12:00:00.123456Z",
  "amount": "100.50",
  "currency": "RUB",
  "description": "Order #1001",
  "metadata": {"order_id": 1001},
  "idempotency_key": "order-1001",
  "webhook_url": "http://host.docker.internal:9000/hook",
  "processed_at": "2026-10-06T12:00:04.512345Z"
}
```

Статусы: `pending`, `succeeded`, `failed`. Если платежа нет, ответ `404`. Без ключа или с неверным ключом ответ `401`.

## Webhook

После обработки на `webhook_url` отправляется `POST` с JSON:

```json
{
  "payment_id": "5b0d0c7e-3c1e-4a37-9d6e-0f2d6f5f7c11",
  "status": "succeeded",
  "amount": "100.50",
  "currency": "RUB",
  "processed_at": "2026-10-06T12:00:04.512345Z"
}
```

Доставкой считается ответ 2xx. Webhook гарантированно доставляется минимум один раз, поэтому получателю стоит дедуплицировать уведомления по `payment_id`.

## Как это работает

1. `POST /api/v1/payments` в одной транзакции сохраняет платёж и событие в таблицу `outbox` (**Outbox pattern**).
2. Relay (фоновая задача в `consumer`) публикует события из `outbox` в очередь `payments.new` и помечает их опубликованными. Событие не теряется, даже если RabbitMQ был недоступен.
3. Consumer получает сообщение, эмулирует обработку (2-5 секунд, 90% успех, 10% ошибка), обновляет статус в БД и отправляет webhook.
4. **Идемпотентность:** `Idempotency-Key` уникален в БД, дубли платежей невозможны. Повторная доставка сообщения не пересчитывает платёж и не дублирует webhook.
5. **Retry:** при сбое (например, недоступен webhook) делается до 3 попыток с экспоненциальной задержкой: 2 секунды, затем 4 секунды. Задержки реализованы очередями `payments.retry.1` и `payments.retry.2`.
6. **Dead Letter Queue:** сообщение, не обработанное за 3 попытки, попадает в `payments.dlq` с причиной ошибки в заголовках.

В таблицу `payments` добавлено поле `webhook_delivered_at`, которого нет в ТЗ. Оно позволяет при повторной обработке не отправлять уже доставленный webhook.