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
BURST = 14              # kills this close together are one moment
KILL_SCORE = {0: 1.5, 1: 3.5, 2: 6.0, 3: 8.0, 4: 9.5, 5: 11.0}
KILL_NAME = {1: "Kill", 2: "Double kill", 3: "Triple kill", 4: "Quadra kill", 5: "Ace"}
LAUGH_MIN = 0.15        # YAMNet laughter score. 99.9% of a real stream sat under 0.26, so this is already rare
WEIGHTS = {"funny": 1.0, "kills": 1.0, "deaths": 1.0, "hype": 1.0}
SHARE = 4               # each wanted kind keeps at least 1/SHARE of the shortlist, when that many exist
SHORTEST, LONGEST = 12, 59


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
        p["tags"] = ["marked"] if p["score"] >= 100 else ["hype"]
    return picks


def frame(first, last, lead, tail, duration):
    """Clip edges around a span of action, with the setup before it and the reaction after it."""
    start = max(first - lead, 0.0)
    end = min(last + tail, duration)
    if end - start < SHORTEST:
        start = max(end - SHORTEST, 0.0)
    if end - start > LONGEST:
        start = end - LONGEST
    return start, end


def locate(event, gun):
    """Keyframes only say a kill happened in the last few seconds. The gunshot in that gap says exactly when."""
    lo, hi = int(event["from"]), int(event["t"]) + 1
    part = gun[lo:hi] if gun is not None else np.zeros(0)
    return float(lo + int(np.argmax(part))) if part.size and part.max() > .2 else event["t"] - 2.0


def reaction(lanes, t):
    """How hard the room reacted in the seconds after t. Returns (score, laughed, shouted)."""
    if not lanes:
        return 0.0, False, False
    lo, hi = int(t), int(t) + 9
    laugh = float(lanes["laugh"][lo:hi].max(initial=0))
    shout = float(lanes["shout"][lo:hi].max(initial=0))
    return min(laugh / .25, 1) * 3 + min(shout / .08, 1) * 1.5, laugh >= LAUGH_MIN, shout >= .05


def moment(first, last, peak, score, lead, tail, duration, tags, reasons, title, events):
    start, end = frame(first, last, lead, tail, duration)
    return {"peak": float(peak), "score": float(score), "start": start, "end": end, "first": float(first),
            "last": float(last), "tags": tags, "reasons": reasons, "title": title, "events": events}


def kill_moment(kills, lanes, duration):
    first, last = kills[0]["at"], kills[-1]["at"]
    bonus, laughed, _ = reaction(lanes, last)
    n = min(len(kills), 5)
    reasons = ["%d enemies went down in %ds" % (n, last - first + 1) if n > 1 else "An enemy went down"]
    if laughed:
        reasons.append("You laughed right after")
    m = moment(first, last, last, KILL_SCORE[n] + bonus, 12, 5, duration, ["kills"] + (["funny"] if laughed else []),
               reasons, KILL_NAME[n], [{"t": k["at"], "kind": "kill"} for k in kills])
    m["round"] = kills[0]["round"]
    return m


def game_moments(game, lanes, duration):
    """Turns the HUD's events into moments: kill bursts, reacted-to deaths and clutches."""
    gun = lanes["gun"] if lanes else None
    events = [dict(e, at=locate(e, gun)) for e in game["events"]]
    out = []
    burst = []
    for e in sorted((e for e in events if e["kind"] == "enemy_down"), key=lambda e: e["at"]):
        if burst and (e["at"] - burst[-1]["at"] > BURST or e["round"] != burst[-1]["round"]):
            out.append(kill_moment(burst, lanes, duration))
            burst = []
        burst.append(e)
    if burst:
        out.append(kill_moment(burst, lanes, duration))
    for e in events:
        if e["kind"] == "you_down":
            bonus, laughed, shouted = reaction(lanes, e["at"])
            if bonus < .5:
                continue        # dying is routine. Dying and reacting to it is the clip
            reasons = ["You died"] + (["You laughed about it"] if laughed else []) + (["You yelled"] if shouted else [])
            out.append(moment(e["at"], e["at"], e["at"], 2.5 + bonus * 1.4, 12, 8, duration,
                              ["deaths"] + (["funny"] if laughed else []), reasons, "Death reaction",
                              [{"t": e["at"], "kind": "death"}]))
        elif e["kind"] == "clutch":
            n = e["against"]
            out.append(moment(e["t"] - 22, e["t"], e["t"], 9.0 + n, 6, 5, duration, ["kills"],
                              ["You won the round alone against %d" % n], "1v%d clutch" % n,
                              [{"t": e["t"], "kind": "clutch"}]))
    return out


