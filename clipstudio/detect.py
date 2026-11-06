"""Finds candidate moments. Pure numpy, no model needed, so it finishes in seconds even on a 4-hour stream.

Every signal is measured against the stream's own recent past, because "loud" and "busy chat" mean different
things on different channels. A signal with no data simply drops out, so quiet streams still get a shortlist.
"""
import re

import numpy as np

BASELINE = 301          # seconds of rolling context
MIN_GAP = 20            # two moments closer than this are the same moment
LEAD_SHARE = 0.72       # most of a clip sits before the peak, so the setup survives
DEAD_AIR = 6            # most seconds of silence allowed before the first word
REACTION = 5            # a reaction lasts at least this long after its peak
HYPE = re.compile(r"\b(lol+|lmao+|kek\w*|omega\w*|pog\w*|clip\s*(it|that)?|w+|l+|no\s*way|wtf|omg|gg+|haha+|"
                  r"bhai+|arre+|kya\s*baat|op+|mast|gajab)\b|[😂🤣💀🔥😱]", re.I)
VOICE = re.compile(r"\b(no+\s*way|oh\s*my\s*god|what+|let'?s\s*go+|holy|bro+|are\s*you\s*kidding|wow+|"
                   r"bhai+|arre+|kya|chal+|maar|gaya|gayi|nahi+|oh\s*no+)\b|भाई|अरे|क्या|नहीं|गया", re.I)


