"""Names what is happening in the audio: laughter, gunfire, shouting. Loudness alone cannot tell a joke from a menu click.

YAMNet is a small, general sound classifier. It reads a 3-hour stream in under a minute on a CPU, so it runs on the
whole stream rather than on a shortlist. If the model cannot be fetched, analysis carries on without it.
"""
import hashlib
import os

import numpy as np

from .paths import data_dir

REPO = "audiomagic/yamnet-onnx"
REVISION = "f25b741c2f0bdc6d7e6db24b5fddda23347dbafd"
FILE = "yamnet.onnx"
SHA256 = "d3835ffbbd4a1bb3e777f0ca217b5007907f5171dd5d17c4236b95b2af8f908e"
RATE = 16000
HOP = 0.48              # one score row per 0.48 s, each covering 0.96 s
CHUNK = 120             # seconds of audio per model call
GROUPS = {"laugh": (13, 15, 16, 17, 18), "gun": (421, 422, 423, 424, 425), "boom": (420,),
          "shout": (6, 7, 8, 9, 11), "cheer": (61, 62)}


def _digest(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def model_path():
    """Fetches the model once. A pinned revision and hash mean the file can never change underneath the app."""
    folder = os.path.join(data_dir(), "models")
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, FILE)
    if os.path.isfile(path) and _digest(path) == SHA256:
        return path
    from huggingface_hub import hf_hub_download
    got = hf_hub_download(REPO, FILE, revision=REVISION, local_dir=folder)
    if _digest(got) != SHA256:
        os.remove(got)
        raise RuntimeError("The sound model did not match its expected hash.")
    return got


def pool(rows, offset, lanes):
    """Folds 0.48 s score rows into per-second lanes, keeping the strongest score in each second."""
    seconds = (offset + np.arange(rows.shape[0]) * HOP + HOP).astype(np.int64)
    for name, columns in GROUPS.items():
        lane = lanes[name]
        keep = seconds < lane.size
        np.maximum.at(lane, seconds[keep], rows[keep][:, list(columns)].max(axis=1))


class Tagger:
    """Feed it audio as it streams past; it keeps one lane per sound group, one value per second."""

    def __init__(self, duration, path=None):
        import onnxruntime
        options = onnxruntime.SessionOptions()
        options.intra_op_num_threads = max((os.cpu_count() or 2) // 2, 1)   # leaves the PC usable meanwhile
        self.session = onnxruntime.InferenceSession(path or model_path(), options,
                                                    providers=["CPUExecutionProvider"])
        self.lanes = {name: np.zeros(int(np.ceil(duration)) + 2, dtype=np.float32) for name in GROUPS}
        self.parts = []
        self.held = 0
        self.done = 0.0

    def feed(self, samples):
        self.parts.append(samples)
        self.held += samples.size
        if self.held >= CHUNK * RATE:
            self.flush()

    def flush(self):
        if self.held >= RATE // 2:
            audio = np.concatenate(self.parts).astype(np.float32)
            pool(self.session.run(["output_0"], {"waveform": audio})[0], self.done, self.lanes)
        self.done += self.held / RATE
        self.parts, self.held = [], 0

    def finish(self):
        self.flush()
        return self.lanes
