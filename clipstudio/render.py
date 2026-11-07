"""Renders a finished 1080x1920 clip with FFmpeg. Uses the GPU encoder when one works, after the stream only."""
import json
import os
import re
import subprocess
import tempfile

from . import edit as clip_edit
from .captions import build_ass
from .media import HIDE, input_args
from .paths import tool

ENCODERS = [
    ("h264_nvenc", ["-preset", "p5", "-cq", "21", "-b:v", "0"]),
    ("h264_amf", ["-quality", "quality", "-rc", "cqp", "-qp_i", "21", "-qp_p", "23"]),
    ("h264_qsv", ["-global_quality", "21"]),
    ("libx264", ["-preset", "veryfast", "-crf", "20"]),
    ("libopenh264", ["-b:v", "8M"]),
]
FILTERS = ("split", "crop", "scale", "vstack", "setsar", "overlay", "gblur", "colorchannelmixer", "subtitles",
           "trim", "setpts", "concat", "asplit", "atrim", "asetpts", "afade", "volume", "loudnorm", "aresample",
           "highpass", "lowpass", "dynaudnorm", "showinfo")
_chosen = None


def pick_encoder():
    """A listed encoder may still fail on this PC, so each is tried on a tiny test render."""
    global _chosen
    if _chosen is None:
        for name, args in ENCODERS:
            test = [tool("ffmpeg"), "-v", "error", "-f", "lavfi", "-i", "color=black:s=256x256:d=0.2", "-c:v", name,
                    *args, "-f", "null", "-"]
            if subprocess.run(test, capture_output=True, creationflags=HIDE).returncode == 0:
                _chosen = (name, args)
                break
        else:
            raise RuntimeError("No working H.264 encoder was found on this PC.")
    return _chosen


def filter_path(path):
    """FFmpeg filter arguments need their own escaping, and Windows drive colons break it otherwise."""
    return path.replace("\\", "/").replace(":", "\\:").replace("'", "\\'")


def clean_name(text):
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", text).strip(" .")
    return name[:60] or "clip"


def layout_filter(layout, size, facecam=None, src="[0:v]", pan=0.0):
    """Builds the video graph. Output pad is [v]. facecam is (x, y, w, h) in source pixels.

    Only LGPL filters may appear here: the released app ships an LGPL FFmpeg, which has no boxblur or eq.
    """
    width, height = size
    if layout == "auto":
        layout = "stack" if facecam else "blur"
    if layout == "stack" and facecam:
        x, y, w, h = facecam
        cam_h = 680
        game_h = 1920 - cam_h
        return (src + "split=2[a][b];"
                "[a]crop=%d:%d:%d:%d,scale=1080:%d:force_original_aspect_ratio=increase,crop=1080:%d[cam];"
                "[b]scale=-2:%d,crop=1080:%d[game];"
                "[cam][game]vstack=inputs=2,setsar=1[v]") % (w, h, x, y, cam_h, cam_h, game_h, game_h)
    if layout == "crop":
        return src + "scale=-2:1920,crop=1080:1920:(iw-1080)*%.3f:0,setsar=1[v]" % ((pan + 1) / 2)
    return (src + "split=2[a][b];"
            "[a]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,gblur=sigma=24,"
            "colorchannelmixer=rr=0.8:gg=0.8:bb=0.8[bg];"
            "[b]scale=1080:-2[fg];"
            "[bg][fg]overlay=0:(H-h)/2,setsar=1[v]")


def join_parts(clip, kind, track=0):
    """Graph that keeps only the uncut parts. Times are relative to the input, which already starts at the clip start.

    Returns (graph text ending in a ';' or empty, the pad to read from).
    """
    keep = clip_edit.keep_ranges(clip)
    source = "[0:v]" if kind == "v" else "[0:a:%d]" % track
    if len(keep) == 1:
        return "", source
    trim, stamp, name = ("trim", "setpts", "p") if kind == "v" else ("atrim", "asetpts", "q")
    parts = []
    split = "split" if kind == "v" else "asplit"
    labels = "".join("[%s%ds]" % (name, i) for i in range(len(keep)))
    text = "%s%s=%d%s;" % (source, split, len(keep), labels)
    for i, (a, b) in enumerate(keep):
        text += "[%s%ds]%s=start=%.3f:end=%.3f,%s=PTS-STARTPTS[%s%d];" % (
            name, i, trim, a - clip["start"], b - clip["start"], stamp, name, i)
        parts.append("[%s%d]" % (name, i))
    media = "v=1:a=0" if kind == "v" else "v=0:a=1"
    return text + "%sconcat=n=%d:%s[%sall];" % ("".join(parts), len(keep), media, name), "[%sall]" % name


