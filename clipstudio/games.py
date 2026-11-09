"""The games Clip Studio knows: names, how to recognise a stream of them, and what a multi-kill is called.

Valorant has a built-in reader (hud.py): its HUD is read directly, with nothing to teach. Every other game is taught
once with a few examples of your own kill notice (teach.py), and that lesson is reused on every later stream.

`notice` boxes are starting guesses, in 1920x1080 game pixels, for where each game shows the notice for your own kill.
They are only guesses: the learner also tries boxes across the whole screen and keeps whichever one really tells your
kills apart, so a wrong guess costs nothing but a little time.
"""
import re

VALORANT_NAMES = {1: "Kill", 2: "Double kill", 3: "Triple kill", 4: "Quadra kill", 5: "Ace"}
BR_NAMES = {1: "Kill", 2: "Double kill", 3: "Triple kill", 4: "Squad wipe"}
COD_NAMES = {1: "Kill", 2: "Double kill", 3: "Triple kill", 4: "Fury kill", 5: "Frenzy kill", 6: "Super kill",
             7: "Mega kill"}

GAMES = {
    "valorant": {"name": "Valorant", "aliases": ("valorant", "valo"), "reader": "valorant", "rounds": True,
                 "notice": [(810, 760, 300, 200), (1480, 80, 430, 260)], "names": VALORANT_NAMES,
                 "tags": ["#valorant", "#valorantclips", "#valorantindia"]},
    "cs2": {"name": "Counter-Strike 2", "aliases": ("cs2", "csgo", "cs go", "counter strike", "counter-strike"),
            "rounds": True, "notice": [(1400, 60, 510, 260)],
            "names": {1: "Kill", 2: "2K", 3: "3K", 4: "4K", 5: "Ace"}, "tags": ["#cs2", "#counterstrike", "#cs2clips"]},
    "bgmi": {"name": "BGMI", "aliases": ("bgmi", "battlegrounds mobile", "pubg mobile", "pubgm"), "gap": 30,
             "notice": [(610, 640, 700, 150), (1380, 40, 520, 140)], "names": BR_NAMES,
             "tags": ["#bgmi", "#bgmiclips", "#bgmiindia"]},
    "pubg": {"name": "PUBG: Battlegrounds", "aliases": ("pubg pc", "pubg battlegrounds", "pubg: battlegrounds",
                                                         "pubg"), "gap": 30,
             "notice": [(620, 700, 680, 140), (1500, 40, 400, 120)], "names": BR_NAMES,
             "tags": ["#pubg", "#pubgpc", "#pubgclips"]},
    "freefire": {"name": "Free Fire", "aliases": ("free fire", "freefire", "ff max", "garena"), "gap": 30,
                 "notice": [(660, 150, 600, 200), (660, 600, 600, 180)], "names": BR_NAMES,
                 "tags": ["#freefire", "#freefiremax", "#ffclips"]},
    "codm": {"name": "Call of Duty: Mobile", "aliases": ("codm", "cod mobile", "call of duty mobile"), "gap": 20,
             "notice": [(760, 600, 400, 260)], "names": COD_NAMES, "tags": ["#codm", "#codmobile", "#callofduty"]},
    "warzone": {"name": "Call of Duty: Warzone", "aliases": ("warzone", "call of duty", "cod "), "gap": 30,
                "notice": [(760, 560, 400, 250)], "names": COD_NAMES, "tags": ["#warzone", "#callofduty", "#cod"]},
    "fortnite": {"name": "Fortnite", "aliases": ("fortnite",), "gap": 30,
                 "notice": [(660, 700, 600, 130)], "names": BR_NAMES, "tags": ["#fortnite", "#fortniteclips"]},
    "apex": {"name": "Apex Legends", "aliases": ("apex legends", "apex"), "gap": 30,
             "notice": [(660, 580, 600, 170)], "names": {1: "Kill", 2: "Double kill", 3: "Squad wipe"},
             "tags": ["#apexlegends", "#apex", "#apexclips"]},
    "overwatch": {"name": "Overwatch 2", "aliases": ("overwatch", "ow2"), "gap": 20,
                  "notice": [(660, 680, 600, 150)],
                  "names": {1: "Kill", 2: "Double kill", 3: "Triple kill", 4: "Quadruple kill", 5: "Quintuple kill",
                            6: "Team kill"}, "tags": ["#overwatch2", "#overwatch"]},
}
DEFAULT_GAP = 25        # seconds between kills that still count as one fight, for games without rounds


def key_of(name):
    """The game key for a stored name or key, or "" when unknown."""
    text = (name or "").strip().lower()
    for key, g in GAMES.items():
        if text in (key, g["name"].lower()):
            return key
    return ""


def name_of(key):
    return GAMES[key]["name"] if key in GAMES else ""


def guess(text):
    """The game a stream title names, for example "VALORANT LIVE | ranked grind" or "BGMI rush gameplay"."""
    low = " " + re.sub(r"[^\w:]+", " ", (text or "").lower()) + " "
    for key, g in GAMES.items():
        if any(" " + alias.strip() + " " in low for alias in g["aliases"]):
            return key
    return ""


def multi_name(key, n):
    names = GAMES.get(key, {}).get("names", VALORANT_NAMES)
    if n in names:
        return names[n]
    return "%d kills" % n


def fight_gap(key):
    return GAMES.get(key, {}).get("gap", DEFAULT_GAP)


def taught(key):
    """Games that need a lesson: everything without a built-in reader."""
    return key in GAMES and GAMES[key].get("reader") is None


def describe(seen):
    """One or two sentences on what the game reader found in a stream, for the review desk."""
    if not seen:
        return ""
    where = {"vertical": " The game was found inside your vertical layout.",
             "boxed": " The game was found inside your layout."}.get(seen.get("layout"), "")
    if seen.get("reader") == "valorant":
        team = seen.get("team_kills", 0)
        return ("Valorant HUD: %d rounds, %d kills by you%s, %d deaths, %d clutches.%s" % (
            seen.get("rounds", 0), seen.get("kills", 0), " (%d by teammates)" % team if team else "",
            seen.get("deaths", 0), seen.get("clutches", 0), where))
    if seen.get("reader") == "banner":
        return ("Valorant: %d kills read from your kill banner. The top bar with the players is not in this "
                "picture, so deaths and rounds come from your voice and sound.%s" % (seen.get("kills", 0), where))
    if seen.get("reader") == "taught":
        return "%s: %d kills found from the kill notice you taught.%s" % (seen.get("game") or "This game",
                                                                         seen.get("kills", 0), where)
    why = seen.get("why") or "No game was recognised, so clips come from your voice, laughter, chat and loudness."
    return "No kills read. " + why + where
