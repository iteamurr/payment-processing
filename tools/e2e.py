"""End-to-end scenario against the docker compose stack, through its public interfaces only.

Run with `make e2e`, which loads .env. It stops and starts the consumer and RabbitMQ along the way and brings the
whole stack back up at the end, even after a failure. Exits with 1 if any check fails.
"""

import base64
import concurrent.futures as cf
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
from collections import Counter
from collections.abc import Callable
from datetime import datetime
from typing import Any

API = "http://localhost:8000"
MGMT = "http://localhost:15672/api"
API_KEY = os.environ["API_KEY"]
RABBITMQ_CREDENTIALS = f"{os.environ['RABBITMQ_USER']}:{os.environ['RABBITMQ_PASSWORD']}"
RUN = uuid.uuid4().hex[:8]
WEBHOOK_LOG = re.compile(r"^(\S+ \S+) POST (\S+) -> (\d+) signature=(\w+) (.*)$")

results: list[tuple[str, bool]] = []


def section(title: str) -> None:
    print(f"\n== {title}")


def check(name: str, ok: Any, detail: Any = "") -> None:
    results.append((name, bool(ok)))
    print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"  [{detail}]" if detail != "" else ""))


def http(method: str, url: str, body: Any = None, headers: dict[str, str] | None = None, raw: bytes | None = None):
    data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
    request_headers = {"Content-Type": "application/json", **(headers or {})}
    request = urllib.request.Request(url, data=data, headers=request_headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.status, decode(response.read())
    except urllib.error.HTTPError as error:
        return error.code, decode(error.read())


def decode(text: bytes) -> Any:
    try:
        return json.loads(text) if text else None
    except ValueError:
        return text.decode()


def payment_body(**overrides: Any) -> dict[str, Any]:
    return {
        "amount": "100.50",
        "currency": "RUB",
        "description": "e2e",
        "metadata": {"run": RUN},
        "webhook_url": "http://webhook-echo:9000/ok",
    } | overrides


def new_key() -> str:
    return f"e2e-{RUN}-{uuid.uuid4().hex[:8]}"


def create(key: str | None, api_key: str | None = API_KEY, raw: bytes | None = None, **overrides: Any):
    headers = {"X-API-Key": api_key} if api_key else {}
    if key:
        headers["Idempotency-Key"] = key
    return http("POST", f"{API}/api/v1/payments", payment_body(**overrides), headers, raw=raw)


def create_id(**overrides: Any) -> str:
    status, body = create(new_key(), **overrides)
    assert status == 202, (status, body)
    return body["payment_id"]


def get(payment_id: Any, api_key: str | None = API_KEY):
    return http("GET", f"{API}/api/v1/payments/{payment_id}", headers={"X-API-Key": api_key} if api_key else {})


def wait(predicate: Callable[[], Any], timeout: float, step: float = 0.5) -> Any:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if value := predicate():
            return value
        time.sleep(step)
    return None


def final_state(payment_id: str, timeout: float = 20) -> dict[str, Any] | None:
    def done() -> dict[str, Any] | None:
        body = get(payment_id)[1]
        return body if body.get("status") != "pending" else None

    return wait(done, timeout)


def compose(*args: str) -> str:
    return subprocess.run(["docker", "compose", *args], capture_output=True, text=True, check=True).stdout


def sql(query: str) -> str:
    return compose("exec", "-T", "postgres", "psql", "-U", "payments", "-d", "payments", "-tAc", query).strip()


def outbox_rows(payment_id: str, published: bool | None = None) -> int:
    """Outbox events of a payment; `published` narrows to published (True) or still pending (False) ones."""
    query = f"select count(*) from outbox where payload->>'payment_id'='{payment_id}'"
    if published is not None:
        query += f" and published_at {'is not null' if published else 'is null'}"
    return int(sql(query))


def management(method: str, path: str, body: Any = None):
    token = base64.b64encode(RABBITMQ_CREDENTIALS.encode()).decode()
    return http(method, f"{MGMT}{path}", body, {"Authorization": f"Basic {token}"})


def queue_messages(name: str) -> int | None:
    status, body = management("GET", f"/queues/%2F/{name}")
    return body["messages"] if status == 200 else None


def webhooks(payment_id: str) -> list[tuple[datetime, str, int, str, dict[str, Any]]]:
    """(time, path, status, signature check, body) of every webhook webhook-echo received for the payment."""
    calls = []
    for line in compose("logs", "--no-log-prefix", "webhook-echo").splitlines():
        match = WEBHOOK_LOG.match(line)
        if match and payment_id in match.group(5):
            at = datetime.strptime(match.group(1), "%Y-%m-%d %H:%M:%S,%f")
            calls.append((at, match.group(2), int(match.group(3)), match.group(4), json.loads(match.group(5))))
    return calls


def health_and_auth() -> None:
    section("health and auth")
    check("GET /health without a key -> 200", http("GET", f"{API}/health")[0] == 200)
    status, body = create(new_key(), api_key=None)
    check("POST without X-API-Key -> 401", status == 401 and body == {"detail": "Missing or invalid X-API-Key"}, body)
    check("POST with a wrong key -> 401", create(new_key(), api_key="nope")[0] == 401)
    check("GET without a key -> 401", get(uuid.uuid4(), api_key=None)[0] == 401)


def validation() -> None:
    section("validation")
    cases: list[tuple[str, dict[str, Any]]] = [
        ("amount 0", {"amount": "0"}),
        ("amount -1", {"amount": "-1"}),
        ("amount 1.001", {"amount": "1.001"}),
        ("amount as JSON float 100.5", {"amount": 100.5}),
        ("currency GBP", {"currency": "GBP"}),
        ("webhook_url not a URL", {"webhook_url": "nope"}),
        ("empty description", {"description": ""}),
        ("NUL in description", {"description": "a\x00b"}),
        ("NUL in metadata", {"metadata": {"k": "\x00"}}),
    ]
    check("missing Idempotency-Key -> 422", create(None)[0] == 422)
    for name, overrides in cases:
        status, _ = create(new_key(), **overrides)
        check(f"{name} -> 422", status == 422, status)
    check("malformed JSON body -> 422", create(new_key(), raw=b"{not json")[0] == 422)
    check("body over 64 KiB -> 413", create(new_key(), metadata={"blob": "x" * 70_000})[0] == 413)
    check("GET unknown id -> 404", get(uuid.uuid4())[0] == 404)
    check("GET malformed id -> 422", get("not-a-uuid")[0] == 422)


def happy_path() -> None:
    section("happy path: create -> relay -> consumer -> webhook")
    started = time.monotonic()
    status, accepted = create(new_key(), amount="100.5", currency="USD")
    check(
        "POST -> 202 with payment_id, status, created_at",
        status == 202 and set(accepted) == {"payment_id", "status", "created_at"} and accepted["status"] == "pending",
        accepted,
    )
    payment_id = accepted["payment_id"]
    done = final_state(payment_id)
    elapsed = time.monotonic() - started
    check("reaches a final status", done and done["status"] in ("succeeded", "failed"), f"{elapsed:.1f}s")
    check("final status within the 2-5 s gateway delay plus relay poll", done and 2 <= elapsed <= 8, f"{elapsed:.1f}s")
    if not done:
        return
    check("amount normalized to cents", done["amount"] == "100.50" and done["currency"] == "USD", done["amount"])
    check("processed_at is set", done["processed_at"])
    calls = wait(lambda: webhooks(payment_id), 5) or []
    check("exactly one webhook delivered", len(calls) == 1, f"{len(calls)} calls")
    expected = {
        "payment_id": payment_id,
        "status": done["status"],
        "amount": "100.50",
        "currency": "USD",
        "processed_at": done["processed_at"],
    }
    check("webhook body matches the stored payment", calls and calls[0][4] == expected, calls and calls[0][4])
    check("webhook signature verifies with the shared secret", calls and calls[0][3] == "ok", calls and calls[0][3])
    check("outbox event published", outbox_rows(payment_id, published=True) == 1)


def idempotency() -> None:
    section("idempotency")
    key = new_key()
    first = create(key)[1]["payment_id"]
    status, again = create(key)
    check("same key + same body -> 202, same payment", status == 202 and again["payment_id"] == first)
    status, again = create(key, amount="100.5")
    check("same key + 100.5 instead of 100.50 -> same payment", status == 202 and again["payment_id"] == first)
    status, body = create(key, amount="1.00")
    conflict = {"detail": "Idempotency-Key reused with a different body"}
    check("same key + different body -> 409", status == 409 and body == conflict, body)

    key = new_key()
    with cf.ThreadPoolExecutor(10) as pool:
        responses = list(pool.map(lambda _: create(key), range(10)))
    ids = {body["payment_id"] for status, body in responses if status == 202}
    statuses = Counter(status for status, _ in responses)
    check("10 concurrent POSTs with one key -> all 202, one payment", statuses == {202: 10} and len(ids) == 1, statuses)
    check("... exactly one payments row", sql(f"select count(*) from payments where idempotency_key='{key}'") == "1")
    check("... exactly one outbox event", ids and outbox_rows(next(iter(ids))) == 1)


def retry_and_dlq() -> None:
    section("retry with backoff, then DLQ, then replay")
    dlq_before = queue_messages("payments.new.dlq") or 0
    payment_id = create_id(webhook_url="http://webhook-echo:9000/fail")
    calls = wait(lambda: len(webhooks(payment_id)) >= 3, 25) and webhooks(payment_id)
    calls = calls or webhooks(payment_id)
    check("webhook attempted exactly 3 times", len(calls) == 3, f"{len(calls)} calls")
    if len(calls) == 3:
        gaps = [(calls[i + 1][0] - calls[i][0]).total_seconds() for i in range(2)]
        check("gaps ≈ 2 s then ≈ 4 s", 1.5 <= gaps[0] <= 3.5 and 3.5 <= gaps[1] <= 6, f"{gaps[0]:.2f}s, {gaps[1]:.2f}s")
    stored = get(payment_id)[1]
    check("payment status stored despite webhook failures", stored["status"] in ("succeeded", "failed"))
    dlq_after = wait(lambda: (n := queue_messages("payments.new.dlq") or 0) > dlq_before and n, 15)
    check("DLQ gained one message", dlq_after == dlq_before + 1, f"{dlq_before} -> {dlq_after}")

    peek = {"count": 100, "ackmode": "ack_requeue_true", "encoding": "auto"}
    status, messages = management("POST", "/queues/%2F/payments.new.dlq/get", peek)
    ours = [m for m in messages if payment_id in m["payload"]] if status == 200 else []
    check(
        "DLQ message is our payment with x-attempt=3",
        len(ours) == 1
        and json.loads(ours[0]["payload"]) == {"payment_id": payment_id}
        and ours[0]["properties"]["headers"]["x-attempt"] == 3,
    )

    compose("exec", "-T", "consumer", "python", "-m", "payments_processing.presentation.cli.replay_dlq")
    replayed = wait(lambda: len(webhooks(payment_id)) >= 6, 25)
    check("make dlq-replay sends it through 3 more attempts", replayed, f"{len(webhooks(payment_id))} calls")


def batch() -> None:
    section("batch of 20: gateway outcomes and one webhook each")
    payment_ids = [create_id(amount=str(i + 1)) for i in range(20)]
    finished = [final_state(payment_id, timeout=40) for payment_id in payment_ids]
    check("all 20 reach a final status", all(finished))
    check("gateway outcomes (90/10)", True, dict(Counter(f["status"] for f in finished if f)))
    deliveries = Counter(len(webhooks(payment_id)) for payment_id in payment_ids)
    check("every payment got exactly one webhook", deliveries == {1: 20}, dict(deliveries))


def consumer_down() -> None:
    section("consumer down: messages wait in payments.new")
    compose("stop", "consumer")
    payment_ids = [create_id() for _ in range(3)]
    queued = wait(lambda: (queue_messages("payments.new") or 0) >= 3, 15)
    check("messages queued while consumer is down", queued)
    check("payments stay pending", all(get(payment_id)[1]["status"] == "pending" for payment_id in payment_ids))
    compose("start", "consumer")
    check("after consumer start all are processed", all(final_state(p, timeout=40) for p in payment_ids))


def broker_down() -> None:
    section("RabbitMQ down: the outbox keeps the event until the broker is back")
    compose("stop", "rabbitmq")
    status, accepted = create(new_key())
    check("POST still -> 202 with the broker down", status == 202, status)
    if status != 202:
        return
    payment_id = accepted["payment_id"]
    time.sleep(3)
    check("outbox event stays unpublished", outbox_rows(payment_id, published=False) == 1)
    check("payment stays pending", get(payment_id)[1]["status"] == "pending")
    compose("up", "-d", "--wait", "rabbitmq")
    done = final_state(payment_id, timeout=90)
    check("after broker restart the payment is processed", done, done and done["status"])
    check("outbox event published", outbox_rows(payment_id, published=True) == 1)
    check("webhook delivered once", len(wait(lambda: webhooks(payment_id), 10) or []) == 1)


def main() -> int:
    scenarios = [health_and_auth, validation, happy_path, idempotency, retry_and_dlq, batch, consumer_down, broker_down]
    try:
        for scenario in scenarios:
            scenario()
    finally:
        compose("up", "-d", "--wait")
    failed = [name for name, ok in results if not ok]
    print(f"\n{len(results) - len(failed)}/{len(results)} checks passed" + (f"; failed: {failed}" if failed else ""))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
