# -*- coding: utf-8 -*-
"""Simple local webhook server for Kling callbacks."""

import argparse
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from KlyingCallback import save_callback_event


class CallbackHandler(BaseHTTPRequestHandler):
    callback_path = "/kling/callback"
    store_dir = os.path.join("result", "callback_state")
    auth_token = None

    def _json_response(self, status_code: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path != self.callback_path:
            self._json_response(404, {"code": 404, "message": "not found"})
            return

        if self.auth_token:
            header_token = self.headers.get("X-Callback-Token")
            query_token = (parse_qs(parsed.query).get("token") or [None])[0]
            if header_token != self.auth_token and query_token != self.auth_token:
                self._json_response(401, {"code": 401, "message": "unauthorized"})
                return

        length = int(self.headers.get("Content-Length", "0") or 0)
        raw = self.rfile.read(length)
        try:
            data = json.loads(raw.decode("utf-8"))
            if not isinstance(data, dict):
                raise ValueError("payload must be object")
            state_path = save_callback_event(data, self.store_dir)
            self._json_response(200, {"code": 0, "message": "ok", "saved_to": state_path})
        except Exception as e:
            self._json_response(400, {"code": 400, "message": f"bad request: {e}"})


def main() -> None:
    parser = argparse.ArgumentParser(description="Run local Kling callback server.")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--path", default="/kling/callback")
    parser.add_argument("--store-dir", default=os.path.join("result", "callback_state"))
    parser.add_argument(
        "--token",
        default=os.getenv("KLING_CALLBACK_TOKEN"),
        help="Optional token. Pass via X-Callback-Token header or ?token=.",
    )
    args = parser.parse_args()

    CallbackHandler.callback_path = args.path
    CallbackHandler.store_dir = args.store_dir
    CallbackHandler.auth_token = args.token

    server = ThreadingHTTPServer((args.host, args.port), CallbackHandler)
    print(f"Callback server listening on http://{args.host}:{args.port}{args.path}")
    if args.token:
        print("Callback token check enabled.")
    print(f"Callback store dir: {args.store_dir}")
    server.serve_forever()


if __name__ == "__main__":
    main()
