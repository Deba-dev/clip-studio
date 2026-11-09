"""What a stream is: the games Clip Studio knows, and the streams that are not games at all (podcasts, Just
Chatting, IRL, music). Names, how to recognise each one from a title, and what to call a run of kills.

Valorant has a built-in reader (hud.py): its HUD is read directly, with nothing to teach. A game with a notice for your
own kill (or goal, or boss win, or K.O.) is taught once with a few examples of that notice (teach.py), and the lesson is
reused on every later stream. Everything else (story games, sandbox games, racing, podcasts, IRL) has no notice to
read: its clips come from your voice, laughter, chat and the loudest moments, which works for any stream.

`notice` boxes are starting guesses, in 1920x1080 game pixels, for where each game shows the notice for your own kill.
They are only guesses: the learner also tries boxes across the whole screen and keeps whichever one really tells your
kills apart, so a wrong guess, or none, costs nothing but a little time.
"""
import re

VALORANT_NAMES = {1: "Kill", 2: "Double kill", 3: "Triple kill", 4: "Quadra kill", 5: "Ace"}
BR_NAMES = {1: "Kill", 2: "Double kill", 3: "Triple kill", 4: "Squad wipe"}
COD_NAMES = {1: "Kill", 2: "Double kill", 3: "Triple kill", 4: "Fury kill", 5: "Frenzy kill", 6: "Super kill",
             7: "Mega kill"}
SHOOTER_NAMES = {1: "Kill", 2: "Double kill", 3: "Triple kill", 4: "Quad kill"}
ROUND_NAMES = {1: "Kill", 2: "2K", 3: "3K", 4: "4K", 5: "Ace"}
MOBA_NAMES = {1: "Kill", 2: "Double kill", 3: "Triple kill", 4: "Quadra kill", 5: "Penta kill"}

# Groups, in the order the game pickers show them.
KINDS = {
    "shooter": "Shooters",
    "royale": "Battle royale",
    "moba": "MOBA and strategy",
    "story": "Story and action",
    "classic": "Old classics",
    "horror": "Horror and party",
    "sandbox": "Sandbox and survival",
    "sports": "Sports and racing",
    "fighting": "Fighting",
    "stream": "Not a game",
}
NOT_GAMES = ("stream",)


def _game(name, kind, aliases, tags, teach=None, names=None, plural=None, gap=None, notice=(), **more):
    """One entry. teach: what the notice you teach is called ("kill", "goal"), or None when there is nothing to read."""
    out = {"name": name, "kind": kind, "aliases": tuple(aliases), "tags": list(tags), "teach": teach,
           "notice": list(notice), "names": names or ({1: teach.capitalize()} if teach else {}),
           "plural": plural or ((teach + "s") if teach else "")}
    if gap is not None:
        out["gap"] = gap
    out.update(more)
    return out


def _kill(name, kind, aliases, tags, names=SHOOTER_NAMES, gap=None, notice=(), **more):
    return _game(name, kind, aliases, tags, "kill", names, "kills", gap, notice, **more)


def _story(name, aliases, tags, kind="story", **more):
    return _game(name, kind, aliases, tags, **more)


