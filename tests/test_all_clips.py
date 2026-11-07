"""Every moment becomes a clip: the best are captioned at once, the rest in the background, and exports never wait."""
from clipstudio import analyze
from clipstudio.db import Library
from clipstudio.settings import Settings
from clipstudio.ui.jobs import Jobs


def moment(start, score, tags=("hype",), **extra):
    return {"start": start, "end": start + 30, "peak": start + 20, "score": score, "reasons": ["test"],
            "tags": list(tags), **extra}


def test_clips_without_captions_are_saved_and_found(tmp_path):
    lib = Library(str(tmp_path / "lib.db"))
    sid = lib.add_session("s", "v.mp4")
    lib.replace_clips(sid, [moment(0, 9, words=[{"w": "hi", "s": 1, "e": 2}]),
                            moment(100, 5, title="Kill", tags=("kills",), captioned=False),
                            moment(200, 4, captioned=False)])
    waiting = lib.uncaptioned(sid)
    assert [c["start"] for c in waiting] == [100, 200]
    assert lib.clips(sid)[0]["captioned"] == "1"
    second = lib.split_clip(waiting[0]["id"], 115)
    assert lib.clip(second)["captioned"] == "0"          # both halves of an uncaptioned clip still need captions


def test_background_captions_respect_edits_and_game_titles(tmp_path, monkeypatch):
    lib = Library(str(tmp_path / "lib.db"))
    sid = lib.add_session("s", "v.mp4")
    lib.replace_clips(sid, [moment(100, 5, title="Kill", tags=("kills",), captioned=False),
                            moment(200, 4, title="Funny moment", tags=("funny",), captioned=False),
                            moment(300, 3, title="My own title", captioned=False)])
    edited = lib.clips(sid)[2]
    lib.update_clip(edited["id"], edit={"cuts": [[305, 306]]})
    said = [{"w": "bhai", "s": 213, "e": 213.5}, {"w": "kya", "s": 215, "e": 215.4}, {"w": "hua", "s": 305, "e": 305.3}]
    monkeypatch.setattr("clipstudio.transcribe.transcribe_window", lambda *a, **k: (said, "hi"))
    monkeypatch.setattr("clipstudio.transcribe.load_model", lambda *a, **k: object())
    assert analyze.caption_rest(lib, sid, Settings(str(tmp_path / "s.json"))) == 3
    kill, funny, own = lib.clips(sid)
    assert lib.uncaptioned(sid) == []
    assert kill["title"] == "Kill"                          # the game's title stays
    assert funny["title"] == "bhai kya"                     # a placeholder gives way to the words at the peak
    assert own["title"] == "My own title" and (own["start"], own["end"]) == (300, 330)   # edited: edges untouched
    assert [w["w"] for w in own["words"]] == ["hua"]


class FakeProc:
    def __init__(self):
        self.killed = False

    def kill(self):
        self.killed = True


def test_an_export_jumps_ahead_of_background_captions():
    jobs = Jobs()
    jobs._next = lambda: None                  # no real worker processes in a unit test
    jobs.current, jobs.proc = ("captions", 1), FakeProc()
    jobs.add("analyze", 2)
    jobs.add("export", 7)
    assert jobs.proc.killed and jobs.cancelled
    assert list(jobs.queue) == [("export", 7), ("captions", 1), ("analyze", 2)]
    jobs.current, jobs.proc = ("analyze", 3), FakeProc()
    jobs.queue.clear()
    jobs.add("captions", 3)
    jobs.add("export", 8)
    assert not jobs.proc.killed and list(jobs.queue) == [("export", 8), ("captions", 3)]


class Seg:
    def __init__(self, text, lp=-0.5, ns=0.0, cr=1.5):
        self.text, self.avg_logprob, self.no_speech_prob, self.compression_ratio = text, lp, ns, cr


def test_a_line_stuck_on_repeat_is_cut_to_two():
    from clipstudio.transcribe import drop_loops
    said = [Seg("Come here."), Seg("Go there."), Seg("Go there"), Seg("go there!"), Seg("Go there."), Seg("No.")]
    assert [s.text for s in drop_loops(said)] == ["Come here.", "Go there.", "Go there", "No."]


def test_translated_speech_is_not_mistaken_for_silence():
    from clipstudio.transcribe import trusted
    assert trusted(Seg("Where did you die?", lp=-0.52, ns=0.85))        # real speech, as the translator scores it
    assert not trusted(Seg("Thank you.", lp=-1.1, ns=0.9))               # silence: likely empty and unsure
    assert not trusted(Seg("garbled", lp=-2.04, ns=0.0))                  # too unsure to show
