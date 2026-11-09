"""Event-anchored punch-in zooms, hook text and transcript search."""
import json
import re
import shutil
import subprocess

import pytest

from clipstudio import captions, edit, effects, insights, render
from clipstudio.paths import tool


def clip(start=100.0, end=140.0, events=(), words=(), layout="blur", **e):
    return {"start": start, "end": end, "edit": e, "words": list(words), "layout": layout, "events": list(events),
            "title": "t", "tags": []}


def filters_in(graph):
    return set(re.findall(r"(?:^|[,;\]])([a-z]+)(?==|,|\[)", graph))


# ---- zoom windows
def test_a_kill_zooms_the_game_around_the_shot():
    c = clip(events=[{"t": 110.0, "kind": "kill"}])
    assert effects.zoom_windows(c, "blur") == {"game": [(109.7, 110.8)]}
    assert effects.output_windows(c, "blur") == {"game": [(9.7, 10.8)]}


def test_a_laugh_zooms_the_webcam_only_when_one_is_shown():
    c = clip(events=[{"t": 120.0, "kind": "laugh"}])
    assert list(effects.zoom_windows(c, "stack")) == ["cam"]
    assert effects.zoom_windows(c, "blur") == {}


def test_a_spray_of_kills_is_one_zoom_not_a_flicker():
    c = clip(events=[{"t": 110.0, "kind": "kill"}, {"t": 110.9, "kind": "kill"}, {"t": 111.5, "kind": "kill"}])
    assert effects.zoom_windows(c, "blur") == {"game": [(109.7, 112.3)]}


def test_zooms_follow_cuts_and_never_leave_the_clip():
    c = clip(events=[{"t": 100.1, "kind": "kill"}, {"t": 120.0, "kind": "kill"}, {"t": 139.9, "kind": "death"}],
             cuts=[[119.0, 125.0]])
    out = effects.output_windows(c, "blur")["game"]
    assert out[0] == (0.0, 0.9)                     # clamped to the clip start
    assert all(b <= edit.length(c) + 1e-6 for _, b in out)
    assert not any(a < 19.0 < b for a, b in out)    # the kill inside the cut is gone with it


def test_zoom_can_be_turned_off():
    assert effects.zoom_windows(clip(events=[{"t": 110.0, "kind": "kill"}], zoom=False), "blur") == {}


def test_preview_and_export_agree_on_when_the_zoom_is_on():
    c = clip(events=[{"t": 110.0, "kind": "kill"}])
    windows = effects.zoom_windows(c, "blur")
    assert effects.zoom_at(windows, 110.0) == {"game": effects.ZOOM["game"]}
    assert effects.zoom_at(windows, 105.0) == {}


@pytest.mark.parametrize("layout,cam", [("stack", (0, 0, 320, 180)), ("blur", None), ("crop", None)])
def test_zoom_graph_uses_released_filters(layout, cam):
    c = clip(layout=layout, events=[{"t": 110.0, "kind": "kill"}, {"t": 120.0, "kind": "laugh"}])
    cmd = render.build_command("v.mp4", c, (1920, 1080), "o.mp4", facecam=cam, encoder=("libx264", []))
    graph = cmd[cmd.index("-filter_complex") + 1]
    assert filters_in(graph) <= set(render.FILTERS)
    assert "between(t,9.700,10.800)" in graph
    assert ("[zc3]" in graph) == (layout == "stack")


def test_no_events_leaves_the_graph_as_it_was():
    plain = render.layout_filter("stack", (1920, 1080), (0, 0, 320, 180))
    assert "overlay" not in plain and "[craw]scale=" in plain


# ---- hook
def test_hook_wraps_into_short_lines_and_is_capped():
    assert effects.hook_lines("Bhai ye kya tha one tap no mercy") == ["Bhai ye kya tha", "one tap no mercy"]
    lines = effects.hook_lines("word " * 40)
    assert len(lines) <= effects.HOOK_LINES and all(len(l) <= effects.HOOK_CHARS for l in lines)
    assert effects.hook_lines("   ") == []


def test_hook_is_written_at_the_top_for_the_first_seconds():
    ass = captions.build_ass([], 0, 20, hook="One tap. No mercy")
    line = [l for l in ass.splitlines() if ",Hook," in l and l.startswith("Dialogue")][0]
    assert line.startswith("Dialogue: 1,0:00:00.00,0:00:02.60,Hook")
    assert "Style: Hook," in ass and ",8,60,60," in ass         # alignment 8 is top centre
    assert "Dialogue" not in captions.build_ass([], 0, 20).split("[Events]")[1].split("\n", 2)[2]


