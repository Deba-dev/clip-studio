"""Brings in a stream that already happened, from its YouTube, Twitch or Kick link."""
import json
import os
import re
import shutil

from .paths import tool

FORMAT = ("bv*[height<=1080][vcodec^=avc1]+ba[ext=m4a]/bv*[height<=1080]+ba/"
          "b[height<=1080]/bv*+ba/b")
PLATFORMS = (("youtube", re.compile(r"^https?://(www\.|m\.)?(youtube\.com/(watch|live/)|youtu\.be/)", re.I)),
             ("twitch", re.compile(r"^https?://(www\.|m\.)?twitch\.tv/(videos/\d+|\w+/video/\d+)", re.I)),
             ("kick", re.compile(r"^https?://(www\.)?kick\.com/[\w-]+/videos/[\w-]+|"
                                 r"^https?://(www\.)?kick\.com/video/[\w-]+", re.I)))
HELP = (("private video", "This video is private. Make it unlisted or public, then try again."),
        ("members-only", "This stream is for members only, so it cannot be downloaded."),
        ("subscriber", "This stream is for subscribers only, so it cannot be downloaded."),
        ("sign in to confirm", "YouTube asked for a sign-in check. Try again later, or add the recording file instead."),
        ("sign in", "This stream needs a sign-in, so it cannot be downloaded."),
        ("this live event will begin", "This stream has not started yet."),
        ("video is unavailable", "This video is unavailable."),
        ("video unavailable", "This video is unavailable."),
        ("404", "That link was not found. The platform may have deleted this past stream."),
        ("unsupported url", "That link is not a past stream on YouTube, Twitch or Kick."),
        ("no space left", "The disk is full."))


def platform_of(url):
    url = url.strip()
    for name, pattern in PLATFORMS:
        if pattern.search(url):
            return name
    return ""


def friendly(error):
    text = re.sub(r"\x1b\[[0-9;]*m", "", str(error))
    low = text.lower()
    for key, message in HELP:
        if key in low:
            return message
    return "Could not get this stream: " + text.replace("ERROR: ", "")[:160]


def base_options():
    options = {"quiet": True, "no_warnings": True, "noprogress": True, "ffmpeg_location": tool("ffmpeg"),
               "windowsfilenames": True, "retries": 5, "fragment_retries": 10, "concurrent_fragment_downloads": 4,
               "socket_timeout": 30}
    runtimes = {name: {} for name in ("deno", "node") if shutil.which(name)}
    if runtimes:
        options["js_runtimes"] = runtimes       # YouTube needs a JavaScript runtime for some formats
    return options


def inspect(url):
    import yt_dlp
    with yt_dlp.YoutubeDL({**base_options(), "format": FORMAT}) as ydl:
        info = ydl.extract_info(url, download=False)
    if info.get("is_live") or info.get("live_status") in ("is_live", "is_upcoming", "post_live"):
        raise ValueError("This stream is still live or still processing. Try again once the platform has finished it.")
    if info.get("_type") == "playlist":
        raise ValueError("That is a playlist. Paste the link of one past stream.")
    return info


def size_of(info):
    formats = info.get("requested_formats") or [info]
    return sum(f.get("filesize") or f.get("filesize_approx") or 0 for f in formats)


def check_space(folder, needed):
    free = shutil.disk_usage(folder).free
    if needed and free < needed * 1.15:
        raise ValueError("This stream needs about %.1f GB and only %.1f GB is free on that drive." % (
            needed / 1e9, free / 1e9))


def describe(done, total, eta):
    if not total:
        return "%.0f MB so far" % (done / 1e6)
    note = "%.2f of %.2f GB" % (done / 1e9, total / 1e9)
    return note + ("  ·  about %d min left" % max(eta // 60, 1) if eta else "")


def download(url, folder, on_progress=lambda value, note: None):
    """Interrupted downloads resume from their .part files when this runs again."""
    import yt_dlp

    def hook(d):
        if d.get("status") == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            done = d.get("downloaded_bytes") or 0
            on_progress(done / total if total else 0.0, describe(done, total, d.get("eta")))

    options = {**base_options(), "format": FORMAT, "merge_output_format": "mp4/mkv", "continuedl": True,
               "outtmpl": os.path.join(folder, "%(title).70B [%(id)s].%(ext)s"), "progress_hooks": [hook]}
    with yt_dlp.YoutubeDL(options) as ydl:
        info = ydl.extract_info(url, download=True)
    return info["requested_downloads"][0]["filepath"]


def youtube_chat(url, folder):
    """YouTube keeps a chat replay for past streams. Returns rows for the library, or [] if there is none."""
    import yt_dlp
    options = {**base_options(), "skip_download": True, "writesubtitles": True, "subtitleslangs": ["live_chat"],
               "outtmpl": os.path.join(folder, "chat-%(id)s.%(ext)s")}
    with yt_dlp.YoutubeDL(options) as ydl:
        info = ydl.extract_info(url, download=True)
    path = os.path.join(folder, "chat-%s.live_chat.json" % info["id"])
    if not os.path.isfile(path):
        return []
    try:
        return parse_live_chat(path)
    finally:
        os.remove(path)


def parse_live_chat(path):
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            try:
                replay = json.loads(line)["replayChatItemAction"]
                t = int(replay.get("videoOffsetTimeMsec", -1)) / 1000
            except (ValueError, KeyError, TypeError):
                continue
            if t < 0:
                continue
            for action in replay.get("actions", []):
                item = (action.get("addChatItemAction") or {}).get("item") or {}
                body = item.get("liveChatTextMessageRenderer") or item.get("liveChatPaidMessageRenderer")
                if not body:
                    continue
                runs = (body.get("message") or {}).get("runs", [])
                text = "".join(r.get("text") or (r.get("emoji") or {}).get("shortcuts", [""])[0] for r in runs)
                author = (body.get("authorName") or {}).get("simpleText", "?")
                rows.append((t, "youtube", author, text))
    return rows
