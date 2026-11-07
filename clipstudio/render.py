"""Renders a finished 9:16 clip with FFmpeg. Uses the GPU encoder when one works, after the stream only."""
import json
import os
import re
import subprocess
import tempfile

from . import edit as clip_edit
from . import upscale
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
           "highpass", "lowpass", "dynaudnorm", "showinfo", "atadenoise", "cas")
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


SIZES = {"720": (720, 1280), "1080": (1080, 1920), "1440": (1440, 2560)}
MAX_FPS = 60
LOW_SOURCE = 720            # a source whose short side is below this is treated as low quality
SHARPEN_FROM = 1.5          # sharpen when the game picture is enlarged this much or more


def even(value):
    return max(int(round(value / 2)) * 2, 2)


def resolve(layout, facecam):
    if layout == "auto":
        return "stack" if facecam else "blur"
    return "blur" if layout == "stack" and not facecam else layout


def enlargement(layout, size, out=(1080, 1920), facecam=None):
    """How many times bigger the game picture gets on the phone screen."""
    width, height = size
    out_w, out_h = out
    layout = resolve(layout, facecam)
    if layout == "stack":
        return (out_h - even(out_h * 680 / 1920)) / height
    if layout == "crop":
        return out_h / height
    return out_w / width


def layout_filter(layout, size, facecam=None, src="[0:v]", pan=0.0, out=(1080, 1920), enhance="off"):
    """Builds the video graph. Output pad is [v]. facecam is (x, y, w, h) in source pixels.

    enhance "auto" cleans compression noise off a low-quality source before enlarging it, and sharpens whenever the
    picture is enlarged a lot. Only LGPL filters may appear here: the released app ships an LGPL FFmpeg, which has no
    boxblur, eq, hqdn3d or smartblur.
    """
    out_w, out_h = out
    layout = resolve(layout, facecam)
    head = ""
    if enhance == "auto" and min(size) < LOW_SOURCE:
        head, src = src + "atadenoise[clean];", "[clean]"
    tail = ",cas=strength=0.6" if enhance == "auto" and enlargement(layout, size, out, facecam) >= SHARPEN_FROM else ""
    if layout == "stack":
        x, y, w, h = facecam
        cam_h = even(out_h * 680 / 1920)
        game_h = out_h - cam_h
        return head + (src + "split=2[a][b];"
                       "[a]crop=%d:%d:%d:%d,scale=%d:%d:force_original_aspect_ratio=increase:flags=lanczos,"
                       "crop=%d:%d[cam];"
                       "[b]scale=-2:%d:flags=lanczos,crop=%d:%d[game];"
                       "[cam][game]vstack=inputs=2,setsar=1%s[v]") % (
            w, h, x, y, out_w, cam_h, out_w, cam_h, game_h, out_w, game_h, tail)
    if layout == "crop":
        return head + src + "scale=-2:%d:flags=lanczos,crop=%d:%d:(iw-%d)*%.3f:0,setsar=1%s[v]" % (
            out_h, out_w, out_h, out_w, (pan + 1) / 2, tail)
    return head + (src + "split=2[a][b];"
                   "[a]scale=%d:%d:force_original_aspect_ratio=increase,crop=%d:%d,gblur=sigma=%d,"
                   "colorchannelmixer=rr=0.8:gg=0.8:bb=0.8[bg];"
                   "[b]scale=%d:-2:flags=lanczos[fg];"
                   "[bg][fg]overlay=0:(H-h)/2,setsar=1%s[v]") % (
        out_w, out_h, out_w, out_h, round(24 * out_w / 1080), out_w, tail)


def frame_rate(choice, source_fps):
    """The chosen rate, never above the source (copied frames add size, not smoothness) and never above 60."""
    source_fps = source_fps or 30
    wanted = MAX_FPS if choice in ("source", "", None) else int(choice)
    return round(min(wanted, source_fps, MAX_FPS), 3)


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
                  measured=None, out=(1080, 1920), fps=30, enhance="off"):
    joined, pad = join_parts(clip, "v")
    e = clip_edit.settings(clip)
    graph = joined + layout_filter(clip.get("layout", "auto"), size, facecam, pad, e["pan"], out, enhance)
    if ass_path:
        graph = graph[:-3] + ",subtitles='%s'[v]" % filter_path(ass_path)
    maps = ["-map", "[v]"]
    if audio:
        joined, pad = join_parts(clip, "a", track)
        graph += ";" + joined + pad + audio_filters(clip, measured) + "[a]"
        maps += ["-map", "[a]"]
    name, args = encoder or pick_encoder()
    if name == "libopenh264":         # the only encoder with a fixed bitrate, so it grows with size and frame rate
        args = ["-b:v", "%dk" % (8000 * out[0] * out[1] / (1080 * 1920) * (1.5 if fps > 30 else 1))]
    return [tool("ffmpeg"), "-v", "error", "-y", "-progress", "pipe:1", "-nostats",
            "-ss", "%.3f" % clip["start"], "-t", "%.3f" % (clip["end"] - clip["start"]), *input_args(source),
            "-filter_complex", graph, *maps,
            "-c:v", name, *args, "-pix_fmt", "yuv420p", "-r", "%g" % fps,
            "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", out_path]


def export_clip(source, clip, size, folder, facecam=None, on_progress=None, audio=True, out=(1080, 1920), fps=30,
                enhance="off"):
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
    report = on_progress or (lambda value, note="": None)
    with tempfile.TemporaryDirectory(prefix="clipstudio") as tmp:
        share = 0.0                     # the part of the progress bar the AI upscaler uses
        if enhance == "ai":
            enhance = "auto"            # the fast filters still tidy up whatever the AI leaves
            scale = upscale.scale_for(size, enlargement(clip.get("layout", "auto"), size, out, facecam))
            if scale:
                share = 0.8
                upscale.install(lambda v: report(0.0, "Getting the AI upscaler (one time, 45 MB) %d%%" % (v * 100)))
                source = upscale.upscale(source, clip["start"], clip["end"], fps, scale, size, tmp,
                                         lambda v: report(v * share, "AI upscaling %dx" % scale))
                clip = clip_edit.shifted(clip, clip["start"])
                size = (size[0] * scale, size[1] * scale)
                facecam = tuple(v * scale for v in facecam) if facecam else None
        measured = measure_loudness(source, clip) if audio and e["auto_loud"] else None
        ass = None
        if clip.get("words"):
            ass = os.path.join(tmp, "captions.ass")
            with open(ass, "w", encoding="utf-8") as f:
                f.write(build_ass(clip_edit.retime_words(clip), 0.0, length, size=int(e["caption_size"]),
                                  margin=int(e["caption_y"]), color=e["caption_color"]))
        cmd = build_command(source, clip, size, partial, ass, facecam, audio=audio, measured=measured, out=out,
                            fps=fps, enhance=enhance)
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, errors="replace",
                                creationflags=HIDE)
        for line in proc.stdout:
            if line.startswith("out_time_us="):
                value = line.split("=", 1)[1].strip()
                if value.isdigit():
                    report(share + (1 - share) * min(int(value) / 1e6 / max(length, 0.1), 1.0), "Exporting")
        err = proc.stderr.read()
        proc.wait()
    if proc.returncode:
        if os.path.exists(partial):
            os.remove(partial)
        raise RuntimeError("Export failed: " + err.strip()[-300:])
    os.replace(partial, final)
    return final
