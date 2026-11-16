import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import threading

from harness import ROOT, run_demo, show_bug


RUN_LOCK = threading.Lock()


class Handler(BaseHTTPRequestHandler):
    def reply(self, status, body, content_type="application/json"):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path.split("?")[0] == "/":
            self.reply(200, (ROOT / "index.html").read_bytes(), "text/html; charset=utf-8")
        elif self.path == "/health":
            self.reply(200, b'{"status":"ok"}')
        else:
            self.reply(404, b'{"error":"Not found"}')

    def do_POST(self):
        if self.path not in ("/api/run", "/api/bug"):
            self.reply(404, b'{"error":"Not found"}')
            return
        # JSON-only, same-origin local UI; no CORS or arbitrary network clients.
        origin = self.headers.get("Origin")
        allowed_origin = f"http://127.0.0.1:{self.server.server_port}"
        if origin and origin != allowed_origin:
            self.reply(403, b'{"error":"Use the local demo page"}')
            return
        if self.headers.get("Content-Type") != "application/json":
            self.reply(415, b'{"error":"JSON required"}')
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 4096:
                raise ValueError("Invalid body length")
            payload = json.loads(self.rfile.read(length))
            if not isinstance(payload, dict):
                raise ValueError("JSON object required")
            if not RUN_LOCK.acquire(blocking=False):
                self.reply(409, b'{"error":"Another demo run is active"}')
                return
            try:
                result = show_bug() if self.path == "/api/bug" else run_demo(
                    payload.get("mode", "engineered"),
                    payload.get("provider", "replay"),
                    payload.get("scenario", "happy"),
                )
            finally:
                RUN_LOCK.release()
            self.reply(200, json.dumps(result).encode("utf-8"))
        except (ValueError, TypeError) as error:
            self.reply(400, json.dumps({"error": str(error)}).encode("utf-8"))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"Open http://127.0.0.1:{server.server_port}", flush=True)
    print("Replay is not a live LLM. Press Ctrl+C to stop.", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
