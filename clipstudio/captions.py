"""Turns word timings into a burned-in caption file (ASS), styled like the captions people make by hand.

A style is a plain dict, so it lives in a clip's edit and is shared by the export and the phone preview, which must
never disagree. Pick a preset, then change anything: font, colours, outline, shadow, box, highlight, animation.
"""
import re

MAX_CHARS = 22
BREAK_GAP = 0.6
HOLD = 0.35
DEVANAGARI = re.compile("[ऀ-ॿ]")
DEVANAGARI_FONT = "Nirmala UI"     # the one font shipped with Windows that covers Hindi script

# Fonts every Windows 10 and 11 PC has.
FONTS = (("Nirmala UI", "Nirmala UI"), ("Bold sans", "Segoe UI Black"), ("Impact", "Impact"),
         ("Heavy", "Arial Black"), ("Comic", "Comic Sans MS"), ("Condensed", "Bahnschrift"),
         ("Marker", "Ink Free"), ("Script", "Segoe Script"), ("Classic", "Franklin Gothic Medium"))
HIGHLIGHTS = (("Colour the word", "color"), ("Box behind the word", "box"), ("Fill as it is said", "fill"),
              ("No highlight", "none"))
ANIMATIONS = (("None", "none"), ("Pop each word", "pop"), ("Bounce in", "bounce"), ("Fade in", "fade"),
              ("Slide up", "slide"))

BASE = {"font": "Nirmala UI", "size": 84, "y": 560, "words": 4, "upper": False, "bold": True, "italic": False,
        "text": "FFFFFF", "highlight": "FFE100", "highlight_mode": "color", "outline": "000000", "outline_width": 7,
        "shadow": 2, "shadow_color": "000000", "box": False, "box_color": "000000", "box_opacity": 60,
        "animation": "none", "tilt": 0, "spacing": 0}

PRESETS = {
    "classic": {"name": "Classic"},
    "pop": {"name": "Pop", "font": "Segoe UI Black", "upper": True, "words": 3, "highlight": "34D399",
            "outline_width": 10, "shadow": 4, "animation": "pop", "size": 90},
    "box": {"name": "Box", "font": "Segoe UI Black", "upper": True, "words": 3, "highlight_mode": "box",
            "highlight": "8B5CF6", "outline_width": 8, "shadow": 0, "animation": "pop"},
    "karaoke": {"name": "Karaoke", "highlight_mode": "fill", "highlight": "FFE100", "text": "FFFFFF",
                "outline_width": 6, "animation": "fade", "words": 5},
    "one": {"name": "One word", "font": "Impact", "upper": True, "words": 1, "size": 120, "outline_width": 9,
            "highlight_mode": "none", "animation": "pop", "shadow": 5},
    "comic": {"name": "Comic", "font": "Comic Sans MS", "text": "FFE100", "highlight": "FF3B6B", "words": 2,
              "outline_width": 9, "tilt": -4, "animation": "bounce", "size": 92},
    "neon": {"name": "Neon", "font": "Bahnschrift", "text": "E0FCFF", "outline": "FF2BD6", "outline_width": 5,
             "highlight": "3DF5FF", "shadow": 0, "upper": True, "animation": "fade"},
    "fire": {"name": "Fire", "font": "Arial Black", "upper": True, "text": "FFF3B0", "highlight": "FF7A00",
             "outline": "8B0000", "outline_width": 9, "shadow_color": "FF3D00", "shadow": 4, "animation": "pop"},
    "minimal": {"name": "Minimal", "font": "Segoe UI Black", "bold": False, "outline_width": 0, "shadow": 0,
                "box": True, "box_opacity": 55, "highlight_mode": "none", "size": 72, "animation": "slide"},
    "marker": {"name": "Marker", "font": "Ink Free", "text": "FFFFFF", "highlight": "FFE100", "words": 3,
               "outline_width": 8, "tilt": 3, "animation": "bounce", "size": 96},
}
PREMIUM_PRESETS = {"neon", "fire", "marker"}     # suggested; see the freemium review page


def style_of(edit, default=None):
    """The full style for a clip: the preset, the user's saved default, then this clip's own changes.

    Clips from older versions only had caption_size, caption_y and caption_color; those still apply.
    """
    own = dict((edit or {}).get("caption_style") or {})
    base = dict(default or {})
    preset = own.get("preset") or base.get("preset") or "classic"
    style = {**BASE, **PRESETS.get(preset, {}), **base, **own, "preset": preset}
    style.pop("name", None)
    for old, new in (("caption_size", "size"), ("caption_y", "y"), ("caption_color", "highlight")):
        if old in (edit or {}) and new not in own:
            style[new] = edit[old]
    style["words"] = max(1, min(int(style["words"]), 8))
    return style


