"""The post-stream pipeline. Three passes make it fast on any PC:

1. Audio, chat and hotkeys rank the whole stream in about the time FFmpeg takes to read the audio. Sound tagging rides
   along on that same read and finds laughter and gunfire.
2. Keyframes of the video are read for the game's own scoreboard, which is how kills and deaths are found.
3. Speech recognition then runs only on the clips that made the shortlist, not on all 4 hours.
"""
import json
import shutil

import numpy as np

from . import detect, hud, media
from .paths import clip_thumb, session_thumb, signals_file
from .settings import Settings

WINDOW_PAD = 10         # extra audio around a candidate, so the transcript can find where the thought began
KILL_CHECKS = 3         # kill moments checked for the streamer's own skull banner, per clip wanted


def make_previews(source, sid, picks, report):
    for i, pick in enumerate(picks):
        report("Making previews", i / max(len(picks), 1))
        media.frame_png(source, pick["peak"], clip_thumb(sid, pick["peak"]), 480)
    if picks:
        try:
            shutil.copyfile(clip_thumb(sid, picks[0]["peak"]), session_thumb(sid))
        except OSError:
            pass


def make_tagger(duration):
    """Sound tagging is a bonus: without it, or offline on the first run, analysis still finishes."""
    try:
        from .sound import Tagger
        return Tagger(duration)
    except Exception:
        return None


def read_game(source, info, report):
    if not info["width"] or abs(info["width"] / max(info["height"], 1) - 16 / 9) > .02:
        return None             # the HUD reader knows 16:9 only, and a stretched 4:3 would misread
    try:
        times, slots, strips = hud.scan(source, info["duration"], lambda v: report("Reading the game", v))
        return hud.read_game(times, slots, strips)
    except (OSError, ValueError, RuntimeError):
        return None


def credit_kills(source, game, moments, limit, duration, report):
    """Only the best kill moments get the closer look, so this stays seconds rather than minutes."""
    deaths = {e["round"]: e["from"] for e in game["events"] if e["kind"] == "you_down"}
    kills = sorted((m for m in moments if m["tags"][0] == "kills" and m.get("round")),
                   key=lambda m: m["score"], reverse=True)
    checked = kills[:limit * KILL_CHECKS]
    for i, m in enumerate(checked):
        report("Checking kills", i / max(len(checked), 1))
        detect.apply_own_kills(m, hud.own_kills(source, m["first"] - 6, m["last"] + 2), deaths.get(m["round"]))
        m["start"], m["end"] = detect.frame(m["first"], m["last"], 12, 5, duration)
    # A kill nobody looked at closely is not known to be the streamer's, so it cannot outrank one that is.
    return [m for m in moments if m not in kills[limit * KILL_CHECKS:]]


def wanted(settings):
    return {name: int(settings.get("want_" + name)) / 100 for name in ("funny", "kills", "deaths", "hype")}


def run(library, sid, settings=None, report=lambda stage, value: None, model=None):
    settings = settings or Settings()
    session = library.session(sid)
    source = session["source"]
    library.update_session(sid, status="analyzing", error="")
    info = media.probe(source)
    library.update_session(sid, duration=info["duration"])

    report("Reading audio", 0.0)
    tagger = make_tagger(info["duration"])
    loud = media.loudness_per_second(source, on_progress=lambda v: report("Reading audio", v), total=info["duration"],
                                     tap=tagger.feed if tagger else None)
    lanes = tagger.finish() if tagger else None
    game = read_game(source, info, report)
    report("Finding moments", 0.5)
    parts = detect.score_moments(loud, library.chat(sid), library.markers(sid), info["duration"],
                                 lag=session["chat_lag"])
    limit = int(settings.get("max_clips"))
    picks = detect.pick_moments(parts, info["duration"], limit, int(settings.get("clip_length")))
    if game:        # lobbies and scoreboards can be loud, but nobody wants a clip of them
        picks = [p for p in picks if p["score"] >= 100 or hud.is_live(game, p["peak"])]
    moments = list(picks)
    if lanes:
        moments += detect.laugh_moments(lanes, info["duration"])
    if game:
        moments += credit_kills(source, game, detect.game_moments(game, lanes, info["duration"]), limit,
                                 info["duration"], report)
    picks = detect.select(moments, limit, wanted(settings))
    library.update_session(sid, chat_lag=parts["lag"], game=game["game"] if game else "")
    extra = {k: v.astype(np.float16) for k, v in (lanes or {}).items() if k in ("laugh", "gun")}
    np.savez_compressed(signals_file(sid), curve=parts["curve"].astype(np.float16), loud=loud.astype(np.float16),
                        events=json.dumps(game["events"] if game else []), **extra)

    report("Loading speech model", 0.0)
    mode = settings.get("caption_mode")
    if model is None and picks:
        from .transcribe import load_model, model_for
        model = load_model(model_for(settings.get("model"), mode))
    language = settings.get("language") or None
    if model is not False and picks and not language:
        report("Finding the language", 0.0)
        from .transcribe import stream_language
        language = stream_language(source, picks)
    roman = bool(settings.get("roman_script"))
    hints = None
    done = []
    for i, pick in enumerate(picks):
        report("Writing captions", i / max(len(picks), 1))
        if model is not False:
            from .transcribe import GAME_WORDS, transcribe_window
            hints = GAME_WORDS.get(game["game"]) if game else None
            start = max(pick["start"] - WINDOW_PAD, 0.0)
            length = pick["end"] - start + WINDOW_PAD
            words, _ = transcribe_window(model, source, start, length, language, roman,
                                         task="translate" if mode == "english" else "transcribe", hotwords=hints)
            refined = detect.refine_with_words(pick, words)
            refined["words"] = [w for w in words if w["e"] > refined["start"] and w["s"] < refined["end"]]
            refined["title"] = pick.get("title") or detect.title_from(words, pick["peak"])
            pick = refined
        done.append(pick)
    done.sort(key=lambda p: p["score"], reverse=True)
    library.replace_clips(sid, done)
    make_previews(source, sid, done, report)
    library.update_session(sid, status="ready", language=language or "")
    library.purge_old_chat()
    report("Done", 1.0)
    return done
