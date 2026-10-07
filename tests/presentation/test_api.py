import unittest
import uuid
from unittest.mock import patch

import punq
from fastapi.testclient import TestClient

import payments_processing.presentation.api.deps as deps
from payments_processing.application.payments.payment_creation import PaymentCreation
from payments_processing.application.payments.payment_lookup import PaymentLookup
from payments_processing.presentation.api.app import build_app
from payments_processing.project.config import Config
from tests.mocks import InMemoryPaymentRepository

API_KEY = "test-key"
BODY = {
    "amount": "100.50",
    "currency": "RUB",
    "description": "Order #1",
    "metadata": {"order_id": 1},
    "webhook_url": "http://hooks.example/ok",
}


def headers(idempotency_key: str | None = "key-1", api_key: str | None = API_KEY) -> dict[str, str]:
    result = {}
    if idempotency_key is not None:
        result["Idempotency-Key"] = idempotency_key
    if api_key is not None:
        result["X-API-Key"] = api_key
    return result


class APITest(unittest.TestCase):
    """TestClient without a `with` block: lifespan (broker, relay) does not run."""

    def setUp(self):
        self.repository = InMemoryPaymentRepository()
        container = punq.Container()
        container.register(Config, instance=Config(database_url="", rabbitmq_url="", api_key=API_KEY))
        container.register(PaymentLookup, instance=PaymentLookup(self.repository))
        container.register(PaymentCreation, instance=PaymentCreation(self.repository))
        patcher = patch.object(deps, "get_api_container", return_value=container)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.client = TestClient(build_app())

    def create(self, body=BODY, **kwargs):
        return self.client.post("/api/v1/payments", json=body, headers=headers(**kwargs))

    def test_health_needs_no_api_key(self):
        response = self.client.get("/health")
        self.assertEqual((response.status_code, response.text), (200, "ok"))

    def test_create_returns_202_with_a_pending_payment(self):
        response = self.create()

        self.assertEqual(response.status_code, 202)
        body = response.json()
        self.assertEqual(set(body), {"payment_id", "status", "created_at"})
        self.assertEqual(body["status"], "pending")
        self.assertIn(uuid.UUID(body["payment_id"]), self.repository.payments)

    def test_repeated_key_with_the_same_body_returns_the_same_payment(self):
        first = self.create().json()
        second = self.create(body=BODY | {"amount": "100.5"})

        self.assertEqual(second.status_code, 202)
        self.assertEqual(second.json()["payment_id"], first["payment_id"])
        self.assertEqual(len(self.repository.payments), 1)

    def test_repeated_key_with_a_different_body_returns_409(self):
        self.create()

        response = self.create(body=BODY | {"amount": "1.00"})

        self.assertEqual(response.status_code, 409)
        self.assertEqual(len(self.repository.payments), 1)

    def test_missing_idempotency_key_returns_422(self):
        self.assertEqual(self.create(idempotency_key=None).status_code, 422)

    def test_missing_or_wrong_api_key_returns_401(self):
        for api_key in (None, "wrong"):
            with self.subTest(api_key=api_key):
                get = self.client.get(f"/api/v1/payments/{uuid.uuid4()}", headers=headers(api_key=api_key))
                self.assertEqual(self.create(api_key=api_key).status_code, 401)
                self.assertEqual(get.status_code, 401)
        self.assertEqual(self.repository.payments, {})

    def test_api_key_is_checked_before_request_validation(self):
        self.assertEqual(self.create(api_key=None, idempotency_key=None).status_code, 401)

    def test_invalid_body_returns_422(self):
        for change in (
            {"amount": "0"},
            {"amount": "-1"},
            {"amount": "1.001"},
            {"currency": "GBP"},
            {"description": ""},
            {"webhook_url": "not a url"},
            {"metadata": ["not", "an", "object"]},
        ):
            with self.subTest(change=change):
                self.assertEqual(self.create(body=BODY | change).status_code, 422)
        self.assertEqual(self.repository.payments, {})

    def test_fractional_json_number_amount_is_rejected(self):
        """json.loads parses it through float: 1234567890123456.78 would be stored as ...456.80."""
        for amount in (1234567890123456.78, 100.5):
            with self.subTest(amount=amount):
                self.assertEqual(self.create(body=BODY | {"amount": amount}).status_code, 422)
        self.assertEqual(self.repository.payments, {})

    def test_amount_as_string_or_integer_is_exact(self):
        for amount, stored in (("1234567890123456.78", "1234567890123456.78"), (100, "100.00")):
            with self.subTest(amount=amount):
                response = self.create(body=BODY | {"amount": amount}, idempotency_key=f"key-{amount}")
                self.assertEqual(response.status_code, 202)
                payment = self.repository.payments[uuid.UUID(response.json()["payment_id"])]
                self.assertEqual(str(payment.money.amount), stored)

    def test_nul_character_returns_422(self):
        """Postgres TEXT and JSONB reject \\u0000; it must not reach the database as a 500."""
        for change in (
            {"description": "a\x00b"},
            {"metadata": {"note": "a\x00b"}},
            {"metadata": {"a\x00b": 1}},
            {"metadata": {"nested": [{"note": "\x00"}]}},
        ):
            with self.subTest(change=change):
                self.assertEqual(self.create(body=BODY | change).status_code, 422)
        self.assertEqual(self.repository.payments, {})

    def test_get_returns_all_payment_fields(self):
        payment_id = self.create().json()["payment_id"]

        response = self.client.get(f"/api/v1/payments/{payment_id}", headers=headers())

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["id"], payment_id)
        self.assertEqual(body["amount"], "100.50")
        self.assertEqual(body["currency"], "RUB")
        self.assertEqual(body["description"], "Order #1")
        self.assertEqual(body["metadata"], {"order_id": 1})
        self.assertEqual(body["status"], "pending")
        self.assertEqual(body["idempotency_key"], "key-1")
        self.assertEqual(body["webhook_url"], "http://hooks.example/ok")
        self.assertIsNotNone(body["created_at"])
        self.assertIsNone(body["processed_at"])

    def test_get_unknown_payment_returns_404(self):
        self.assertEqual(self.client.get(f"/api/v1/payments/{uuid.uuid4()}", headers=headers()).status_code, 404)

    def test_get_with_malformed_id_returns_422(self):
        self.assertEqual(self.client.get("/api/v1/payments/not-a-uuid", headers=headers()).status_code, 422)

    def test_error_body_matches_its_openapi_description(self):
        """Status, body and docs come from one ApiError class, so they cannot drift apart."""
        self.create()
        responses = {
            401: self.create(api_key=None),
            404: self.client.get(f"/api/v1/payments/{uuid.uuid4()}", headers=headers()),
            409: self.create(body=BODY | {"amount": "1.00"}),
        }
        paths = self.client.get("/openapi.json").json()["paths"]
        documented = {
            401: paths["/api/v1/payments"]["post"]["responses"]["401"],
            404: paths["/api/v1/payments/{payment_id}"]["get"]["responses"]["404"],
            409: paths["/api/v1/payments"]["post"]["responses"]["409"],
        }

        for status, response in responses.items():
            with self.subTest(status=status):
                self.assertEqual(response.status_code, status)
                self.assertEqual(response.json(), {"detail": documented[status]["description"]})
                self.assertTrue(
                    documented[status]["content"]["application/json"]["schema"]["$ref"].endswith("/ErrorOut")
                )

    def test_oversized_body_returns_413_before_validation(self):
        """FastAPI buffers the whole body before validating it; the limit keeps a huge metadata out of memory."""
        response = self.create(body=BODY | {"metadata": {"blob": "x" * 70_000}})

        self.assertEqual(response.status_code, 413)
        self.assertEqual(response.json(), {"detail": "Request body is larger than 64 KiB"})
        self.assertEqual(self.repository.payments, {})

    def test_body_under_the_limit_is_accepted(self):
        self.assertEqual(self.create(body=BODY | {"metadata": {"blob": "x" * 60_000}}).status_code, 202)