def audio_filters(clip, measured=None):
    """Mute and the user's gain, then loudness, so nothing the user does can make it clip. Fades go last to stay clean."""
    e = clip_edit.settings(clip)
    keep = clip_edit.keep_ranges(clip)
    steps = []
    for a, b in clip_edit.merge(e["mute"]):
        lo, hi = clip_edit.to_output(max(a, keep[0][0]), keep), clip_edit.to_output(min(b, keep[-1][1]), keep)
        if lo is not None and hi is not None and hi > lo:
            steps.append("volume=0:enable='between(t,%.3f,%.3f)'" % (lo, hi))
    if e["gain_db"] and not e["auto_loud"]:
        steps.append("volume=%.2fdB" % e["gain_db"])
    if e["auto_loud"]:
        target = clip_edit.TARGET_LUFS + e["gain_db"]
        loud = "loudnorm=I=%.1f:TP=%.1f:LRA=11" % (max(min(target, -5.0), -40.0), clip_edit.TRUE_PEAK)
        if measured:
            loud += (":measured_I=%s:measured_TP=%s:measured_LRA=%s:measured_thresh=%s:offset=%s:linear=true"
                     % (measured["input_i"], measured["input_tp"], measured["input_lra"], measured["input_thresh"],
                        measured["target_offset"]))
        else:
            loud += ":print_format=json"
        steps.append(loud)
    steps.append("aresample=48000")
    total = clip_edit.length(clip)
    if e["fade_in"] > 0:
        steps.append("afade=t=in:st=0:d=%.2f" % e["fade_in"])
    if e["fade_out"] > 0:
        steps.append("afade=t=out:st=%.2f:d=%.2f" % (max(total - e["fade_out"], 0), e["fade_out"]))
    return ",".join(steps)


def measure_loudness(source, clip, track=0):
    """First half of two-pass loudness: an audio-only read of the clip. Linear gain keeps the voice sounding natural."""
    joined, pad = join_parts(clip, "a", track)
    graph = joined + pad + audio_filters(clip) + "[a]"
    cmd = [tool("ffmpeg"), "-hide_banner", "-nostats", "-ss", "%.3f" % clip["start"],
           "-t", "%.3f" % (clip["end"] - clip["start"]), *input_args(source), "-vn", "-filter_complex", graph,
           "-map", "[a]", "-f", "null", "-"]
    out = subprocess.run(cmd, capture_output=True, text=True, errors="replace", creationflags=HIDE)
    found = re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", out.stderr)
    if not found:
        return None
    values = json.loads(found.group(0))
    return values if values["input_i"] not in ("-inf", "inf") else None


def build_command(source, clip, size, out_path, ass_path=None, facecam=None, encoder=None, track=0, audio=True,
                  measured=None):
    joined, pad = join_parts(clip, "v")
    e = clip_edit.settings(clip)
    graph = joined + layout_filter(clip.get("layout", "auto"), size, facecam, pad, e["pan"])
    if ass_path:
        graph = graph[:-3] + ",subtitles='%s'[v]" % filter_path(ass_path)
    maps = ["-map", "[v]"]
    if audio:
        joined, pad = join_parts(clip, "a", track)
        graph += ";" + joined + pad + audio_filters(clip, measured) + "[a]"
        maps += ["-map", "[a]"]
    name, args = encoder or pick_encoder()
    return [tool("ffmpeg"), "-v", "error", "-y", "-progress", "pipe:1", "-nostats",
            "-ss", "%.3f" % clip["start"], "-t", "%.3f" % (clip["end"] - clip["start"]), *input_args(source),
            "-filter_complex", graph, *maps,
            "-c:v", name, *args, "-pix_fmt", "yuv420p", "-r", "30",
            "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", out_path]


def export_clip(source, clip, size, folder, facecam=None, on_progress=None, audio=True):
    """Writes to a temporary name first, so a crash can never leave a broken file that looks finished."""
    base = clean_name(clip.get("title") or "clip %d" % clip.get("rank", 1))
    final = os.path.join(folder, base + ".mp4")
    n = 2
    while os.path.exists(final):
        final = os.path.join(folder, "%s (%d).mp4" % (base, n))
        n += 1
    partial = final + ".part.mp4"
    length = clip_edit.length(clip)
    e = clip_edit.settings(clip)
    measured = measure_loudness(source, clip) if audio and e["auto_loud"] else None
    with tempfile.TemporaryDirectory(prefix="clipstudio") as tmp:
        ass = None
        if clip.get("words"):
            ass = os.path.join(tmp, "captions.ass")
            with open(ass, "w", encoding="utf-8") as f:
                f.write(build_ass(clip_edit.retime_words(clip), 0.0, length, size=int(e["caption_size"]),
                                  margin=int(e["caption_y"]), color=e["caption_color"]))
        cmd = build_command(source, clip, size, partial, ass, facecam, audio=audio, measured=measured)
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, errors="replace",
                                creationflags=HIDE)
        for line in proc.stdout:
            if line.startswith("out_time_us=") and on_progress:
                value = line.split("=", 1)[1].strip()
                if value.isdigit():
                    on_progress(min(int(value) / 1e6 / max(length, 0.1), 1.0))
        err = proc.stderr.read()
        proc.wait()
    if proc.returncode:
        if os.path.exists(partial):
            os.remove(partial)
        raise RuntimeError("Export failed: " + err.strip()[-300:])
    os.replace(partial, final)
    return final
