"""Dev webhook receiver: logs every POST with its signature check; paths starting with /fail answer 500."""

import hashlib
import hmac
import logging
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

SECRET = os.environ["WEBHOOK_SECRET"].encode()


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        status = 500 if self.path.startswith("/fail") else 200
        signature = self.signature(body)
        logging.info("POST %s -> %s signature=%s %s", self.path, status, signature, body.decode(errors="replace"))
        self.send_response(status)
        self.send_header("Content-Length", "0")
        self.end_headers()

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
