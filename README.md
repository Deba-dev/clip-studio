# Clip Studio

Stream normally. When OBS stops recording, Clip Studio builds a ranked shortlist of your best moments on your own PC. You can also paste the link to a finished YouTube, Twitch or Kick stream. You review the shortlist, fix a trim or a word, and export 9:16 clips with captions.

The market research behind these decisions is in [reports/Stream clipping tools and gaps.md](reports/Stream%20clipping%20tools%20and%20gaps.md) and [reports/Clipping apps - how they work and features.md](reports/Clipping%20apps%20-%20how%20they%20work%20and%20features.md). Every feature, with a way to check it, is listed in [FEATURES.md](FEATURES.md).

## How it works

1. **During the stream:** only light logging runs. The app records chat and your moment markers (F9, or saving an OBS replay). Nothing touches the GPU.
2. **After the stream:** analysis waits until the stream has ended, then runs in a low-priority background process.
   - Pass 1 reads the audio once for loudness and for sounds: laughter, gunfire and shouting.
   - Pass 2 finds the game picture inside the recording first, so a vertical stream (webcam stacked over a cropped game) reads like a plain one. It then reads the keyframes for the game's own HUD. In Valorant that gives every kill, your deaths, clutches and which parts are menus, and each kill is checked for being yours. Kills are grouped per round into Kill, Double, Triple, Quadra and Ace clips, with the quiet walking between kills cut out, and every death becomes a clip too.
   - Ten games are known: Valorant, Counter-Strike 2, BGMI, PUBG: Battlegrounds, Free Fire, Call of Duty: Mobile, Call of Duty: Warzone, Fortnite, Apex Legends and Overwatch 2. Valorant is read from its HUD. The others learn your kill notice once (**Teach a kill**: pause on two of your kills and press *This frame shows my kill*), and every later stream of that game is read with it.
   - The review desk says what the game reader saw on each stream, or why it found no kills.
   - Pass 3 runs speech recognition only on the shortlisted clips, which keeps it fast without a GPU.
3. **Review desk:** each clip says why it was picked and carries a tag: Funny, Kill, Death or Hype. A live phone preview shows the real layout, captions and loudness. Cut, split, trim, mute, fade and change caption style, with undo and redo on all of it. Search finds any word said in any clip, in Hindi or Roman letters.
   - **Punch-in zoom:** the picture snaps in on the game at the second of each kill or death, and on your webcam when you laugh. The times come from the HUD and the sound model, not guessed from the transcript.
   - **Hook:** big text over the first 2.6 seconds, typed or suggested from the clip's title ideas.
   - **Kill counter:** KILL, DOUBLE KILL, TRIPLE KILL pops up at the frame each kill lands, named the way the game names it.
4. **Export:** clips render at 720p, 1080p or 1440p, at the stream's frame rate up to 60 fps, and at -14 LUFS, the level phones play at, with a hardware encoder when one works. Low-quality streams can be cleaned up and sharpened, or AI upscaled on the graphics card.

## Editing keys

| Key | Does |
|---|---|
| Space | Play or pause |
| Left, Right | Back or forward 1 second |
| J, L | Back or forward 5 seconds |
| `,` `.` | One frame back or forward |
| Home, End | Clip start or end |
| `[` `]` | Start or end the clip here |
| I, O, Delete | Mark a part, then cut it out |
| S | Split into two clips |
| M | Mute the preview |
| Ctrl+Z, Ctrl+Y | Undo, redo |
| K, X | Keep, skip |

## Run it

Needs Python 3.12 and FFmpeg on PATH.

```
py -3.12 -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python main.py
```

In OBS, turn on Tools > WebSocket Server Settings and put the password in Clip Studio's Settings. You can also press **Add a recording** to try it on any existing video.

The first analysis downloads the speech model, about 1.6 GB for the default size, a 145 MB model that identifies the language, and a 16 MB sound model.

## Tests

```
.venv\Scripts\python -m pip install pytest
.venv\Scripts\python -m pytest tests
```

## Code map

| File | Job |
|---|---|
| `clipstudio/detect.py` | Scores moments, learns chat delay, sets clip edges |
| `clipstudio/sound.py` | Laughter, gunfire and shouting from the audio |
| `clipstudio/hud.py` | Reads kills and deaths from Valorant's HUD |
| `clipstudio/view.py` | Finds the game picture inside vertical and boxed layouts |
| `clipstudio/games.py` | The ten games: names, title matching, multi-kill names, the reader's report |
| `clipstudio/teach.py` | Teach a kill: learns any game's kill notice from marked examples, then finds every kill |
| `clipstudio/edit.py` | Cuts, mutes and loudness targets, shared by preview and export |
| `clipstudio/effects.py` | Punch-in zooms placed on kills, deaths and laughs, the hook text and the kill counter |
| `clipstudio/analyze.py` | The post-stream pipeline |
| `clipstudio/transcribe.py` | faster-whisper with word timings |
| `clipstudio/roman.py` | Devanagari to Roman captions |
| `clipstudio/captions.py` | Burned-in ASS captions |
| `clipstudio/render.py` | FFmpeg layouts and export |
| `clipstudio/obs.py` | obs-websocket v5 client and session tracking |
| `clipstudio/chat.py` | Twitch, Kick and YouTube chat logging, chat file import |
| `clipstudio/worker.py` | The separate background process |
| `clipstudio/fetch.py` | Downloads past streams and YouTube chat replay |
| `clipstudio/insights.py` | Virality score, title ideas, hashtags and transcript search |
| `clipstudio/account.py`, `plans.py` | Sign-in, Premium, and the free plan's caps |
| `clipstudio/ui/premium.py`, `ui/recent.py` | Premium screens, recent-streams picker |
| (payments) | Sign-in, Premium and gift keys come from ZunimiLabs Pay, a separate project shared by every ZunimiLabs app |
| `clipstudio/upscale.py` | Optional AI upscaling with Real-ESRGAN for low-quality streams |
| `clipstudio/cleanup.py` | Removes the app's own leftovers at start and after each update |
| `clipstudio/ui/fx.py` | Motion system, icons and custom controls |
| `clipstudio/ui/phone.py` | Live 9:16 preview |
| `clipstudio/ui/timeline.py` | Activity map and trim bar |
| `clipstudio/ui/` | The rest of the PySide6 interface |

## Before a public release

- Bundle an LGPL FFmpeg in `tools/`, without x264 or x265, and confirm it includes libass and the hardware encoders.
- Get legal review of H.264/AAC patents and CUDA redistribution.
- Check the name: "Clip Studio" is close to Clip Studio Paint, and another project uses `clips-studio`.
- Review the terms for the unofficial chat connections, especially Kick's.
- Review link downloads with a lawyer. YouTube's and Kick's terms restrict downloading, so the app asks users to confirm they own the stream or have permission.
