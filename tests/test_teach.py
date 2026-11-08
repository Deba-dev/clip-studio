"""Teach a kill, end to end on a synthetic game video: two marked kills find the rest, and nothing else."""
import shutil
import subprocess

import numpy as np
import pytest

from clipstudio import teach
from clipstudio.paths import tool

KILLS = [6.0, 22.0, 41.5, 63.0, 80.0, 107.0, 131.0]      # notices fill about a tenth of the video
FLASH = 52.0            # a full-screen flash: bright, but not a kill
OTHER = 95.0            # a different message box (zone closing, say) somewhere else
SIZE, FPS, SECONDS = (640, 360), 15, 140


def glyphs(rng, rows, cols, scale):
    """A block pattern standing in for text."""
    return np.kron(rng.random((rows, cols)) > .5, np.ones((scale, scale), dtype=bool))


def make_game(path):
    w, h = SIZE
    rng = np.random.default_rng(1)
    world = rng.random((h * 2, w * 2)).astype(np.float32)
    for _ in range(3):           # a smooth, textured world to scroll over, so every frame's background differs
        world = (world + np.roll(world, 1, 0) + np.roll(world, 1, 1) + np.roll(world, -1, 0)) / 4
    world = (world - world.min()) / (world.max() - world.min())
    fixed = glyphs(np.random.default_rng(2), 3, 22, 4)              # "YOU KNOCKED OUT"
    names = [glyphs(np.random.default_rng(10 + i), 3, 12, 4) for i in range(len(KILLS))]
    other = glyphs(np.random.default_rng(3), 3, 30, 4)
    proc = subprocess.Popen([tool("ffmpeg"), "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s",
                             "%dx%d" % SIZE, "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-preset", "ultrafast",
                             "-pix_fmt", "yuv420p", "-g", str(FPS * 2), str(path)], stdin=subprocess.PIPE)
    for i in range(SECONDS * FPS):
        t = i / FPS
        ox, oy = int(140 * np.sin(t / 3) + 150), int(90 * np.cos(t / 4) + 100)
        g = world[oy:oy + h, ox:ox + w] * 170 + 40
        frame = np.repeat(g[:, :, None], 3, axis=2)
        frame[330:345, 20:180] = (40, 200, 60)                         # a health bar that never changes
        for n, k in enumerate(KILLS):
            if k <= t < k + 2.0:
                y, x = 250, 200
                frame[y - 6:y + 18, x - 8:x + 248] *= .35                  # the notice's dark plate
                frame[y:y + 12, x:x + 88][fixed] = 255
                frame[y:y + 12, x + 100:x + 148][names[n]] = (255, 80, 80)  # the victim's name changes
        if FLASH <= t < FLASH + .5:
            frame[:] = np.minimum(frame + 150, 255)
        if OTHER <= t < OTHER + 2.0:
            frame[40:52, 60:180][other] = 255
        proc.stdin.write(np.clip(frame, 0, 255).astype(np.uint8).tobytes())
    proc.stdin.close()
    assert proc.wait() == 0


@pytest.fixture(scope="module")
def game(tmp_path_factory):
    if not shutil.which(tool("ffmpeg")):
        pytest.skip("needs FFmpeg")
    path = tmp_path_factory.mktemp("teach") / "game.mp4"
    make_game(path)
    return str(path)


def test_two_marked_kills_find_every_kill_and_nothing_else(game, tmp_path, monkeypatch):
    monkeypatch.setenv("CLIPSTUDIO_DATA", str(tmp_path))
    view = "scale=1920:1080"
    for t in (KILLS[0] + .3, KILLS[1] + .3):
        teach.add_example("bgmi", game, t, view)
    found = teach.examples("bgmi")
    pos, after, before, negatives = teach.gather(found, (game, view, SECONDS, [e["t"] for e in found]))
    model, message = teach.learn(pos, after, before, negatives, "bgmi")
    assert model is not None, message
    teach.save("bgmi", model)
    model = teach.load("bgmi")
    kills = teach.scan(game, view, model, [(0.0, float(SECONDS))])
    assert len(kills) == len(KILLS), kills
    assert all(abs(f - k) <= .6 for f, k in zip(kills, KILLS)), kills


def test_a_lesson_that_cannot_tell_kills_apart_says_so():
    flat = [np.full((teach.H, teach.W), 90, np.float32)]
    model, message = teach.learn(flat * 2, flat * 4, flat * 4, flat * 10)
    assert model is None and "mark" in message.lower()
    model, message = teach.learn(flat, flat * 2, flat * 2, flat * 10)
    assert model is None and "one more" in message


def test_hits_need_the_notice_to_hold_and_count_once():
    s = [0, .9, 0, 0, .9, .9, .9, .9, .8, .9, 0, 0, 0, 0, 0, 0, .9, .9]
    assert teach.hits(s, 10.0, .5) == [11.0, 14.0]


def test_scan_looks_around_gunfire_only():
    gun = np.zeros(300)
    gun[[50, 52, 200]] = .9
    assert teach.windows(gun, 300) == [(49.0, 57.0), (199.0, 205.0)]
    assert teach.windows(None, 300) == [(0.0, 300)]


def test_found_kills_join_the_list_without_touching_your_work(tmp_path):
    from clipstudio.db import Library
    lib = Library(str(tmp_path / "lib.db"))
    sid = lib.add_session("s", "v.mp4")
    base = {"peak": 0.0, "score": 3.0, "reasons": ["Loud"], "tags": ["hype"]}
    lib.replace_clips(sid, [dict(base, start=90.0, end=120.0, title="loud"),
                            dict(base, start=300.0, end=330.0, title="mine")])
    mine = [c for c in lib.clips(sid) if c["title"] == "mine"][0]
    lib.update_clip(mine["id"], state="kept")
    kill = {"peak": 110.0, "score": 9.0, "start": 95.0, "end": 115.0, "tags": ["kills"], "reasons": ["You got 2 kills"],
            "title": "Double kill", "events": [{"t": 105.0, "kind": "kill"}], "edit": {"cuts": [[100.0, 102.0]]}}
    kept_kill = dict(kill, start=305.0, end=320.0, peak=310.0)
    assert lib.add_kill_clips(sid, [kill, kept_kill]) == 1
    titles = {c["title"]: c for c in lib.clips(sid)}
    assert set(titles) == {"Double kill", "mine"}                  # the loud clip gave way; your kept clip did not
    assert titles["Double kill"]["edit"] == {"cuts": [[100.0, 102.0]]} and "hype" in titles["Double kill"]["tags"]
    assert titles["Double kill"]["captioned"] == "0"
    assert lib.add_kill_clips(sid, [kill]) == 0                    # finding it twice adds nothing
    lib.close()
