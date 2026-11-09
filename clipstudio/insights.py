"""Which clip to post first, and what to call it. Pure logic over what analysis already knows about each clip.

The virality score (0 to 99) is a prioritising aid, like the ones Opus Clip and StreamYard show: it rewards what short
clips that travel tend to share. A hook in the first seconds, a reaction you can hear, a kill or a laugh, a length that
holds attention, and a moment that stood out from the rest of the stream. It is not a promise about views.
"""
import re

from . import edit as clip_edit
from . import games as game_list
from .games import GAMES
from .roman import to_roman

REACTION = re.compile(r"\b(bhai|bro|kya|what|oh|no+|omg|wtf|haha+|lol|yaar|arre|abe|wow|bruh|damn|crazy|insane|"
                      r"clutch|ace|sorry|kaise|kaisa|nahi|nooo+)\b", re.I)
GAME_TAGS = {g["name"]: g["tags"] for g in GAMES.values()}
KIND_TAGS = {"kills": ["#clutch", "#headshot"], "funny": ["#funny", "#funnymoments"], "deaths": ["#fail", "#gamingfails"],
             "hype": ["#hype"], "marked": ["#highlights"]}
LANGUAGE_TAGS = {"hi": ["#hindi", "#hinglish", "#indiangamer"], "bn": ["#bengali", "#indiangamer"],
                 "en": ["#gamer"]}
STREAM_TAGS = {"funny": ["#funny", "#funnymoments"], "hype": ["#viral"], "marked": ["#highlights"]}
STREAM_LANGUAGE_TAGS = {"hi": ["#hindi", "#hinglish"], "bn": ["#bengali"], "en": []}
TEMPLATES = {
    "kills": ["This clutch was insane", "One tap. No mercy", "How did I hit that?"],
    "funny": ["I couldn't stop laughing", "Bhai ye kya tha", "We are not okay"],
    "deaths": ["Why does this always happen to me", "I did NOT see that coming", "Pain."],
    "hype": ["Chat went crazy for this", "The loudest moment of the stream", "This is why I stream"],
    "marked": ["You have to see this", "Best moment of the stream", "Wait for it"],
}


def searchable(text):
    """Lower case Roman letters and digits only, so "भाई", "Bhai!" and "bhai" all read the same."""
    return " ".join(re.sub(r"[^\w]+", " ", to_roman(text or "").lower()).split())


def find(clip, query):
    """Stream time where the query was said in this clip, the clip start for a name match, or None."""
    q = searchable(query)
    if not q:
        return None
    words = clip.get("words") or []
    text, starts = "", []
    for w in words:
        starts.append(len(text))
        text += searchable(w["w"]) + " "
    at = (" " + text).find(" " + q)        # from the start of a word, so "ace" does not match "place"
    if at >= 0:
        return words[max(i for i, s in enumerate(starts) if s <= at)]["s"]
    return clip["start"] if q in searchable(clip.get("title")) else None


def virality(clip, best_score=None):
    """0 to 99. best_score is the stream's top non-hotkey score, so a clip is judged against its own stream."""
    words = clip.get("words") or []
    keep = clip_edit.keep_ranges(clip) if "edit" in clip else [(clip["start"], clip["end"])]
    start, length = keep[0][0], sum(b - a for a, b in keep)
    tags = clip.get("tags") or []
    points = 0.0
    # Stood out from the stream: up to 30
    score = clip.get("score", 0)
    relative = 1.0 if score >= 100 else score / max(best_score or score or 1, 1)
    points += 30 * max(0.0, min(relative, 1.0))
    # A hook: someone speaks or reacts in the first 3 seconds, up to 20
    opening = [w for w in words if w["s"] - start <= 3]
    points += 12 if opening else 0
    points += 8 if any(REACTION.search(w["w"]) for w in opening) else 0
    # A reaction you can hear anywhere in the clip, up to 12
    reactions = sum(1 for w in words if REACTION.search(w["w"]))
    points += min(reactions, 4) * 3
    # What happened, up to 22
    kinds = {"kills": 12, "funny": 12, "marked": 10, "deaths": 8, "hype": 6}
    points += min(sum(kinds.get(t, 0) for t in tags), 22)
    if "clutch" in " ".join(clip.get("reasons") or []).lower():
        points += 4
    # A length that holds attention: 15 to 35 seconds is best, up to 12
    if 15 <= length <= 35:
        points += 12
    elif 10 <= length <= 50:
        points += 7
    elif length <= 59:
        points += 3
    return int(max(0, min(round(points), 99)))


def label(score):
    return "Post this first" if score >= 75 else "Strong" if score >= 55 else "Worth a look" if score >= 35 else "Weak"


def hashtags(clip, game="", language=""):
    key = game_list.key_of(game)
    playing = not key or game_list.is_game(key)       # podcasts, IRL and Just Chatting are not #gaming
    tags = ["#shorts"] + (["#gaming"] if playing else [])
    tags += GAME_TAGS.get(game, ["#" + re.sub(r"\W", "", game.lower())] if game else [])
    kind_tags = KIND_TAGS if playing else STREAM_TAGS
    kills_read = not key or game_list.notice_word(key) == "kill"
    for kind in (clip.get("tags") or [])[:2]:
        if kind != "kills" or kills_read:
            tags += kind_tags.get(kind, [])
    tags += (LANGUAGE_TAGS if playing else STREAM_LANGUAGE_TAGS).get(language, [])
    seen, out = set(), []
    for t in tags:
        if t not in seen and len(t) > 1:
            seen.add(t)
            out.append(t)
    return out[:10]


def titles(clip, game=""):
    """Three title ideas: the words spoken at the peak, then two that fit what kind of moment it is."""
    out = []
    peak = clip.get("peak", clip["start"])
    spoken = " ".join(w["w"].strip() for w in clip.get("words") or [] if peak - 6 <= w["s"] <= peak + 3).strip(" ,.")
    if 2 <= len(spoken.split()) <= 9:
        out.append(spoken[0].upper() + spoken[1:] + (" 😳" if "funny" not in (clip.get("tags") or []) else " 💀"))
    kind = (clip.get("tags") or ["hype"])[0]
    key = game_list.key_of(game)
    if kind in ("kills", "deaths") and key and game_list.notice_word(key) != "kill":
        kind = "hype"       # a goal or a K.O. is not "One tap", and a podcast has no deaths
    options = TEMPLATES.get(kind, TEMPLATES["hype"])
    turn = int(clip.get("id") or clip.get("rank") or 0)       # neighbouring clips start on different ideas
    for i in range(len(options)):
        if len(out) >= 3:
            break
        out.append(options[(turn + i) % len(options)] + (" | " + game if game else ""))
    return out[:3]


def post_text(clip, game="", language=""):
    """What goes next to an exported clip: a title and its hashtags, ready to paste."""
    return "%s\n\n%s\n" % ((titles(clip, game) or ["Clip"])[0], " ".join(hashtags(clip, game, language)))