def test_hook_in_hindi_script_gets_a_font_that_can_draw_it():
    assert "Style: Hook,Nirmala UI" in captions.build_ass([], 0, 5, hook="भाई ये क्या था")


# ---- search
def test_search_finds_hinglish_in_either_script():
    words = [{"w": "अरे", "s": 101.0, "e": 101.3}, {"w": "भाई", "s": 101.4, "e": 101.8},
             {"w": "clutch!", "s": 105.0, "e": 105.5}, {"w": "kar", "s": 106.0, "e": 106.2}]
    c = clip(words=words)
    assert insights.find(c, "bhai") == 101.4
    assert insights.find(c, "BHAI") == 101.4
    assert insights.find(c, "भाई") == 101.4
    assert insights.find(c, "clutch kar") == 105.0
    assert insights.find(c, "ace") is None
    assert insights.find(c, "") is None


def test_search_matches_the_clip_name_too():
    c = clip()
    c["title"] = "Triple kill"
    assert insights.find(c, "triple") == c["start"]


# ---- a real export with every effect
@pytest.mark.skipif(not shutil.which(tool("ffmpeg")), reason="needs FFmpeg")
@pytest.mark.parametrize("layout,cam", [("stack", (0, 0, 200, 120)), ("blur", None), ("crop", None)])
def test_real_export_with_zooms_and_a_hook(tmp_path, layout, cam):
    video = tmp_path / "v.mp4"
    subprocess.run([tool("ffmpeg"), "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=s=640x360:r=30:d=6",
                    "-f", "lavfi", "-i", "sine=f=330:d=6", "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac",
                    str(video)], check=True)
    c = clip(0.5, 5.5, layout=layout, events=[{"t": 2.0, "kind": "kill"}, {"t": 4.0, "kind": "laugh"}],
             hook="One tap. No mercy", cuts=[[3.0, 3.4]])
    path = render.export_clip(str(video), c, (640, 360), str(tmp_path), facecam=cam, out=(720, 1280))
    info = json.loads(subprocess.run([tool("ffprobe"), "-v", "error", "-print_format", "json", "-show_streams", path],
                                     capture_output=True).stdout)
    v = [s for s in info["streams"] if s["codec_type"] == "video"][0]
    assert (v["width"], v["height"]) == (720, 1280)
    assert float(v["duration"]) == pytest.approx(4.6, abs=.25)


# ---- kill tally
def test_tally_counts_each_kill_the_way_the_game_names_it():
    c = clip(events=[{"t": 105.0, "kind": "kill"}, {"t": 108.0, "kind": "kill"}, {"t": 130.0, "kind": "death"}])
    assert effects.tally(c, "valorant") == [(5.0, "KILL"), (8.0, "DOUBLE KILL")]
    assert effects.tally(c, "cs2")[1] == (8.0, "2K")
    assert effects.tally(clip(events=c["events"], tally=False)) == []


def test_tally_follows_cuts_and_shows_until_the_next_kill():
    c = clip(events=[{"t": 105.0, "kind": "kill"}, {"t": 125.0, "kind": "kill"}], cuts=[[110.0, 120.0]])
    marks = effects.tally(c)
    assert marks == [(5.0, "KILL"), (15.0, "DOUBLE KILL")]
    assert effects.tally_at(marks, 5.5) == ("KILL", .5) and effects.tally_at(marks, 7.0) is None
    ass = captions.build_ass([], 0, 30, tally=marks)
    assert ass.count(",Tally,") == 2 and "Style: Tally," in ass and r"{\fad(" in ass and "\x0c" not in ass


@pytest.mark.skipif(not shutil.which(tool("ffmpeg")), reason="needs FFmpeg")
def test_real_export_with_a_kill_tally(tmp_path):
    video = tmp_path / "v.mp4"
    subprocess.run([tool("ffmpeg"), "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=s=640x360:r=30:d=4",
                    "-f", "lavfi", "-i", "sine=d=4", "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac",
                    str(video)], check=True)
    c = clip(0.0, 4.0, events=[{"t": 1.0, "kind": "kill"}, {"t": 2.0, "kind": "kill"}])
    path = render.export_clip(str(video), c, (640, 360), str(tmp_path), out=(720, 1280), game="BGMI")
    assert path.endswith(".mp4")


def test_podcast_clips_are_not_tagged_as_gaming():
    clip = {"tags": ["funny", "kills"], "start": 0}
    tags = insights.hashtags(clip, "Podcast", "hi")
    assert "#gaming" not in tags and "#headshot" not in tags and "#podcast" in tags
    assert "#headshot" in insights.hashtags(clip, "Valorant", "hi")
    assert "#headshot" not in insights.hashtags(clip, "EA Sports FC", "en")
