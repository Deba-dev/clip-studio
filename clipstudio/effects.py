"""Edits placed on what really happened in the stream. Pure logic, shared by the preview and the export.

Other clippers guess where to zoom from the transcript. Clip Studio already knows the second of every kill from the
HUD and of every laugh from the sound model, so the punch-in lands on the shot itself:
    a kill, clutch or death zooms the game picture around its centre, where an FPS keeps the crosshair
    a laugh zooms the webcam, when the layout shows one
The zoom is a snap cut in and out, the punch-in style gaming edits use, so it needs no easing and the preview and the
export can never drift apart.

Hook text is a line on screen for the first seconds, the part of a Short that decides whether people keep watching.
"""
from . import edit as clip_edit

ZOOM = {"game": 1.3, "cam": 1.2}
# kind: (what zooms, seconds before the event, seconds after it)
KINDS = {"kill": ("game", .3, .8), "clutch": ("game", .3, 1.2), "death": ("game", .2, .7), "laugh": ("cam", .15, 1.3)}
MIN_ZOOM = .25          # shorter than this, after cuts, reads as a glitch rather than a punch-in
HOOK_SECONDS = 2.6
HOOK_CHARS = 18         # per line: the hook sits at the top, where a phone's UI leaves the full width free
HOOK_LINES = 3
HOOK_MAX = 60


def zoom_windows(clip, layout):
    """Stream-time windows {target: [(a, b), ...]} for this clip. layout is the resolved one: stack, blur or crop."""
    if not clip_edit.settings(clip)["zoom"]:
        return {}
    found = {}
    for event in clip.get("events") or []:
        kind = KINDS.get(event.get("kind"))
        if not kind:
            continue
        target, before, after = kind
        if target == "cam" and layout != "stack":
            continue
        a, b = max(event["t"] - before, clip["start"]), min(event["t"] + after, clip["end"])
        if b > a:
            found.setdefault(target, []).append([a, b])
    return {target: [tuple(r) for r in clip_edit.merge(ranges)] for target, ranges in found.items()}


def output_windows(clip, layout):
    """The same windows in finished-clip time, split around cuts, dropping slivers too short to read."""
    keep = clip_edit.keep_ranges(clip)
    out = {}
    for target, ranges in zoom_windows(clip, layout).items():
        for a, b in ranges:
            for ka, kb in keep:
                lo, hi = max(a, ka), min(b, kb)
                if hi - lo >= MIN_ZOOM:
                    out.setdefault(target, []).append((round(clip_edit.to_output(lo, keep), 3),
                                                       round(clip_edit.to_output(hi, keep), 3)))
    return out


def zoom_at(windows, t):
    """{target: factor} at stream time t, for the preview."""
    return {target: ZOOM[target] for target, ranges in windows.items() if any(a <= t <= b for a, b in ranges)}


def hook_lines(text):
    """The hook wrapped into short centred lines. Captions never wrap on their own, so this decides the breaks."""
    words = " ".join((text or "").split())[:HOOK_MAX].split()
    lines = []
    for word in words:
        if lines and len(lines[-1]) + 1 + len(word) <= HOOK_CHARS:
            lines[-1] += " " + word
        else:
            lines.append(word)
    return lines[:HOOK_LINES]


TALLY_SECONDS = 1.2


def tally(clip, game_key="valorant"):
    """[(finished-clip seconds, label)], one per kill: the running count named the way the game names it, so the
    clip says KILL, DOUBLE KILL, TRIPLE KILL at the frame each one lands."""
    if not clip_edit.settings(clip)["tally"]:
        return []
    from . import games
    keep = clip_edit.keep_ranges(clip)
    kills = sorted(e["t"] for e in clip.get("events") or []
                   if e.get("kind") == "kill" and clip["start"] <= e["t"] <= clip["end"])
    out = []
    for n, t in enumerate(kills, 1):
        at = clip_edit.to_output(t, keep)
        if at is not None:
            out.append((round(at, 3), games.multi_name(game_key or "valorant", n).upper()))
    return out


def tally_at(marks, t, length=None):
    """The label showing at finished-clip time t, and how long it has shown, or None."""
    for i, (at, label) in enumerate(marks):
        end = min(at + TALLY_SECONDS, marks[i + 1][0] if i + 1 < len(marks) else at + TALLY_SECONDS)
        if at <= t < end:
            return label, t - at
    return None
