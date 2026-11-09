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
         "हूं": "hoon", "कर": "kar", "पर": "par", "अब": "ab", "सब": "sab", "गया": "gaya", "रहा": "raha", "भई": "bhai", "भाइ": "bhai", "मत": "mat", "अभी": "abhi",
         "कुछ": "kuch", "बहुत": "bahut", "मुझे": "mujhe", "तुम": "tum", "हम": "hum", "वो": "woh", "ये": "yeh",
         "पता": "pata", "चल": "chal", "बस": "bas", "सही": "sahi", "मार": "maar", "देख": "dekh"}


def _units(word):
    """Splits a word into syllable units: [consonant, vowel, inherent vowel?, nasal]."""
    units, i = [], 0
    while i < len(word):
        ch, step = word[i], 1
        if word[i + 1:i + 2] == NUKTA and word[i:i + 2] in CONSONANTS:
            ch, step = word[i:i + 2], 2
        nxt = word[i + step:i + step + 1]
        if ch in CONSONANTS:
            if nxt == HALANT:
                units.append([CONSONANTS[ch], "", False, ""])
                step += 1
            elif nxt in SIGNS:
                units.append([CONSONANTS[ch], SIGNS[nxt], False, ""])
                step += 1
            else:
                units.append([CONSONANTS[ch], "a", True, ""])
        elif ch in VOWELS:
            units.append(["", VOWELS[ch], False, ""])
        elif ch in SIGNS:           # a vowel sign Whisper put after a vowel: still a vowel, never raw Devanagari
            units.append(["", SIGNS[ch], False, ""])
        elif ch in NASAL:
            if units:
                units[-1][3] += NASAL[ch]
            else:
                units.append(["", NASAL[ch], False, ""])
        elif ch in (HALANT, NUKTA) or DEVANAGARI.match(ch) and ch != "।":
            pass                    # a stray mark, or a sign this table does not know: dropped, never shown raw
        else:
            units.append([".", "", False, ""] if ch == "।" else [ch, "", False, ""])
        i += step
    return units


def _word(word):
    if word in FIXED:
        return FIXED[word]
    units = _units(word)
    # The unwritten vowel is silent at the end of a word, and in the middle between a vowel and a consonant that has
    # its own vowel: "देखता" is typed "dekhta", "इसको" "isko", "समझता" "samajhta".
    if len(units) > 1 and units[-1][2] and not units[-1][3]:
        units[-1][1] = ""
    for i in range(len(units) - 2, 0, -1):
        here, before, after = units[i], units[i - 1], units[i + 1]
        if here[2] and not here[3] and here[0] and before[1] and after[0] and after[1]:
            here[1] = ""
    return "".join(c + v + n for c, v, _, n in units)


def to_roman(text):
    if not DEVANAGARI.search(text):
        return text
    text = text.translate(DIGITS)
    return re.sub(r"[ऀ-ॿ]+", lambda m: _word(m.group(0)), text)
