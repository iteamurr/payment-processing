"""Dev webhook receiver: logs every POST and supports permanent or bounded failures for E2E checks."""

import hashlib
import hmac
import json
import logging
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

SECRET = os.environ["WEBHOOK_SECRET"].encode()
FAILURES: dict[tuple[str, str], int] = {}
FAILURES_LOCK = threading.Lock()


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        status = self.response_status(body)
        signature = self.signature(body)
        logging.info("POST %s -> %s signature=%s %s", self.path, status, signature, body.decode(errors="replace"))
        self.send_response(status)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def response_status(self, body: bytes) -> int:
        """`/fail` always fails; `/fail/N` fails the first N calls for one payment, then recovers."""
        if self.path == "/fail":
            return 500
        if self.path.startswith("/fail/"):
            try:
                failures = int(self.path.removeprefix("/fail/"))
                payment_id = str(json.loads(body)["payment_id"])
            except (KeyError, TypeError, ValueError, json.JSONDecodeError):
                return 500
            key = (self.path, payment_id)
            with FAILURES_LOCK:
                calls = FAILURES[key] = FAILURES.get(key, 0) + 1
            return 500 if calls <= failures else 200
        return 200

    def signature(self, body: bytes) -> str:
        """How a real receiver verifies the payments-processing webhook signature."""
        timestamp = self.headers.get("X-Webhook-Timestamp")
        received = self.headers.get("X-Webhook-Signature")
        if not timestamp or not received:
            return "missing"
        expected = "sha256=" + hmac.new(SECRET, f"{timestamp}.".encode() + body, hashlib.sha256).hexdigest()
        return "ok" if hmac.compare_digest(received, expected) else "bad"

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    ThreadingHTTPServer(("0.0.0.0", 9000), Handler).serve_forever()
