"""Speech to word timings with faster-whisper. Runs after the stream, in the worker process only."""
import ctypes
import re

from .media import audio_window
from .roman import to_roman

HALLUCINATIONS = re.compile(r"(thanks? for watching|subscribe|subtitles? by|amara\.org)", re.I)


def has_cuda():
    try:
        import ctranslate2
        return ctranslate2.get_cuda_device_count() > 0 and _cuda_libraries_present()
    except Exception:
        return False


def _cuda_libraries_present():
    """A driver alone is not enough: Whisper also needs the cuBLAS runtime, which is an optional download."""
    for name in ("cublas64_12.dll", "cublas64_13.dll"):
        try:
            ctypes.WinDLL(name)
            return True
        except OSError:
            pass
    return False


def load_model(name="small", device=None):
    from faster_whisper import WhisperModel
    device = device or ("cuda" if has_cuda() else "cpu")
    return WhisperModel(name, device=device, compute_type="int8_float16" if device == "cuda" else "int8")


def transcribe_window(model, source, start, length, language=None, roman=True, track=0):
    """Returns ([{"w","s","e"}], language) with times in stream time."""
    audio = audio_window(source, start, length, track)
    if audio.size < 1600:
        return [], language or ""
    segments, info = model.transcribe(audio, language=language or None, word_timestamps=True, vad_filter=True,
                                      vad_parameters={"min_silence_duration_ms": 400},
                                      condition_on_previous_text=False, beam_size=3)
    words = []
    for segment in segments:
        if segment.no_speech_prob > 0.8 or HALLUCINATIONS.search(segment.text):
            continue        # game noise makes Whisper invent words, so doubtful segments are dropped
        for w in segment.words or []:
            text = w.word.strip()
            if text:
                words.append({"w": to_roman(text) if roman else text,
                              "s": round(start + w.start, 3), "e": round(start + w.end, 3)})
    return words, info.language
