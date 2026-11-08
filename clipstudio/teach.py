"""Teach a kill: learns what your own kill notice looks like from a few examples, for any game.

Every shooter tells you when you got a kill: a skull banner, "YOU KNOCKED OUT", "ELIMINATED", a medal, a highlighted
kill feed line. The notice looks the same every time, while the game behind it never does. So a few marked frames
are enough to find every other kill:

1. For each example the learner reads the frame (the notice), the same frame a quarter and half a second later (the
   notice is still there, the picture behind it has moved), and the scene a moment before (no notice yet).
2. It tries boxes across the whole screen, starting with the game's usual notice spots, and keeps the box whose edge
   pattern matches the examples and matches nothing else, including random moments of the same stream.
3. Scanning then reads only that box, four times a second, around every burst of gunfire, and a match that holds for
   half a second is a kill.

The lesson is saved per game and reused on every later stream, and each new example makes it better. Edge patterns
are used instead of colours, so a different map, a darker scene or a teammate's skin does not matter.
"""
import json
import os
import subprocess

import numpy as np

from .games import GAMES
from .media import HIDE, input_args
from .paths import data_dir, tool

W, H = 640, 360         # the game picture size the learner works at
FPS = 4
AFTER = (.25, .5)       # the notice is still up; the scene behind it has moved
BEFORE = (-1.5, -2.5)   # the same scene, before the kill
NEGATIVES = 40
HOLD = 2                # samples in a row: half a second at 4 per second
GAP = 1.2               # a notice that drops out for less than this is the same notice
SIZES = ((150, 50), (210, 70), (280, 90), (130, 130), (360, 120))
STRIDE = (24, 18)
KEEP = .3               # the template's strongest edges that take part in matching
MIN_SPLIT = .12         # examples must beat everything else by at least this much
MIN_EXAMPLES = 2


def folder():
    path = os.path.join(data_dir(), "games")
    os.makedirs(path, exist_ok=True)
    return path


def examples_path(game):
    return os.path.join(folder(), game + ".json")


def model_path(game):
    return os.path.join(folder(), game + ".npz")


