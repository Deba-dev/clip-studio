Clip Studio 0.7.7 fixes a failed analysis after a cut-off speech-model download, and lets you choose how the window opens and closes. It includes everything from 0.7.6.

## New in this version

- **A broken speech-model download fixes itself:** if the 1.6 GB model download was cut off, analysis failed with "Unable to open file 'model.bin'". Clip Studio now spots the broken download, removes it and fetches the model again. If that fails too, it says plainly that the download didn't finish and to check the internet.
- **Window modes:** Windowed, Borderless or Fullscreen in **Settings → App → Window**. F11 switches fullscreen any time.
- **Tray:** closing the window or pressing Esc keeps Clip Studio running in the tray, so it keeps listening to OBS and F9. You can switch each off, and quit from the tray icon.

From 0.7.6:

- **Film suite** and **Midnight gold** looks, switchable in Settings.

From 0.7.5:

- **More than 90 games**, **podcasts, Just Chatting and IRL**, **teach a goal, boss win or K.O.**, and a **searchable game list**.

From 0.7.4:

- **Kills with any weapon skin**, **360p and 720p downloads read**, **captions in Hinglish, not English**, **faster captions**, and **every stream layout**.

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
