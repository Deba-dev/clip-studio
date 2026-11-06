"""Devanagari to Roman script, because Hinglish captions are usually read in Roman letters.

Whisper often writes Hindi speech in Devanagari. This is a rule-based reading aid rather than a dictionary, and it
drops the silent final vowel, which is how Hindi speakers type: "क्या" -> "kya", "भाई" -> "bhai", "गया" -> "gaya".
"""
import re

CONSONANTS = {
    "क": "k", "ख": "kh", "ग": "g", "घ": "gh", "ङ": "n", "च": "ch", "छ": "chh", "ज": "j", "झ": "jh", "ञ": "n",
    "ट": "t", "ठ": "th", "ड": "d", "ढ": "dh", "ण": "n", "त": "t", "थ": "th", "द": "d", "ध": "dh", "न": "n",
    "प": "p", "फ": "ph", "ब": "b", "भ": "bh", "म": "m", "य": "y", "र": "r", "ल": "l", "ळ": "l", "व": "v",
    "श": "sh", "ष": "sh", "स": "s", "ह": "h", "ड़": "r", "ढ़": "rh", "क़": "q", "ख़": "kh", "ग़": "g", "ज़": "z",
    "फ़": "f", "य़": "y",
}
VOWELS = {"अ": "a", "आ": "aa", "इ": "i", "ई": "ee", "उ": "u", "ऊ": "oo", "ऋ": "ri", "ए": "e", "ऐ": "ai",
          "ओ": "o", "औ": "au", "ऑ": "o", "ॲ": "e"}
SIGNS = {"ा": "a", "ि": "i", "ी": "i", "ु": "u", "ू": "u", "ृ": "ri", "े": "e", "ै": "ai", "ो": "o", "ौ": "au",
         "ॉ": "o", "ॅ": "e"}
NASAL = {"ं": "n", "ँ": "n", "ः": "h"}
HALANT = "्"
NUKTA = "़"
DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")
DEVANAGARI = re.compile(r"[ऀ-ॿ]")
FIXED = {"है": "hai", "हैं": "hain", "मैं": "main", "में": "mein", "नहीं": "nahi", "हाँ": "haan", "हां": "haan",
         "क्या": "kya", "भाई": "bhai", "क्यों": "kyun", "यार": "yaar", "और": "aur", "तो": "toh", "हूँ": "hoon",
         "हूं": "hoon", "कर": "kar", "पर": "par", "अब": "ab", "सब": "sab", "गया": "gaya", "रहा": "raha"}


def _word(word):
    if word in FIXED:
        return FIXED[word]
    out = []
    i = 0
    while i < len(word):
        ch = word[i]
        pair = word[i:i + 2]
        if pair[1:2] == NUKTA and pair in CONSONANTS:
            ch, step = pair, 2
        else:
            step = 1
        if ch in CONSONANTS:
            out.append(CONSONANTS[ch])
            nxt = word[i + step:i + step + 1]
            if nxt == HALANT:
                step += 1
            elif nxt in SIGNS:
                out.append(SIGNS[nxt])
                step += 1
            else:
                out.append("a")
        elif ch in VOWELS:
            out.append(VOWELS[ch])
        elif ch in NASAL:
            out.append(NASAL[ch])
        elif ch == "।":
            out.append(".")
        else:
            out.append(ch)
        i += step
    text = "".join(out)
    last = word.rstrip("।")[-1:]
    if last in CONSONANTS and len(text) > 2 and text.endswith("a") and not text.endswith("aa"):
        text = text[:-1]        # the unwritten final vowel is silent in Hindi
    return text


def to_roman(text):
    if not DEVANAGARI.search(text):
        return text
    text = text.translate(DIGITS)
    return re.sub(r"[ऀ-ॿ]+", lambda m: _word(m.group(0)), text)
