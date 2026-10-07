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

1. **«3 попытки» — это три обработки или три повтора?** Три обработки всего: первая и два повтора с экспоненциальной задержкой 5 с × 5ⁿ, то есть через 5 и 25 с (retry-очереди с TTL). Окно в 30 с переживает перезапуск Postgres или брокера, а не отправляет в DLQ всё, что было в обработке. После третьей неудачи сообщение уходит в `payments.new.dlq`.
2. **Что повторяем?** Технические сбои: webhook ответил не 2xx или не ответил за 10 с, ошибка БД. Отказ шлюза (10%) — бизнес-результат: платёж получает `failed`, webhook уходит, повторов нет.
3. **Тот же `Idempotency-Key` с другим телом?** `409 Conflict`. С тем же телом — `202` и уже созданный платёж с текущим статусом. Тело сравнивается по sha256 канонического JSON, поэтому `100` и `100.00` — одно и то же.
4. **Область действия ключа идемпотентности?** Глобальная: при одном статическом API-ключе клиент один.
5. **Может ли webhook прийти дважды?** Да, доставка at-least-once. Клиент дедуплицирует по `payment_id`. Статус платежа при этом меняется ровно один раз (условный `UPDATE … WHERE status = 'pending'`).
6. **Что если сообщение придёт дважды, в том числе одновременно?** Шлюз идемпотентен по `payment.id`: повторный вызов возвращает результат первого списания и не списывает снова. Эмулятор помнит списания в памяти процесса; реальному шлюзу `payment.id` передавался бы как ключ идемпотентности.
7. **Где работает outbox relay?** Фоновой задачей в процессе api. `SELECT … FOR UPDATE SKIP LOCKED` позволяет запускать несколько реплик api.
8. **В каком виде передавать `amount`?** Строкой (`"100.50"`) или целым числом. Дробное JSON-число (`100.5`) отклоняется с `422`: при разборе JSON оно проходит через `float` и после ~15 значащих цифр молча округляется.
9. **Зачем сервис `webhook-echo`?** Dev-приёмник webhook, чтобы результат был виден без внешних сервисов. Пути `/fail*` отвечают 500 — так проверяются retry и DLQ.
10. **Что происходит с сообщением в DLQ?** Если все три попытки упали до списания (например, была недоступна БД), платёж остаётся `pending`; если не дошёл только webhook — статус уже итоговый. Автоматически из DLQ ничего не возвращается: после устранения причины `make dlq-replay` переносит сообщения обратно в `payments.new` как первые попытки.
11. **`X-API-Key` нужен и на служебных эндпоинтах?** Нет. Ключ обязателен на всех эндпоинтах API (`/api/v1/*`). Пробы `/health` и `/ready`, а также документация `/docs` и `/openapi.json` открыты.
12. **Можно ли указать любой `webhook_url`?** Только адрес, который разрешается в публичные IP — иначе клиент мог бы через webhook обращаться к нашей внутренней сети. Очевидно внутренние (`localhost`, IP-литералы частных сетей и link-local, включая `169.254.169.254`) API отклоняет сразу с `422`. Остальные consumer резолвит до списания и ещё раз перед отправкой; если адрес оказался внутренним, платёж получает `failed` без списания (виден через GET), а сообщение уходит в DLQ без повторов. Исключения задаются `WEBHOOK_ALLOWED_HOSTS` и действуют одинаково для api и consumer (в compose это `webhook-echo`). Ограничение: httpx резолвит имя заново, поэтому смена DNS-записи между проверкой и подключением (DNS rebinding) не закрыта.
13. **Удаляются ли записи outbox?** Нет, опубликованные записи остаются с `published_at`. Для продакшена нужна периодическая чистка, например удаление записей старше нескольких дней.
14. **Что проверяют пробы?** `/health` — что процесс жив, без проверки зависимостей. `/ready` — что Postgres отвечает на `SELECT 1` за 2 с; по нему работает healthcheck api в compose. RabbitMQ в `/ready` намеренно не входит: благодаря outbox api принимает платежи и без брокера, а readiness, завязанный на брокер, вывел бы api из балансировки именно тогда, когда outbox должен выручать.
15. **Что если consumer падает на сообщении?** Повторная доставка после падения сохраняет `x-attempt`, поэтому счётчик попыток её не остановит. Очереди — quorum: у `payments.new` задан `x-delivery-limit: 5`, после пятой неподтверждённой доставки сообщение уходит в DLQ. Перенос в DLQ — `at-least-once`, чтобы сообщение не потерялось по дороге.

