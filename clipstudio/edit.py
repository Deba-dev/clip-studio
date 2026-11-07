"""What a clip becomes after editing. Pure logic, shared by the preview and the export so they can never disagree.

The clip's start and end stay in stream time. Everything else lives in clip["edit"], which the app can change freely:
    cuts       [[a, b], ...] stream-time ranges removed from the middle
    auto_loud  bring the clip to the loudness phones expect
    gain_db    the user's own change on top of that
    fade_in, fade_out   seconds
    mute       [[a, b], ...] stream-time ranges silenced, for example a slur or a teammate's name
    pan        -1..1, where the Centre crop sits across the frame
    caption_size, caption_y, caption_color
"""
import math

TARGET_LUFS = -14.0     # what YouTube Shorts, TikTok and Reels play at
TRUE_PEAK = -1.5
DEFAULTS = {"cuts": [], "mute": [], "auto_loud": True, "gain_db": 0.0, "fade_in": 0.0, "fade_out": 0.0, "pan": 0.0,
            "caption_size": 84, "caption_y": 560, "caption_color": "FFE100"}
MIN_PART = 0.1
METER_OFFSET = -3.0     # mono RMS reads 3 dB under stereo LUFS. Measured on seven real clips: within 1.7 dB after this


def settings(clip):
    return {**DEFAULTS, **(clip.get("edit") or {})}


def merge(ranges):
    out = []
    for a, b in sorted((min(r), max(r)) for r in ranges):
        if out and a <= out[-1][1]:
            out[-1][1] = max(out[-1][1], b)
        else:
            out.append([a, b])
    return out


def keep_ranges(clip):
    """The parts of the stream that survive, in order."""
    start, end = clip["start"], clip["end"]
    out, at = [], start
    for a, b in merge(settings(clip)["cuts"]):
        a, b = max(a, start), min(b, end)
        if b <= a:
            continue
        if a - at >= MIN_PART:
            out.append((at, a))
        at = max(at, b)
    if end - at >= MIN_PART:
        out.append((at, end))
    return out or [(start, start + MIN_PART)]


def length(clip):
    return sum(b - a for a, b in keep_ranges(clip))


def to_output(t, keep):
    """Stream time to finished-clip time. None when t was cut out."""
    done = 0.0
    for a, b in keep:
        if a <= t <= b:
            return done + t - a
        done += b - a
    return None


def skip_cut(t, keep):
    """Where playback should really be at t: a position inside a cut jumps to the next kept part."""
    for a, b in keep:
        if t < a:
            return a
        if t <= b:
            return t
    return None


def add_cut(clip, a, b):
    """Returns a new edit with a..b removed, refusing to cut the whole clip away."""
    edit = dict(clip.get("edit") or {})
    edit["cuts"] = merge(settings(clip)["cuts"] + [[a, b]])
    return edit if length({**clip, "edit": edit}) >= 1 else None


def retime_words(clip):
    """Words in finished-clip time. Words inside a cut go with it."""
    keep = keep_ranges(clip)
    out = []
    for w in clip.get("words") or []:
        s, e = to_output(w["s"], keep), to_output(w["e"], keep)
        if s is None and e is None:
            continue
        if s is None:
            s = max(e - (w["e"] - w["s"]), 0.0)
        if e is None:
            e = s + (w["e"] - w["s"])
        out.append({**w, "s": round(s, 3), "e": round(e, 3)})
    return out


def gated_level(values):
    """Loudness the way a meter reads it: quiet stretches between sounds do not count, however long they are."""
    power = [10 ** (float(db) / 10) for db in values if db > -60]
    if not power:
        return None
    gate = sum(power) / len(power) / 10
    loud = [v for v in power if v >= gate]
    return 10 * math.log10(sum(loud) / len(loud))


def estimate_gain(levels, clip):
    """Roughly how many dB the export will add, from the per-second levels, without touching the video file."""
    edit = settings(clip)
    if not edit["auto_loud"]:
        return edit["gain_db"]
    level = gated_level([db for a, b in keep_ranges(clip) for db in levels[int(a):int(b) + 1]])
    if level is None:
        return edit["gain_db"]
    return max(min(TARGET_LUFS - level + METER_OFFSET, 24.0), -12.0) + edit["gain_db"]
