import base64
import hashlib
import json

import numpy as np
import pytest

from clipstudio import captions, chat, detect, fetch, render
from clipstudio.db import Library
from clipstudio.obs import RecordingTracker, auth_string
from clipstudio.roman import to_roman
from clipstudio.worker import parse_facecam


@pytest.fixture
def library(tmp_path):
    lib = Library(str(tmp_path / "lib.db"))
    yield lib
    lib.close()


def quiet_stream(seconds=1800, seed=1):
    rng = np.random.default_rng(seed)
    return rng.normal(-32, 1.5, seconds).astype(np.float32)


def test_audio_peak_found_with_no_chat_at_all():
    loud = quiet_stream()
    loud[900:906] = -8
    parts = detect.score_moments(loud, [], [], 1800)
    picks = detect.pick_moments(parts, 1800, limit=3)
    assert picks and abs(picks[0]["peak"] - 902) < 8
    assert parts["chat_trust"] == 0
    assert "Chat spiked" not in " ".join(picks[0]["reasons"])


def test_tiny_chat_cannot_outvote_audio():
    loud = quiet_stream()
    loud[400:405] = -9
    rows = [(1200 + i * 0.3, "twitch", "friend", "hi") for i in range(5)]
    picks = detect.pick_moments(detect.score_moments(loud, rows, [], 1800), 1800, limit=1)
    assert abs(picks[0]["peak"] - 402) < 8


def test_busy_chat_spike_found_on_silent_moment_and_lag_applied():
    rng = np.random.default_rng(2)
    loud = quiet_stream()
    rows = [(float(t), "kick", "v", "hello") for t in rng.uniform(0, 1800, 900)]
    rows += [(1000 + i * 0.1, "twitch", "v", "KEKW") for i in range(120)]
    picks = detect.pick_moments(detect.score_moments(loud, rows, [], 1800, lag=10), 1800, limit=2)
    assert abs(picks[0]["peak"] - 996) < 10
    assert any("Chat spiked" in r for r in picks[0]["reasons"])


def test_lag_is_learned_from_the_stream():
    rng = np.random.default_rng(3)
    loud = quiet_stream(3600)
    rows = [(float(t), "twitch", "v", "x") for t in rng.uniform(0, 3600, 400)]
    for peak in range(200, 3400, 300):
        loud[peak:peak + 4] = -8
        rows += [(peak + 17 + i * 0.1, "twitch", "v", "lol") for i in range(40)]
    n = 3600
    lag = detect.estimate_lag(loud, detect.chat_series([r[0] for r in rows], n))
    assert 13 <= lag <= 21


def test_hotkey_always_comes_first():
    loud = quiet_stream()
    loud[900:906] = -8
    parts = detect.score_moments(loud, [], [(300.0, "hotkey")], 1800)
    picks = detect.pick_moments(parts, 1800, limit=3)
    assert picks[0]["peak"] == 300.0
    assert picks[0]["reasons"] == ["You marked this with the hotkey"]


def test_picks_stay_inside_the_video():
    loud = quiet_stream(120)
    loud[2:5] = -5
    loud[116:119] = -5
    for p in detect.pick_moments(detect.score_moments(loud, [], [], 120), 120, limit=4):
        assert 0 <= p["start"] < p["end"] <= 120


def test_clip_starts_at_a_pause_and_keeps_the_setup():
    words = [{"w": "a", "s": 80.0, "e": 80.4}, {"w": "b", "s": 80.5, "e": 81.0},
             {"w": "setup", "s": 84.0, "e": 84.5}, {"w": "c", "s": 84.6, "e": 85.0},
             {"w": "what", "s": 100.0, "e": 100.3}, {"w": "no", "s": 100.4, "e": 100.8},
             {"w": "way", "s": 102.2, "e": 102.6}, {"w": "end", "s": 105.0, "e": 105.5}]
    pick = {"peak": 100.0, "start": 83.0, "end": 108.0, "score": 3.0, "reasons": ["x"]}
    out = detect.refine_with_words(pick, words)
    assert out["start"] == 84.0
    assert out["end"] == pytest.approx(106.5)      # the breaths inside the reaction do not end the clip


