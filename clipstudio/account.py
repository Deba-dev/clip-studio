"""The signed-in account and its plan, from the Clip Studio licence server.

Sign-in opens Google in the browser and comes back to a one-time local port, like the OBS and YouTube apps do. The
last answer from the server is kept, so Premium keeps working offline for a week.
"""
import http.server
import json
import os
import secrets
import socket
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
import webbrowser

from .version import VERSION

API = os.environ.get("CLIPSTUDIO_API") or "https://clipstudio.zunimilabs.online"
GRACE = 7 * 86400          # Premium keeps working this long without reaching the server
AGENT = "ClipStudio/" + VERSION
SIGN_IN_WAIT = 300


class AccountError(Exception):
    """A plain sentence for the user."""


class Account:
    def __init__(self, settings):
        self.settings = settings

    # ---- what is known locally (no network; the worker process uses only these)
    def cache(self):
        return dict(self.settings.get("account_cache") or {})

    def signed_in(self):
        return bool(self.settings.get("account_token"))

    def email(self):
        return self.cache().get("email", "")

    def plan(self, now=None):
        c = self.cache()
        now = now or time.time()
        fresh = now - c.get("checked", 0) <= GRACE
        if self.signed_in() and fresh and c.get("plan") == "premium" and c.get("until", 0) > now:
            return "premium"
        return "free"

    def billing_live(self):
        """Limits apply only once the server takes payments; until then nobody is locked out of anything."""
        return bool(self.cache().get("billing") or self.settings.get("billing_live"))

    def device_id(self):
        did = self.settings.get("device_id")
        if not did:
            did = uuid.uuid4().hex
            self.settings.set("device_id", did)
        return did

    # ---- server calls (blocking: run them off the UI thread)
    def call(self, method, path, body=None, auth=True):
        headers = {"User-Agent": AGENT, "X-Device-Id": self.device_id(), "X-Device-Name": socket.gethostname()[:60]}
        if auth:
            headers["Authorization"] = "Bearer " + (self.settings.get("account_token") or "")
        data = None
        if body is not None:
            data = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(API + path, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                return json.loads(response.read() or b"{}")
        except urllib.error.HTTPError as e:
            try:
                message = json.loads(e.read()).get("error")
            except ValueError:
                message = ""
            if e.code == 401 and auth:
                self.forget()
                raise AccountError("You were signed out. Sign in again to use Premium.")
            raise AccountError(message or "The Clip Studio server answered with an error (%d)." % e.code)
        except (urllib.error.URLError, OSError, ValueError):
            raise AccountError("Could not reach the Clip Studio server. Check the internet connection.")

    def plans(self):
        info = self.call("GET", "/plans", auth=False)
        self.settings.set("billing_live", bool(info.get("live")))
        self.settings.set("sign_in_ready", bool(info.get("sign_in")))
        return info

    def refresh(self):
        info = self.call("GET", "/me")
        info["checked"] = time.time()
        self.settings.set("account_cache", info)
        return info

    def forget(self):
        self.settings.set("account_token", "")
        self.settings.set("account_cache", {})

    def sign_out(self):
        try:
            self.call("POST", "/logout")
        except AccountError:
            pass
        self.forget()

    def buy_url(self, cycle, region):
        return self.call("POST", "/buy-link", {"cycle": cycle, "region": region})["url"]

    def activate(self, key):
        info = self.call("POST", "/activate", {"key": key.strip()})
        info["checked"] = time.time()
        self.settings.set("account_cache", info)
        return info

    def remove_device(self, device_id):
        info = self.call("POST", "/devices/remove", {"device_id": device_id})
        info["checked"] = time.time()
        self.settings.set("account_cache", info)
        return info

    def sign_in(self, open_url=webbrowser.open, wait=SIGN_IN_WAIT):
        """Opens Google sign-in in the browser and waits for the server to hand back a session token."""
        state = secrets.token_urlsafe(24)
        got = {}

        class Done(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                query = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
                if query.get("state", [""])[0] != state:
                    self.send_error(400)
                    return
                got.update({k: v[0] for k, v in query.items()})
                ok = "token" in got
                page = ("<h1>You are signed in</h1><p>Go back to Clip Studio. You can close this tab.</p>" if ok else
                        "<h1>Sign-in did not finish</h1><p>Go back to Clip Studio and try again.</p>")
                body = ('<!doctype html><meta charset="utf-8"><title>Clip Studio</title><body style="font:16px '
                        'Segoe UI;background:#0b0820;color:#f3f0ff;display:grid;place-items:center;height:90vh;'
                        'text-align:center">' + page).encode()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):
                pass

        server = http.server.HTTPServer(("127.0.0.1", 0), Done)
        server.timeout = 1
        port = server.server_address[1]
        open_url("%s/login?%s" % (API, urllib.parse.urlencode({"port": port, "state": state})))
        deadline = time.time() + wait
        try:
            while not got and time.time() < deadline:
                server.handle_request()
        finally:
            server.server_close()
        if "token" not in got:
            raise AccountError("Sign-in was cancelled or took too long." if not got.get("error") else
                               "Google sign-in did not finish. Please try again.")
        self.settings.set("account_token", got["token"])
        return self.refresh()


def run_in_thread(work, done):
    """Runs a blocking account call, then done(result, error) on whatever thread done marshals to."""
    def go():
        try:
            done(work(), None)
        except AccountError as e:
            done(None, str(e))
        except Exception as e:          # never let a network surprise kill the app
            done(None, "Something went wrong: %s" % str(e)[:120])
    threading.Thread(target=go, daemon=True).start()