GAMES = {
    # Shooters
    "valorant": _kill("Valorant", "shooter", ("valorant", "valo"), ["#valorant", "#valorantclips", "#valorantindia"],
                      VALORANT_NAMES, notice=[(810, 760, 300, 200), (1480, 80, 430, 260)], reader="valorant",
                      rounds=True),
    "cs2": _kill("Counter-Strike 2", "shooter", ("cs2", "csgo", "cs go", "counter strike", "counter strike 2"),
                 ["#cs2", "#counterstrike", "#cs2clips"], ROUND_NAMES, notice=[(1400, 60, 510, 260)], rounds=True),
    "overwatch": _kill("Overwatch 2", "shooter", ("overwatch", "overwatch 2", "ow2"), ["#overwatch2", "#overwatch"],
                       {1: "Kill", 2: "Double kill", 3: "Triple kill", 4: "Quadruple kill", 5: "Quintuple kill",
                        6: "Team kill"}, gap=20, notice=[(660, 680, 600, 150)]),
    "r6": _kill("Rainbow Six Siege", "shooter", ("rainbow six", "rainbow six siege", "r6", "r6s", "siege"),
                ["#rainbowsixsiege", "#r6", "#r6siege"], ROUND_NAMES, notice=[(760, 600, 400, 200)], rounds=True),
    "blackops": _kill("Call of Duty: Black Ops", "shooter", ("black ops", "black ops 6", "black ops 7", "bo6", "bo7",
                                                              "cod multiplayer", "call of duty black ops"),
                      ["#blackops", "#callofduty", "#cod"], COD_NAMES, gap=20, notice=[(760, 560, 400, 250)]),
    "battlefield": _kill("Battlefield", "shooter", ("battlefield", "battlefield 6", "battlefield 2042", "bf6",
                                                    "bf2042"), ["#battlefield", "#battlefield6"], gap=20,
                         notice=[(760, 620, 400, 160)]),
    "marvelrivals": _kill("Marvel Rivals", "shooter", ("marvel rivals",), ["#marvelrivals", "#marvelrivalsclips"],
                          {1: "Kill", 2: "Double kill", 3: "Triple kill", 4: "Quad kill", 5: "Penta kill",
                           6: "Hexa kill"}, gap=20, notice=[(660, 680, 600, 150)]),
    "thefinals": _kill("The Finals", "shooter", ("the finals",), ["#thefinals", "#thefinalsclips"], gap=20),
    "halo": _kill("Halo Infinite", "shooter", ("halo", "halo infinite"), ["#halo", "#haloinfinite"],
                  {1: "Kill", 2: "Double kill", 3: "Triple kill", 4: "Overkill", 5: "Killtacular", 6: "Killtrocity"},
                  gap=10),
    "destiny": _kill("Destiny 2", "shooter", ("destiny 2", "destiny"), ["#destiny2", "#destinythegame"], gap=20),
    "tf2": _kill("Team Fortress 2", "shooter", ("team fortress", "team fortress 2", "tf2"), ["#tf2", "#teamfortress2"],
                 gap=20, notice=[(1400, 40, 510, 260)]),
    "deadlock": _kill("Deadlock", "shooter", ("deadlock",), ["#deadlock", "#deadlockgame"], MOBA_NAMES, gap=20),
    # Battle royale
    "bgmi": _kill("BGMI", "royale", ("bgmi", "battlegrounds mobile", "pubg mobile", "pubgm"),
                  ["#bgmi", "#bgmiclips", "#bgmiindia"], BR_NAMES, gap=30,
                  notice=[(610, 640, 700, 150), (1380, 40, 520, 140)]),
    "pubg": _kill("PUBG: Battlegrounds", "royale", ("pubg pc", "pubg battlegrounds", "pubg: battlegrounds", "pubg"),
                  ["#pubg", "#pubgpc", "#pubgclips"], BR_NAMES, gap=30,
                  notice=[(620, 700, 680, 140), (1500, 40, 400, 120)]),
    "freefire": _kill("Free Fire", "royale", ("free fire", "freefire", "ff max", "garena"),
                      ["#freefire", "#freefiremax", "#ffclips"], BR_NAMES, gap=30,
                      notice=[(660, 150, 600, 200), (660, 600, 600, 180)]),
    "codm": _kill("Call of Duty: Mobile", "royale", ("codm", "cod mobile", "call of duty mobile"),
                  ["#codm", "#codmobile", "#callofduty"], COD_NAMES, gap=20, notice=[(760, 600, 400, 260)]),
    "warzone": _kill("Call of Duty: Warzone", "royale", ("warzone", "call of duty", "cod"),
                     ["#warzone", "#callofduty", "#cod"], COD_NAMES, gap=30, notice=[(760, 560, 400, 250)]),
    "fortnite": _kill("Fortnite", "royale", ("fortnite",), ["#fortnite", "#fortniteclips"], BR_NAMES, gap=30,
                      notice=[(660, 700, 600, 130)]),
    "apex": _kill("Apex Legends", "royale", ("apex legends", "apex"), ["#apexlegends", "#apex", "#apexclips"],
                  {1: "Kill", 2: "Double kill", 3: "Squad wipe"}, gap=30, notice=[(660, 580, 600, 170)]),
    # MOBA and strategy
    "lol": _kill("League of Legends", "moba", ("league of legends",), ["#leagueoflegends", "#lol", "#lolclips"],
                 MOBA_NAMES, gap=12, notice=[(560, 120, 800, 200)]),
    "dota2": _kill("Dota 2", "moba", ("dota", "dota 2", "dota2"), ["#dota2", "#dota"],
                   {1: "Kill", 2: "Double kill", 3: "Triple kill", 4: "Ultra kill", 5: "Rampage"}, gap=18,
                   notice=[(560, 120, 800, 200)]),
    "mlbb": _kill("Mobile Legends", "moba", ("mobile legends", "mlbb", "ml bb"), ["#mlbb", "#mobilelegends"],
                  {1: "Kill", 2: "Double kill", 3: "Triple kill", 4: "Maniac", 5: "Savage"}, gap=12,
                  notice=[(560, 160, 800, 200)]),
    "pokemonunite": _kill("Pokémon Unite", "moba", ("pokemon unite",), ["#pokemonunite"], gap=12),
    "clashroyale": _story("Clash Royale", ("clash royale",), ["#clashroyale", "#clashroyaleclips"], "moba"),
    "coc": _story("Clash of Clans", ("clash of clans", "coc"), ["#clashofclans", "#coc"], "moba"),
    # Story and action
    "gta5": _story("GTA V", ("gta", "gta 5", "gta v", "gtav", "gta5", "gta online", "gta rp", "gtarp",
                             "grand theft auto", "grand theft auto v"), ["#gta5", "#gtav", "#gtaonline"]),
    "gta6": _story("GTA VI", ("gta 6", "gta vi", "gta6", "grand theft auto vi"), ["#gta6", "#gtavi"]),
    "rdr2": _story("Red Dead Redemption 2", ("red dead", "red dead redemption", "red dead redemption 2", "rdr2",
                                             "rdr 2"), ["#rdr2", "#reddeadredemption2"]),
    "eldenring": _game("Elden Ring", "story", ("elden ring", "nightreign", "elden ring nightreign"),
                       ["#eldenring", "#eldenringclips"], "boss win", {1: "Boss down"}, "boss wins", 10,
                       [(460, 420, 1000, 240)]),
    "darksouls": _game("Dark Souls", "story", ("dark souls", "dark souls 3", "ds3"), ["#darksouls", "#soulslike"],
                       "boss win", {1: "Boss down"}, "boss wins", 10, [(460, 420, 1000, 240)]),
    "sekiro": _game("Sekiro", "story", ("sekiro",), ["#sekiro", "#soulslike"], "boss win", {1: "Boss down"},
                    "boss wins", 10, [(460, 420, 1000, 240)]),
    "wukong": _game("Black Myth: Wukong", "story", ("black myth", "black myth wukong", "wukong"),
                    ["#blackmythwukong", "#wukong"], "boss win", {1: "Boss down"}, "boss wins", 10),
    "gow": _story("God of War", ("god of war", "gow", "god of war ragnarok", "ragnarok"),
                  ["#godofwar", "#godofwarragnarok"]),
    "spiderman": _story("Marvel's Spider-Man", ("spider man", "spiderman", "spider man 2"),
                        ["#spiderman", "#spiderman2"]),
    "tlou": _story("The Last of Us", ("last of us", "the last of us", "tlou"), ["#thelastofus", "#tlou"]),
    "cyberpunk": _story("Cyberpunk 2077", ("cyberpunk", "cyberpunk 2077"), ["#cyberpunk2077", "#cyberpunk"]),
    "ghost": _story("Ghost of Tsushima", ("ghost of tsushima", "ghost of yotei", "tsushima"),
                    ["#ghostoftsushima"]),
    "re": _story("Resident Evil", ("resident evil", "resident evil 4", "re4", "re village", "resident evil requiem"),
                 ["#residentevil", "#survivalhorror"]),
    "ac": _story("Assassin's Creed", ("assassin s creed", "assassins creed", "ac shadows", "ac valhalla"),
                 ["#assassinscreed"]),
    "hogwarts": _story("Hogwarts Legacy", ("hogwarts", "hogwarts legacy"), ["#hogwartslegacy"]),
    "uncharted": _story("Uncharted", ("uncharted",), ["#uncharted"]),
    "farcry": _story("Far Cry", ("far cry", "farcry"), ["#farcry"]),
    "batman": _story("Batman: Arkham", ("batman", "arkham", "arkham knight"), ["#batman", "#arkham"]),
    "detroit": _story("Detroit: Become Human", ("detroit become human", "detroit: become human"), ["#detroit"]),
    # Old classics
    "gtasa": _story("GTA San Andreas", ("san andreas", "gta san andreas", "gta sa"), ["#gtasanandreas", "#gtasa"],
                    "classic"),
    "gtavc": _story("GTA Vice City", ("vice city", "gta vice city", "gta vc"), ["#gtavicecity", "#vicecity"],
                    "classic"),
    "gta4": _story("GTA IV", ("gta 4", "gta iv", "gta4"), ["#gta4", "#gtaiv"], "classic"),
    "igi": _kill("Project IGI", "classic", ("igi", "project igi", "igi 2"), ["#projectigi", "#igi"], gap=20),
    "cs16": _kill("Counter-Strike 1.6", "classic", ("cs 1 6", "cs1 6", "counter strike 1 6", "cs 16"),
                  ["#cs16", "#counterstrike"], ROUND_NAMES, notice=[(1400, 40, 510, 200)], rounds=True),
    "nfsmw": _story("NFS Most Wanted", ("most wanted", "nfs most wanted", "nfs mw"), ["#nfsmostwanted", "#nfs"],
                    "classic"),
    "roadrash": _story("Road Rash", ("road rash", "roadrash"), ["#roadrash", "#retrogaming"], "classic"),
    "pop": _story("Prince of Persia", ("prince of persia",), ["#princeofpersia", "#retrogaming"], "classic"),
    "maxpayne": _story("Max Payne", ("max payne",), ["#maxpayne"], "classic"),
    "mafia": _story("Mafia", ("mafia", "mafia 2", "mafia ii"), ["#mafia", "#mafiagame"], "classic"),
    "halflife": _story("Half-Life", ("half life", "half life 2"), ["#halflife"], "classic"),
    "doom": _story("Doom", ("doom", "doom eternal"), ["#doom"], "classic"),
    "hitman": _story("Hitman", ("hitman", "hitman 3"), ["#hitman"], "classic"),
    "mario": _story("Super Mario", ("mario", "super mario"), ["#supermario", "#retrogaming"], "classic"),
    "pokemon": _story("Pokémon", ("pokemon",), ["#pokemon"], "classic"),
    "retro": _story("Retro / emulator", ("retro", "emulator", "ps2", "ps1", "psp", "nes", "snes", "sega"),
                    ["#retrogaming", "#retro"], "classic", generic=True),
    # Horror and party
    "phasmo": _story("Phasmophobia", ("phasmophobia", "phasmo"), ["#phasmophobia", "#horrorgaming"], "horror"),
    "lethal": _story("Lethal Company", ("lethal company",), ["#lethalcompany"], "horror"),
    "repo": _story("R.E.P.O.", ("r e p o", "repo game"), ["#repo", "#horrorgaming"], "horror"),
    "dbd": _story("Dead by Daylight", ("dead by daylight", "dbd"), ["#deadbydaylight", "#dbd"], "horror"),
    "outlast": _story("Outlast", ("outlast", "outlast trials"), ["#outlast", "#horrorgaming"], "horror"),
    "amongus": _story("Among Us", ("among us", "amongus"), ["#amongus"], "horror"),
    "fallguys": _story("Fall Guys", ("fall guys",), ["#fallguys"], "horror"),
    "peak": _story("Peak", ("peak game",), ["#peakgame"], "horror"),
    "horror": _story("Other horror game", ("horror", "horror game"), ["#horrorgaming", "#horror"], "horror", generic=True),
    # Sandbox and survival
    "minecraft": _story("Minecraft", ("minecraft", "mcpe", "minecraft pe"), ["#minecraft", "#minecraftclips"],
                        "sandbox"),
    "roblox": _story("Roblox", ("roblox",), ["#roblox", "#robloxclips"], "sandbox"),
    "terraria": _story("Terraria", ("terraria",), ["#terraria"], "sandbox"),
    "rust": _kill("Rust", "sandbox", ("rust",), ["#rust", "#rustgame"], gap=30),
    "ark": _story("ARK", ("ark", "ark survival", "ark survival ascended"), ["#arksurvival"], "sandbox"),
    "palworld": _story("Palworld", ("palworld",), ["#palworld"], "sandbox"),
    "valheim": _story("Valheim", ("valheim",), ["#valheim"], "sandbox"),
    "subnautica": _story("Subnautica", ("subnautica",), ["#subnautica"], "sandbox"),
    "stardew": _story("Stardew Valley", ("stardew", "stardew valley"), ["#stardewvalley", "#cozygames"], "sandbox"),
    "sims": _story("The Sims", ("sims", "the sims", "sims 4"), ["#thesims", "#sims4"], "sandbox"),
    # Sports and racing
    "eafc": _game("EA Sports FC", "sports", ("ea fc", "fc 25", "fc 26", "fc25", "fc26", "fifa", "fut"),
                  ["#eafc", "#fifa", "#fut"], "goal", {1: "Goal", 2: "Brace", 3: "Hat-trick"}, "goals", 8),
    "efootball": _game("eFootball", "sports", ("efootball", "pes"), ["#efootball", "#pes"], "goal",
                       {1: "Goal", 2: "Brace", 3: "Hat-trick"}, "goals", 8),
    "rocketleague": _game("Rocket League", "sports", ("rocket league",), ["#rocketleague", "#rlclips"], "goal",
                          {1: "Goal", 2: "Brace", 3: "Hat-trick"}, "goals", 8),
    "nba2k": _story("NBA 2K", ("nba 2k", "nba2k", "2k25", "2k26"), ["#nba2k", "#2k"], "sports"),
    "cricket24": _story("Cricket 24", ("cricket 24", "cricket 26"), ["#cricket24", "#cricketgame"], "sports"),
    "realcricket": _story("Real Cricket", ("real cricket", "rc24", "rc 24", "rc25", "rc 25"),
                          ["#realcricket", "#cricketgame"], "sports"),
    "wwe2k": _story("WWE 2K", ("wwe 2k", "wwe2k", "wwe"), ["#wwe2k", "#wwe"], "sports"),
    "forza": _story("Forza Horizon", ("forza", "forza horizon", "forza horizon 5", "forza horizon 6"),
                    ["#forzahorizon", "#forza"], "sports"),
    "nfs": _story("Need for Speed", ("need for speed", "nfs", "nfs unbound", "nfs heat"), ["#needforspeed", "#nfs"],
                  "sports"),
    "asphalt": _story("Asphalt", ("asphalt", "asphalt 9", "asphalt legends"), ["#asphalt", "#asphaltlegends"],
                      "sports"),
    "f1": _story("F1", ("f1 24", "f1 25", "f1 game"), ["#f1", "#f1game"], "sports"),
    "ets2": _story("Euro Truck Simulator", ("euro truck", "ets2", "truck simulator", "bus simulator"),
                   ["#ets2", "#trucksimulator"], "sports"),
    # Fighting
    "tekken": _game("Tekken 8", "fighting", ("tekken", "tekken 8", "tekken 7"), ["#tekken8", "#tekken"], "K.O.",
                    {1: "K.O."}, "K.O.s", 15),
    "sf6": _game("Street Fighter 6", "fighting", ("street fighter", "street fighter 6", "sf6"),
                 ["#streetfighter6", "#sf6"], "K.O.", {1: "K.O."}, "K.O.s", 15),
    "mk": _game("Mortal Kombat", "fighting", ("mortal kombat", "mortal kombat 1", "mk1", "mk11"),
                ["#mortalkombat", "#mk1"], "K.O.", {1: "K.O."}, "K.O.s", 15),
    "smash": _story("Super Smash Bros.", ("smash bros", "super smash bros", "smash ultimate"), ["#smashbros"],
                    "fighting"),
    # Not a game: clips from your voice, laughter, chat and the loudest moments
    "justchatting": _story("Just Chatting", ("just chatting", "justchatting", "q&a", "qna"), ["#justchatting", "#streamhighlights"],
                           "stream"),
    "podcast": _story("Podcast", ("podcast", "podcasts", "interview"),
                      ["#podcast", "#podcastclips"], "stream"),
    "irl": _story("IRL", ("irl", "irl stream", "vlog"), ["#irl", "#irlstream"],
                  "stream"),
    "reaction": _story("Reaction / watch along", ("reaction", "reacting", "watch along", "watchalong",
                                                  "watch party"), ["#reaction", "#reactionvideo"], "stream"),
    "music": _story("Music", ("music stream", "singing", "karaoke", "dj set"),
                    ["#music", "#livemusic"], "stream"),
    "art": _story("Art and creative", ("art stream", "drawing", "painting"),
                  ["#art", "#creative"], "stream"),
    "coding": _story("Coding and tech", ("coding", "programming"),
                     ["#coding", "#tech"], "stream"),
    "cooking": _story("Cooking", ("cooking",), ["#cooking", "#food"], "stream"),
    "fitness": _story("Fitness", ("workout", "gym stream", "yoga"), ["#fitness", "#workout"], "stream"),
    "sportswatch": _story("Sports watch along", ("ipl", "cricket live", "match live", "football live",
                                                 "live score", "ipl watchalong", "cricket watchalong", "match watchalong"), ["#cricket", "#ipl", "#sports"],
                          "stream"),
    "study": _story("Study with me", ("study with me", "study stream", "pomodoro"),
                    ["#studywithme", "#study"], "stream"),
    "other": _story("Other stream", (), ["#livestream", "#streamhighlights"], "stream"),
}
DEFAULT_GAP = 25        # seconds between kills that still count as one fight, for games without rounds


