"""Приёмник webhook для ручной проверки.

Запуск: python scripts/webhook_receiver.py [порт] [--fail] [--public].
"""

import sys
from http.server import BaseHTTPRequestHandler, HTTPServer

FAIL = "--fail" in sys.argv
HOST = "0.0.0.0" if "--public" in sys.argv else "127.0.0.1"
PORT = next((int(arg) for arg in sys.argv[1:] if arg.isdigit()), 9000)


class Handler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length).decode()
        print(f"POST {self.path} -> {body}", flush=True)
        self.send_response(500 if FAIL else 200)
        self.end_headers()

    def log_message(self, format: str, *args: object) -> None:
        pass


if __name__ == "__main__":
    print(f"Listening on {HOST}:{PORT} (fail={FAIL})", flush=True)
    HTTPServer((HOST, PORT), Handler).serve_forever()