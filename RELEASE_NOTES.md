Clip Studio 0.7.2 says clearly when an analysis is done, lets you change settings for all clips at once, and deletes a stream's or clip's files when you remove it.

## New in this version

- **"Analysis complete":** when a stream is done, the progress panel ticks every step and says how many clips are ready, then slides away. Before, the captions written in the background afterwards made the panel jump back to the start, so it looked like the analysis was running again.
- **Settings for all clips:** a new **This clip / All clips** switch in the review desk. With All clips on, sound (volume, loudness, fades), caption style, layout, crop position, zoom and the kill counter change on every clip of the stream at once, and one undo takes it back. Cuts, length, name, hook and caption words stay per clip.
- **Removing deletes the files:** removing a stream from the list now also deletes its recording and its exported clips, and removing a clip (the new bin button next to Export) deletes its exported video. They go to the Recycle Bin, and the app asks first and says what will go. A recording another stream in the list still uses is kept.

From 0.7.1:

- **Kills in vertical streams:** if you stream with your webcam stacked over the game, Clip Studio finds the game picture inside the layout and reads it.
- **Every kill round and every death is a clip**, named Kill, Double kill, Triple kill, Quadra kill or Ace, with won 1vN clutches joined in.
- **Ten games**, with **Teach a kill** for every game other than Valorant.
- **Punch-in zoom, hook text and a kill counter** on your clips, and **search what was said** across all clips.

## Install

1. Download `ClipStudio-Setup.exe` below and run it. It updates an existing install and keeps your streams and clips.
2. Windows may show "Windows protected your PC" because the app is not signed yet. Click **More info**, then **Run anyway**.

You need Windows 10 or 11. The first analysis downloads about 1.8 GB of models. Past streams are large, so a 2-hour stream can need around 15 GB of free space while it downloads.

## Known limits

- Only clip streams you own or have permission to use.
- Valorant is the only game read from its HUD. The other nine need two marked kills first, and they find your kills but not your deaths.
- Teach a kill was tested on test videos, not yet on real recordings of each game. Mark another kill if it misses some.
- A multi-kill where the game's kill notice never leaves the screen between kills can count as one kill.
- Hindi captions on noisy game audio can still contain wrong words. You can edit them before export.
- The virality score is a guide for what to post first, not a promise about views.
- Without a set-up NVIDIA graphics card, captions take about 15 minutes for every 2.5 hours of stream.
- Twitch and Kick links have not been tested on real streams yet.
