"""Localhost simulator: python simulator/server.py  ->  http://localhost:8000"""

import json
import re
import sys
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, str(Path(__file__).parent))
import algos  # noqa: E402

HERE = Path(__file__).parent


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype):
        data = body if isinstance(body, bytes) else body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _json(self, code, obj):
        self._send(code, json.dumps(obj), "application/json")

    def do_GET(self):
        url = urlparse(self.path)
        q = parse_qs(url.query)
        if url.path in ("/", "/index.html"):
            return self._send(200, (HERE / "index.html").read_bytes(), "text/html; charset=utf-8")
        if url.path in ("/api/board", "/api/run"):
            raw = q.get("date", [""])[0]
            try:
                if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw):
                    raise ValueError
                day = date.fromisoformat(raw)
            except ValueError:
                return self._json(400, {"error": "invalid_date"})
            if url.path == "/api/board":
                return self._json(200, {"date": raw, "board": algos.board_json(day)})
            algo = q.get("algo", [""])[0]
            if algo not in algos.ALGOS:
                return self._json(400, {"error": "unknown_algo"})
            try:
                limit = min(max(float(q.get("limit", ["30"])[0]), 1), 120)
            except ValueError:
                return self._json(400, {"error": "invalid_limit"})
            exposed = algos.exposed_for(day)
            if algo in algos.RANDOMISED:
                # one run: recording only logs improvements, so it doesn't distort timing
                result = algos.run(algo, exposed, record=True, time_limit=limit)
            else:
                # timing run is un-instrumented; a second run records animation steps
                result = algos.run(algo, exposed, record=False, time_limit=limit)
                if result["status"] != "timeout":
                    rec = algos.run(algo, exposed, record=True, time_limit=limit)
                    result["steps"], result["steps_truncated"] = rec["steps"], rec["steps_truncated"]
                else:
                    result["steps"], result["steps_truncated"] = [], False
            return self._json(200, result)
        self._send(404, "not found", "text/plain")

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    print(f"Daydoku simulator on http://localhost:{port}")
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
