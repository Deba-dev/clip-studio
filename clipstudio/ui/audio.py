"""Preview audio that can go above 100%.

Qt's audio output stops at the file's own level, so a quiet stream would stay quiet in the preview even though the
export comes out loud. Here decoded audio passes through our own gain on its way to the speakers, which makes the
preview sound like the finished clip. If that path is unavailable, the plain output is used and only the boost is lost.
"""
import numpy as np
from PySide6.QtCore import QObject
from PySide6.QtMultimedia import QAudioBufferOutput, QAudioFormat, QAudioOutput, QAudioSink, QMediaDevices

CEILING = 0.95
RECOVER = 1.02          # how fast a limited peak lets go, per buffer


def limit(samples, gain, held):
    """Applies gain without clipping. Returns (samples, the gain reduction to carry into the next buffer)."""
    out = samples * gain
    peak = float(np.abs(out).max()) if out.size else 0.0
    held = min(held * RECOVER, 1.0)
    if peak * held > CEILING:
        held = CEILING / peak
    return out * held, held


def stretch(samples, rate):
    """Fits interleaved stereo to the playback speed. Audio arrives at that speed but the speakers play at one speed."""
    frames = samples.reshape(-1, 2)
    count = int(frames.shape[0] / rate)
    if rate == 1 or count < 2:
        return samples
    at = np.linspace(0, frames.shape[0] - 1, count)
    grid = np.arange(frames.shape[0])
    return np.stack([np.interp(at, grid, frames[:, 0]), np.interp(at, grid, frames[:, 1])], axis=1).ravel()


class PreviewAudio(QObject):
    def __init__(self, player):
        super().__init__(player)
        self.player = player
        self.boost = 1.0        # what the clip's export will add
        self.volume = 1.0       # the listener's own monitor level
        self.muted = False
        self.silent = False     # the playhead is inside a muted part of the clip
        self.held = 1.0
        self.rate = 1.0
        self.sink = None
        self.device = None
        self.plain = None
        fmt = QAudioFormat()
        fmt.setSampleRate(48000)
        fmt.setChannelCount(2)
        fmt.setSampleFormat(QAudioFormat.SampleFormat.Float)
        speaker = QMediaDevices.defaultAudioOutput()
        if speaker.isNull() or not speaker.isFormatSupported(fmt):
            self.plain = QAudioOutput(self)
            player.setAudioOutput(self.plain)
            return
        self.tap = QAudioBufferOutput(fmt, self)
        self.tap.audioBufferReceived.connect(self.on_buffer)
        self.sink = QAudioSink(speaker, fmt, self)
        self.sink.setBufferSize(48000 * 2 * 4 // 4)     # a quarter second: short enough that seeking feels instant
        self.device = self.sink.start()
        player.setAudioBufferOutput(self.tap)

    def set_boost(self, db):
        self.boost = 10 ** (db / 20)

    def set_volume(self, value):
        self.volume = value
        if self.plain:
            self.plain.setVolume(value)

    def set_muted(self, muted):
        self.muted = muted
        if self.plain:
            self.plain.setMuted(muted)

    def set_rate(self, rate):
        self.rate = rate

    def set_silent(self, silent):
        self.silent = silent

    def flush(self):
        """Drops what is queued, so a seek is heard at once rather than a quarter second late."""
        if self.sink:
            self.sink.reset()
            self.device = self.sink.start()

    def on_buffer(self, buffer):
        if self.device is None:
            return
        data = np.frombuffer(bytes(buffer.constData()), dtype=np.float32)
        gain = 0.0 if self.muted or self.silent else self.boost * self.volume
        data, self.held = limit(stretch(data, self.rate), gain, self.held)
        self.device.write(data.astype(np.float32).tobytes())
