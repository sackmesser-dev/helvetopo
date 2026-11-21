#!/usr/bin/env python3
"""Lokaler Testserver für das Portal mit derselben Content-Security-Policy wie auf dem Webserver.

So fallen Inline-Skripte, Inline-Styles und style-Attribute schon lokal auf (Fehler in der Browser-Konsole).

Aufruf:
    python3 -I src/portal/serve_csp.py [--port 8768] [--dir src/portal/prototype]
"""
import argparse
import functools
import http.server
from pathlib import Path

CSP = ("default-src 'self'; img-src 'self' data:; object-src 'none'; "
       "base-uri 'self'; frame-ancestors 'none'")


class Handler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Content-Security-Policy", CSP)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Cache-Control", "no-cache")
        super().end_headers()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8768)
    ap.add_argument("--dir", type=Path, default=Path(__file__).resolve().parent / "prototype")
    args = ap.parse_args()
    handler = functools.partial(Handler, directory=str(args.dir))
    with http.server.ThreadingHTTPServer(("127.0.0.1", args.port), handler) as srv:
        print(f"http://127.0.0.1:{args.port}/ mit CSP: {CSP}")
        srv.serve_forever()


if __name__ == "__main__":
    main()