def examples(game):
    try:
        with open(examples_path(game), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return []


def add_example(game, source, t, view):
    """Notes one kill. The frames are read later, in the background job, never on the app's thread."""
    found = examples(game)
    if any(e["source"] == source and abs(e["t"] - t) < 1.0 for e in found):
        return len(found)
    found.append({"source": source, "t": round(float(t), 3), "view": view})
    tmp = examples_path(game) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(found, f, indent=1)
    os.replace(tmp, examples_path(game))
    return len(found)


def forget(game):
    for path in (examples_path(game), model_path(game), os.path.join(folder(), game + "-frames.npz")):
        if os.path.exists(path):
            os.remove(path)


def grab(source, t, view):
    """One grey game picture at t, W x H, as float32. None when the moment cannot be read."""
    cmd = [tool("ffmpeg"), "-v", "error", "-ss", "%.3f" % max(t, 0), *input_args(source), "-frames:v", "1",
           "-vf", "%s,scale=%d:%d,format=gray" % (view, W, H), "-f", "rawvideo", "-"]
    out = subprocess.run(cmd, capture_output=True, creationflags=HIDE).stdout
    return np.frombuffer(out, np.uint8).reshape(H, W).astype(np.float32) if len(out) == W * H else None


def edges(img):
    """Detail without brightness: the picture minus a 7-pixel box blur, so lighting and colour drop out."""
    img = np.asarray(img, dtype=np.float32)
    k = 7
    pad = np.pad(img, k // 2, mode="edge")
    c = np.cumsum(np.cumsum(pad, axis=0), axis=1)
    c = np.pad(c, ((1, 0), (1, 0)))
    blur = (c[k:, k:] - c[:-k, k:] - c[k:, :-k] + c[:-k, :-k]) / (k * k)
    return img - blur


def unit(x):
    x = x - x.mean()
    return x / max(float(x.std()), 1e-3)


def score(crop, template, mask):
    """How much a box looks like the notice: correlation over the template's strongest edges, -1 to 1."""
    a, b = crop[mask], template[mask]
    a = a - a.mean()
    b = b - b.mean()
    return float((a * b).sum() / max(np.sqrt((a * a).sum() * (b * b).sum()), 1e-6))


def candidates(game):
    """Boxes in learner pixels: the game's usual notice spots first, then a grid over the whole screen."""
    out = []
    for x, y, w, h in GAMES.get(game, {}).get("notice", []):
        k = W / 1920
        out.append((int(x * k), int(y * k), max(int(w * k), 40), max(int(h * k), 30)))
    for w, h in SIZES:
        for y in range(0, H - h + 1, STRIDE[1]):
            for x in range(0, W - w + 1, STRIDE[0]):
                out.append((x, y, w, h))
    return out


def gather(found, negatives_from, report=lambda v: None):
    """Reads every frame the lesson needs: per example the notice, after it and before it; and random moments."""
    pos, after, before = [], [], []
    total = len(found) * (1 + len(AFTER) + len(BEFORE)) + NEGATIVES
    done = 0
    for e in found:
        frames = [grab(e["source"], e["t"] + d, e["view"]) for d in (0, *AFTER, *BEFORE)]
        done += len(frames)
        report(done / total)
        if any(f is None for f in frames):
            continue            # the recording is gone or moved: this example cannot teach any more
        pos.append(frames[0])
        after.extend(frames[1:1 + len(AFTER)])
        before.extend(frames[1 + len(AFTER):])
    source, view, duration, avoid = negatives_from
    negatives = []
    rng = np.random.default_rng(7)
    for t in rng.uniform(duration * .05, duration * .95, NEGATIVES) if duration > 0 else []:
        if any(abs(t - a) < 4 for a in avoid):
            continue
        f = grab(source, t, view)
        done += 1
        report(done / total)
        if f is not None:
            negatives.append(f)
    return pos, after, before, negatives


def learn(pos, after, before, negatives, game=""):
    """The box and edge pattern that pick out the notice. Returns (model, message); model is None on failure."""
    if not pos:
        return None, "None of the marked kills could be read. Mark a kill again on a stream you still have."
    if len(pos) < MIN_EXAMPLES:
        return None, ("Mark one more kill. Two kills show which part of the notice stays the same, like the words "
                      "around the enemy's name.")
    sets = {name: [edges(f) for f in frames] for name, frames in
            (("pos", pos), ("after", after), ("before", before), ("neg", negatives))}
    best = None
    for box in candidates(game):
        x, y, w, h = box
        cut = {k: [f[y:y + h, x:x + w] for f in v] for k, v in sets.items()}
        template = np.mean([unit(c) for c in cut["pos"]], axis=0)
        strength = np.abs(template)
        if float(strength.std()) < .05:
            continue
        mask = strength >= np.quantile(strength, 1 - KEEP)
        if len(cut["pos"]) >= 2:        # each example against the others: the honest test of a pattern
            mine = [score(c, np.mean([unit(o) for j, o in enumerate(cut["pos"]) if j != i], axis=0), mask)
                    for i, c in enumerate(cut["pos"])]
        else:
            mine = []
        mine += [score(c, template, mask) for c in cut["after"]]
        if not mine:
            continue
        # A random moment can hold a real kill too, so random moments speak through their 75th percentile: kill
        # notices fill far less than a quarter of any stream. The moments just before each kill are the sure ones.
        others = [score(c, template, mask) for c in cut["neg"]]
        crowd = float(np.percentile(others, 75)) if others else 0.0
        hard = sorted(score(c, template, mask) for c in cut["before"])
        sure = hard[-2] if len(hard) >= 4 else (hard[-1] if hard else 0.0)     # a multi-kill can show one early
        top_other = max(crowd, sure)
        low_mine = float(np.percentile(mine, 20))
        split = low_mine - top_other
        if best is None or split > best[0]:
            best = (split, box, template, mask, low_mine, top_other)
    if best is None or best[0] < MIN_SPLIT:
        return None, ("These kills do not look alike enough to find others. Pause where the kill notice is clearly "
                      "on screen and mark one or two more.")
    split, box, template, mask, low_mine, top_other = best
    model = {"box": np.array(box), "template": template.astype(np.float32), "mask": mask,
             "threshold": np.float32(top_other + split * .45), "split": np.float32(split),
             "examples": np.int32(len(pos))}
    return model, "Learned from %d kill%s" % (len(pos), "s" if len(pos) > 1 else "")


def save(game, model):
    np.savez_compressed(model_path(game), **model)


def load(game):
    try:
        with np.load(model_path(game)) as z:
            return {k: z[k] for k in z.files}
    except (OSError, ValueError, KeyError):
        return None


def windows(gun, duration, lead=1.0, tail=5.0, join=15.0):
    """Where to look: around every burst of gunfire, since a kill follows a shot. The whole stream without it."""
    if gun is None or not np.any(np.asarray(gun) > .2):
        return [(0.0, duration)] if duration > 0 else []
    out = []
    for t in np.flatnonzero(np.asarray(gun, dtype=np.float32) > .2):
        a, b = max(t - lead, 0.0), min(t + tail, duration)
        if out and a - out[-1][1] <= join:
            out[-1][1] = max(out[-1][1], b)
        else:
            out.append([a, b])
    return [tuple(w) for w in out]


MARGIN = 4              # pixels read around the box, so its edges come out exactly as they did when learning


def read_box(source, view, start, length, box):
    """The model's box with a margin, FPS times a second, from start for length seconds. Returns (frames, inner)."""
    x, y, w, h = (int(v) for v in box)
    x0, y0 = max(x - MARGIN, 0), max(y - MARGIN, 0)
    x1, y1 = min(x + w + MARGIN, W), min(y + h + MARGIN, H)
    cw, ch = x1 - x0, y1 - y0
    graph = "fps=%d,%s,scale=%d:%d,crop=%d:%d:%d:%d,format=gray" % (FPS, view, W, H, cw, ch, x0, y0)
    cmd = [tool("ffmpeg"), "-v", "error", "-ss", "%.3f" % start, "-t", "%.3f" % length, *input_args(source), "-an",
           "-vf", graph, "-f", "rawvideo", "-"]
    out = subprocess.run(cmd, capture_output=True, creationflags=HIDE).stdout
    size = cw * ch
    frames = np.frombuffer(out[:len(out) // size * size], np.uint8).reshape(-1, ch, cw).astype(np.float32)
    return frames, (slice(y - y0, y - y0 + h), slice(x - x0, x - x0 + w))


def hits(scores, start, threshold):
    """Kill times from a run of scores: a match that holds HOLD samples, one kill per notice."""
    out, run, last_end = [], None, -1e9
    for i, s in enumerate(list(scores) + [-1.0]):
        t = start + i / FPS
        if s >= threshold:
            if run is None:
                run = t
        elif run is not None:
            if t - run >= HOLD / FPS - 1e-6:     # a flicker shorter than that is neither a kill nor a notice
                if run - last_end >= GAP:
                    out.append(round(run, 2))
                last_end = t
            run = None
    return out


def scan(source, view, model, spans, report=lambda v: None):
    """Times of your kills in the given spans, read with a learned model."""
    found = []
    total = sum(b - a for a, b in spans) or 1.0
    done = 0.0
    for a, b in spans:
        frames, inner = read_box(source, view, a, b - a, model["box"])
        scores = [score(edges(f)[inner], model["template"], model["mask"]) for f in frames]
        found += hits(scores, a, float(model["threshold"]))
        done += b - a
        report(done / total)
    return found
