Clip Studio 0.6.1 makes the review preview smooth, lets you pause an analysis, and stops an analysis cleanly when you close the app.

## New in this version

- **Smooth preview:** the review desk no longer stutters while a clip plays. The activity map under the player was being redrawn many times a second (about 60 ms each time on a long stream); it is now drawn once, and playback only moves the playhead. The trim bar and the phone preview got the same treatment.
- **Pause and Resume:** the progress panel on the Streams page has a Pause button next to Stop. Pausing frees your PC straight away (speech recognition and FFmpeg included), and Resume carries on from exactly where it stopped.
- **Closing the app stops the analysis:** if you close Clip Studio, or the PC shuts down, during an analysis, it is cancelled instead of starting again by itself on the next launch. The stream shows *Stopped*; choose **Analyze again** from its card menu when you want it.
- **Nothing keeps running in the background:** if the app is closed in any way, including a crash or End task, the analysis and any FFmpeg it started end with it.

## Install

1. Download `ClipStudio-Setup.exe` below and run it. It updates an existing install and keeps your streams and clips.
2. Windows may show "Windows protected your PC" because the app is not signed yet. Click **More info**, then **Run anyway**.

You need Windows 10 or 11. The first analysis downloads about 1.8 GB of models. Past streams are large, so a 2-hour stream can need around 15 GB of free space while it downloads.

## Known limits

- Only clip streams you own or have permission to use.
- Kills and deaths are read from Valorant only. Other games are clipped from laughter, speech, chat and loudness.
- Hindi captions on noisy game audio can still contain wrong words. You can edit them before export.
- The virality score is a guide for what to post first, not a promise about views.
- Without a set-up NVIDIA graphics card, captions take about 15 minutes for every 2.5 hours of stream.
- Twitch and Kick links have not been tested on real streams yet.
- Background captions for a stream that already finished analysing still carry on after a restart.
