"""Cleanup removes only the app's own leftovers, and AI upscaling picks a sensible size."""
import os
import time

import pytest

from clipstudio import cleanup, edit, transcribe, upscale
from clipstudio.db import Library
from clipstudio.settings import Settings


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("CLIPSTUDIO_DATA", str(tmp_path / "data"))
    monkeypatch.setenv("CLIPSTUDIO_EXPORTS", str(tmp_path / "exports"))
    monkeypatch.setenv("HF_HUB_CACHE", str(tmp_path / "shared"))
    monkeypatch.setattr("clipstudio.fetch.fixed_drives", lambda: [])
    monkeypatch.setattr("tempfile.gettempdir", lambda: str(tmp_path / "temp"))
    os.makedirs(tmp_path / "temp")
    return tmp_path


def touch(path, age=0.0, size=10):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(b"x" * size)
    stamp = time.time() - age
    os.utime(path, (stamp, stamp))
    return path


DAY = 24 * 3600


def test_unused_speech_models_go_and_used_ones_move_out_of_the_shared_folder(home):
    settings = Settings(str(home / "s.json"))
    for name in ("large-v3-turbo", "small", "base", "medium"):
        touch(str(home / "shared" / transcribe.cache_name(name) / "model.bin"))
    touch(str(home / "shared" / "models--someone--else" / "model.bin"))
    freed = cleanup.models(settings)
    kept = set(os.listdir(transcribe.models_dir()))
    assert kept == {transcribe.cache_name("large-v3-turbo"), transcribe.cache_name("base")}
    assert freed == 20                                              # small and medium
    assert os.listdir(home / "shared") == ["models--someone--else"]     # another app's model is never touched


def test_english_captions_keep_the_translation_model(home):
    settings = Settings(str(home / "s.json"))
    settings.set("caption_mode", "english")
    assert "medium" in cleanup.needed_models(settings)


def test_partial_downloads_stay_only_while_their_stream_waits(home):
    library = Library(str(home / "lib.db"))
    settings = Settings(str(home / "s.json"))
    folder = home / "dl"
    settings.set("downloads_folder", str(folder))
    library.add_session("waiting", "", url="https://www.youtube.com/watch?v=AAAAAAAAAAA", folder=str(folder))
    keep = touch(str(folder / "Stream [AAAAAAAAAAA].f299.mp4.part"), DAY)
    gone = touch(str(folder / "Old [BBBBBBBBBBB].f299.mp4.part"), DAY)
    gone_temp = touch(str(folder / "Old [BBBBBBBBBBB].temp.mp4"), DAY)
    fresh = touch(str(folder / "Busy [CCCCCCCCCCC].f140.m4a.part"))     # still being written
    finished = touch(str(folder / "Done [DDDDDDDDDDD].mp4"), DAY)
    cleanup.partial_downloads(library, settings)
    assert os.path.exists(keep) and os.path.exists(fresh) and os.path.exists(finished)
    assert not os.path.exists(gone) and not os.path.exists(gone_temp)


def test_crashed_exports_and_orphans_go(home):
    library = Library(str(home / "lib.db"))
    settings = Settings(str(home / "s.json"))
    sid = library.add_session("alive", "v.mp4")
    data = home / "data"
    alive = touch(str(data / "thumbs" / ("s%d.jpg" % sid)))
    orphan = touch(str(data / "thumbs" / ("s%d_40.jpg" % (sid + 7))))
    old_temp = touch(str(home / "temp" / "clipstudio123" / "captions.ass"), DAY)
    os.utime(home / "temp" / "clipstudio123", (time.time() - DAY,) * 2)
    part = touch(str(home / "exports" / "clip.mp4.part.mp4"), DAY)
    clip = touch(str(home / "exports" / "clip.mp4"), DAY)
    old_tool = touch(str(data / "tools" / "realesrgan-20200101" / "a.exe"))
    new_tool = touch(str(data / "tools" / upscale.NAME / "realesrgan-ncnn-vulkan.exe"))
    cleanup.full(library, settings)
    assert os.path.exists(alive) and os.path.exists(clip) and os.path.exists(new_tool)
    for path in (orphan, part, old_tool, str(home / "temp" / "clipstudio123")):
        assert not os.path.exists(path), path


def test_ai_scale_only_for_low_quality_sources():
    assert upscale.scale_for((360, 640), 3.0) == 3
    assert upscale.scale_for((640, 360), 1.69) == 2
    assert upscale.scale_for((480, 854), 4.0) == 4
    assert upscale.scale_for((1920, 1080), 1.78) == 0           # already good: the fast filters are enough
    assert upscale.scale_for((720, 1280), 1.2) == 0             # hardly enlarged


def test_shifted_clip_keeps_every_time_relative():
    clip = {"start": 100.0, "end": 130.0, "words": [{"w": "hi", "s": 101.0, "e": 101.5}],
            "edit": {"cuts": [[110, 112]], "mute": [[120, 121]], "pan": 0.3}}
    moved = edit.shifted(clip, 100.0)
    assert (moved["start"], moved["end"]) == (0.0, 30.0)
    assert moved["edit"]["cuts"] == [[10, 12]] and moved["edit"]["mute"] == [[20, 21]] and moved["edit"]["pan"] == .3
    assert moved["words"][0]["s"] == 1.0
    assert edit.length(moved) == edit.length(clip)


def _snapshot(name, size):
    folder = os.path.join(transcribe.models_dir(), transcribe.cache_name(name), "snapshots", "abc")
    os.makedirs(folder)
    with open(os.path.join(folder, "config.json"), "w") as f:
        f.write("{}")
    if size is not None:
        with open(os.path.join(folder, "model.bin"), "wb") as f:
            f.truncate(size)
    return folder


def test_a_cut_off_model_download_is_seen_and_removed(home):
    assert transcribe.model_complete("small")                   # not downloaded yet is fine
    _snapshot("small", None)                                    # download stopped before model.bin
    assert not transcribe.model_complete("small")
    transcribe.forget("small")
    assert not os.path.exists(os.path.join(transcribe.models_dir(), transcribe.cache_name("small")))
    _snapshot("base", 2 << 20)
    assert transcribe.model_complete("base")


def test_a_broken_model_is_downloaded_once_more_then_explained(home, monkeypatch):
    import sys
    import types
    calls = []

    class Whisper:
        def __init__(self, name, **kw):
            calls.append(name)
            raise RuntimeError("Unable to open file 'model.bin' in model 'x'")

    monkeypatch.setitem(sys.modules, "faster_whisper", types.SimpleNamespace(WhisperModel=Whisper))
    monkeypatch.setattr(transcribe, "has_cuda", lambda: False)
    _snapshot("small", 2 << 20)
    with pytest.raises(RuntimeError, match="did not download completely"):
        transcribe.load_model("small")
    assert calls == ["small", "small"]
    assert not os.path.exists(os.path.join(transcribe.models_dir(), transcribe.cache_name("small")))