def robust_z(series, window=BASELINE):
    """How unusual each second is against a rolling median, in spread units. Outliers cannot inflate the baseline."""
    x = np.asarray(series, dtype=np.float64)
    n = x.size
    if n == 0:
        return x
    step = max(window // 15, 1)
    probes = np.arange(0, n, step)
    half = window // 2
    med = np.empty(probes.size)
    spread = np.empty(probes.size)
    for i, p in enumerate(probes):
        part = x[max(p - half, 0):p + half + 1]
        m = np.median(part)
        med[i] = m
        spread[i] = np.median(np.abs(part - m))
    grid = np.arange(n)
    med = np.interp(grid, probes, med)
    spread = np.interp(grid, probes, spread) * 1.4826
    floor = max(float(np.std(x)) * 0.25, 1e-6)
    return (x - med) / np.maximum(spread, floor)


def smooth(series, width=5):
    series = np.asarray(series, dtype=np.float64)
    if series.size == 0:
        return series
    kernel = np.hanning(width + 2)[1:-1]
    return np.convolve(series, kernel / kernel.sum(), mode="same")


def chat_series(times, length, weights=None):
    out = np.zeros(length)
    idx = np.floor(np.asarray(times, dtype=np.float64)).astype(np.int64)
    keep = (idx >= 0) & (idx < length)
    values = 1.0 if weights is None else np.asarray(weights, dtype=np.float64)[keep]
    np.add.at(out, idx[keep], values)
    return out


def estimate_lag(loud, chat, low=2, high=40, default=10.0):
    """Viewers react after the moment. Learn this channel's delay by sliding chat over the audio."""
    n = min(len(loud), len(chat))
    if n < high * 4 or np.count_nonzero(chat[:n]) < 30:
        return default
    a = np.clip(robust_z(loud[:n]), 0, None)
    b = smooth(chat[:n], 5)
    a = a - a.mean()
    b = b - b.mean()
    denom = float(np.linalg.norm(a) * np.linalg.norm(b)) or 1.0
    best, best_score = default, 0.0
    for lag in range(low, high + 1):
        score = float(np.dot(a[:n - lag], b[lag:])) / denom
        if score > best_score:
            best, best_score = float(lag), score
    return best if best_score > 0.08 else default


def score_moments(loud, chat_rows, markers, duration, lag=None):
    """chat_rows: (t, platform, author, text). Returns the fused curve and the parts behind it."""
    n = max(int(np.ceil(duration)), len(loud), 1)
    level = np.full(n, -90.0)
    level[:len(loud)] = loud
    times = [r[0] for r in chat_rows]
    raw_chat = chat_series(times, n)
    lag = estimate_lag(level, raw_chat) if lag is None else lag
    shifted = np.asarray(times, dtype=np.float64) - lag
    on_time = chat_series(shifted, n)
    hype = chat_series(shifted, n, [1.0 if HYPE.search(r[3]) else 0.0 for r in chat_rows]) if chat_rows else np.zeros(n)
    platforms = {}
    for row, t in zip(chat_rows, shifted):
        platforms.setdefault(row[1], []).append(t)

    z_audio = np.clip(smooth(robust_z(level), 5), 0, 8)
    rise = np.clip(smooth(np.diff(level, prepend=level[0]), 3) / 6.0, 0, 3)
    per_minute = len(chat_rows) / max(duration / 60.0, 1.0)
    # Chat earns its weight: at 1 message a minute, a "spike" is two friends saying hi.
    chat_trust = float(np.clip((per_minute - 1.0) / 9.0, 0.0, 1.0))
    z_chat = np.clip(smooth(robust_z(smooth(on_time, 11)), 7), 0, 8)
    z_hype = np.clip(smooth(robust_z(smooth(hype, 11)), 7), 0, 8)
    curve = z_audio * (1.0 - 0.45 * chat_trust) + rise + chat_trust * (0.9 * z_chat + 0.6 * z_hype)
    return {"curve": curve, "audio": z_audio, "chat": z_chat, "hype": z_hype, "lag": lag, "chat_trust": chat_trust,
            "markers": markers, "per_platform": {k: chat_series(v, n) for k, v in platforms.items()}}


def _reasons(parts, peak):
    lo, hi = max(peak - 6, 0), peak + 7
    out = []
    if parts["audio"][lo:hi].max(initial=0) >= 2.0:
        out.append("Your audio jumped well above the level around it")
    if parts["chat_trust"] > 0 and parts["chat"][lo:hi].max(initial=0) >= 2.0:
        seen = [k for k, v in parts["per_platform"].items() if v[lo:hi].sum() >= 3]
        where = " + ".join(s.title() for s in sorted(seen))
        out.append("Chat spiked" + (" on " + where if where else ""))
    if parts["chat_trust"] > 0 and parts["hype"][lo:hi].max(initial=0) >= 2.0:
        out.append("Viewers reacted with hype words")
    return out or ["Stood out from the rest of this stream"]


def pick_moments(parts, duration, limit=12, length=45):
    """Top peaks, spaced out, with hotkey marks always first: a human choice beats any detector."""
    curve = parts["curve"].copy()
    picks = []
    for t, kind in parts["markers"]:
        if kind == "hotkey" and all(abs(p["peak"] - t) >= MIN_GAP for p in picks):
            picks.append({"peak": float(t), "score": 100.0, "reasons": ["You marked this with the hotkey"]})
            curve[max(int(t) - MIN_GAP, 0):int(t) + MIN_GAP] = 0
    floor = max(float(np.percentile(curve, 90)) if curve.size else 0.0, 0.5)
    while len(picks) < limit * 2 and curve.size:
        i = int(np.argmax(curve))
        if curve[i] < floor:
            break
        picks.append({"peak": float(i), "score": float(curve[i]), "reasons": _reasons(parts, i)})
        curve[max(i - MIN_GAP, 0):i + MIN_GAP] = 0
    for p in picks:
        p["start"] = max(p["peak"] - length * LEAD_SHARE, 0.0)
        p["end"] = min(p["start"] + length, duration)
    return picks


def refine_with_words(pick, words, max_length=59):
    """Uses the transcript to fix the classic clipper failure: starting mid-sentence and missing the setup.

    words: [{"w","s","e"}] in stream time. The start moves to the nearest real pause, so the clip opens at the
    beginning of a thought, and the end moves to the first pause after the reaction.
    """
    if not words:
        return pick
    peak = pick["peak"]
    pauses = [(a["e"], b["s"]) for a, b in zip(words, words[1:]) if b["s"] - a["e"] >= 0.7]
    start = pick["start"]
    near = [b for _, b in pauses if b <= peak - 4 and abs(b - start) <= 14]
    if near:
        start = min(near, key=lambda b: abs(b - start))
    spoken = [w for w in words if w["e"] > start]
    if spoken and spoken[0]["s"] - start > DEAD_AIR:
        start = spoken[0]["s"] - DEAD_AIR       # nobody watches half a minute of nothing on a phone
    # A reaction has short breaths inside it, so only a long pause well after the peak counts as finished.
    ends = [a["e"] for a, b in zip(words, words[1:]) if b["s"] - a["e"] >= 1.5 and a["e"] >= peak + REACTION]
    last = words[-1]["e"]
    end = ends[0] + 0.6 if ends else (last + 1.0 if last >= peak else pick["end"])
    end = max(min(end, pick["end"] + 8), peak + 2)
    if end - start > max_length:
        start = end - max_length
    pick = dict(pick, start=max(start, 0.0), end=end)
    voice = sum(1 for w in words if pick["start"] <= w["s"] <= pick["end"] and VOICE.search(w["w"]))
    if voice >= 2:
        pick["score"] += min(voice, 5) * 0.4
        pick["reasons"] = pick["reasons"] + ["You reacted out loud"]
    return pick


def title_from(words, peak):
    near = [w["w"].strip() for w in words if peak - 8 <= w["s"] <= peak + 4]
    text = " ".join(near).strip(" ,.")
    return (text[:57] + "...") if len(text) > 60 else text
