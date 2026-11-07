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
STUCK = 0.8                         # how often a slot may be filled beside an empty one before it counts as an overlay


def _detail(patch):
    g = patch.astype(np.float32).mean(axis=2)
    return float(np.abs(g[1:-1, 1:-1] * 4 - g[:-2, 1:-1] - g[2:, 1:-1] - g[1:-1, :-2] - g[1:-1, 2:]).mean())


def read_slots(strip):
    """Which of the ten portrait slots hold a player in one keyframe. strip is the top bar, RGB."""
    out = []
    for cx in ALLIES + ENEMIES:
        x = cx - LEFT
        out.append(x + 20 <= strip.shape[1] and _detail(strip[28:72, x - 20:x + 20]) > PORTRAIT)
    return out


def high_pass(gray):
    g = gray.astype(np.float32)
    kernel = np.ones(9, dtype=np.float32) / 9
    return g - np.apply_along_axis(lambda row: np.convolve(row, kernel, "same"), 1, g)


def similarity(a, b):
    a = (a - a.mean()) / max(float(a.std()), 1e-3)
    b = (b - b.mean()) / max(float(b.std()), 1e-3)
    return float((a * b).mean())


def scan(source, duration=0.0, on_progress=None):
    """Returns (times, slots[n, 10], ability strips[n, h, w]) from the keyframes of a video."""
    graph = ("[0:v]scale=1920:1080,split[a][b];[a]crop=%d:%d:%d:0[t];[b]crop=%d:%d:%d:975[l];"
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
            slots.append(read_slots(frame[:TOP]))
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


def is_live(game, t):
    """Was a round being played at time t? Lobbies, agent select and scoreboards are not."""
    i = int(np.searchsorted(game["times"], t))
    last = game["live"].size - 1
    return bool(game["live"][max(min(i, last), 0)] or game["live"][max(min(i - 1, last), 0)])


def skull_runs(frames, fps=4):
    """Finds kill banners in crops around the crosshair. A banner holds for a second; a bright wall does not look like one."""
    if not len(frames):
        return []
    yy, xx = np.mgrid[:SKULL, :SKULL]
    radius = np.hypot(xx - SKULL / 2, yy - SKULL / 2)
    core, outer = radius < 30, radius >= 80
    hits = []
    for f in frames:
        white = f.min(axis=2) > 205
        hits.append(.15 < white[core].mean() < .75 and white[outer].mean() < .12)
    runs, start = [], None
    for i, on in enumerate(hits + [False]):
        if on and start is None:
            start = i
        elif not on and start is not None:
            if i - start >= 3:
                runs.append(start / fps)
            start = None
    return runs


def own_kills(source, start, end):
    """Times of the streamer's own kills between two moments, read from the skull banner."""
    start = max(start, 0.0)
    graph = "fps=4,scale=1920:1080,crop=%d:%d:%d:%d" % (SKULL, SKULL, 960 - SKULL // 2, 860 - SKULL // 2)
    cmd = [tool("ffmpeg"), "-v", "error", "-ss", "%.3f" % start, "-t", "%.3f" % (end - start), *input_args(source),
           "-an", "-vf", graph, "-pix_fmt", "rgb24", "-f", "rawvideo", "-"]
    out = subprocess.run(cmd, capture_output=True, creationflags=HIDE).stdout
    size = SKULL * SKULL * 3
    frames = np.frombuffer(out[:len(out) // size * size], np.uint8).reshape(-1, SKULL, SKULL, 3)
    return [start + t for t in skull_runs(frames)]