def _words(text):
    return " " + " ".join(re.sub(r"[^\w:&]+", " ", (text or "").lower()).split()) + " "


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
    """The game a stream title names, for example "VALORANT LIVE | ranked grind" or "BGMI rush gameplay".

    The longest name in the title wins, so "GTA San Andreas" is San Andreas and not GTA V, and "PUBG Mobile" is BGMI.
    A named game comes before a catch-all like "horror game", and any game before a stream that is not one:
    "Valorant podcast with friends" is a Valorant stream."""
    low = _words(text)
    best, size = "", 0
    for key, g in GAMES.items():
        for alias in g["aliases"]:
            words = _words(alias)
            weight = len(words) + (0 if g["kind"] in NOT_GAMES else 1000 if g.get("generic") else 2000)
            if words.strip() and words in low and weight > size:
                best, size = key, weight
    return best


def grouped():
    """[(group name, [(key, game name)])] in picker order."""
    return [(label, [(k, g["name"]) for k, g in GAMES.items() if g["kind"] == kind]) for kind, label in KINDS.items()]


def is_game(key):
    return key in GAMES and GAMES[key]["kind"] not in NOT_GAMES


def notice_word(key):
    """What the notice taught for this game is called ("kill", "goal", "boss win"), or "" when there is none."""
    return GAMES.get(key, {}).get("teach") or ""


