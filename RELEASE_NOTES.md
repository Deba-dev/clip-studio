The first public test version of Clip Studio. It finds the best moments in your stream and turns them into vertical clips with captions, on your own PC.

**This is an early version.** Expect rough edges, and please report what breaks.

## What it does

- **Clip a past stream:** paste a YouTube, Twitch or Kick link, or add a video file from your PC.
- **Clip after you stream:** connect OBS and your shortlist builds itself when recording stops. Press F9 live to mark a moment.
- **Review before you post:** each clip says why it was picked. Preview the vertical layout and captions on a phone screen, drag trim handles that snap to words, fix caption text, and undo anything.
- **Export:** 1080x1920 video with word-by-word captions, using your graphics card when it can.

Analysis runs on your PC. You choose where downloads and clips are saved.

## Install

1. Download `ClipStudio-Setup.exe` below and run it.
2. Windows may show "Windows protected your PC" because the app is not signed yet. Click **More info**, then **Run anyway**.

You need Windows 10 or 11. The first analysis downloads a speech model of about 480 MB. Past streams are large, so a 2-hour stream can need around 10 GB of free space while it downloads.

## Known limits

- Only clip streams you own or have permission to use.
- The OBS connection has not been tested with a real copy of OBS yet.
- Clip picking has not been tested widely on real streams.
- Hindi and Hinglish captions use a general speech model, so expect mistakes. You can edit them before export.
- Twitch and Kick links have not been tested on real streams yet. Their past chat is not fetched automatically.
- Recordings that OBS splits into parts export correctly but have no preview.
- Posting straight to YouTube Shorts is not included yet.
