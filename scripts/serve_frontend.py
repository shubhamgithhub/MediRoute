"""Serve frontend/ for local development with caching switched off, so every reload shows the latest
HTML, CSS and JS (plain `python -m http.server` lets the browser keep stale pages).

    python scripts/serve_frontend.py            # http://127.0.0.1:5500/index.html
    python scripts/serve_frontend.py --port 5501
"""
from __future__ import annotations

import argparse
import functools
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

FRONTEND = Path(__file__).resolve().parents[1] / "frontend"


class NoCacheHandler(SimpleHTTPRequestHandler):
    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-store, must-revalidate")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        super().end_headers()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=5500)
    ap.add_argument("--bind", default="127.0.0.1")
    args = ap.parse_args()
    handler = functools.partial(NoCacheHandler, directory=str(FRONTEND))
    with ThreadingHTTPServer((args.bind, args.port), handler) as server:
        print(f"Serving {FRONTEND} at http://{args.bind}:{args.port}/index.html (no caching)")
        server.serve_forever()


if __name__ == "__main__":
    main()
