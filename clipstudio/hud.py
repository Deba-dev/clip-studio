"""Reads Valorant's own HUD, because the game already knows who died.

The top bar shows one portrait per living player, so the bar is a live scoreboard: a portrait leaving means a player
died. The ability icons belong to the player being watched, so when they stop matching, the streamer is dead and
spectating. The skull banner under the crosshair appears only for the streamer's own kills.

Only keyframes are decoded, which takes under a minute for a 3-hour stream. A stream with no such bar returns None and
detection falls back to sound and speech, so other games still work.
"""
import re
import subprocess
import threading

import numpy as np

from .media import HIDE, input_args
from .paths import tool

WIDTH, TOP, LOW = 1120, 90, 70      # the strip read from each keyframe, in 1080p pixels
LEFT = 400                          # strip x origin
ALLIES = (465, 532, 597, 665, 730)  # portrait centres
ENEMIES = (1190, 1257, 1322, 1388, 1455)
PORTRAIT = 18.0                     # detail score: filled slots measured 28-80, empty ones 1-6
ALIVE_MATCH = 0.7                   # ability icons match at about 0.9 when alive, under 0.6 when spectating
HOLD = 3                            # a drop must last this many keyframes: smoke and flashes cover portraits briefly
MENU_GAP = 12                       # keyframes between rounds before a new match is assumed
SKULL = 180                         # crop around the kill banner
BANNER_W, HALF = 200, 80            # the banner crop is wider, so the mirror axis can shift a little
MIRROR, EDGES = .7, 8               # banners measured .75-.96 symmetric with edges 9-41; game scenes under .55
STRAIGHT = 1.2                      # banners measured .55-1.18, the buy menu's tiles 1.2-1.34 and up
LONGEST_BANNER = 3.5                # seconds; banners hold about 2, the buy menu's symmetric tiles stay for many
CONTAINED = 2.0                     # banners' edges sit 2-8x more inside the ring than outside; doorways about 1.5
STUCK = 0.8                         # how often a slot may be filled beside an empty one before it counts as an overlay


def _detail(patch, k=1):
    """Edge strength. k is the step between compared pixels: a 360p stream blown up to 1080p is smooth at one pixel
    and only shows its edges three pixels apart, so k follows the upscale (view.stride)."""
    g = patch.astype(np.float32).mean(axis=2)
    return float(np.abs(g[k:-k, k:-k] * 4 - g[:-2 * k, k:-k] - g[2 * k:, k:-k] - g[k:-k, :-2 * k]
                        - g[k:-k, 2 * k:]).mean())


def read_slots(strip, k=1):
    """Which of the ten portrait slots hold a player in one keyframe. strip is the top bar, RGB."""
    out = []
    for cx in ALLIES + ENEMIES:
        x = cx - LEFT
        out.append(x + 20 <= strip.shape[1] and _detail(strip[28:72, x - 20:x + 20], k) > PORTRAIT)
    return out


def high_pass(gray):
    g = gray.astype(np.float32)
    kernel = np.ones(9, dtype=np.float32) / 9
    return g - np.apply_along_axis(lambda row: np.convolve(row, kernel, "same"), 1, g)


def similarity(a, b):
    a = (a - a.mean()) / max(float(a.std()), 1e-3)
    b = (b - b.mean()) / max(float(b.std()), 1e-3)
    return float((a * b).mean())


