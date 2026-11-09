"""Where the game is inside a recording.

Plenty of streams are not a plain 16:9 game picture: a vertical stream stacks the webcam over a cropped game, a
"just chatting" layout shrinks the game into a box, and some recordings carry black bars. Readers of the game's HUD
need the game picture itself, so this finds it once per stream and turns it into the 1920x1080 picture the readers
expect.

The finder looks for black separator rows and columns that stay black through the whole stream, splits the frame
into the bands between them, and takes the largest band as the game. A game shown at full height with its sides cut
off (the usual vertical-stream crop) is put back in the middle of a 1920x1080 frame, so HUD positions still line up.
"""
import subprocess

import numpy as np

from .media import HIDE, input_args
from .paths import tool

PROBE_W = 192           # width of the small frames the finder reads
SAMPLES = 14
BLACK = 16              # mean brightness under this is a separator
STEADY = .8             # share of samples in which a row must be black to count as a separator
MIN_BAND = .12          # a band shorter than this share of the frame is a border, not a picture
WIDE = 16 / 9


def sample_frames(source, duration, count=SAMPLES, width=PROBE_W):
    """Small grey frames spread across the stream, skipping its first and last minutes of menus."""
    frames = []
    for t in np.linspace(duration * .06, duration * .94, count) if duration > 0 else [0.0]:
        cmd = [tool("ffmpeg"), "-v", "error", "-ss", "%.2f" % t, *input_args(source), "-frames:v", "1",
               "-vf", "scale=%d:-2,format=gray" % width, "-f", "rawvideo", "-"]
        out = subprocess.run(cmd, capture_output=True, creationflags=HIDE).stdout
        if out:
            frames.append(np.frombuffer(out, np.uint8))
    sizes = {f.size for f in frames}
    if not frames or len(sizes) != 1 or frames[0].size % width:
        return None
    return np.stack(frames).reshape(len(frames), -1, width)


def runs(keep, minimum):
    """(start, end) runs of True at least minimum long."""
    out, start = [], None
    for i, on in enumerate(list(keep) + [False]):
        if on and start is None:
            start = i
        elif not on and start is not None:
            if i - start >= minimum:
                out.append((start, i))
            start = None
    return out


def bands(frames):
    """Picture bands (x, y, w, h) in probe pixels, largest first."""
    n, h, w = frames.shape
    dark_rows = (frames.mean(axis=2) < BLACK).mean(axis=0) >= STEADY
    out = []
    for y0, y1 in runs(~dark_rows, max(int(h * MIN_BAND), 2)):
        part = frames[:, y0:y1]
        dark_cols = (part.mean(axis=1) < BLACK).mean(axis=0) >= STEADY
        cols = runs(~dark_cols, max(int(w * MIN_BAND), 2))
        if cols:
            x0, x1 = max(cols, key=lambda c: c[1] - c[0])
            out.append((x0, y0, x1 - x0, y1 - y0))
    return sorted(out, key=lambda b: b[2] * b[3], reverse=True)


def find_game_area(source, size, duration):
    """(x, y, w, h) of the game picture in source pixels, and a word for the layout: full, vertical or boxed."""
    width, height = size
    whole = (0, 0, width, height)
    if not width or not height:
        return whole, "full"
    frames = sample_frames(source, duration)
    found = bands(frames) if frames is not None else []
    if not found:
        return whole, "full"
    k = width / PROBE_W
    x, y, w, h = found[0]
    area = tuple(int(round(v * k / 2)) * 2 for v in (x, y, w, h))
    area = (area[0], area[1], min(area[2], width - area[0]), min(area[3], height - area[1]))
    if area[2] * area[3] >= .9 * width * height:
        return whole, "full"
    return area, "vertical" if height > width else "boxed"


def game_filter(area, size):
    """FFmpeg filter that turns the recording into the 1920x1080 game picture the HUD readers measure."""
    width, height = size
    if not area or tuple(area) == (0, 0, width, height):
        if abs(width / max(height, 1) - WIDE) <= .02:
            return "scale=1920:1080"
        area = (0, 0, width, height)
    x, y, w, h = area
    crop = "crop=%d:%d:%d:%d," % (w, h, x, y)
    ratio = w / max(h, 1)
    if ratio < WIDE - .02:      # full height, sides cut off: put it back in the middle
        return crop + "scale=-2:1080,pad=1920:1080:(ow-iw)/2:0"
    if ratio > WIDE + .02:      # wider than 16:9: full width, centred top to bottom
        return crop + "scale=1920:-2,pad=1920:1080:0:(oh-ih)/2"
    return crop + "scale=1920:1080"


def stride(area, size):
    """How many times the game picture is enlarged on its way to 1920x1080, rounded: 1 for 1080p and up, 3 for the
    game square of a 360x640 phone download. The HUD readers compare pixels this far apart."""
    width, height = size
    x, y, w, h = area if area else (0, 0, width, height)
    if not w or not h:
        return 1
    grow = 1080 / h if w / h < WIDE - .02 else 1920 / w if w / h > WIDE + .02 else 1080 / h
    return max(int(grow + .5), 1)


def parse(text):
    try:
        values = [int(v) for v in (text or "").split(",")]
    except ValueError:
        return None
    return tuple(values) if len(values) == 4 and values[2] > 0 and values[3] > 0 else None
