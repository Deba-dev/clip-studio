"""The post-stream pipeline. Three passes make it fast on any PC:

1. Audio, chat and hotkeys rank the whole stream in about the time FFmpeg takes to read the audio. Sound tagging rides
   along on that same read and finds laughter and gunfire.
2. Keyframes of the video are read for the game's own scoreboard, which is how kills and deaths are found.
3. Speech recognition then runs on the best clips first, so the review desk opens quickly. Every other moment found
   is saved as a clip too, and a separate background job captions those one by one afterwards.
"""
import json
import shutil

import numpy as np

from . import detect, hud, media
from .paths import clip_thumb, session_thumb, signals_file
from .settings import Settings

WINDOW_PAD = 10         # extra audio around a candidate, so the transcript can find where the thought began
KILL_CHECKS = 3         # kill moments checked for the streamer's own skull banner, per clip wanted
KILL_CHECKS_MIN = 40    # with every moment kept, at least this many kill moments get the closer look
ALL_MOMENTS = 150       # a sanity cap on clips per stream; a 4-hour stream rarely has more real moments than this


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
    checked = kills[:max(limit * KILL_CHECKS, KILL_CHECKS_MIN)]
    for i, m in enumerate(checked):
        report("Checking kills", i / max(len(checked), 1))
        detect.apply_own_kills(m, hud.own_kills(source, m["first"] - 6, m["last"] + 2), deaths.get(m["round"]))
        m["start"], m["end"] = detect.frame(m["first"], m["last"], 12, 5, duration)
    # A kill nobody looked at closely is not known to be the streamer's, so it cannot outrank one that is.
    return [m for m in moments if m not in kills[len(checked):]]


def placeholder(pick):
    """A title for a clip that has no transcript yet. The transcript replaces it later."""
    return {"kills": "Kill", "deaths": "Death reaction", "funny": "Funny moment",
            "marked": "Marked moment"}.get((pick.get("tags") or ["hype"])[0], "Hype moment")


def caption(model, source, pick, settings, language, game="", refine=True, keep_title=True):
    """Speech recognition for one clip. refine=False keeps the clip's edges, for clips the user already changed.

    A title from the game (Kill, Death reaction) or from the user stays; otherwise the words spoken at the peak become
    the title.
    """
    from .transcribe import GAME_WORDS, transcribe_window
    mode = settings.get("caption_mode")
    start = max(pick["start"] - WINDOW_PAD, 0.0)
    length = pick["end"] - start + WINDOW_PAD
    words, _ = transcribe_window(model, source, start, length, language, bool(settings.get("roman_script")),
                                 task="translate" if mode == "english" else "transcribe", hotwords=GAME_WORDS.get(game))
    out = detect.refine_with_words(pick, words) if refine else dict(pick)
    out["words"] = [w for w in words if w["e"] > out["start"] and w["s"] < out["end"]]
    own = pick.get("title") if keep_title else ""
    out["title"] = own or detect.title_from(words, pick["peak"]) or placeholder(pick)
    out["captioned"] = True
    return out


def caption_stored(library, sid, cid, model, settings):
    """Captions one saved clip. Edges move only for clips nobody has touched yet."""
    session, clip = library.session(sid), library.clip(cid)
    untouched = clip["state"] == "new" and not clip["edit"]
    # The placeholder only stood in for a transcript; a game title (Kill) or one the user typed is kept.
    keep = clip["title"] != placeholder(clip) or (clip["tags"] or [""])[0] in ("kills", "deaths")
    done = caption(model, session["source"], clip, settings, session["language"] or settings.get("language") or None,
                   session["game"], refine=untouched, keep_title=keep)
    fields = {"words": done["words"], "title": done["title"], "captioned": "1"}
    if untouched:
        fields.update(start=done["start"], end=done["end"], score=done["score"], reasons=json.dumps(done["reasons"]))
    library.update_clip(cid, **fields)


def caption_rest(library, sid, settings=None, report=lambda stage, value, note="": None):
    """The background pass: captions every clip analysis saved without a transcript, best first."""
    settings = settings or Settings()
    waiting = library.uncaptioned(sid)
    if not waiting:
        return 0
    from .transcribe import load_model, model_for
    report("Captioning more clips", 0.0, "Loading the speech model")
    model = load_model(model_for(settings.get("model"), settings.get("caption_mode")))
    total = len(waiting)
    for i, clip in enumerate(waiting):
        if library.clip(clip["id"]) is None:
            continue                # deleted while waiting
        caption_stored(library, sid, clip["id"], model, settings)
        report("Captioning more clips", (i + 1) / total, "%d of %d" % (i + 1, total))
    return total


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
    first = int(settings.get("max_clips"))
    picks = detect.pick_moments(parts, info["duration"], ALL_MOMENTS, int(settings.get("clip_length")))
    if game:        # lobbies and scoreboards can be loud, but nobody wants a clip of them
        picks = [p for p in picks if p["score"] >= 100 or hud.is_live(game, p["peak"])]
    moments = list(picks)
    if lanes:
        moments += detect.laugh_moments(lanes, info["duration"])
    if game:
        moments += credit_kills(source, game, detect.game_moments(game, lanes, info["duration"]), first,
                                 info["duration"], report)
    weights = wanted(settings)
    picks = detect.select(moments, first, weights)          # the best, with a mix of kinds: captioned now
    rest = [m for m in detect.select(moments, ALL_MOMENTS, weights)
            if not any(detect.overlaps(m, p) for p in picks)]   # every other moment: captioned in the background
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
    done = []
    for i, pick in enumerate(picks):
        report("Writing captions", i / max(len(picks), 1))
        done.append(caption(model, source, pick, settings, language, game["game"] if game else "")
                    if model is not False else pick)
    done += [dict(m, title=m.get("title") or placeholder(m), captioned=False) for m in rest]
    done.sort(key=lambda p: p["score"], reverse=True)
    library.replace_clips(sid, done)
    make_previews(source, sid, done, report)
    library.update_session(sid, status="ready", language=language or "")
    library.purge_old_chat()
    report("Done", 1.0)
    return done