def scan(source, duration=0.0, on_progress=None, view="scale=1920:1080", k=1):
    """Returns (times, slots[n, 10], ability strips[n, h, w]) from the keyframes of a video.

    view turns the recording into the 1920x1080 game picture (view.game_filter), so vertical and boxed layouts read
    the same as a plain game recording. k is view.stride: how many times the game picture was enlarged.
    """
    graph = ("[0:v]" + view + ",split[a][b];[a]crop=%d:%d:%d:0[t];[b]crop=%d:%d:%d:975[l];"
             "[t][l]vstack=inputs=2,showinfo[v]" % (WIDTH, TOP, LEFT, WIDTH, LOW, LEFT))
    cmd = [tool("ffmpeg"), "-v", "info", "-nostats", "-skip_frame", "nokey", *input_args(source),
           "-filter_complex", graph, "-map", "[v]", "-fps_mode", "passthrough", "-pix_fmt", "rgb24",
           "-f", "rawvideo", "-"]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=HIDE)
    stamps = []

    def read_times():
        for line in proc.stderr:
            m = re.search(rb"pts_time:([\d.]+)", line)
            if m:
                stamps.append(float(m.group(1)))

    reader = threading.Thread(target=read_times, daemon=True)
    reader.start()
    size = WIDTH * (TOP + LOW) * 3
    slots, strips = [], []
    try:
        while True:
            raw = proc.stdout.read(size)
            if len(raw) < size:
                break
            frame = np.frombuffer(raw, np.uint8).reshape(TOP + LOW, WIDTH, 3)
            slots.append(read_slots(frame[:TOP], k))
            strips.append(frame[TOP:, 240:880].mean(axis=2).astype(np.uint8))
            if on_progress and duration and stamps and len(slots) % 50 == 0:
                on_progress(min(stamps[-1] / duration, 1.0))
    finally:
        proc.stdout.close()
        proc.wait()
    reader.join(2)
    count = min(len(stamps), len(slots))
    return (np.array(stamps[:count]), np.array(slots[:count], dtype=bool).reshape(-1, 10),
            np.array(strips[:count], dtype=np.uint8).reshape(count, LOW, 640))


def split_rounds(allies, enemies):
    """Finds rounds in the portrait counts. Returns (first, last) keyframe pairs; a round starts when players reappear."""
    total = allies + enemies
    rounds, start, gap = [], None, 0
    for i in range(total.size):
        full = allies[i] >= 4 and enemies[i] >= 3     # one enemy slot is often hidden behind a webcam
        back = i > 0 and total[i] >= total[i - 1] + 2
        if full and (start is None or back):
            if start is not None:
                rounds.append((start, i - 1))
            start, gap = i, 0
        elif start is not None:
            gap = gap + 1 if total[i] == 0 else 0
            if gap >= 3:
                rounds.append((start, i - gap))
                start, gap = None, 0
    if start is not None:
        rounds.append((start, total.size - 1))
    return [r for r in rounds if r[1] - r[0] >= 3]


def settled(counts):
    """Removes brief dips, then holds each drop: inside one round a dead player stays dead."""
    n = counts.size
    held = np.array([counts[i:min(i + HOLD + 1, n)].max() for i in range(n)])
    return np.minimum.accumulate(held)


def trim_round(allies, enemies, a, b):
    """A round's last keyframes can already be a menu. An empty bar means the round is over, not that everyone died."""
    while b > a and allies[b] + enemies[b] == 0:
        b -= 1
    return b


def alive_track(rounds, allies, enemies, strips):
    """When the streamer died in each round. Built per match, since each match can use a different agent.

    The buy menu hides the ability bar, so low readings only count once a teammate slot has actually gone.
    Returns {round index: keyframe of death}, and the set of rounds where the bar could be read at all.
    """
    matches = []
    for n, r in enumerate(rounds):
        if matches and r[0] - matches[-1][-1][1][1] <= MENU_GAP:
            matches[-1].append((n, r))
        else:
            matches.append([(n, r)])
    deaths, known = {}, set()
    for match in matches:
        if len(match) < 3:
            continue
        frames = [i for _, (a, b) in match for i in range(a, b + 1)]
        filtered = {i: high_pass(strips[i]) for i in frames}
        whole = [i for i in frames if allies[i] >= 4]
        template = np.median(np.stack([filtered[i] for i in whole]), axis=0)
        scores = {i: similarity(filtered[i], template) for i in frames}
        if np.percentile([scores[i] for i in whole], 75) < ALIVE_MATCH:
            continue            # no steady ability bar here, for example in Deathmatch
        for n, (a, b) in match:
            known.add(n)
            team = settled(allies[a:b + 1])
            for i in range(a + 1, b):
                # Death is final within a round, so two low readings in a row are enough and a lone one is ignored.
                if team[i - a] < team[0] and scores[i] < ALIVE_MATCH and scores[i + 1] < ALIVE_MATCH:
                    deaths[n] = i
                    break
    return deaths, known


def drop_overlays(slots):
    """A webcam over a slot looks like a player who never dies, so that slot is ignored.

    Portraits pack towards the timer, so a real player's slot is empty whenever the slot nearer the timer is.
    """
    slots = slots.copy()
    for side in ((4, 3, 2, 1, 0), (5, 6, 7, 8, 9)):
        for inner, outer in zip(side, side[1:]):
            gaps = ~slots[:, inner]
            if gaps.mean() > .02 and slots[gaps, outer].mean() > STUCK:
                slots[:, outer] = False
    return slots


