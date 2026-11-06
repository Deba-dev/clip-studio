"""The post-stream pipeline. Two passes make it fast on any PC:

1. Audio, chat and hotkeys rank the whole stream in about the time FFmpeg takes to read the audio.
2. Speech recognition then runs only on the windows that made the shortlist, not on all 4 hours.
"""
from . import detect, media
from .settings import Settings

WINDOW_PAD = 10         # extra audio around a candidate, so the transcript can find where the thought began


def run(library, sid, settings=None, report=lambda stage, value: None, model=None):
    settings = settings or Settings()
    session = library.session(sid)
    source = session["source"]
    library.update_session(sid, status="analyzing", error="")
    info = media.probe(source)
    library.update_session(sid, duration=info["duration"])

    report("Reading audio", 0.0)
    loud = media.loudness_per_second(source, on_progress=lambda v: report("Reading audio", v), total=info["duration"])
    parts = detect.score_moments(loud, library.chat(sid), library.markers(sid), info["duration"],
                                 lag=session["chat_lag"])
    limit = int(settings.get("max_clips"))
    picks = detect.pick_moments(parts, info["duration"], limit, int(settings.get("clip_length")))
    library.update_session(sid, chat_lag=parts["lag"])

    report("Loading speech model", 0.0)
    if model is None and picks:
        from .transcribe import load_model
        model = load_model(settings.get("model"))
    language = settings.get("language") or session["language"] or None
    roman = bool(settings.get("roman_script"))
    done = []
    for i, pick in enumerate(picks):
        report("Writing captions", i / max(len(picks), 1))
        if model is not False:
            from .transcribe import transcribe_window
            start = max(pick["start"] - WINDOW_PAD, 0.0)
            length = pick["end"] - start + WINDOW_PAD
            words, seen = transcribe_window(model, source, start, length, language, roman)
            language = language or seen
            refined = detect.refine_with_words(pick, words)
            refined["words"] = [w for w in words if w["e"] > refined["start"] and w["s"] < refined["end"]]
            refined["title"] = detect.title_from(words, pick["peak"])
            pick = refined
        done.append(pick)
    done.sort(key=lambda p: p["score"], reverse=True)
    library.replace_clips(sid, done[:limit])
    library.update_session(sid, status="ready", language=language or "")
    library.purge_old_chat()
    report("Done", 1.0)
    return done[:limit]