## Архитектура

```
POST /api/v1/payments ──► api: payments + outbox в одной транзакции ──► 202
api, фоновый outbox relay (подключается к брокеру сам) ──► exchange payments ──► payments.new
payments.new ──► consumer: шлюз (2–5 с) → статус в БД → webhook ──► ack
   ├─ ошибка на попытке 1 или 2 ──► payments.new.retry.N (TTL 5 / 25 с) ──► снова payments.new
   └─ ошибка на попытке 3 ──► reject ──► payments.dlx ──► payments.new.dlq
```

| Слой | Что внутри |
|---|---|
| `domain/` | `Payment`, `Money`, `OutboxEvent` и `PaymentCreated`, доменные ошибки, порты (ABC) |
| `application/` | use cases: `PaymentCreation`, `PaymentLookup`, `PaymentProcessing`, `OutboxRelay` |
| `infrastructure/` | Postgres (модели, репозитории), RabbitMQ (`topology`, `retry`, `client`, `dlq`), webhook через httpx, эмулятор шлюза |
| `presentation/` | HTTP API (FastAPI), consumer (FastStream), CLI `replay_dlq` |
| `project/` | конфиг из env, DI-контейнер (punq), логирование |

## Запуск

```bash
cp .env.example .env
docker compose up --build
```

Логины, пароли, `API_KEY` и `WEBHOOK_SECRET` берутся из `.env`; ниже в примерах значения из `.env.example`.

| Сервис | Адрес |
|---|---|
| API (Swagger: `/docs`) | http://localhost:8000 |
| RabbitMQ UI (`RABBITMQ_USER` / `RABBITMQ_PASSWORD`) | http://localhost:15672 |
| webhook-echo | http://localhost:9000, логи: `docker compose logs -f webhook-echo` |

Миграции применяет одноразовый сервис `migrate`; api и consumer стартуют после его успешного завершения. Данные Postgres и RabbitMQ лежат в именованных томах (`docker compose down -v` их удаляет). Несколько consumer: `docker compose up --scale consumer=3`.

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
POST /ok -> 200 signature=ok {"payment_id":"15e41556-aa0a-4475-879d-7b38d835ca0c","status":"succeeded","amount":"100.50","currency":"RUB","processed_at":"2026-10-07T18:02:44.960146Z"}
```

### Подпись webhook

Каждый webhook подписан HMAC-SHA256 на секрете `WEBHOOK_SECRET`:

```
X-Webhook-Timestamp: 1791403957
X-Webhook-Signature: sha256=<hex от HMAC-SHA256(WEBHOOK_SECRET, "{timestamp}.{тело запроса}")>
```

Получатель пересчитывает подпись по сырому телу и сравнивает её через constant-time сравнение; запросы со старым timestamp стоит отбрасывать, это защищает от повторной отправки перехваченного запроса. Пример проверки — в `tools/webhook_echo/server.py`.

DLQ: создайте платёж с `"webhook_url": "http://webhook-echo:9000/fail"`. Примерно через 35 с (до 1 с на опрос relay, 2–5 с шлюз, затем повторы через 5 и 25 с) сообщение появится в очереди `payments.new.dlq` в RabbitMQ UI. Вернуть его в обработку: `make dlq-replay`.

## Тесты

```bash
make lint        # ruff
make typecheck   # pyright: strict для src и migrations
make test        # unit-тесты; тесты с БД и брокером пропускаются
make e2e         # сквозной сценарий через HTTP против compose-стека
```

`make e2e` (нужен `.env`) поднимает стек и проверяет его только через внешние интерфейсы (HTTP API, логи `webhook-echo`, RabbitMQ management API, Postgres): авторизацию, валидацию, полный путь до webhook, идемпотентность (включая 10 параллельных запросов), подпись webhook, retry с задержками 5 и 25 с, DLQ и `dlq-replay`, пачку из 20 платежей, остановку consumer и RabbitMQ. По ходу перезапускает consumer и RabbitMQ, в конце возвращает стек в рабочее состояние.

С Postgres и RabbitMQ. `api` и `consumer` должны быть остановлены, иначе они заберут outbox-записи и сообщения тестов. Тесты очищают таблицы и очереди dev-окружения:

```bash
docker compose up -d --wait postgres rabbitmq
DATABASE_URL=postgresql+asyncpg://payments:payments@localhost:5432/payments \
RABBITMQ_URL=amqp://payments:payments@localhost:5672/ \
make test
```