def apply_own_kills(m, own, dead=None):
    """Credits a kill moment. The skull banner also shows while spectating, so anything after the streamer's death
    in that round belongs to a teammate. dead is the last moment the streamer was surely alive."""
    mine = [t for t in own if dead is None or t < dead]
    n = min(len(mine), 5)
    if n:
        m["score"] = KILL_SCORE[n] + 2.0 + (m["score"] - KILL_SCORE[min(len(m["events"]), 5)])
        m["title"] = KILL_NAME[n]
        m["reasons"] = ["You got %d kills" % n if n > 1 else "You got the kill"] + m["reasons"][1:]
        m["events"] = [{"t": t, "kind": "kill"} for t in mine]
        m["first"], m["last"], m["peak"] = mine[0], mine[-1], mine[-1]
    else:
        m["score"] *= .4
        m["title"] = "Team fight"
        m["tags"] = ["hype"] + [t for t in m["tags"] if t not in ("kills", "hype")]
        m["reasons"] = ["Your team got the kill"] + m["reasons"][1:]
    return m


def laugh_moments(lanes, duration):
    """Laughter is the best funny-moment detector there is. Most of the clip sits before it: that is the joke."""
    lane = np.array(lanes["laugh"], dtype=np.float64)
    out = []
    while lane.size:
        i = int(np.argmax(lane))
        peak = float(lane[i])
        if peak < LAUGH_MIN:
            break
        lasting = int((lanes["laugh"][max(i - 6, 0):i + 7] >= .08).sum())
        out.append(moment(i, i, i, 4.0 + peak * 7 + min(lasting, 6) * .5, 20, 6, duration, ["funny"],
                          ["You laughed" if lasting < 4 else "A long laugh"], "Funny moment",
                          [{"t": float(i), "kind": "laugh"}]))
        lane[max(i - MIN_GAP, 0):i + MIN_GAP] = 0
    return out


def overlaps(a, b):
    return a["start"] < b["end"] and b["start"] < a["end"]


def absorb(keep, other):
    """Two signals on the same moment make it better, and it stays one clip."""
    keep["score"] += other["score"] * .35
    keep["tags"] = keep["tags"] + [t for t in other["tags"] if t not in keep["tags"]]
    keep["reasons"] = keep["reasons"] + [r for r in other["reasons"] if r not in keep["reasons"]]
    keep["events"] = keep.get("events", []) + other.get("events", [])
    if "first" in other:
        keep["first"] = min(keep.get("first", other["first"]), other["first"])
        keep["last"] = max(keep.get("last", other["last"]), other["last"])
        keep["start"] = min(keep["start"], other["start"])
        keep["end"] = max(keep["end"], other["end"])
        if keep["end"] - keep["start"] > LONGEST:
            keep["start"] = keep["end"] - LONGEST


def select(moments, limit, weights=None):
    """The shortlist: the user's priorities, no duplicates, and never twelve clips of the same kind."""
    weights = {**WEIGHTS, **(weights or {})}
    ranked = []
    for m in moments:
        if m["score"] >= 100:
            ranked.append(m)
            continue
        weight = max((weights.get(t, 1.0) for t in m["tags"]), default=1.0)
        if weight > 0:
            ranked.append(dict(m, score=m["score"] * weight))
    ranked.sort(key=lambda m: m["score"], reverse=True)
    taken = []
    for m in ranked:
        twin = next((k for k in taken if overlaps(k, m)), None)
        if twin:
            absorb(twin, m)
        else:
            taken.append(dict(m))
    taken.sort(key=lambda m: m["score"], reverse=True)
    chosen, spare = taken[:limit], taken[limit:]
    floor = max(limit // SHARE, 1)
    for tag in ("kills", "deaths", "funny"):
        if weights.get(tag, 1.0) <= 0:
            continue
        for extra in [m for m in spare if tag in m["tags"]][:max(floor - sum(tag in m["tags"] for m in chosen), 0)]:
            counts = {t: sum(t in m["tags"] for m in chosen) for t in ("funny", "kills", "deaths")}
            loser = next((m for m in reversed(chosen) if m["score"] < 100 and
                          all(counts[t] > floor for t in m["tags"] if t in counts)), None)
            if loser:
                chosen[chosen.index(loser)] = extra
    chosen.sort(key=lambda m: m["score"], reverse=True)
    return chosen


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
    if "first" in pick:         # the transcript may move the edges, but never so far that the action is lost
        start = min(start, pick["first"] - 3)
        end = max(end, pick["last"] + 2)
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
