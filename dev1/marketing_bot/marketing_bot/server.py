"""Webhook receiver at http://127.0.0.1:8899/pulse plus a poll loop.

Webhooks on the department service fire only for approved/rejected, routed
tasks, and executed actions. listing_live from sales/engineering often misses
that, so we also poll GET /api/events.
"""
import json
import logging
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import config
from .bot import MarketingBot

log = logging.getLogger("marketing")


def _process_event(bot, ev):
    try:
        bot.handle_event(ev)
    except Exception:
        log.exception("webhook handler failed")


class _Handler(BaseHTTPRequestHandler):
    bot = None

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path in ("/health", "/pulse"):
            self._send(200, {"ok": True, "dept": config.DEPT, "mode": self.bot.mode, "webhook": config.WEBHOOK_URL})
            return
        self._send(404, {"ok": False, "error": "not found"})

    def do_POST(self):
        path = self.path.split("?", 1)[0]
        if path != "/pulse":
            self._send(404, {"ok": False, "error": "not found"})
            return
        n = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(n) if n else b""
        try:
            ev = json.loads(raw.decode() or "{}")
        except json.JSONDecodeError:
            self._send(400, {"ok": False, "error": "body must be JSON"})
            return
        # Ack before draft/QA work. A synchronous handler held the socket ~23s and the hub hit BrokenPipe.
        self._send(202, {"ok": True, "accepted": True})
        threading.Thread(
            target=_process_event, args=(self.bot, ev), name="marketing-pulse", daemon=True,
        ).start()

    def _send(self, code, body):
        data = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, fmt, *args):
        log.info("http " + fmt, *args)


def serve(bot, host=None, port=None):
    _Handler.bot = bot
    httpd = ThreadingHTTPServer((host or config.HOST, port or config.PORT), _Handler)
    thread = threading.Thread(target=httpd.serve_forever, name="marketing-http", daemon=True)
    thread.start()
    log.info("listening on http://%s:%s/pulse", httpd.server_address[0], httpd.server_address[1])
    return httpd


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    bot = MarketingBot()
    bot.register_webhook()
    try:
        bot.announce()
    except Exception as e:
        log.warning("announce failed (continuing): %s", e)
    httpd = serve(bot)
    log.info("polling %s every %ss (mode=%s)", config.DEPARTMENTS_URL, config.POLL_SEC, bot.mode)
    try:
        while True:
            bot.poll_once()
            time.sleep(config.POLL_SEC)
    except KeyboardInterrupt:
        log.info("stopping")
    finally:
        httpd.shutdown()
