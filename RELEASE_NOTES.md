Clip Studio now finds kills, deaths and funny moments, and every clip comes out at full phone loudness.

**This is an early version.** Expect rough edges, and please report what breaks.

## New in this version

- **Smarter clip picking:** laughter marks funny moments. In Valorant, the game's own HUD shows kills, your deaths and clutches, and menus, lobbies and scoreboards are skipped. Each clip carries a tag: Funny, Kill, Death or Hype.
- **Choose what you want:** in Settings, set how much you want funny moments, kills, deaths and loud moments.
- **A real editor:** play, pause, jump 5 seconds, step one frame, set the start or end, cut out a part, split a clip, and undo or redo any change. Every tool has a keyboard key.
- **Sound fixed:** clips export at -14 LUFS, the level phones play at, so they are no longer too quiet. The preview plays at that level too. You can also change the clip volume, add fades and mute a part.
- **Better captions:** a stronger speech model, the stream's language decided across the whole stream instead of from the first clip, and unclear speech left blank instead of filled with made-up words. You can also caption in English translation, and pick caption size, height and colour.
- **More flexible review desk:** resize the panels, filter and sort clips, and see kills, deaths and laughter on the stream map.

Streams analyzed by an older version keep their clips. Choose **Analyze again** on a stream to get the new picking.

## Install

1. Download `ClipStudio-Setup.exe` below and run it.
2. Windows may show "Windows protected your PC" because the app is not signed yet. Click **More info**, then **Run anyway**.

You need Windows 10 or 11. The first analysis downloads about 1.8 GB of models. Past streams are large, so a 2-hour stream can need around 10 GB of free space while it downloads.

## Known limits

- Only clip streams you own or have permission to use.
- Kills and deaths are read from Valorant only. Other games are clipped from laughter, speech, chat and loudness.
- A webcam over Valorant's top bar can hide one enemy, so some kills are missed.
- Laughter from teammates in voice chat also counts as a funny moment.
- Captions on noisy game audio can still be wrong or missing. You can edit them before export.
- Without a set-up NVIDIA graphics card, captions take about 15 minutes for a 2.5-hour stream.
- The OBS connection has not been tested with a real copy of OBS yet.
- Twitch and Kick links have not been tested on real streams yet. Their past chat is not fetched automatically.
- Recordings that OBS splits into parts export correctly but have no preview.
