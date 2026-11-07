"""Everything that reads video files through FFmpeg."""
import json
import os
import subprocess

import numpy as np

from .paths import tool

HIDE = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
RATE = 16000
VOICE = "highpass=f=100,lowpass=f=7500,dynaudnorm=f=200:g=11:m=12"     # lifts quiet speech for recognition only


def input_args(source):
    """OBS auto-split recordings are joined by a small .ffconcat list, so they act like one file."""
    return ["-f", "concat", "-safe", "0", "-i", source] if source.endswith(".ffconcat") else ["-i", source]


def write_concat(files, path):
    with open(path, "w", encoding="utf-8") as f:
        f.write("ffconcat version 1.0\n")
        for name in files:
            f.write("file '%s'\n" % name.replace("\\", "/").replace("'", "'\\''"))
    return path


def probe(source):
    args = [tool("ffprobe"), "-v", "error", "-print_format", "json", "-show_format", "-show_streams"]
    args += ["-f", "concat", "-safe", "0", "-i", source] if source.endswith(".ffconcat") else [source]
    out = subprocess.run(args, capture_output=True, creationflags=HIDE)
    if out.returncode:
        raise RuntimeError("Could not read this video: " + out.stderr.decode("utf-8", "replace").strip()[-200:])
    info = json.loads(out.stdout)
    video = next((s for s in info["streams"] if s["codec_type"] == "video"), None)
    audio = [s for s in info["streams"] if s["codec_type"] == "audio"]
    if video is None:
        raise RuntimeError("This file has no video track.")
    return {"duration": float(info["format"].get("duration") or video.get("duration") or 0),
            "width": int(video["width"]), "height": int(video["height"]), "audio_tracks": len(audio)}


def loudness_per_second(source, track=0, on_progress=None, total=0.0, tap=None):
    """Mean level in dB for every second. Streams through a pipe, so a 4-hour file needs no temp space.

    tap, when given, sees every second of audio too, so sound tagging costs no second read of the file.
    """
    cmd = [tool("ffmpeg"), "-v", "error", *input_args(source), "-map", "0:a:%d" % track,
           "-ac", "1", "-ar", str(RATE), "-f", "s16le", "-"]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, creationflags=HIDE)
    chunk = RATE * 2
    levels = []
    try:
        while True:
            raw = proc.stdout.read(chunk)
            if len(raw) < 2:
                break
            samples = np.frombuffer(raw[:len(raw) // 2 * 2], dtype="<i2").astype(np.float32) / 32768.0
            if tap:
                tap(samples)
            rms = float(np.sqrt(np.mean(samples * samples))) if samples.size else 0.0
            levels.append(20 * np.log10(max(rms, 1e-5)))
            if on_progress and total and len(levels) % 60 == 0:
                on_progress(min(len(levels) / total, 1.0))
    finally:
        proc.stdout.close()
        proc.wait()
    if proc.returncode and not levels:
        raise RuntimeError("Could not read the audio track of this video.")
    return np.array(levels, dtype=np.float32)


def audio_window(source, start, length, track=0, voice=False):
    """A float32 16 kHz mono slice, ready for speech recognition."""
    cmd = [tool("ffmpeg"), "-v", "error", "-ss", "%.3f" % max(start, 0), "-t", "%.3f" % length,
           *input_args(source), "-map", "0:a:%d" % track, "-ac", "1", "-ar", str(RATE),
           *(["-af", VOICE] if voice else []), "-f", "s16le", "-"]
    out = subprocess.run(cmd, capture_output=True, creationflags=HIDE)
    if out.returncode:
        raise RuntimeError(out.stderr.decode("utf-8", "replace").strip()[-200:])
    return np.frombuffer(out.stdout[:len(out.stdout) // 2 * 2], dtype="<i2").astype(np.float32) / 32768.0


def frame_png(source, t, path, width=0):
    scale = ["-vf", "scale=%d:-2" % width, "-q:v", "4"] if width else []
    cmd = [tool("ffmpeg"), "-v", "error", "-y", "-ss", "%.3f" % t, *input_args(source), "-frames:v", "1", *scale, path]
    return subprocess.run(cmd, capture_output=True, creationflags=HIDE).returncode == 0
