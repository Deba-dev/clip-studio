"""Speech to word timings with faster-whisper. Runs after the stream, in the worker process only."""
import ctypes
import os
import re
import shutil
from collections import Counter

from .media import audio_window
from .paths import data_dir
from .roman import to_roman

HALLUCINATIONS = re.compile(r"(thanks? for watching|subscribe|subtitles? by|amara\.org)", re.I)
# On noisy game audio Whisper can drift into a script nobody spoke, such as Telugu or Chinese in the middle of Hindi.
SCRIPTS = {"hi": "ऀ-ॿ", "mr": "ऀ-ॿ", "ne": "ऀ-ॿ", "bn": "ঀ-৿",
           "as": "ঀ-৿", "ta": "஀-௿", "te": "ఀ-౿", "en": ""}
SURE = 0.9              # a window may differ from the stream's language only when Whisper is this certain
VOTES = 6               # windows sampled to decide the stream's language
# large-v3-turbo names Hindi speech as English with 0.85-0.99 confidence, then writes invented English. A small model
# named the same real stream correctly in 10 of 11 windows, so a small model decides and the large one transcribes.
LANGUAGE_MODEL = "base"
LOW_CONFIDENCE = -1.2   # segments below this average log probability read as noise
REPEATING = 2.4         # compression ratio above this is the same words looping
GAME_WORDS = {"Valorant": "Valorant, Jett, Reyna, Sage, Omen, Phoenix, Raze, Sova, Killjoy, Cypher, Viper, spike, "
                          "defuse, plant, clutch, ace, headshot, one tap, Vandal, Phantom, Operator, rotate, push"}


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


# Where faster-whisper fetches each model the app offers, so cleanup knows them without importing it.
REPOS = {"large-v3-turbo": "mobiuslabsgmbh/faster-whisper-large-v3-turbo", "medium": "Systran/faster-whisper-medium",
         "small": "Systran/faster-whisper-small", "base": "Systran/faster-whisper-base"}


def models_dir():
    """The app's own model folder, so an update can remove unused models without touching other apps' files."""
    path = os.path.join(data_dir(), "models", "whisper")
    os.makedirs(path, exist_ok=True)
    return path


def cache_name(name):
    return "models--" + REPOS[name].replace("/", "--")


def shared_cache():
    return os.environ.get("HF_HUB_CACHE") or os.path.join(
        os.environ.get("HF_HOME") or os.path.join(os.path.expanduser("~"), ".cache", "huggingface"), "hub")


def adopt(name):
    """Older versions kept models in the shared Hugging Face folder. Moving one is instant and saves a re-download."""
    if name not in REPOS:
        return
    mine, theirs = os.path.join(models_dir(), cache_name(name)), os.path.join(shared_cache(), cache_name(name))
    if not os.path.isdir(mine) and os.path.isdir(theirs):
        try:
            os.replace(theirs, mine)
        except OSError:
            shutil.move(theirs, mine)       # another drive


def load_model(name="large-v3-turbo", device=None):
    from faster_whisper import WhisperModel
    device = device or ("cuda" if has_cuda() else "cpu")
    try:
        adopt(name)
    except OSError:
        pass                                # then it is simply downloaded again
    return WhisperModel(name, device=device, compute_type="int8_float16" if device == "cuda" else "int8",
                        cpu_threads=max((os.cpu_count() or 4) - 2, 4), download_root=models_dir())


def model_for(name, mode):
    """large-v3-turbo was not trained to translate, so English captions need a model that was."""
    return "medium" if mode == "english" and "turbo" in name else name


def stream_language(source, picks, track=0, model=None):
    """Votes across the stream, because one window can be wrong. Returns None if nothing could be heard."""
    model = model or load_model(LANGUAGE_MODEL)
    votes = Counter()
    step = max(len(picks) // VOTES, 1)
    for pick in picks[::step][:VOTES]:
        audio = audio_window(source, pick["start"], min(pick["end"] - pick["start"], 30), track)
        if audio.size < 16000:
            continue
        try:
            for language, chance in model.detect_language(audio, vad_filter=True)[2]:
                votes[language] += chance
        except (ValueError, RuntimeError, IndexError):
            continue            # a window with no speech has nothing to vote with
    return votes.most_common(1)[0][0] if votes else None


def readable(word, language):
    """False for a word in a script this language does not use."""
    extra = SCRIPTS.get(language)
    if extra is None:
        return True
    return not re.search(r"[^\W\d_]", re.sub("[A-Za-zÀ-ɏ%s]" % extra, "", word))


def trusted(segment):
    if segment.no_speech_prob > 0.8 or HALLUCINATIONS.search(segment.text):
        return False        # game noise makes Whisper invent words, so doubtful segments are dropped
    return segment.avg_logprob >= LOW_CONFIDENCE and segment.compression_ratio <= REPEATING


def transcribe_window(model, source, start, length, language=None, roman=True, track=0, task="transcribe",
                      hotwords=None):
    """Returns ([{"w","s","e"}], language) with times in stream time."""
    audio = audio_window(source, start, length, track, voice=True)
    if audio.size < 1600:
        return [], language or ""
    segments, info = model.transcribe(audio, language=language or None, task=task, word_timestamps=True,
                                      vad_filter=True, vad_parameters={"min_silence_duration_ms": 400},
                                      condition_on_previous_text=False, beam_size=5, hotwords=hotwords)
    spoken = info.language
    words = []
    for segment in segments:
        if not trusted(segment):
            continue
        for w in segment.words or []:
            text = w.word.strip()
            if text and readable(text, "en" if task == "translate" else spoken):
                words.append({"w": to_roman(text) if roman else text,
                              "s": round(start + w.start, 3), "e": round(start + w.end, 3)})
    return words, spoken