def multi_name(key, n):
    g = GAMES.get(key, {})
    names = g.get("names") or VALORANT_NAMES
    if n in names:
        return names[n]
    return "%d %s" % (n, g.get("plural") or "kills")


def fight_gap(key):
    return GAMES.get(key, {}).get("gap", DEFAULT_GAP)


def taught(key):
    """Games that need a lesson: those with a notice to read and no built-in reader."""
    return key in GAMES and GAMES[key].get("reader") is None and bool(GAMES[key]["teach"])


def no_notice(key):
    """Why a stream of this kind has nothing to read on screen, and where its clips come from instead."""
    name = name_of(key)
    if not is_game(key):
        return "%s stream: clips come from your voice, laughter, chat and the loudest moments." % name
    return ("%s has no kill notice to read, so clips come from your voice, laughter, chat and the loudest moments "
            "of the game." % name)


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
        key = key_of(seen.get("game"))
        word = notice_word(key) or "kill"
        return "%s: %d %s found from the %s notice you taught.%s" % (
            seen.get("game") or "This game", seen.get("kills", 0), GAMES.get(key, {}).get("plural") or "kills",
            word, where)
    if seen.get("reader") == "none":
        return seen.get("why") or ""
    why = seen.get("why") or "No game was recognised, so clips come from your voice, laughter, chat and loudness."
    return "No kills read. " + why + where
