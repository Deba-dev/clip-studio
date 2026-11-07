"""AI upscaling with Real-ESRGAN, for streams that only exist in low quality.

It runs through Vulkan, so any recent GPU works without CUDA. The program and its models are a one-time download of
about 45 MB, of which about 10 MB is kept. The anime-video model suits games: it keeps HUD text and edges sharp.
"""
import hashlib
import math
import os
import shutil
import subprocess
import time
import urllib.request
import zipfile

from .media import HIDE, input_args
from .paths import data_dir, tool

NAME = "realesrgan-20220424"        # a new version gets a new folder; cleanup removes the old ones
URL = ("https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.5.0/"
       "realesrgan-ncnn-vulkan-20220424-windows.zip")
SHA256 = "abc02804e17982a3be33675e4d471e91ea374e65b70167abc09e31acb412802d"
KEEP = ("realesrgan-ncnn-vulkan.exe", "vcomp140.dll") + tuple(
    "models/realesr-animevideov3-x%d.%s" % (n, ext) for n in (2, 3, 4) for ext in ("bin", "param"))
MAX_SOURCE = 1080       # at 1080p and above the AI adds little and costs many minutes, so the fast filters are used
BYTES_PER_PIXEL = 0.5   # an upscaled JPEG frame, measured at about 1 MB for 1080x1920


def folder():
    return os.path.join(data_dir(), "tools", NAME)


def program():
    return os.path.join(folder(), "realesrgan-ncnn-vulkan.exe")


def installed():
    return all(os.path.isfile(os.path.join(folder(), name)) for name in KEEP)


def install(on_progress=lambda value: None):
    """Downloads once and checks the file against a pinned hash before anything is unpacked."""
    if installed():
        return
    os.makedirs(folder(), exist_ok=True)
    archive = os.path.join(folder(), "download.zip")
    sha, done = hashlib.sha256(), 0
    request = urllib.request.Request(URL, headers={"User-Agent": "ClipStudio"})
    try:
        with urllib.request.urlopen(request, timeout=30) as response, open(archive, "wb") as f:
            total = int(response.headers.get("Content-Length") or 0)
            while chunk := response.read(1 << 16):
                f.write(chunk)
                sha.update(chunk)
                done += len(chunk)
                if total:
                    on_progress(done / total)
        if sha.hexdigest() != SHA256:
            raise RuntimeError("The AI upscaler did not download correctly. Please try again.")
        with zipfile.ZipFile(archive) as z:
            for name in KEEP:
                target = os.path.join(folder(), *name.split("/"))
                os.makedirs(os.path.dirname(target), exist_ok=True)
                with z.open(name) as src, open(target, "wb") as dst:
                    shutil.copyfileobj(src, dst)
    finally:
        if os.path.exists(archive):
            os.remove(archive)


def scale_for(size, enlarge):
    """2, 3 or 4 times, or 0 when the AI should not run: the source is already good, or it is hardly enlarged."""
    if min(size) >= MAX_SOURCE or enlarge < 1.5:
        return 0
    return min(max(math.ceil(enlarge - 0.05), 2), 4)


def upscale(source, start, end, fps, scale, size, tmp, on_progress=lambda value: None):
    """Writes an upscaled copy of start..end, beginning at 0, and returns its path.

    The frames are JPEG pictures copied straight into the file, so the AI's work is never compressed twice.
    """
    need = (end - start) * fps * size[0] * size[1] * scale * scale * BYTES_PER_PIXEL * 1.3
    free = shutil.disk_usage(tmp).free
    if free < need + 2e9:
        raise RuntimeError("AI upscaling this clip needs about %.1f GB of free space on %s, but only %.1f GB is free."
                           % ((need + 2e9) / 1e9, os.path.splitdrive(tmp)[0] or tmp, free / 1e9))
    frames_in, frames_out = os.path.join(tmp, "in"), os.path.join(tmp, "out")
    os.makedirs(frames_in)
    os.makedirs(frames_out)
    subprocess.run([tool("ffmpeg"), "-v", "error", "-y", "-ss", "%.3f" % start, "-t", "%.3f" % (end - start),
                    *input_args(source), "-map", "0:v:0", "-vf", "fps=%g" % fps, "-q:v", "2",
                    os.path.join(frames_in, "%08d.jpg")], check=True, capture_output=True, creationflags=HIDE)
    total = len(os.listdir(frames_in))
    log = os.path.join(tmp, "upscale.log")
    # It prints a line per frame, so its output goes to a file: an unread pipe fills up and freezes it.
    with open(log, "wb") as sink:
        proc = subprocess.Popen([program(), "-i", frames_in, "-o", frames_out, "-n",
                                 "realesr-animevideov3-x%d" % scale, "-s", str(scale), "-f", "jpg"],
                                cwd=folder(), stdout=sink, stderr=sink, creationflags=HIDE)
        try:
            while proc.poll() is None:
                time.sleep(0.5)
                on_progress(min(len(os.listdir(frames_out)) / max(total, 1), 1.0))
        finally:
            if proc.poll() is None:
                proc.kill()             # the export was stopped, so the GPU is let go at once
                proc.wait()
    with open(log, "rb") as f:
        err = f.read()[-2000:].decode("utf-8", "replace")
    if proc.returncode or len(os.listdir(frames_out)) < total:
        raise RuntimeError("The AI upscaler could not run on this PC. It needs a graphics driver with Vulkan. "
                           + err.strip()[-160:])
    shutil.rmtree(frames_in, ignore_errors=True)
    path = os.path.join(tmp, "upscaled.mkv")
    subprocess.run([tool("ffmpeg"), "-v", "error", "-y", "-framerate", "%g" % fps,
                    "-i", os.path.join(frames_out, "%08d.jpg"),
                    "-ss", "%.3f" % start, "-t", "%.3f" % (end - start), *input_args(source),
                    "-map", "0:v", "-map", "1:a?", "-c", "copy", path],
                   check=True, capture_output=True, creationflags=HIDE)
    shutil.rmtree(frames_out, ignore_errors=True)
    return path
