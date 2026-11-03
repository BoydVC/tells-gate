"""Tiny stdlib HTTP server: GET / (live page), POST /check, GET /rules, GET /health."""
from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from .core import check, load_rules, PASS_AT, WARN_AT

PAGE = Path(__file__).resolve().parent.parent / "web" / "index.html"
MAX_BYTES = 200_000


def make_handler(rules):
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _send(self, code, body, ctype="application/json"):
            data = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode()
            self.send_response(code)
            self.send_header("Content-Type", ctype + "; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.end_headers()
            self.wfile.write(data)

        def do_OPTIONS(self):
            self._send(204, b"")

        def do_GET(self):
            path = urlparse(self.path).path
            if path in ("/", "/index.html"):
                return self._send(200, PAGE.read_bytes(), "text/html")
            if path == "/health":
                return self._send(200, {"ok": True, "rules": len(rules), "pass_at": PASS_AT, "warn_at": WARN_AT})
            if path == "/rules":
                return self._send(200, [{"id": r.id, "name": r.name, "why": r.why, "fix": r.fix,
                                         "weight": r.weight, "cap": r.cap, "example": r.example} for r in rules])
            self._send(404, {"error": "not found"})

        def do_POST(self):
            if urlparse(self.path).path != "/check":
                return self._send(404, {"error": "not found"})
            n = int(self.headers.get("Content-Length") or 0)
            if n > MAX_BYTES:
                return self._send(413, {"error": "too large"})
            raw = self.rfile.read(n)
            try:
                body = json.loads(raw or b"{}")
                text = body["text"]
                if not isinstance(text, str):
                    raise TypeError
            except Exception:
                return self._send(400, {"error": "body must be JSON {\"text\": string}"})
            rep = check(text, rules, llm=bool(body.get("llm")))
            out = rep.to_dict()
            min_score = body.get("min_score")
            out["gate"] = "block" if (rep.score < min_score if isinstance(min_score, int) else rep.verdict == "fail") else "allow"
            self._send(200, out)

    return H


def serve(host="127.0.0.1", port=4350, banned=None):
    rules = load_rules(banned)
    srv = ThreadingHTTPServer((host, port), make_handler(rules))
    print(f"tells-gate on http://{host}:{port}  ({len(rules)} rules)")
    srv.serve_forever()
