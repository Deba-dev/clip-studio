Clip Studio 0.5.0 makes your clips sharper and smoother, adds AI upscaling for low-quality streams, and cleans up after itself.

## New in this version

- **Full-quality downloads:** vertical streams used to download at only 360p. Every past stream now downloads at its full 1080p, from the highest-bitrate copy the platform has.
- **Choose resolution and frame rate:** in Settings > Export, pick 720p, 1080p or 1440p, and match the stream's frame rate up to 60 fps, or choose 60, 30 or 24. 1440p uploads usually stay sharper on YouTube Shorts.
- **AI upscaling:** set Low-quality video to **AI upscale**, and streams below 1080p are redrawn at 2 to 4 times their size on your graphics card. It needs a one-time 45 MB download and a graphics driver with Vulkan, and takes a couple of minutes per clip.
- **Sharper exports:** better resizing everywhere, plus a fast clean-up that smooths compression blocks and sharpens any picture enlarged for the phone screen.
- **Keeps your drive clean:** after every update, Clip Studio removes speech models your settings no longer use, half-finished downloads of streams you removed, leftovers from stopped exports, and old installers. Your streams, clips and settings are never touched.

If you added a vertical stream with an older version, remove it and add its link again to get the full-quality copy.

## Install

1. Download `ClipStudio-Setup.exe` below and run it.
2. Windows may show "Windows protected your PC" because the app is not signed yet. Click **More info**, then **Run anyway**.

You need Windows 10 or 11. The first analysis downloads about 1.8 GB of models. Past streams are large, so a 2-hour stream can need around 15 GB of free space while it downloads.

## Known limits

- Only clip streams you own or have permission to use.
- Kills and deaths are read from Valorant only. Other games are clipped from laughter, speech, chat and loudness.
- A webcam over Valorant's top bar can hide one enemy, so some kills are missed.
- AI upscaling cannot invent detail the stream never had, and surfaces can look slightly painted.
- Without a set-up NVIDIA graphics card, captions take about 15 minutes for a 2.5-hour stream.
- Twitch and Kick links have not been tested on real streams yet. Their past chat is not fetched automatically.
- Recordings that OBS splits into parts export correctly but have no preview.
