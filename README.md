# Тестовое задание: Асинхронный сервис процессинга платежей

## Описание

Необходимо реализовать микросервис для асинхронной обработки платежей. Сервис принимает запросы на оплату, обрабатывает их через внешний платежный шлюз (эмуляцию) и уведомляет клиента о результате через webhook.

## Сущности

### Платеж (Payment)

- ID платежа (уникальный идентификатор)
- Сумма (decimal)
- Валюта (RUB, USD, EUR)
- Описание (строка)
- Метаданные (JSON поле для дополнительной информации)
- Статус (pending, succeeded, failed)
- Idempotency key (уникальный ключ для защиты от дублей)
- Webhook URL (для уведомления о результате)
- Даты создания и обработки

## Функционал API

### 1. Создание платежа

**POST /api/v1/payments**

- Заголовок: `Idempotency-Key` (обязательный)
- Body: сумма, валюта, описание, метаданные, webhook_url
- Ответ: 202 Accepted, payment_id, статус, created_at

### 2. Получение информации о платеже

**GET /api/v1/payments/{payment_id}**

- Ответ: детальная информация о платеже

## Технические требования

### Брокер сообщений

- При создании платежа публикуется событие в очередь `payments.new`
- Один consumer:
  - Получает сообщение из очереди
  - Эмулирует обработку платежа (2-5 сек, 90% успех, 10% ошибка)
  - Обновляет статус в БД
  - Отправляет webhook уведомление на указанный URL
  - Реализует повторные попытки при ошибках отправки

### Гарантии доставки

- Outbox pattern для гарантированной публикации событий
- Idempotency key для защиты от дублей
- Dead Letter Queue для сообщений, не обработанных после 3 попыток

### Аутентификация

- Статический API ключ в заголовке `X-API-Key` для всех эндпоинтов

## Стек технологий

- **FastAPI** + Pydantic v2
- **SQLAlchemy 2.0** (асинхронный режим)
- **PostgreSQL**
- **RabbitMQ** (FastStream)
- **Alembic** (миграции)
- **Docker** + docker-compose

## Требования к результату

1. **Модели и миграции**: таблицы payments и outbox
2. **API эндпоинты**: создание и получение платежа
3. **Consumer**: один обработчик, делающий всё
4. **Outbox pattern**: гарантированная доставка событий
5. **Retry**: 3 попытки с экспоненциальной задержкой
6. **Dead Letter Queue**: для окончательно упавших сообщений
7. **Docker**: compose файл с postgres, rabbitmq, api, consumer
8. **Документация**: README с запуском и примерами

## Критерии оценки

- Архитектура и чистота кода
- Корректная реализация Outbox pattern
- Работа с RabbitMQ (очереди, обменники, DLQ)
- Идемпотентность
- Обработка ошибок и retry логика
- Работоспособность Docker-окружения

## Допущения

Чего не хватало в задании (вопрос → принятый ответ):

1. **«3 попытки» — это три обработки или три повтора?** Три обработки всего: первая и два повтора с задержками 2 и 4 с (retry-очереди с TTL). После третьей неудачи сообщение уходит в `payments.new.dlq`.
2. **Что повторяем?** Технические сбои: webhook ответил не 2xx или не ответил за 10 с, ошибка БД. Отказ шлюза (10%) — бизнес-результат: платёж получает `failed`, webhook уходит, повторов нет.
3. **Тот же `Idempotency-Key` с другим телом?** `409 Conflict`. С тем же телом — `202` и уже созданный платёж с текущим статусом. Тело сравнивается по sha256 канонического JSON, поэтому `100` и `100.00` — одно и то же.
4. **Область действия ключа идемпотентности?** Глобальная: при одном статическом API-ключе клиент один.
5. **Может ли webhook прийти дважды?** Да, доставка at-least-once. Клиент дедуплицирует по `payment_id`. Статус платежа при этом меняется ровно один раз (условный `UPDATE … WHERE status = 'pending'`).
6. **Что если consumer упадёт во время эмуляции шлюза?** Сообщение без ack вернётся в очередь, и шлюз будет вызван повторно. Реальному шлюзу передавался бы `payment.id` как ключ идемпотентности.
7. **Где работает outbox relay?** Фоновой задачей в процессе api. `SELECT … FOR UPDATE SKIP LOCKED` позволяет запускать несколько реплик api.
8. **Зачем сервис `webhook-echo`?** Dev-приёмник webhook, чтобы результат был виден без внешних сервисов. Пути `/fail*` отвечают 500 — так проверяются retry и DLQ.

## Запуск

```bash
docker compose up --build
```

| Сервис | Адрес |
|---|---|
| API (Swagger: `/docs`) | http://localhost:8000 |
| RabbitMQ UI (guest / guest) | http://localhost:15672 |
| webhook-echo | http://localhost:9000, логи: `docker compose logs -f webhook-echo` |

API-ключ в compose: `dev-api-key`. Миграции применяет сервис `api` при старте. Несколько consumer: `docker compose up --scale consumer=3`.

## Примеры

Создать платёж:

```bash
curl -s -X POST http://localhost:8000/api/v1/payments \
  -H 'X-API-Key: dev-api-key' \
  -H 'Idempotency-Key: order-42' \
  -H 'Content-Type: application/json' \
  -d '{"amount": "100.50", "currency": "RUB", "description": "Заказ #42", "metadata": {"order_id": 42}, "webhook_url": "http://webhook-echo:9000/ok"}'
```

```json
{"payment_id": "15e41556-aa0a-4475-879d-7b38d835ca0c", "status": "pending", "created_at": "2026-10-07T18:02:39.167056Z"}
```

Повтор с тем же ключом и телом вернёт тот же `payment_id`; с тем же ключом и другим телом — `409`.

Получить платёж (через 2–5 с статус станет `succeeded` или `failed`):

```bash
curl -s http://localhost:8000/api/v1/payments/15e41556-aa0a-4475-879d-7b38d835ca0c -H 'X-API-Key: dev-api-key'
```

```json
{"id": "15e41556-aa0a-4475-879d-7b38d835ca0c", "amount": "100.50", "currency": "RUB", "description": "Заказ #42", "metadata": {"order_id": 42}, "status": "succeeded", "idempotency_key": "order-42", "webhook_url": "http://webhook-echo:9000/ok", "created_at": "2026-10-07T18:02:39.167056Z", "processed_at": "2026-10-07T18:02:44.960146Z"}
```

Webhook в логах `webhook-echo`:

```
POST /ok -> 200 {"payment_id":"15e41556-aa0a-4475-879d-7b38d835ca0c","status":"succeeded","amount":"100.50","currency":"RUB","processed_at":"2026-10-07T18:02:44.960146+00:00"}
```

DLQ: создайте платёж с `"webhook_url": "http://webhook-echo:9000/fail"`. Через ~6 с (три попытки) сообщение появится в очереди `payments.new.dlq` в RabbitMQ UI.

## Тесты

```bash
make test   # unit-тесты; тесты с БД и брокером пропускаются
```

С Postgres и RabbitMQ (без запущенного `consumer`, иначе он заберёт сообщения интеграционного теста):

```bash
docker compose up -d --wait postgres rabbitmq
DATABASE_URL=postgresql+asyncpg://payments:payments@localhost:5432/payments \
RABBITMQ_URL=amqp://guest:guest@localhost:5672/ \
make test
```