def test_refined_clip_stays_under_a_minute():
    words = [{"w": "x", "s": float(t), "e": t + 0.5} for t in range(0, 200, 2)]
    pick = {"peak": 150.0, "start": 60.0, "end": 158.0, "score": 3.0, "reasons": ["x"]}
    out = detect.refine_with_words(pick, words)
    assert out["end"] - out["start"] <= 59


def test_reanalysis_keeps_finished_work(library):
    sid = library.add_session("s", "v.mp4")
    base = {"peak": 15.0, "score": 1.0, "reasons": ["r"]}
    library.replace_clips(sid, [{**base, "start": 0.0, "end": 30.0}, {**base, "start": 100.0, "end": 130.0}])
    first, second = library.clips(sid)
    library.update_clip(first["id"], state="kept", start=2.0)
    library.replace_clips(sid, [{**base, "start": 5.0, "end": 35.0}, {**base, "start": 200.0, "end": 230.0}])
    clips = library.clips(sid)
    assert [c["start"] for c in clips] == [2.0, 200.0]


def test_deleting_a_session_leaves_the_recording(library, tmp_path):
    video = tmp_path / "stream.mp4"
    video.write_bytes(b"x")
    sid = library.add_session("s", str(video))
    library.add_chat(sid, [(1.0, "twitch", "a", "hi")])
    library.delete_session(sid)
    assert video.exists() and library.sessions() == [] and library.chat(sid) == []


def test_old_chat_is_purged(library):
    sid = library.add_session("s", "v.mp4")
    library.add_chat(sid, [(1.0, "twitch", "a", "hi")])
    library.con.execute("UPDATE chat SET added=0")
    assert library.purge_old_chat() == 1


def test_captions_highlight_each_word_and_use_clip_time():
    words = [{"w": "bhai", "s": 10.0, "e": 10.4}, {"w": "kya", "s": 10.5, "e": 10.8}, {"w": "{bad}", "s": 11.0, "e": 11.4}]
    text = captions.build_ass(words, 10.0, 20.0)
    lines = [x for x in text.splitlines() if x.startswith("Dialogue")]
    assert len(lines) == 3
    assert lines[0].startswith("Dialogue: 0,0:00:00.00,0:00:00.50")
    assert lines[-1].split(",")[2] == "0:00:01.75"
    assert captions.HIGHLIGHT + "bhai" in lines[0]
    assert "{bad}" not in text and "bad" in text


def test_caption_lines_break_on_pause_and_length():
    words = [{"w": "one", "s": 0, "e": .2}, {"w": "two", "s": .3, "e": .5}, {"w": "three", "s": 2, "e": 2.2}]
    assert [len(x) for x in captions.group_words(words)] == [2, 1]
    long = [{"w": "abcdefghij", "s": i, "e": i + .5} for i in range(4)]
    assert all(len(x) <= 2 for x in captions.group_words(long))


@pytest.mark.parametrize("hindi,roman", [("क्या", "kya"), ("भाई", "bhai"), ("नहीं", "nahi"), ("गया", "gaya"),
                                         ("मारा", "mara"), ("बंदा", "banda"), ("hello", "hello"), ("खतम", "khatam")])
def test_roman_script(hindi, roman):
    assert to_roman(hindi) == roman


def test_windows_path_survives_filter_escaping():
    assert render.filter_path(r"C:\Temp\a.ass") == "C\\:/Temp/a.ass"


def test_export_names_are_safe():
    assert render.clean_name('what?? no: "way"/') == "what no way"
    assert render.clean_name("...") == "clip"


def test_stack_layout_uses_the_facecam_rectangle():
    graph = render.layout_filter("auto", (1920, 1080), (1500, 700, 400, 300))
    assert "crop=400:300:1500:700" in graph and "vstack" in graph and graph.endswith("[v]")
    assert "boxblur" in render.layout_filter("auto", (1920, 1080))


