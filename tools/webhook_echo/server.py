"""Dev webhook receiver: logs every POST; paths starting with /fail answer 500 to exercise retries and the DLQ."""

import logging
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        status = 500 if self.path.startswith("/fail") else 200
        logging.info("POST %s -> %s %s", self.path, status, body.decode(errors="replace"))
        self.send_response(status)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    ThreadingHTTPServer(("0.0.0.0", 9000), Handler).serve_forever()
