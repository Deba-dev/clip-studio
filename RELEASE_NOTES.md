Clip Studio 0.7.4 finds far more of your kills, writes captions in the Hinglish you actually speak, and works with every stream layout. It includes everything from 0.7.3.

## New in this version

- **Kills with any weapon skin:** skins replace the white skull with their own kill banner (an eye, a crest, an X diamond...). These kills used to count as your teammate's. Clip Studio now recognises any kill banner. On a real 3-hour stream, kills found went from 15 to 29.
- **Low-quality and downloaded streams:** a 360p or 720p download from YouTube used to show no players in Valorant's top bar, so no kills were found at all. It is now read as well as a 1080p recording.
- **No kill is lost:** a fight where an enemy went down while you were alive becomes a clip even when the kill banner was hidden by smoke or an ability. It ranks below your own kills, and you decide what to keep.
- **Captions in Hinglish, not English:** captions were often translated into English ("The fiend has hit, brother") or missing during fights. They now follow what you say ("dushman ko lag gaya bhai"), and Hindi words are spelled the way people type them ("dekhta", "isko").
- **Faster captions:** speech is recognised once per stream, so overlapping clips no longer read the same audio again. Your kills are also checked several at a time.
- **Every layout:** horizontal or vertical, with or without a webcam. A vertical stream with no webcam band hides Valorant's top bar, so kills are read from the kill banner alone. A vertical recording is exported whole, so your face no longer shows twice.

From 0.7.3 and 0.7.2:

- **Updates get through when GitHub is struggling:** a failed download retries, then uses GitHub's other route.
- **"Analysis complete"**, a **This clip / All clips** switch for settings, and removing a stream or clip deletes its files (to the Recycle Bin, after asking).

From 0.7.1:

- **Kills in vertical streams**, **every kill round and every death is a clip**, **ten games** with **Teach a kill**, and **punch-in zoom, hook text and a kill counter**.

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
