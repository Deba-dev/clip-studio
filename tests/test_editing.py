"""The editor, the loudness chain, and the game moments. Numbers come from a real 2h39m Valorant stream."""
import json
import os
import re
import shutil
import subprocess

import numpy as np
import pytest

from clipstudio import captions, detect, edit, hud, render, sound, transcribe
from clipstudio.db import Library
from clipstudio.paths import tool
from clipstudio.ui.audio import CEILING, limit, stretch


def clip(start=100.0, end=140.0, **e):
    return {"start": start, "end": end, "edit": e, "words": [], "layout": "blur"}


# ---- cuts
def test_a_cut_removes_time_and_keeps_both_sides():
    c = clip(cuts=[[110, 120]])
    assert edit.keep_ranges(c) == [(100.0, 110), (120, 140.0)]
    assert edit.length(c) == 30


def test_overlapping_cuts_merge_and_edges_are_clamped():
    c = clip(cuts=[[90, 105], [130, 135], [133, 150]])
    assert edit.keep_ranges(c) == [(105, 130)]


def test_cutting_everything_is_refused():
    assert edit.add_cut(clip(), 100, 140) is None
    assert edit.add_cut(clip(), 110, 120)["cuts"] == [[110, 120]]


def test_playback_jumps_over_a_cut_and_ends_after_the_last_part():
    keep = edit.keep_ranges(clip(cuts=[[110, 120]]))
    assert edit.skip_cut(105, keep) == 105
    assert edit.skip_cut(115, keep) == 120
    assert edit.skip_cut(141, keep) is None


def test_caption_words_follow_the_cut():
    c = clip(cuts=[[110, 120]])
    c["words"] = [{"w": "before", "s": 105, "e": 106}, {"w": "gone", "s": 112, "e": 113}, {"w": "after", "s": 125, "e": 126}]
    out = edit.retime_words(c)
    assert [w["w"] for w in out] == ["before", "after"]
    assert out[0]["s"] == 5 and out[1]["s"] == 15      # 10 kept seconds, then 5 more


# ---- loudness
def test_quiet_clip_estimate_matches_the_measured_gap():
    assert edit.estimate_gain(np.full(200, -26.0), clip()) == pytest.approx(9.0)


def test_estimate_ignores_silence_and_respects_the_user():
    levels = np.full(200, -26.0)
    levels[105:135] = -90
    assert edit.estimate_gain(levels, clip()) == pytest.approx(9.0)
    assert edit.estimate_gain(levels, clip(gain_db=3)) == pytest.approx(12.0)
    assert edit.estimate_gain(levels, clip(auto_loud=False, gain_db=3)) == 3


def test_preview_limiter_never_clips_and_recovers():
    loud = np.array([.5, -.5], dtype=np.float32)
    out, held = limit(loud, 4.0, 1.0)
    assert np.abs(out).max() <= CEILING + 1e-6 and held < 1
    _, later = limit(np.array([.01], dtype=np.float32), 4.0, held)
    assert later > held


@pytest.mark.parametrize("rate,frames", [(1.0, 1000), (2.0, 500), (.5, 2000)])
def test_preview_sound_fits_the_playback_speed(rate, frames):
    assert stretch(np.zeros(2000, dtype=np.float32), rate).size == frames * 2


def filters_in(graph):
    return set(re.findall(r"(?:^|[,;\]])([a-z]+)(?==|,|\[)", graph))


@pytest.mark.parametrize("e", [{}, {"cuts": [[110, 120]]}, {"fade_in": 1, "fade_out": 2, "mute": [[105, 106]]},
                               {"auto_loud": False, "gain_db": 6}])
def test_every_filter_is_on_the_released_ffmpeg_list(e):
    cmd = render.build_command("v.mp4", clip(**e), (1920, 1080), "o.mp4", encoder=("libx264", []))
    graph = cmd[cmd.index("-filter_complex") + 1]
    assert filters_in(graph) <= set(render.FILTERS), filters_in(graph) - set(render.FILTERS)


