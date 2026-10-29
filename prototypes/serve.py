"""Serve the prototypes and collect feedback: python3 prototypes/serve.py [port]. Feedback goes to feedback.jsonl."""
import http.server
import json
import pathlib
import sys
import time

ROOT = pathlib.Path(__file__).parent
LOG = ROOT / "feedback.jsonl"


class H(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **k):
        super().__init__(*a, directory=str(ROOT), **k)

    def do_GET(self):
        if self.path == "/feedback":
            rows = [json.loads(l) for l in LOG.read_text().splitlines() if l.strip()] if LOG.exists() else []
            body = json.dumps(rows).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body)
            return
        super().do_GET()

    def do_POST(self):
        if self.path != "/feedback":
            self.send_error(404)
            return
        row = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
        row["t"] = time.time()
        with LOG.open("a") as f:
            f.write(json.dumps(row) + "\n")
        self.send_response(204)
        self.end_headers()

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8940
    http.server.ThreadingHTTPServer(("127.0.0.1", port), H).serve_forever()
