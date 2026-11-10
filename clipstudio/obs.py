"""A small obs-websocket v5 client: follows recording state and asks for nothing heavy during a stream."""
import base64
import hashlib
import json
import threading
import time
import uuid

from websockets.exceptions import ConnectionClosed
from websockets.sync.client import connect

EVENTS_OUTPUTS = 1 << 6     # stream, record and replay buffer events
EVENTS_GENERAL = 1 << 0     # CustomEvent: Zunimi Studio sends its Mark moment this way


def auth_string(password, salt, challenge):
    secret = base64.b64encode(hashlib.sha256((password + salt).encode()).digest()).decode()
    return base64.b64encode(hashlib.sha256((secret + challenge).encode()).digest()).decode()


class ObsClient(threading.Thread):
    """Calls on_event(name, data) from this thread. Reconnects by itself, so OBS can start after the app."""

    def __init__(self, host, port, password, on_event, on_status):
        super().__init__(daemon=True)
        self.url = "ws://%s:%d" % (host, int(port))
        self.password = password
        self.on_event = on_event
        self.on_status = on_status
        self.stop_flag = threading.Event()
        self.ws = None
        self.pending = {}

    def stop(self):
        self.stop_flag.set()

    def run(self):
        while not self.stop_flag.is_set():
            try:
                with connect(self.url, subprotocols=["obswebsocket.json"], open_timeout=3) as ws:
                    self.ws = ws
                    self._identify(ws)
                    self.on_status("Connected to OBS", True)
                    self.request("GetRecordStatus")
                    self._listen(ws)
            except PermissionError as e:       # must come first: it is also a kind of OSError
                self.ws = None
                self.on_status(str(e), False)
                self.stop_flag.wait(15)
                continue
            except (OSError, TimeoutError, ConnectionClosed):
                pass
            self.ws = None
            self.on_status("Waiting for OBS...", False)
            self.stop_flag.wait(5)

    def _identify(self, ws):
        hello = json.loads(ws.recv(timeout=5))["d"]
        reply = {"rpcVersion": 1, "eventSubscriptions": EVENTS_OUTPUTS | EVENTS_GENERAL}
        need = hello.get("authentication")
        if need:
            if not self.password:
                raise PermissionError("OBS needs its WebSocket password (see Settings)")
            reply["authentication"] = auth_string(self.password, need["salt"], need["challenge"])
        ws.send(json.dumps({"op": 1, "d": reply}))
        try:
            message = json.loads(ws.recv(timeout=5))
        except ConnectionClosed as e:
            raise PermissionError("OBS refused the WebSocket password") from e
        if message.get("op") != 2:
            raise ConnectionError("Unexpected reply from OBS")

    def _listen(self, ws):
        while not self.stop_flag.is_set():
            try:
                message = json.loads(ws.recv(timeout=1))
            except TimeoutError:
                continue
            data = message.get("d", {})
            if message.get("op") == 5:
                self.on_event(data.get("eventType", ""), data.get("eventData") or {})
            elif message.get("op") == 7:
                self.on_event("Reply:" + self.pending.pop(data.get("requestId"), ""), data.get("responseData") or {})

    def request(self, kind, data=None):
        ws = self.ws
        if ws is None:
            return
        rid = uuid.uuid4().hex
        self.pending[rid] = kind
        try:
            ws.send(json.dumps({"op": 6, "d": {"requestType": kind, "requestId": rid, "requestData": data or {}}}))
        except (OSError, ConnectionClosed):
            pass


class RecordingTracker:
    """Turns OBS events into library sessions. Separate from the socket, so it can be tested without OBS."""

    def __init__(self, library, on_finished, clock=time.time):
        self.library = library
        self.on_finished = on_finished
        self.clock = clock
        self.sid = None
        self.started = 0.0
        self.files = []

    def recording_time(self):
        return self.clock() - self.started if self.sid else None

    def handle(self, name, data):
        if name == "RecordStateChanged":
            state = data.get("outputState")
            path = data.get("outputPath") or ""
            if state == "OBS_WEBSOCKET_OUTPUT_STARTED":
                self.started = self.clock()
                self.files = [path] if path else []
                label = time.strftime("Stream %d %b %Y, %H:%M", time.localtime(self.started))
                self.sid = self.library.add_session(label, path, self.started)
            elif state == "OBS_WEBSOCKET_OUTPUT_STOPPED" and self.sid:
                if path and path not in self.files:
                    self.files.append(path)
                self._finish()
        elif name == "ReplayBufferSaved":
            self.mark()         # streamers already press this key on good moments
        elif name == "CustomEvent" and data.get("zunimi") == "mark":
            self.mark("zunimi")     # Zunimi Studio's Mark moment (menu, hotkey, phone or Stream Deck)
        elif name == "RecordFileChanged" and self.sid:
            path = data.get("newOutputPath")
            if path and path not in self.files:
                self.files.append(path)

    def mark(self, kind="hotkey"):
        t = self.recording_time()
        if t is not None:
            self.library.add_marker(self.sid, t, kind)
        return t

    def _finish(self):
        from .media import write_concat
        from .paths import data_dir
        import os
        sid, files = self.sid, self.files
        self.sid = None
        if len(files) > 1:
            source = write_concat(files, os.path.join(data_dir(), "session-%d.ffconcat" % sid))
        else:
            source = files[0] if files else ""
        if source:
            self.library.update_session(sid, source=source)
            self.on_finished(sid)
        else:
            self.library.update_session(sid, status="failed", error="OBS did not report a recording file.")