def stamp(t):
    cs = int(round(max(t, 0) * 100))
    return "%d:%02d:%02d.%02d" % (cs // 360000, cs // 6000 % 60, cs // 100 % 60, cs % 100)


def escape(text):
    return re.sub(r"[{}\\]", "", text).replace("\n", " ").strip()


def group_words(words, max_words=4, max_chars=MAX_CHARS):
    """Short bursts are readable on a phone: break on a pause, a full stop, or a width limit."""
    lines, line, chars = [], [], 0
    limit = max(max_chars, 10 * max_words // 4 + 6) if max_words > 4 else max_chars
    for w in words:
        text = escape(w["w"])
        if not text:
            continue
        gap = bool(line) and w["s"] - line[-1]["e"] >= BREAK_GAP
        if line and (gap or len(line) >= max_words or chars + len(text) + 1 > limit):
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


def bgr(rgb, alpha=0):
    """ASS colours are written alpha, blue, green, red, where alpha 0 is solid."""
    rgb = (rgb or "FFFFFF").upper()
    return "&H%02X%s%s%s" % (alpha, rgb[4:6], rgb[2:4], rgb[0:2])


def highlight(rgb):
    return "{\\c%s&}" % bgr(rgb)


def shown(text, style):
    return text.upper() if style["upper"] else text


def font_for(text, style):
    return DEVANAGARI_FONT if DEVANAGARI.search(text) else style["font"]


def header(style, sample=""):
    box_alpha = round(255 * (1 - style["box_opacity"] / 100))
    border = 3 if style["box"] else 1
    outline = 14 if style["box"] else style["outline_width"]       # with a box, Outline is the box padding
    outline_colour = bgr(style["box_color"], box_alpha) if style["box"] else bgr(style["outline"])
    return ("[Script Info]\nScriptType: v4.00+\nPlayResX: 1080\nPlayResY: 1920\nWrapStyle: 2\n"
            "ScaledBorderAndShadow: yes\n\n[V4+ Styles]\n"
            "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, "
            "Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, "
            "MarginL, MarginR, MarginV, Encoding\n"
            "Style: Cap,%s,%d,%s,%s,%s,%s,%d,%d,0,0,100,100,%d,%d,%d,%d,%d,2,70,70,%d,1\n\n"
            "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n") % (
        font_for(sample, style), style["size"], bgr(style["text"]),
        bgr(style["text"]) if style["highlight_mode"] != "fill" else bgr(style["text"]),
        outline_colour, bgr(style["shadow_color"], 96), -1 if style["bold"] else 0, -1 if style["italic"] else 0,
        style["spacing"], style["tilt"], border, outline, style["shadow"], style["y"])


def entrance(style, first):
    """Tags that animate a line as it appears. Only the first event of a line animates, so it does not repeat."""
    if not first:
        return ""
    return {"bounce": "{\\fscx70\\fscy70\\t(0,110,\\fscx108\\fscy108)\\t(110,190,\\fscx100\\fscy100)}",
            "fade": "{\\fad(140,0)}",
            "slide": "{\\fad(100,0)\\frx40\\t(0,160,\\frx0)}"}.get(style["animation"], "")


def word_tags(style):
    """How the spoken word looks."""
    mode = style["highlight_mode"]
    pop = "\\fscx100\\fscy100\\t(0,70,\\fscx124\\fscy124)\\t(70,150,\\fscx112\\fscy112)" \
        if style["animation"] == "pop" else ""
    if mode == "color":
        return "{\\c%s&%s}" % (bgr(style["highlight"]), pop)
    if mode == "box":       # a thick outline in the highlight colour reads as a rounded box behind the word
        return "{\\3c%s&\\bord%d\\c%s&%s}" % (bgr(style["highlight"]), max(style["outline_width"], 6) + 10,
                                              bgr(style["text"]), pop)
    return "{%s}" % pop if pop else ""


def plain_tags(style, first=False):
    """Undoes the spoken word's look for the words after it, without cancelling the line's entrance animation."""
    border = 14 if style["box"] else style["outline_width"]
    outline = bgr(style["box_color"], round(255 * (1 - style["box_opacity"] / 100))) if style["box"] \
        else bgr(style["outline"])
    scale = ""
    if style["animation"] == "pop":
        scale = "\\fscx100\\fscy100"
    elif first and style["animation"] in ("bounce", "slide"):
        scale = entrance(style, True)[1:-1]         # the same timed tags, so these words keep animating in step
    return "{\\c%s&\\3c%s&\\bord%d%s}" % (bgr(style["text"]), outline, border, scale)


def build_ass(words, start, end, style=None, **old):
    """words are in stream time; output times are relative to the clip start.

    old keeps the former call style working: size=, margin=, color=.
    """
    style = dict(style or style_of({}))
    if old:
        style.update({k: v for k, v in (("size", old.get("size")), ("y", old.get("margin")),
                                        ("highlight", old.get("color"))) if v is not None})
    inside = [w for w in words if w["e"] > start and w["s"] < end]
    lines = group_words(inside, style["words"])
    events = []
    for n, line in enumerate(lines):
        # The last word lingers a moment, so a line never blinks off the instant it is said.
        hold = min(line[-1]["e"] + HOLD, lines[n + 1][0]["s"]) if n + 1 < len(lines) else line[-1]["e"] + HOLD
        texts = [shown(x["w"], style) for x in line]
        if style["highlight_mode"] == "fill":      # one event; each word fills with colour as it is said
            a = max(line[0]["s"], start) - start
            b = max(min(hold, end) - start, a + 0.05)
            parts = []
            for i, x in enumerate(line):
                nxt = line[i + 1]["s"] if i + 1 < len(line) else line[-1]["e"]
                parts.append("{\\kf%d}%s" % (max(int((nxt - x["s"]) * 100), 1), texts[i]))
            body = "{\\1c%s&\\2c%s&}" % (bgr(style["highlight"]), bgr(style["text"])) + " ".join(parts)
            events.append("Dialogue: 0,%s,%s,Cap,,0,0,0,,%s%s" % (stamp(a), stamp(b), entrance(style, True), body))
            continue
        for i, w in enumerate(line):
            a = max(w["s"], start) - start
            nxt = line[i + 1]["s"] if i + 1 < len(line) else hold
            b = max(min(nxt, end) - start, a + 0.05)
            body = " ".join((word_tags(style) + t + plain_tags(style, i == 0)) if j == i else t
                            for j, t in enumerate(texts))
            events.append("Dialogue: 0,%s,%s,Cap,,0,0,0,,%s%s" % (stamp(a), stamp(b), entrance(style, i == 0), body))
    sample = " ".join(w["w"] for w in inside)
    return header(style, sample) + "\n".join(events) + "\n"
