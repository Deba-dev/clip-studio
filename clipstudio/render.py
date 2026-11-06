"""Renders a finished 1080x1920 clip with FFmpeg. Uses the GPU encoder when one works, after the stream only."""
import os
import re
import subprocess
import tempfile

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


def layout_filter(layout, size, facecam=None):
    """Builds the video graph. Output pad is [v]. facecam is (x, y, w, h) in source pixels."""
    width, height = size
    if layout == "auto":
        layout = "stack" if facecam else "blur"
    if layout == "stack" and facecam:
        x, y, w, h = facecam
        cam_h = 680
        game_h = 1920 - cam_h
        return ("[0:v]split=2[a][b];"
                "[a]crop=%d:%d:%d:%d,scale=1080:%d:force_original_aspect_ratio=increase,crop=1080:%d[cam];"
                "[b]scale=-2:%d,crop=1080:%d[game];"
                "[cam][game]vstack=inputs=2,setsar=1[v]") % (w, h, x, y, cam_h, cam_h, game_h, game_h)
    if layout == "crop":
        return "[0:v]scale=-2:1920,crop=1080:1920,setsar=1[v]"
    return ("[0:v]split=2[a][b];"
            "[a]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=24:2,eq=brightness=-0.12[bg];"
            "[b]scale=1080:-2[fg];"
            "[bg][fg]overlay=0:(H-h)/2,setsar=1[v]")


def build_command(source, clip, size, out_path, ass_path=None, facecam=None, encoder=None, track=0):
    graph = layout_filter(clip.get("layout", "auto"), size, facecam)
    if ass_path:
        graph = graph[:-3] + ",subtitles='%s'[v]" % filter_path(ass_path)
    name, args = encoder or pick_encoder()
    return [tool("ffmpeg"), "-v", "error", "-y", "-progress", "pipe:1", "-nostats",
            "-ss", "%.3f" % clip["start"], "-t", "%.3f" % (clip["end"] - clip["start"]), *input_args(source),
            "-filter_complex", graph, "-map", "[v]", "-map", "0:a:%d?" % track,
            "-c:v", name, *args, "-pix_fmt", "yuv420p", "-r", "30",
            "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", out_path]


def export_clip(source, clip, size, folder, facecam=None, on_progress=None):
    """Writes to a temporary name first, so a crash can never leave a broken file that looks finished."""
    base = clean_name(clip.get("title") or "clip %d" % clip.get("rank", 1))
    final = os.path.join(folder, base + ".mp4")
    n = 2
    while os.path.exists(final):
        final = os.path.join(folder, "%s (%d).mp4" % (base, n))
        n += 1
    partial = final + ".part.mp4"
    length = clip["end"] - clip["start"]
    with tempfile.TemporaryDirectory(prefix="clipstudio") as tmp:
        ass = None
        if clip.get("words"):
            ass = os.path.join(tmp, "captions.ass")
            with open(ass, "w", encoding="utf-8") as f:
                f.write(build_ass(clip["words"], clip["start"], clip["end"]))
        cmd = build_command(source, clip, size, partial, ass, facecam)
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