def steady(counts):
    """A one-keyframe blip is a flash or a smoke, and must not look like a new round or a massacre."""
    padded = np.concatenate(([counts[0]], counts, [counts[-1]]))
    return np.median(np.stack([padded[:-2], padded[1:-1], padded[2:]]), axis=0).astype(counts.dtype)


def read_game(times, slots, strips):
    """Turns keyframes into events. Returns None when this does not look like Valorant."""
    if times.size < 20:
        return None
    slots = drop_overlays(slots)
    allies = steady(slots[:, :5].sum(axis=1))
    enemies = steady(slots[:, 5:].sum(axis=1))
    rounds = [(a, trim_round(allies, enemies, a, b)) for a, b in split_rounds(allies, enemies)]
    if len(rounds) < 3:
        return None
    deaths, known = alive_track(rounds, allies, enemies, strips)
    events = []
    live = np.zeros(times.size, dtype=bool)
    for n, (a, b) in enumerate(rounds):
        live[a:b + 1] = True
        ally, enemy = settled(allies[a:b + 1]), settled(enemies[a:b + 1])
        lone_against = 0
        for i in range(1, ally.size):
            at = a + i
            t, before = float(times[at]), float(times[at - 1])
            if deaths.get(n) == at:
                events.append({"t": t, "from": before, "kind": "you_down", "round": n + 1})
            for _ in range(int(enemy[i - 1] - enemy[i])):
                events.append({"t": t, "from": before, "kind": "enemy_down", "round": n + 1})
            for _ in range(int(ally[i - 1] - ally[i])):
                events.append({"t": t, "from": before, "kind": "ally_down", "round": n + 1})
            if ally[i] == 1 and enemy[i] >= 2 and n in known and (n not in deaths or at < deaths[n]):
                lone_against = max(lone_against, int(enemy[i]))
        if lone_against and enemy[-1] == 0 and n not in deaths:
            events.append({"t": float(times[b]), "from": float(times[b]), "kind": "clutch", "round": n + 1,
                           "against": lone_against})
    return {"game": "Valorant", "events": events, "rounds": len(rounds), "live": live, "times": times}


def diagnose(times, slots):
    """What the reader saw, for the stream's report when no game was found."""
    if times.size < 20:
        return "Only %d keyframes could be read, too few to follow a match" % times.size
    slots = drop_overlays(slots)
    rounds = split_rounds(steady(slots[:, :5].sum(axis=1)), steady(slots[:, 5:].sum(axis=1)))
    seen = float(slots.any(axis=1).mean())
    if seen < .05:
        return "Valorant's top bar with the player portraits was not found in the game picture"
    return "The top bar was seen in %d%% of keyframes, but only %d rounds could be followed" % (seen * 100, len(rounds))


def is_live(game, t):
    """Was a round being played at time t? Lobbies, agent select and scoreboards are not."""
    i = int(np.searchsorted(game["times"], t))
    last = game["live"].size - 1
    return bool(game["live"][max(min(i, last), 0)] or game["live"][max(min(i - 1, last), 0)])


def _box(g, k):
    """Mean over a (2k)x(2k) box, edges repeated: a fast blur."""
    c = np.cumsum(np.pad(g, ((k, k), (0, 0)), mode="edge"), axis=0)
    g = (c[2 * k:] - c[:-2 * k]) / (2 * k)
    c = np.cumsum(np.pad(g, ((0, 0), (k, k)), mode="edge"), axis=1)
    return (c[:, 2 * k:] - c[:, :-2 * k]) / (2 * k)


