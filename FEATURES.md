# Clip Studio feature list

Every feature in the app, with what it does. **New** marks what version 0.7.0 added. Each new feature has a quick way to check it. ★ marks features no other clipping app was found to offer in [the research](reports/Clipping%20apps%20-%20how%20they%20work%20and%20features.md).

## Finding clips

| | Feature | What it does | How to check it |
|---|---|---|---|
| | Post-stream analysis | Starts when OBS stops recording, runs at low priority on your PC, never during the stream | Stop a recording in OBS |
| | Past stream links | Paste a YouTube, Twitch or Kick link; it downloads the stream and its chat replay | Streams page, add a link |
| | Hotkey markers | F9 or saving an OBS replay marks a moment that always becomes a clip | Press F9 while recording |
| | Sound reading | Finds laughter, gunfire and shouting in your audio | Funny clips say "You laughed" |
| | Chat spikes | Twitch, Kick and YouTube chat on one timeline, with the chat delay learned per channel | Clip reasons say "Chat spiked" |
| | Speech recognition | Hindi, Hinglish, Bengali and more, only on shortlisted clips so it stays fast without a GPU | Captions tab |
| | Mix of kinds | The shortlist keeps room for funny, kill and death clips, with your own weights | Settings > What to look for |
| **New** ★ | Game found in any layout | Finds the game picture inside a vertical stream (webcam on top, game below) or a boxed layout, so the game is still read. **This is why your last stream had no kill clips:** it was vertical, and the old reader gave up on anything that was not 16:9 | Analyze your vertical stream again; the line under the review title says "The game was found inside your vertical layout" |
| **New** | Every kill becomes a clip | Every kill moment is checked for being yours. Before, only the top few were checked and the rest were dropped | More Kill clips after a new analysis |
| **New** | Multi-kill clips per round | Your kills in one round are one clip: Kill, Double kill, Triple kill, Quadra kill, Ace | Filter: Kills |
| **New** | Clutches with their kills | A won 1vN round joins the kills in it: "1v3 clutch, triple kill" | A clutch clip's title |
| **New** | Every death becomes a clip | Deaths you reacted to rank first, quiet ones sit lower in the list | Filter: Deaths |
| **New** ★ | Quiet parts cut out | A slow multi-kill gets the walking between kills cut, so an 80-second ace plays in under a minute | Reasons say "The quiet parts between kills are cut out"; the trim bar shows the cuts |
| **New** | No menu clips | With the game read, loud moments in lobbies and agent select are dropped | No agent-select clips |
| **New** | Teammates' kills | Kills that were not yours become a clip only if you reacted | "Team fight" clips |
| **New** | Game reader report | The review desk says what was read (rounds, your kills, teammates' kills, deaths, clutches) or why no kills were read | The line under the review title |

## Games

| | Feature | What it does | How to check it |
|---|---|---|---|
| **New** | 10 games | Valorant, Counter-Strike 2, BGMI, PUBG: Battlegrounds, Free Fire, Call of Duty: Mobile, Call of Duty: Warzone, Fortnite, Apex Legends, Overwatch 2 | Settings > Main game, or the game picker in the review header |
| **New** | Game from the title | "BGMI rush gameplay" or "VALORANT LIVE" picks the game by itself | Add a stream with a game in its title |
| | Valorant HUD reader | Kills, your deaths, clutches and menus straight from the HUD, with nothing to teach | Valorant streams |
| **New** ★ | Teach a kill | For any game: pause on two of your kills, press **This frame shows my kill**, then **Find every kill**. It learns your kill notice and finds every other kill, now and on every later stream of that game | Review desk > Clip tab > Teach a kill |
| **New** | Game names for multi-kills | Ace in Valorant, 3K in CS2, Squad wipe in BGMI and Apex, Fury kill in Call of Duty | Clip titles and the kill counter |
| **New** | Game hashtags | Hashtags per game | Clip tab > Post it |

## Review desk

| | Feature | What it does | How to check it |
|---|---|---|---|
| | Reason and tag per clip | Why it was picked, and Funny, Kill, Death or Hype | Clip tab |
| | Live phone preview | The real 9:16 layout, captions, effects and loudness before export | Centre of the review desk |
| | Editing | Cut, split, trim, mute, fade, with undo and redo on everything | Editing keys in the README |
| | Webcam + game layout | Mark your webcam once; clips stack it over the game | Mark webcam |
| | Caption styles | 10 presets plus fonts, colours, outline, box, highlight and animation | Captions tab |
| | Virality score and sorting | Which clip to post first (Premium) | Sort: Most likely to go viral |
| | Title and hashtag ideas | Ready to copy (Premium) | Clip tab > Post it |
| | Compilations | Joins the kept clips you can see, for example only kills (Premium) | Make a compilation |
| **New** ★ | Transcript search | Finds any word said in any clip, in Hindi or Roman letters. Enter plays from just before the words | Search box above the clip list: type "bhai" |

## Effects on the clip

| | Feature | What it does | How to check it |
|---|---|---|---|
| **New** ★ | Punch-in zoom | Snaps in on the game at the second of each kill or death, and on your webcam when you laugh. Times come from the HUD and the sound, not guessed | Look tab > Punch-in zoom; play a kill clip |
| **New** | Hook text | Big text over the first 2.6 seconds, typed or suggested | Clip tab > Hook |
| **New** ★ | Kill counter | KILL, DOUBLE KILL, TRIPLE KILL pops up at the frame each kill lands | Look tab > Kill counter; play a multi-kill clip |

## Export

| | Feature | What it does | How to check it |
|---|---|---|---|
| | 9:16 export | 720p, 1080p or 1440p (Premium), up to 60 fps (Premium) | Settings > Export |
| | Phone loudness | -14 LUFS, the level Shorts, Reels and TikTok play at | Audio tab |
| | Hardware encoder | NVIDIA, AMD or Intel when one works | Faster exports |
| | Clean up and AI upscale | Sharpens enlarged pictures; Real-ESRGAN for low-quality streams (Premium) | Settings > Low-quality video |
| | Title file | A .txt with title and hashtags beside each export (Premium) | Exports folder |

## Look and feel

| | Feature | What it does | How to check it |
|---|---|---|---|
| | Motion that stays out of the way | Every animation stops while OBS records or streams, and Reduce motion turns them off | Settings > App |
| **New** | Settings page rework | One card per topic with each setting explained in a line, a side menu that follows your scrolling and glides to a section, and a search box | Open Settings, type "obs" |
| **New** | Save bar | Changes wait in a bar that slides up from the bottom: Save changes, Discard, or Ctrl+S. Leaving with unsaved changes tells you they are waiting | Change any setting |
| **New** | Game tiles | The main game is picked from tiles, not a dropdown | Settings > Game |
| **New** | Sliders in words | "What to look for" sliders say Never, Less, Normal, More or Most | Settings > Clips |
| **New** | Button ripple and sweep | A ripple spreads from where you click; primary buttons get a sweep of light on hover; icons nudge toward where they lead | Hover and click any button |
| **New** | Busy and done buttons | Buttons spin while their job runs and turn green with a check when it is done: Save changes → Saved, Check for updates → You're up to date, Export → Exported, Find every kill → Found N, Copy → Copied | Press Save changes or Export |

## App

| | Feature | What it does |
|---|---|---|
| | Pause and resume | Frees your PC mid-analysis and carries on later |
| | Safe re-analysis | Kept and exported clips are never replaced |
| | Updates | Checks, downloads and installs updates, and cleans up its own leftovers |
| | Free plan and Premium | 3 streams a week free, with caps on exports and styles; Premium removes them |

## Not built yet

- **Posting to YouTube Shorts, Reels and TikTok.** Every paid competitor has this. It needs a Google Cloud project for sign-in first.
- **Death reading for taught games.** Taught games find your kills; deaths still come from Valorant's HUD only.
- **Built-in readers for the other nine games.** They need real recordings of each game to build and test against.