def make_video(path, seconds=12):
    subprocess.run([tool("ffmpeg"), "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=s=640x360:r=30:d=%d" % seconds,
                    "-f", "lavfi", "-i", "sine=f=330:d=%d" % seconds, "-af", "volume=-34dB",
                    "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", str(path)], check=True)


def loudness_of(path):
    out = subprocess.run([tool("ffmpeg"), "-hide_banner", "-nostats", "-i", str(path), "-af",
                          "loudnorm=print_format=json", "-f", "null", "-"], capture_output=True, text=True, errors="replace")
    return float(json.loads(re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", out.stderr).group(0))["input_i"])


# The release build fetches FFmpeg after the tests run. Its smoke step then exports through the same chain.
@pytest.mark.skipif(not shutil.which(tool("ffmpeg")), reason="needs FFmpeg")
def test_real_export_of_a_quiet_clip_with_a_cut_reaches_phone_loudness(tmp_path):
    video = tmp_path / "v.mp4"
    make_video(video)
    c = clip(1.0, 11.0, cuts=[[4.0, 6.0]], fade_out=.5)
    c["words"] = [{"w": "hello", "s": 2.0, "e": 2.5}, {"w": "gone", "s": 5.0, "e": 5.5}]
    path = render.export_clip(str(video), c, (640, 360), str(tmp_path))
    info = json.loads(subprocess.run([tool("ffprobe"), "-v", "error", "-print_format", "json", "-show_format", path],
                                     capture_output=True).stdout)
    assert float(info["format"]["duration"]) == pytest.approx(8.0, abs=.25)      # 10 seconds minus the 2 cut
    assert loudness_of(path) == pytest.approx(-14, abs=1.5)
    assert loudness_of(video) < -30


def test_captions_use_the_chosen_colour():
    assert captions.highlight("FF0000") == "{\\c&H000000FF&}"    # ASS writes alpha, then blue first
    words = [{"w": "a", "s": 0, "e": 1}]
    assert "&H000000FF&" in captions.build_ass(words, 0, 2, color="FF0000")


# ---- split and undo in the library
def test_split_then_join_gives_back_the_same_clip(tmp_path):
    lib = Library(str(tmp_path / "l.db"))
    sid = lib.add_session("s", "v.mp4")
    lib.replace_clips(sid, [{"start": 0, "end": 40, "peak": 5, "score": 3, "reasons": ["r"], "tags": ["funny"]},
                            {"start": 100, "end": 120, "peak": 110, "score": 2, "reasons": ["r"]}])
    first, last = lib.clips(sid)
    other = lib.split_clip(first["id"], 15.0)
    assert [(c["start"], c["end"]) for c in lib.clips(sid)] == [(0, 15), (15, 40), (100, 120)]
    assert lib.clip(other)["tags"] == ["funny"]
    lib.join_clips(first["id"], other)
    assert [(c["start"], c["end"], c["rank"]) for c in lib.clips(sid)] == [(0, 40, 1), (100, 120, 2)]
    lib.close()


def test_edits_survive_a_round_trip(tmp_path):
    lib = Library(str(tmp_path / "l.db"))
    sid = lib.add_session("s", "v.mp4")
    lib.replace_clips(sid, [{"start": 0, "end": 40, "peak": 5, "score": 3, "reasons": ["r"]}])
    c = lib.clips(sid)[0]
    lib.update_clip(c["id"], edit={"cuts": [[1, 2]], "gain_db": 3})
    assert lib.clip(c["id"])["edit"] == {"cuts": [[1, 2]], "gain_db": 3}
    lib.close()


# ---- the HUD
def fake_keyframes(states):
    """states: (allies, enemies) per keyframe. Allies fill from the centre, as the game does."""
    slots = np.zeros((len(states), 10), dtype=bool)
    for i, (a, e) in enumerate(states):
        slots[i, 5 - a:5] = True
        slots[i, 5:5 + e] = True
    return np.arange(len(states)) * 5.0, slots


def strips_for(states, dead=()):
    rng = np.random.default_rng(1)
    alive, spectate = rng.integers(0, 255, (70, 640)), rng.integers(0, 255, (70, 640))
    return np.array([spectate if i in dead else alive for i in range(len(states))], dtype=np.uint8)


ROUND = [(5, 5)] * 6 + [(5, 4)] * 4 + [(4, 4)] * 4 + [(3, 2)] * 4 + [(3, 0)] * 3


def test_portraits_leaving_become_kills_and_team_deaths():
    states = (ROUND + [(0, 0)] * 2) * 3
    times, slots = fake_keyframes(states)
    game = hud.read_game(times, slots, strips_for(states))
    kinds = [e["kind"] for e in game["events"]]
    assert game["rounds"] == 3
    assert kinds.count("enemy_down") == 15 and kinds.count("ally_down") == 6 and "you_down" not in kinds


def test_a_smoke_over_the_bar_is_not_a_death():
    states = (([(5, 5)] * 6 + [(5, 2)] + [(5, 5)] * 10 + [(5, 4)] * 4 + [(0, 0)] * 2)) * 3
    times, slots = fake_keyframes(states)
    game = hud.read_game(times, slots, strips_for(states))
    assert sum(e["kind"] == "enemy_down" for e in game["events"]) == 3


def test_a_webcam_over_a_slot_is_not_an_immortal_player():
    states = (ROUND + [(0, 0)] * 8) * 3
    times, slots = fake_keyframes(states)
    slots[:, 9] = True
    game = hud.read_game(times, slots, strips_for(states))
    assert not hud.is_live(game, times[len(ROUND) + 4])


def test_ability_bar_changing_means_the_streamer_died():
    states = ROUND * 4
    dead = set(range(14, len(ROUND)))
    times, slots = fake_keyframes(states)
    game = hud.read_game(times, slots, strips_for(states, dead))
    assert [e for e in game["events"] if e["kind"] == "you_down"][0]["t"] == times[14]


def test_a_won_one_v_two_is_a_clutch():
    one = [(5, 5)] * 6 + [(1, 3)] * 5 + [(1, 2)] * 5 + [(1, 0)] * 5
    states = one * 4
    times, slots = fake_keyframes(states)
    game = hud.read_game(times, slots, strips_for(states))
    clutches = [e for e in game["events"] if e["kind"] == "clutch"]
    assert len(clutches) == 4 and clutches[0]["against"] == 3


def test_other_games_are_left_to_sound_and_speech():
    times, slots = fake_keyframes([(0, 0)] * 100)
    assert hud.read_game(times, slots, np.zeros((100, 70, 640), dtype=np.uint8)) is None


def test_skull_needs_to_hold_for_a_moment():
    frames = np.zeros((12, hud.SKULL, hud.SKULL, 3), dtype=np.uint8)
    frames[2, 75:105, 75:105] = 255              # one bright frame is noise
    frames[6:10, 75:105, 75:105] = 255           # four in a row is a banner
    assert hud.skull_runs(frames) == [1.5]


# ---- picking moments
def lanes(n=2000):
    return {k: np.zeros(n, dtype=np.float32) for k in sound.GROUPS}


def test_a_laugh_becomes_a_funny_clip_with_its_setup():
    s = lanes()
    s["laugh"][500:505] = .6
    m = detect.laugh_moments(s, 2000)
    assert len(m) == 1 and m[0]["tags"] == ["funny"]
    assert m[0]["start"] <= 480 and m[0]["end"] >= 505


def test_a_triple_kill_beats_a_loud_nothing():
    s = lanes()
    s["gun"][300] = s["gun"][306] = s["gun"][311] = .9
    game = {"events": [{"t": t + 2, "from": t - 2, "kind": "enemy_down", "round": 1} for t in (300, 306, 311)]}
    m = detect.game_moments(game, s, 2000)
    assert len(m) == 1 and m[0]["title"] == "Triple kill"
    assert m[0]["first"] == 300 and m[0]["last"] == 311      # placed on the gunshots, not the keyframes
    loud = {"peak": 900.0, "score": 5.0, "start": 880.0, "end": 910.0, "tags": ["hype"], "reasons": ["r"]}
    assert detect.select(m + [loud], 1)[0]["title"] == "Triple kill"


def test_a_death_with_no_reaction_is_not_a_clip():
    game = {"events": [{"t": 100.0, "from": 95.0, "kind": "you_down", "round": 1}]}
    assert detect.game_moments(game, lanes(), 2000) == []
    s = lanes()
    s["laugh"][102] = .5
    m = detect.game_moments(game, s, 2000)
    assert m and set(m[0]["tags"]) == {"deaths", "funny"}


def test_skull_seen_after_dying_belongs_to_a_teammate():
    game = {"events": [{"t": 100.0, "from": 95.0, "kind": "enemy_down", "round": 1}]}
    m = detect.game_moments(game, None, 2000)[0]
    before = m["score"]
    detect.apply_own_kills(m, own=[98.0], dead=60.0)       # died long before: this was spectating
    assert m["title"] == "Team fight" and m["score"] < before


def test_your_own_kill_is_credited():
    game = {"events": [{"t": 100.0, "from": 95.0, "kind": "enemy_down", "round": 1}]}
    m = detect.game_moments(game, None, 2000)[0]
    detect.apply_own_kills(m, own=[97.0, 99.0])
    assert m["title"] == "Double kill" and m["reasons"][0] == "You got 2 kills"


def test_a_kind_set_to_zero_never_appears():
    m = [{"peak": 10.0, "score": 9.0, "start": 0.0, "end": 20.0, "tags": ["deaths"], "reasons": []},
         {"peak": 100.0, "score": 3.0, "start": 90.0, "end": 110.0, "tags": ["funny"], "reasons": []}]
    assert [c["tags"] for c in detect.select(m, 5, {"deaths": 0})] == [["funny"]]


def test_one_moment_found_twice_is_one_clip_with_both_reasons():
    a = {"peak": 10.0, "score": 9.0, "start": 0.0, "end": 20.0, "tags": ["kills"], "reasons": ["kill"]}
    b = {"peak": 12.0, "score": 6.0, "start": 2.0, "end": 22.0, "tags": ["funny"], "reasons": ["laugh"]}
    out = detect.select([a, b], 5)
    assert len(out) == 1 and set(out[0]["tags"]) == {"kills", "funny"} and out[0]["reasons"] == ["kill", "laugh"]


def test_the_shortlist_keeps_room_for_funny_moments():
    kills = [{"peak": i * 100.0, "score": 20.0 - i, "start": i * 100.0, "end": i * 100.0 + 20, "tags": ["kills"],
              "reasons": []} for i in range(10)]
    funny = [{"peak": 5000.0 + i * 100, "score": 4.0, "start": 5000.0 + i * 100, "end": 5020.0 + i * 100,
              "tags": ["funny"], "reasons": []} for i in range(3)]
    out = detect.select(kills + funny, 8)
    assert len(out) == 8 and sum("funny" in c["tags"] for c in out) == 2


def test_transcript_edges_never_lose_the_action():
    pick = {"peak": 100.0, "start": 88.0, "end": 105.0, "first": 95.0, "last": 100.0, "score": 5, "reasons": []}
    words = [{"w": "a", "s": 96.0, "e": 96.2}, {"w": "b", "s": 97.0, "e": 97.2}]
    out = detect.refine_with_words(pick, words)
    assert out["start"] <= 92 and out["end"] >= 102


# ---- language
class Segment:
    def __init__(self, text="ok", logprob=-.5, ratio=1.5, no_speech=.1):
        self.text, self.avg_logprob, self.compression_ratio, self.no_speech_prob = text, logprob, ratio, no_speech


def test_noise_shaped_segments_are_dropped():
    assert transcribe.trusted(Segment())
    assert not transcribe.trusted(Segment(logprob=-1.6))
    assert not transcribe.trusted(Segment(ratio=3.0))
    assert not transcribe.trusted(Segment(no_speech=.9, logprob=-1.1))     # likely silence and unsure: nobody spoke
    assert transcribe.trusted(Segment(no_speech=.9))        # confident words: the translator's no-speech score lies


def test_words_in_a_script_nobody_spoke_are_dropped():
    assert transcribe.readable("भाई", "hi") and transcribe.readable("clutch", "hi")
    assert not transcribe.readable("మ్యంభి", "hi") and not transcribe.readable("行", "hi")
    assert not transcribe.readable("भाई", "en")
    assert transcribe.readable("anything", "xx")


def test_the_language_is_voted_across_the_stream(monkeypatch):
    class Model:
        said = iter(["en", "hi", "hi", "hi"])

        def detect_language(self, audio, vad_filter=True):
            return None, None, [(next(self.said), .8)]

    monkeypatch.setattr(transcribe, "audio_window", lambda *a, **k: np.zeros(32000, dtype=np.float32))
    picks = [{"start": i * 100.0, "end": i * 100.0 + 30} for i in range(4)]
    assert transcribe.stream_language("v.mp4", picks, model=Model()) == "hi"    # the first window no longer decides


def test_translation_needs_a_model_trained_for_it():
    assert transcribe.model_for("large-v3-turbo", "english") == "medium"
    assert transcribe.model_for("large-v3-turbo", "spoken") == "large-v3-turbo"


@pytest.mark.skipif(os.environ.get("CI") == "true", reason="needs the model file")
def test_sound_lanes_pool_to_the_right_second():
    s = lanes(20)
    rows = np.zeros((6, 521), dtype=np.float32)
    rows[4, 13] = .7            # row 4 covers 1.92 s to 2.88 s
    sound.pool(rows, 0.0, s)
    assert s["laugh"].argmax() == 2 and s["laugh"].max() == pytest.approx(.7)


@pytest.mark.parametrize("layout,cam", [("stack", (0, 0, 300, 200)), ("blur", None), ("crop", None)])
@pytest.mark.parametrize("out", list(render.SIZES.values()))
def test_every_export_size_fills_the_frame_with_released_filters(layout, cam, out):
    graph = render.layout_filter(layout, (640, 360), cam, out=out, enhance="auto")
    assert filters_in(graph) <= set(render.FILTERS), filters_in(graph) - set(render.FILTERS)
    assert "atadenoise" in graph                              # 360p counts as low quality
    assert ("cas=" in graph) == (render.enlargement(layout, (640, 360), out, cam) >= render.SHARPEN_FROM)
    assert "%d:%d" % out in graph or "crop=%d:" % out[0] in graph


def test_enhance_leaves_a_good_source_alone_unless_it_is_enlarged():
    assert "atadenoise" not in render.layout_filter("blur", (1920, 1080), enhance="auto")
    assert "cas=" not in render.layout_filter("blur", (1920, 1080), enhance="auto")      # 1920 wide fits 1080
    assert "cas=" in render.layout_filter("crop", (1920, 1080), enhance="auto")          # cropping enlarges 1.8x
    assert "cas=" not in render.layout_filter("crop", (1920, 1080), enhance="off")


def test_frame_rate_never_invents_frames():
    assert render.frame_rate("source", 60) == 60
    assert render.frame_rate("source", 144) == 60
    assert render.frame_rate("60", 30) == 30
    assert render.frame_rate("30", 59.94) == 30
    assert render.frame_rate("source", 0) == 30


@pytest.mark.skipif(not shutil.which(tool("ffmpeg")), reason="needs FFmpeg")
def test_real_export_uses_the_chosen_size_and_rate(tmp_path):
    video = tmp_path / "v.mp4"
    make_video(video, 4)
    path = render.export_clip(str(video), clip(0.5, 3.5), (640, 360), str(tmp_path), out=(720, 1280), fps=24,
                              enhance="auto")
    out = subprocess.run([tool("ffprobe"), "-v", "error", "-select_streams", "v:0", "-show_entries",
                          "stream=width,height,r_frame_rate", "-of", "csv=p=0", path], capture_output=True, text=True)
    assert out.stdout.strip() == "720,1280,24/1"
