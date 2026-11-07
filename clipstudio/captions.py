"""Turns word timings into a burned-in caption file (ASS), with the spoken word highlighted."""
import re

MAX_WORDS = 4
MAX_CHARS = 22
BREAK_GAP = 0.6
HOLD = 0.35
HEADER = """[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Cap,{font},{size},&H00FFFFFF,&H00FFFFFF,&H00000000,&H64000000,-1,0,0,0,100,100,0,0,1,7,2,2,70,70,{margin},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
PLAIN = "{\\c&HFFFFFF&}"


def stamp(t):
    cs = int(round(max(t, 0) * 100))
    return "%d:%02d:%02d.%02d" % (cs // 360000, cs // 6000 % 60, cs // 100 % 60, cs % 100)


def escape(text):
    return re.sub(r"[{}\\]", "", text).replace("\n", " ").strip()


def group_words(words):
    """Short bursts are readable on a phone: break on a pause, a full stop, or a width limit."""
    lines, line, chars = [], [], 0
    for w in words:
        text = escape(w["w"])
        if not text:
            continue
        gap = bool(line) and w["s"] - line[-1]["e"] >= BREAK_GAP
        if line and (gap or len(line) >= MAX_WORDS or chars + len(text) + 1 > MAX_CHARS):
            lines.append(line)
            line, chars = [], 0
        line.append({**w, "w": text})
        chars += len(text) + 1
        if text[-1] in ".?!।":
            lines.append(line)
            line, chars = [], 0
    if line:
        lines.append(line)
    return lines


def apply_text(words, text):
    """Keeps timings when a transcript is edited: same word count maps one to one, otherwise words spread evenly."""
    tokens = text.split()
    if not tokens or not words:
        return []
    if len(tokens) == len(words):
        return [{**w, "w": t} for w, t in zip(words, tokens)]
    start, end = words[0]["s"], words[-1]["e"]
    step = (end - start) / len(tokens)
    return [{"w": t, "s": round(start + i * step, 3), "e": round(start + (i + 1) * step, 3)}
            for i, t in enumerate(tokens)]


def highlight(rgb):
    """ASS colours are written blue, green, red."""
    return "{\\c&H%s%s%s&}" % (rgb[4:6], rgb[2:4], rgb[0:2])


def build_ass(words, start, end, font="Nirmala UI", size=84, margin=560, color="FFE100"):
    """words are in stream time; output times are relative to the clip start.

    Nirmala UI ships with Windows and covers both Latin and Devanagari.
    """
    inside = [w for w in words if w["e"] > start and w["s"] < end]
    events = []
    lines = group_words(inside)
    for n, line in enumerate(lines):
        # The last word lingers a moment, so a line never blinks off the instant it is said.
        hold = min(line[-1]["e"] + HOLD, lines[n + 1][0]["s"]) if n + 1 < len(lines) else line[-1]["e"] + HOLD
        for i, w in enumerate(line):
            a = max(w["s"], start) - start
            nxt = line[i + 1]["s"] if i + 1 < len(line) else hold
            b = max(min(nxt, end) - start, a + 0.05)
            text = " ".join((highlight(color) + x["w"] + PLAIN) if j == i else x["w"] for j, x in enumerate(line))
            events.append("Dialogue: 0,%s,%s,Cap,,0,0,0,,%s" % (stamp(a), stamp(b), text))
    return HEADER.format(font=font, size=size, margin=margin) + "\n".join(events) + "\n"
