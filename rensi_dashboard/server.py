#!/usr/bin/env python3
"""Portable dashboard server: stdlib http.server, whitelist routes only,
shared-secret auth (header, cookie, or one-time query param), and an
optional in-process scheduler (two daemon threads) that replaces the
systemd-timer pair for people who just want to run one process and have
it work -- on Windows, Mac, or any Linux, with or without systemd.
"""
import hmac
import http.server
import importlib.resources
import re
import sys
import threading
import time
import traceback
from urllib.parse import parse_qs, urlsplit

from . import core
from . import aggregate

SLUG = re.compile(r"^(?!\.)[A-Za-z0-9_.-]{1,80}$")
COOKIE_NAME = "rdtok"


def _index_html_bytes():
    try:
        return importlib.resources.files("rensi_dashboard").joinpath("web/index.html").read_bytes()
    except Exception:
        # Fallback for editable/dev installs where package_data resolution differs.
        import os
        here = os.path.dirname(__file__)
        with open(os.path.join(here, "web", "index.html"), "rb") as f:
            return f.read()


class Handler(http.server.BaseHTTPRequestHandler):
    timeout = 10
    protocol_version = "HTTP/1.1"

    def _send_bytes(self, data, ctype, extra_headers=None):
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        for k, v in (extra_headers or []):
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(data)

    def _send_file(self, path, ctype):
        try:
            with open(path, "rb") as f:
                data = f.read()
        except Exception:
            self.send_error(404)
            return
        self._send_bytes(data, ctype)

    def _authorized(self):
        token = core.get_or_create_token()
        hdr = self.headers.get("X-Dashboard-Token", "")
        if hdr and hmac.compare_digest(hdr, token):
            return True, None
        cookie_header = self.headers.get("Cookie", "")
        for part in cookie_header.split(";"):
            part = part.strip()
            if part.startswith(COOKIE_NAME + "="):
                val = part[len(COOKIE_NAME) + 1:]
                if val and hmac.compare_digest(val, token):
                    return True, None
        q = parse_qs(urlsplit(self.path).query)
        qtok = (q.get("t") or [""])[0]
        if qtok and hmac.compare_digest(qtok, token):
            # One-time handoff: authorize this request AND ask the browser to
            # remember it via a cookie, so the token doesn't need to stay in
            # the URL for every subsequent fetch.
            return True, "{}={}; Path=/; HttpOnly; SameSite=Strict; Max-Age=2592000".format(COOKIE_NAME, token)
        return False, None

    def do_GET(self):
        ok, set_cookie = self._authorized()
        if not ok:
            self.send_error(403)
            return
        extra = [("Set-Cookie", set_cookie)] if set_cookie else []

        p = urlsplit(self.path).path
        if p in ("/", "/index.html"):
            self._send_bytes(_index_html_bytes(), "text/html; charset=utf-8", extra)
            return
        if p == "/data.json":
            self._send_file(core.DATA_FILE, "application/json")
            return
        m = re.match(r"^/session/([^/]+)\.json$", p)
        if m and SLUG.match(m.group(1)):
            self._send_file(core.SESSION_DIR / (m.group(1) + ".json"), "application/json")
            return
        self.send_error(404)

    def log_message(self, *a):
        pass


def _scheduler_loop(name, interval_s, fn):
    while True:
        try:
            fn()
        except Exception:
            print("[rensi-dashboard] {} refresh failed:".format(name), file=sys.stderr)
            traceback.print_exc()
        time.sleep(interval_s)


def start_scheduler():
    """Two daemon threads replacing the systemd-timer pair: a slow one that
    also hits the official rate-limit API, a fast one that only re-parses
    local transcripts so an open session feels live without waiting on the
    slow call. Wrapped per-iteration so one bad transcript or one
    claude-monitor hiccup can't silently kill the loop forever."""
    threading.Thread(target=_scheduler_loop, args=("full", core.FULL_INTERVAL_S, aggregate.full_refresh), daemon=True).start()
    threading.Thread(target=_scheduler_loop, args=("fast", core.FAST_INTERVAL_S, aggregate.fast_refresh), daemon=True).start()


def run(with_scheduler=True):
    core.ensure_dirs()
    core.get_or_create_token()
    if with_scheduler:
        # Don't block the HTTP server's startup on the first refresh -- on a
        # cold cache (many/large transcripts, first run ever) that full pass
        # can take a while, and a browser opened immediately would see
        # "connection refused" instead of a page that simply loads its data
        # a few seconds late. The scheduler thread's own first loop
        # iteration does this priming, concurrently with serve_forever().
        start_scheduler()
    with http.server.ThreadingHTTPServer((core.HOST, core.PORT), Handler) as s:
        s.serve_forever()


if __name__ == "__main__":
    run(with_scheduler="--no-scheduler" not in sys.argv)