def test_obs_auth_matches_the_protocol():
    secret = base64.b64encode(hashlib.sha256(b"pwsalt").digest()).decode()
    expected = base64.b64encode(hashlib.sha256((secret + "chal").encode()).digest()).decode()
    assert auth_string("pw", "salt", "chal") == expected


def test_tracker_builds_a_session_from_obs_events(library):
    finished = []
    now = [1000.0]
    tracker = RecordingTracker(library, finished.append, clock=lambda: now[0])
    tracker.handle("RecordStateChanged", {"outputState": "OBS_WEBSOCKET_OUTPUT_STARTED", "outputPath": "a.mkv"})
    now[0] = 1090.0
    assert tracker.mark() == 90.0
    tracker.handle("RecordStateChanged", {"outputState": "OBS_WEBSOCKET_OUTPUT_STOPPED", "outputPath": "a.mkv"})
    sid = finished[0]
    assert library.session(sid)["source"] == "a.mkv"
    assert library.markers(sid) == [(90.0, "hotkey")]
    assert tracker.mark() is None


def test_split_recording_becomes_one_source(library, monkeypatch, tmp_path):
    monkeypatch.setenv("CLIPSTUDIO_DATA", str(tmp_path))
    finished = []
    tracker = RecordingTracker(library, finished.append)
    tracker.handle("RecordStateChanged", {"outputState": "OBS_WEBSOCKET_OUTPUT_STARTED", "outputPath": "a.mkv"})
    tracker.handle("RecordFileChanged", {"newOutputPath": "b.mkv"})
    tracker.handle("RecordStateChanged", {"outputState": "OBS_WEBSOCKET_OUTPUT_STOPPED", "outputPath": "b.mkv"})
    source = library.session(finished[0])["source"]
    assert source.endswith(".ffconcat")
    assert open(source, encoding="utf-8").read().count("file '") == 2


def test_chat_parsers():
    line = ":bob!bob@bob.tmi.twitch.tv PRIVMSG #chan :clip that"
    assert chat.parse_twitch_line(line) == ("bob", "clip that")
    event = '{"content":"nice [emote:1:KEKW]","sender":{"username":"amy"}}'
    assert chat.parse_kick_event("App\\Events\\ChatMessageEvent", event) == ("amy", "nice KEKW")
    assert chat.youtube_id("https://www.youtube.com/live/abcdefghijk?x=1") == "abcdefghijk"


def test_chat_file_import(tmp_path):
    path = tmp_path / "chat.csv"
    path.write_text("12.5,amy,hello, world\nbad line\n", encoding="utf-8")
    assert chat.parse_chat_file(str(path)) == [(12.5, "import", "amy", "hello, world")]


def test_facecam_parsing():
    assert parse_facecam("10,20,300,200") == (10, 20, 300, 200)
    assert parse_facecam("") is None and parse_facecam("1,2,0,4") is None


def test_transcript_edit_keeps_timings():
    words = [{"w": "helo", "s": 1.0, "e": 1.5}, {"w": "wrld", "s": 2.0, "e": 2.5}]
    assert captions.apply_text(words, "hello world") == [{"w": "hello", "s": 1.0, "e": 1.5}, {"w": "world", "s": 2.0, "e": 2.5}]
    spread = captions.apply_text(words, "one two three")
    assert len(spread) == 3 and spread[0]["s"] == 1.0 and spread[-1]["e"] == 2.5
    assert captions.apply_text(words, "   ") == []


def test_saved_replay_becomes_a_marker(library):
    tracker = RecordingTracker(library, lambda sid: None, clock=lambda: 50.0)
    tracker.handle("RecordStateChanged", {"outputState": "OBS_WEBSOCKET_OUTPUT_STARTED", "outputPath": "a.mkv"})
    tracker.handle("ReplayBufferSaved", {"savedReplayPath": "r.mkv"})
    assert library.markers(tracker.sid) == [(0.0, "hotkey")]


