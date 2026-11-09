"""Finding the game inside a vertical stream, laid out like the real one: webcam on top, cropped game below."""
import shutil
import subprocess

import numpy as np
import pytest

from clipstudio import games, hud, view
from clipstudio.paths import tool

ALIVE = (4, 3)                  # four allies and three enemies on the top bar
CAM, GAP = 600, 40              # webcam band height, black gap under it
TOP = CAM + GAP                 # the game band starts here and is 1080 x 1080: Valorant's centre, full height


def game_frame(rng):
    """A 1920x1080 game picture with portraits on the top bar where Valorant puts them."""
    g = np.full((1080, 1920, 3), 70, np.uint8)
    g[200:] = rng.integers(40, 120, (880, 1920, 3), dtype=np.uint8)        # the world
    for cx in hud.ALLIES[5 - ALIVE[0]:] + hud.ENEMIES[:ALIVE[1]]:
        g[28:72, cx - 20:cx + 20] = rng.integers(0, 255, (44, 40, 3), dtype=np.uint8)
    return g


@pytest.fixture(scope="module")
def vertical(tmp_path_factory):
    if not shutil.which(tool("ffmpeg")):
        pytest.skip("needs FFmpeg")
    path = tmp_path_factory.mktemp("view") / "vertical.mp4"
    rng = np.random.default_rng(4)
    proc = subprocess.Popen([tool("ffmpeg"), "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", "1080x1920",
                             "-r", "2", "-i", "-", "-c:v", "libx264", "-preset", "ultrafast", "-g", "1",
                             "-pix_fmt", "yuv420p", str(path)], stdin=subprocess.PIPE)
    for _ in range(40):
        frame = np.zeros((1920, 1080, 3), np.uint8)
        frame[:CAM] = rng.integers(60, 200, (CAM, 1080, 3), dtype=np.uint8)       # the webcam
        frame[TOP:TOP + 1080] = game_frame(rng)[:, 420:1500]                       # the game, sides cut off
        proc.stdin.write(frame.tobytes())
    proc.stdin.close()
    assert proc.wait() == 0
    return str(path)


def test_the_game_is_found_below_the_webcam(vertical):
    area, layout = view.find_game_area(vertical, (1080, 1920), 20.0)
    assert layout == "vertical"
    x, y, w, h = area
    assert abs(x) <= 12 and abs(y - TOP) <= 12 and abs(w - 1080) <= 12 and abs(h - 1080) <= 12


def test_the_hud_reads_through_the_vertical_layout(vertical):
    area, _ = view.find_game_area(vertical, (1080, 1920), 20.0)
    times, slots, _ = hud.scan(vertical, 20.0, view=view.game_filter(area, (1080, 1920)))
    expected = [False] * (5 - ALIVE[0]) + [True] * (ALIVE[0] + ALIVE[1]) + [False] * (5 - ALIVE[1])
    assert len(times) >= 30
    assert (slots == expected).all(axis=1).mean() > .9


def test_a_plain_game_recording_is_left_alone():
    assert view.game_filter((0, 0, 1920, 1080), (1920, 1080)) == "scale=1920:1080"
    assert view.game_filter((0, 640, 1080, 1080), (1080, 1920)).endswith("pad=1920:1080:(ow-iw)/2:0")


def test_separator_rows_split_bands_largest_first():
    frames = np.zeros((6, 100, 50), np.uint8)
    frames[:, 0:30] = 120           # webcam
    frames[:, 40:90] = 90           # game
    assert view.bands(frames)[0] == (0, 40, 50, 50)


def test_stream_titles_name_their_game():
    assert games.guess("VALORANT LIVE | Hindi ranked") == "valorant"
    assert games.guess("BGMI rush gameplay 🔥") == "bgmi"
    assert games.guess("PUBG Mobile scrims") == "bgmi"
    assert games.guess("PUBG PC chicken dinner") == "pubg"
    assert games.guess("COD Mobile ranked") == "codm"
    assert games.guess("Just chatting") == "justchatting"
    assert games.guess("chill stream with bhai") == ""
    assert games.guess("GTA San Andreas full story") == "gtasa"
    assert games.guess("GTA 5 RP live") == "gta5"
    assert games.guess("Counter-Strike 1.6 nostalgia") == "cs16"
    assert games.guess("Phasmophobia horror game with friends") == "phasmo"
    assert games.guess("Valorant podcast with the squad") == "valorant"
    assert games.guess("Ep 12 | podcast with bhai") == "podcast"
    assert games.guess("FC 26 ultimate team") == "eafc"


def test_every_game_names_its_multi_kills():
    assert games.multi_name("valorant", 5) == "Ace"
    assert games.multi_name("cs2", 3) == "3K"
    assert games.multi_name("apex", 3) == "Squad wipe"
    assert games.multi_name("bgmi", 7) == "7 kills"
    assert games.multi_name("eafc", 3) == "Hat-trick"
    assert games.multi_name("tekken", 2) == "2 K.O.s"


def test_every_kind_of_stream_is_listed_once():
    names = [g["name"] for g in games.GAMES.values()]
    assert len(names) == len(set(names)) and len(names) > 100
    assert all(g["kind"] in games.KINDS for g in games.GAMES.values())
    listed = [k for _, entries in games.grouped() for k, _ in entries]
    assert sorted(listed) == sorted(games.GAMES)
    assert games.taught("cs2") and games.taught("eafc") and not games.taught("valorant")
    assert not games.taught("gta5") and not games.taught("podcast")
    assert games.is_game("minecraft") and not games.is_game("podcast")
    assert all(games.key_of(g["name"]) == k for k, g in games.GAMES.items())


def test_streams_without_a_notice_say_where_clips_come_from():
    assert "voice" in games.no_notice("podcast")
    assert games.describe({"reader": "none", "why": games.no_notice("gta5")}).startswith("GTA V has no kill notice")
    assert "goals" in games.describe({"reader": "taught", "game": "EA Sports FC", "kills": 3})


def test_the_report_says_why_no_kills_were_read():
    assert "vertical layout" in games.describe({"reader": "valorant", "rounds": 12, "kills": 9, "deaths": 7,
                                                "clutches": 1, "layout": "vertical"})
    assert games.describe({"reader": "", "why": "Valorant's top bar was not found"}).startswith("No kills read.")
    assert games.describe({}) == ""