_r = np.hypot(np.mgrid[:SKULL, :BANNER_W][1] - BANNER_W / 2 + .5, np.mgrid[:SKULL, :BANNER_W][0] - SKULL / 2 + .5)
INNER, OUTER = (_r > 10) & (_r < 70), _r >= 80
_ys, _xs = np.nonzero((_r[:, (BANNER_W // 2 - HALF):(BANNER_W // 2 + HALF)] > 10)
                      & (_r[:, (BANNER_W // 2 - HALF):(BANNER_W // 2 + HALF)] < 75))
SHIFTS = np.arange(-10, 11, 2)
# For every axis shift, the ring's pixels and their mirror images, so all shifts are compared in one step.
_COLS = BANNER_W // 2 - HALF + SHIFTS[:, None] + _xs[None, :]
_MIRROR = BANNER_W // 2 - HALF + SHIFTS[:, None] + (2 * HALF - 1 - _xs)[None, :]


def banner_score(frame):
    """(mirror symmetry, edge strength, inside/outside edges, straight lines) under the crosshair, frame grey (or RGB) SKULL x BANNER_W.

    Every kill banner is mirror-symmetric whatever the weapon skin (the default skull, an eye in blue rings, a
    pentagon crest, an X diamond...), and the game world behind it almost never is. The axis may sit a few pixels off
    centre. A banner also keeps inside its ring, while a symmetric doorway or an ability overlay runs past it.
    """
    g = frame.astype(np.float32)
    if g.ndim == 3:
        g = g.mean(axis=2)
    h = _box(g, 2) - _box(g, 10)
    edges = np.abs(h)
    inside = float(edges[INNER].mean() / max(edges[OUTER].mean(), .5))
    a, b = h[_ys[None, :], _COLS], h[_ys[None, :], _MIRROR]
    spread = a.std(axis=1)
    a = (a - a.mean(axis=1, keepdims=True)) / np.maximum(spread, 1e-3)[:, None]
    b = (b - b.mean(axis=1, keepdims=True)) / np.maximum(b.std(axis=1), 1e-3)[:, None]
    corr = np.where(spread >= 1, (a * b).mean(axis=1), -1.0)
    return float(corr.max()), float(spread[len(SHIFTS) // 2]), inside, straightness(h)


def straightness(h):
    """How much of the picture is long straight lines. Banners are round; the buy menu is a grid of tiles."""
    c = h[:, BANNER_W // 2 - HALF:BANNER_W // 2 + HALF]
    spread = max(float(c.std()), 1e-3)
    return max(float(np.abs(c.mean(axis=1)).max()), float(np.abs(c[10:-10].mean(axis=0)).max())) / spread


def is_banner(frame):
    sym, edges, inside, lines = banner_score(frame)
    return sym >= MIRROR and edges >= EDGES and inside >= CONTAINED and lines < STRAIGHT


def skull_runs(frames, fps=4):
    """Finds kill banners in crops around the crosshair. A banner holds for a second or two, never much longer."""
    if not len(frames):
        return []
    hits = [is_banner(f) for f in frames]
    runs, start = [], None
    for i, on in enumerate(hits + [False]):
        if on and start is None:
            start = i
        elif not on and start is not None:
            if 3 <= i - start <= LONGEST_BANNER * fps:
                runs.append(start / fps)
            start = None
    return runs


def own_kills(source, start, end, view="scale=1920:1080"):
    """Times of the streamer's own kills between two moments, read from the kill banner."""
    start = max(start, 0.0)
    graph = "fps=4,%s,crop=%d:%d:%d:%d,format=gray" % (view, BANNER_W, SKULL, 960 - BANNER_W // 2, 860 - SKULL // 2)
    cmd = [tool("ffmpeg"), "-v", "error", "-ss", "%.3f" % start, "-t", "%.3f" % (end - start), *input_args(source),
           "-an", "-vf", graph, "-f", "rawvideo", "-"]
    out = subprocess.run(cmd, capture_output=True, creationflags=HIDE).stdout
    size = SKULL * BANNER_W
    frames = np.frombuffer(out[:len(out) // size * size], np.uint8).reshape(-1, SKULL, BANNER_W)
    return [start + t for t in skull_runs(frames)]


CHUNK = 120             # seconds of banner crops read at once: 4 frames a second of a 3-hour stream would not fit


def banner_kills(source, spans, view="scale=1920:1080", on_progress=None):
    """The streamer's kills read from the kill banner alone, for streams whose top bar is out of the picture (a
    vertical stream with no webcam band crops the game to 9:16, but the banner sits in the middle and survives).

    spans: [(start, end)] to look at, usually around gunfire (teach.windows). Returns kill times.
    """
    pieces = [(a, min(a + CHUNK + 2, b)) for s, b in spans for a in np.arange(s, b, CHUNK)]
    total = sum(b - a for a, b in pieces) or 1.0
    found, done = [], 0.0
    for a, b in pieces:
        for t in own_kills(source, float(a), float(b), view):
            if not any(abs(t - u) < 1.5 for u in found):
                found.append(t)
        done += b - a
        if on_progress:
            on_progress(min(done / total, 1.0))
    return sorted(found)