def test_reaction_is_not_cut_at_its_first_breath():
    words = [{"w": "oh", "s": 95.0, "e": 95.5}, {"w": "my", "s": 97.4, "e": 97.8}, {"w": "god", "s": 98.6, "e": 99.0},
             {"w": "bro", "s": 100.0, "e": 100.8}, {"w": "later", "s": 120.0, "e": 120.5}]
    pick = {"peak": 95.0, "start": 70.0, "end": 115.0, "score": 3.0, "reasons": ["x"]}
    assert detect.refine_with_words(pick, words)["end"] == pytest.approx(101.4)


def test_dead_air_before_the_first_word_is_trimmed():
    words = [{"w": "wow", "s": 230.0, "e": 230.5}, {"w": "shot", "s": 231.0, "e": 231.5}]
    pick = {"peak": 230.0, "start": 197.0, "end": 242.0, "score": 3.0, "reasons": ["x"]}
    assert detect.refine_with_words(pick, words)["start"] == 224.0


@pytest.mark.parametrize("url,name", [
    ("https://www.youtube.com/watch?v=abcdefghijk", "youtube"), ("https://youtu.be/abcdefghijk", "youtube"),
    ("https://www.youtube.com/live/abcdefghijk", "youtube"), ("https://www.twitch.tv/videos/123456", "twitch"),
    ("https://kick.com/somebody/videos/abc-123", "kick"), ("https://kick.com/video/abc-123", "kick"),
    ("https://example.com/video", ""), ("not a link", ""), ("https://www.twitch.tv/somebody", "")])
def test_platform_from_link(url, name):
    assert fetch.platform_of(url) == name


def test_download_errors_read_like_a_person_wrote_them():
    assert "private" in fetch.friendly("ERROR: [youtube] abc: Private video. Sign in")
    assert "subscribers" in fetch.friendly("ERROR: [twitch] 1: This video is only available to subscribers")
    assert fetch.friendly("ERROR: weird").startswith("Could not get this stream: weird")


def test_low_disk_stops_the_download_before_it_starts(tmp_path):
    with pytest.raises(ValueError, match="GB"):
        fetch.check_space(str(tmp_path), 10 ** 15)
    fetch.check_space(str(tmp_path), 0)


def test_youtube_chat_replay_parses(tmp_path):
    message = {"addChatItemAction": {"item": {"liveChatTextMessageRenderer": {
        "message": {"runs": [{"text": "no way "}, {"emoji": {"shortcuts": [":fire:"]}}]},
        "authorName": {"simpleText": "amy"}}}}}
    good = {"replayChatItemAction": {"actions": [message], "videoOffsetTimeMsec": "12500"}}
    before = {"replayChatItemAction": {"actions": [message], "videoOffsetTimeMsec": "-3000"}}
    sticker = {"replayChatItemAction": {"actions": [{"addChatItemAction": {"item": {"x": {}}}}],
                                        "videoOffsetTimeMsec": "1"}}
    path = tmp_path / "c.json"
    path.write_text("\n".join(json.dumps(x) for x in (good, before, sticker)) + "\nnot json\n", encoding="utf-8")
    assert fetch.parse_live_chat(str(path)) == [(12.5, "youtube", "amy", "no way :fire:")]


def test_old_libraries_gain_the_link_column(tmp_path):
    import sqlite3
    path = str(tmp_path / "old.db")
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE sessions (id INTEGER PRIMARY KEY, name TEXT NOT NULL, source TEXT NOT NULL, "
                "created REAL NOT NULL, record_start REAL, duration REAL DEFAULT 0, status TEXT DEFAULT 'new', "
                "error TEXT DEFAULT '', chat_lag REAL, facecam TEXT DEFAULT '', language TEXT DEFAULT '')")
    con.commit()
    con.close()
    lib = Library(path)
    assert lib.session(lib.add_session("s", "", url="https://x"))["url"] == "https://x"
    lib.close()
