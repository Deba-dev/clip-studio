"""Release gate: the packaged app must analyze a video and export a captioned clip using only what it ships with.

Runs on GitHub's build machine, which has no GPU, so it also proves the no-GPU encoder works.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, ".")
from clipstudio.db import Library  # noqa: E402
from clipstudio.render import FILTERS  # noqa: E402

APP = os.path.abspath(r"dist\ClipStudio\ClipStudio.exe")
TOOLS = os.path.abspath(r"dist\ClipStudio\_internal\tools")
FFMPEG = os.path.join(TOOLS, "ffmpeg.exe")
FFPROBE = os.path.join(TOOLS, "ffprobe.exe")


def need(ok, message):
    if not ok:
        raise SystemExit("FAILED: " + message)
    print("ok:", message)


def text(*args):
    return subprocess.run(args, capture_output=True, text=True, errors="replace").stdout


def worker(job, target, env):
    out = subprocess.run([APP, "--worker", job, str(target)], capture_output=True, text=True, encoding="utf-8",
                         env=env, timeout=1200)
    lines = out.stdout.strip().splitlines()
    print(job, "rc", out.returncode, lines[-1:] )
    need(out.returncode == 0 and lines, job + " finished")
    return json.loads(lines[-1])


need(os.path.isfile(FFMPEG) and os.path.isfile(FFPROBE), "FFmpeg is bundled")
need("--enable-gpl" not in text(FFMPEG, "-version"), "FFmpeg is not a GPL build")
encoders = text(FFMPEG, "-hide_banner", "-encoders")
need("libx264" not in encoders, "no x264 inside")
need("libopenh264" in encoders, "a no-GPU H.264 encoder exists")
need(all(e in encoders for e in ("h264_nvenc", "h264_amf", "h264_qsv")), "NVIDIA, AMD and Intel encoders exist")
available = text(FFMPEG, "-hide_banner", "-filters")
missing = [f for f in FILTERS if " %s " % f not in available]
need(not missing, "every filter the layouts use exists (missing: %s)" % missing)

work = tempfile.mkdtemp(prefix="clipsmoke")
env = {**os.environ, "CLIPSTUDIO_DATA": os.path.join(work, "data"), "CLIPSTUDIO_EXPORTS": os.path.join(work, "out")}
env.pop("PATH_FFMPEG", None)
env["PATH"] = os.environ["SystemRoot"] + r"\System32"        # the app must not lean on anything else on this PC
os.environ["CLIPSTUDIO_DATA"] = env["CLIPSTUDIO_DATA"]
os.makedirs(env["CLIPSTUDIO_DATA"])

video = os.path.join(work, "stream.mp4")
subprocess.run([FFMPEG, "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=s=1280x720:r=30:d=120",
                "-f", "lavfi", "-i", "sine=f=440:d=120", "-af", "volume='if(between(t,60,66),1,0.02)':eval=frame",
                "-c:v", "libopenh264", "-b:v", "1M", "-c:a", "aac", video], check=True)

library = Library()
sid = library.add_session("Smoke", video)
library.close()
need(worker("analyze", sid, env).get("done"), "analysis ran, including the first-run speech model download")

library = Library()
clips = library.clips(sid)
need(clips and any(55 <= c["peak"] <= 70 for c in clips), "the loud moment was found")
clip = next(c for c in clips if 55 <= c["peak"] <= 70)
library.update_clip(clip["id"], words=[{"w": "caption", "s": clip["start"] + 1, "e": clip["start"] + 3}])
library.update_session(sid, facecam="900,450,300,220")
library.close()
for layout in ("blur", "stack", "crop"):
    library = Library()
    library.update_clip(clip["id"], layout=layout)
    library.close()
    result = worker("export", clip["id"], env)
    need("path" in result and os.path.isfile(result["path"]), layout + " layout wrote a clip")
    info = json.loads(text(FFPROBE, "-v", "error", "-print_format", "json", "-show_streams", result["path"]))
    stream = next(s for s in info["streams"] if s["codec_type"] == "video")
    need((stream["codec_name"], stream["width"], stream["height"]) == ("h264", 1080, 1920), layout + " is 1080x1920 H.264")
    need(any(s["codec_type"] == "audio" for s in info["streams"]), layout + " has audio")
shutil.rmtree(work, ignore_errors=True)
print("SMOKE TEST PASSED")
