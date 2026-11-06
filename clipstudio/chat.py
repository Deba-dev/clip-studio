"""Live chat readers, plus chat-file import. Same public, read-only connections ChatDoom uses.

Readers only log (time, platform, author, text). That is CPU-light and safe to run while streaming.
"""
import asyncio
import json
import re
import threading
import time
import urllib.request

PUSHER_URL = "wss://ws-us2.pusher.com/app/32cbd69e4b950bf97679?protocol=7&client=js&version=8.4.0&flash=false"
VIDEO_ID = re.compile(r"(?:v=|youtu\.be/|/live/|/shorts/)([\w-]{11})")


def youtube_id(text):
    text = text.strip()
    found = VIDEO_ID.search(text)
    if found:
        return found.group(1)
    return text if re.fullmatch(r"[\w-]{11}", text) else ""


def parse_twitch_line(line):
    found = re.search(r":([^!\s]+)![^ ]+ PRIVMSG #\S+ :(.*)$", line)
    return (found.group(1), found.group(2)) if found else None


def parse_kick_event(event, raw):
    if not event.endswith("ChatMessageEvent"):
        return None
    try:
        data = json.loads(raw) if isinstance(raw, str) else raw
        text = re.sub(r"\[emote:\d+:([^\]]+)\]", r"\1", data.get("content", ""))
        return (data.get("sender") or {}).get("username", "?"), text
    except (ValueError, AttributeError):
        return None


class ChatReader(threading.Thread):
    platform = ""

    def __init__(self, target, on_message, on_status=lambda platform, text: None):
        super().__init__(daemon=True)
        self.target = target.strip()
        self.on_message = on_message
        self.on_status = on_status
        self.stop_flag = threading.Event()

    def stop(self):
        self.stop_flag.set()

    def emit(self, author, text):
        self.on_message(time.time(), self.platform, author, text)

    def status(self, text):
        self.on_status(self.platform, text)

    def run(self):
        try:
            self.read()
        except Exception as e:
            self.status("Error: %s" % str(e)[:80])


class TwitchReader(ChatReader):
    platform = "twitch"

    def read(self):
        asyncio.run(self.loop())

    async def loop(self):
        import websockets
        channel = self.target.lstrip("#").lower()
        while not self.stop_flag.is_set():
            try:
                async with websockets.connect("wss://irc-ws.chat.twitch.tv:443") as ws:
                    await ws.send("PASS SCHMOOPIIE")
                    await ws.send("NICK justinfan%d" % (10000 + id(self) % 80000))
                    await ws.send("JOIN #" + channel)
                    self.status("Connected")
                    while not self.stop_flag.is_set():
                        try:
                            data = await asyncio.wait_for(ws.recv(), 1)
                        except asyncio.TimeoutError:
                            continue
                        for line in data.split("\r\n"):
                            if line.startswith("PING"):
                                await ws.send("PONG :tmi.twitch.tv")
                            else:
                                parsed = parse_twitch_line(line)
                                if parsed:
                                    self.emit(*parsed)
            except Exception as e:
                self.status("Reconnecting (%s)" % str(e)[:40])
            await asyncio.sleep(3)


class KickReader(ChatReader):
    platform = "kick"

    def lookup(self):
        req = urllib.request.Request("https://kick.com/api/v2/channels/" + self.target.lower(), headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36",
            "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as r:
            return str(json.load(r)["chatroom"]["id"])

    def read(self):
        asyncio.run(self.loop())

    async def loop(self):
        import websockets
        try:
            room = self.target if self.target.isdigit() else await asyncio.to_thread(self.lookup)
        except Exception:
            return self.status("Kick blocked the lookup: enter the numeric chatroom ID in Settings")
        while not self.stop_flag.is_set():
            try:
                async with websockets.connect(PUSHER_URL) as ws:
                    while not self.stop_flag.is_set():
                        try:
                            raw = await asyncio.wait_for(ws.recv(), 1)
                        except asyncio.TimeoutError:
                            continue
                        message = json.loads(raw)
                        event = message.get("event", "")
                        if event == "pusher:connection_established":
                            await ws.send(json.dumps({"event": "pusher:subscribe", "data": {
                                "auth": "", "channel": "chatrooms.%s.v2" % room}}))
                        elif event == "pusher_internal:subscription_succeeded":
                            self.status("Connected")
                        elif event == "pusher:ping":
                            await ws.send(json.dumps({"event": "pusher:pong", "data": {}}))
                        else:
                            parsed = parse_kick_event(event, message.get("data", "{}"))
                            if parsed:
                                self.emit(*parsed)
            except Exception as e:
                self.status("Reconnecting (%s)" % str(e)[:40])
            await asyncio.sleep(3)


class YouTubeReader(ChatReader):
    platform = "youtube"

    def read(self):
        import pytchat
        video = youtube_id(self.target)
        if not video:
            return self.status("Enter a live link or video ID in Settings")
        while not self.stop_flag.is_set():
            chat = None
            try:
                chat = pytchat.create(video_id=video, interruptable=False)
                self.status("Connected")
                while not self.stop_flag.is_set() and chat.is_alive():
                    for item in chat.get().sync_items():
                        if item.type in ("textMessage", "superChat"):
                            self.emit(item.author.name, item.message)
                    self.stop_flag.wait(1)
            except Exception as e:
                self.status("Reconnecting (%s)" % str(e)[:40])
            finally:
                if chat is not None:
                    try:
                        chat.terminate()
                    except Exception:
                        pass
            self.stop_flag.wait(5)


class ChatLogger:
    """Starts a reader for each configured platform and batches messages into the library."""

    def __init__(self, library, settings, on_status=lambda platform, text: None):
        self.library = library
        self.on_status = on_status
        self.settings = settings
        self.readers = []
        self.buffer = []
        self.lock = threading.Lock()
        self.sid = None
        self.started = 0.0

    def start(self, sid, started):
        self.stop()
        self.sid, self.started = sid, started
        for key, cls in (("twitch_channel", TwitchReader), ("kick_channel", KickReader),
                         ("youtube_video", YouTubeReader)):
            target = self.settings.get(key)
            if target:
                reader = cls(target, self.add, self.on_status)
                reader.start()
                self.readers.append(reader)

    def add(self, when, platform, author, text):
        with self.lock:
            self.buffer.append((when - self.started, platform, author, text))

    def flush(self):
        with self.lock:
            rows, self.buffer = self.buffer, []
        if rows and self.sid:
            self.library.add_chat(self.sid, rows)

    def stop(self):
        for reader in self.readers:
            reader.stop()
        self.readers = []
        self.flush()
        self.sid = None


def parse_chat_file(path):
    """Imports a saved chat for an older recording. Reads TwitchDownloader JSON and plain `seconds,author,text` CSV."""
    with open(path, encoding="utf-8-sig") as f:
        text = f.read()
    if text.lstrip().startswith("{"):
        rows = []
        for c in json.loads(text).get("comments", []):
            body = (c.get("message") or {}).get("body", "")
            author = (c.get("commenter") or {}).get("display_name", "?")
            rows.append((float(c.get("content_offset_seconds", 0)), "twitch", author, body))
        return rows
    rows = []
    for line in text.splitlines():
        parts = line.split(",", 2)
        try:
            rows.append((float(parts[0]), "import", parts[1], parts[2]))
        except (IndexError, ValueError):
            continue
    return rows
