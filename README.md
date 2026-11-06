# Clip Studio

Stream normally. When OBS stops recording, Clip Studio builds a ranked shortlist of your best moments on your own PC. You review them, fix a trim or a word, and export 9:16 clips with captions.

The market research behind these decisions is in [reports/Stream clipping tools and gaps.md](reports/Stream%20clipping%20tools%20and%20gaps.md).

## How it works

1. **During the stream:** only light logging runs. The app records chat and your moment markers (F9, or saving an OBS replay). Nothing touches the GPU.
2. **After the stream:** analysis waits until the stream has ended, then runs in a low-priority background process.
   - Pass 1 ranks the whole stream from audio, chat and markers.
   - Pass 2 runs speech recognition only on the shortlisted windows, which keeps it fast without a GPU.
3. **Review desk:** each clip says why it was picked. Trim, add setup, edit captions and undo anything.
4. **Export:** clips render at 1080x1920 with a hardware encoder when one works.

## Run it

Needs Python 3.12 and FFmpeg on PATH.

```
py -3.12 -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python main.py
```

In OBS, turn on Tools > WebSocket Server Settings and put the password in Clip Studio's Settings. You can also press **Add a recording** to try it on any existing video.

The first analysis downloads the speech model, about 480 MB for the default size.

## Tests

```
.venv\Scripts\python -m pip install pytest
.venv\Scripts\python -m pytest tests
```

## Code map

| File | Job |
|---|---|
| `clipstudio/detect.py` | Scores moments, learns chat delay, sets clip edges |
| `clipstudio/analyze.py` | The two-pass post-stream pipeline |
| `clipstudio/transcribe.py` | faster-whisper with word timings |
| `clipstudio/roman.py` | Devanagari to Roman captions |
| `clipstudio/captions.py` | Burned-in ASS captions |
| `clipstudio/render.py` | FFmpeg layouts and export |
| `clipstudio/obs.py` | obs-websocket v5 client and session tracking |
| `clipstudio/chat.py` | Twitch, Kick and YouTube chat logging, chat file import |
| `clipstudio/worker.py` | The separate background process |
| `clipstudio/ui/` | PySide6 interface |

## Before a public release

- Bundle an LGPL FFmpeg in `tools/`, without x264 or x265, and confirm it includes libass and the hardware encoders.
- Get legal review of H.264/AAC patents and CUDA redistribution.
- Check the name: "Clip Studio" is close to Clip Studio Paint, and another project uses `clips-studio`.
- Review the terms for the unofficial chat connections, especially Kick's.
