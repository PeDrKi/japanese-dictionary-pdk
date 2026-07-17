"""
domain/kana.py — Kana (hiragana + katakana) to Hepburn romaji converter.
No external dependencies. Moved from utils/ (Stage: utils/ cleanup) since
this is pure conversion logic, not I/O.
"""

# ── Mapping tables ────────────────────────────────────────────────────────────

_HIRAGANA = {
    "あ":"a",  "い":"i",  "う":"u",  "え":"e",  "お":"o",
    "か":"ka", "き":"ki", "く":"ku", "け":"ke", "こ":"ko",
    "さ":"sa", "し":"shi","す":"su", "せ":"se", "そ":"so",
    "た":"ta", "ち":"chi","つ":"tsu","て":"te", "と":"to",
    "な":"na", "に":"ni", "ぬ":"nu", "ね":"ne", "の":"no",
    "は":"ha", "ひ":"hi", "ふ":"fu", "へ":"he", "ほ":"ho",
    "ま":"ma", "み":"mi", "む":"mu", "め":"me", "も":"mo",
    "や":"ya",             "ゆ":"yu",             "よ":"yo",
    "ら":"ra", "り":"ri", "る":"ru", "れ":"re", "ろ":"ro",
    "わ":"wa",                                    "を":"wo",
    "ん":"n",
    # Voiced
    "が":"ga", "ぎ":"gi", "ぐ":"gu", "げ":"ge", "ご":"go",
    "ざ":"za", "じ":"ji", "ず":"zu", "ぜ":"ze", "ぞ":"zo",
    "だ":"da", "ぢ":"ji", "づ":"zu", "で":"de", "ど":"do",
    "ば":"ba", "び":"bi", "ぶ":"bu", "べ":"be", "ぼ":"bo",
    # Semi-voiced
    "ぱ":"pa", "ぴ":"pi", "ぷ":"pu", "ぺ":"pe", "ぽ":"po",
    # Compound
    "きゃ":"kya","きゅ":"kyu","きょ":"kyo",
    "しゃ":"sha","しゅ":"shu","しょ":"sho",
    "ちゃ":"cha","ちゅ":"chu","ちょ":"cho",
    "にゃ":"nya","にゅ":"nyu","にょ":"nyo",
    "ひゃ":"hya","ひゅ":"hyu","ひょ":"hyo",
    "みゃ":"mya","みゅ":"myu","みょ":"myo",
    "りゃ":"rya","りゅ":"ryu","りょ":"ryo",
    "ぎゃ":"gya","ぎゅ":"gyu","ぎょ":"gyo",
    "じゃ":"ja", "じゅ":"ju", "じょ":"jo",
    "びゃ":"bya","びゅ":"byu","びょ":"byo",
    "ぴゃ":"pya","ぴゅ":"pyu","ぴょ":"pyo",
}

# Build katakana map by offset (katakana = hiragana + 0x60)
_KATAKANA = {
    chr(ord(k) + 0x60): v
    for k, v in _HIRAGANA.items()
    if len(k) == 1 and '\u3041' <= k <= '\u3096'
}
# Add katakana compounds
_KATAKANA_COMPOUNDS = {
    "キャ":"kya","キュ":"kyu","キョ":"kyo",
    "シャ":"sha","シュ":"shu","ショ":"sho",
    "チャ":"cha","チュ":"chu","チョ":"cho",
    "ニャ":"nya","ニュ":"nyu","ニョ":"nyo",
    "ヒャ":"hya","ヒュ":"hyu","ヒョ":"hyo",
    "ミャ":"mya","ミュ":"myu","ミョ":"myo",
    "リャ":"rya","リュ":"ryu","リョ":"ryo",
    "ギャ":"gya","ギュ":"gyu","ギョ":"gyo",
    "ジャ":"ja", "ジュ":"ju", "ジョ":"jo",
    "ビャ":"bya","ビュ":"byu","ビョ":"byo",
    "ピャ":"pya","ピュ":"pyu","ピョ":"pyo",
    "ファ":"fa", "フィ":"fi", "フェ":"fe", "フォ":"fo",
    "ウィ":"wi", "ウェ":"we", "ウォ":"wo",
    "ティ":"ti", "ディ":"di", "デュ":"dyu",
    "ツァ":"tsa","ツィ":"tsi","ツェ":"tse","ツォ":"tso",
}
_KATAKANA.update(_KATAKANA_COMPOUNDS)

# Merged table: compounds first (longer keys matched first)
_ALL = {}
_ALL.update({k: v for k, v in _HIRAGANA.items() if len(k) > 1})
_ALL.update({k: v for k, v in _KATAKANA.items() if len(k) > 1})
_ALL.update({k: v for k, v in _HIRAGANA.items() if len(k) == 1})
_ALL.update({k: v for k, v in _KATAKANA.items() if len(k) == 1})


# ── Public function ───────────────────────────────────────────────────────────

def kana_to_romaji(text: str) -> str:
    """
    Convert a kana string to Hepburn romaji.
    Handles mixed hiragana/katakana, small tsu (っ/ッ) doubling,
    long vowel mark (ー), separators (、/ /).
    Non-kana characters are passed through unchanged.
    """
    if not text:
        return ""

    result = []
    i = 0
    n = len(text)

    while i < n:
        ch = text[i]

        # Small tsu — double the next consonant
        if ch in ("っ", "ッ"):
            if i + 1 < n:
                next_romaji = _convert_at(text, i + 1)
                if next_romaji and next_romaji[0].isalpha():
                    result.append(next_romaji[0])   # doubled consonant
            i += 1
            continue

        # Long vowel mark (katakana)
        if ch == "ー":
            if result:
                # Repeat last vowel
                last = result[-1]
                vowels = "aeiou"
                for c in reversed(last):
                    if c in vowels:
                        result.append(c)
                        break
            i += 1
            continue

        # Separators — pass through as space/comma
        if ch in ("、", "・", "/", " ", "　"):
            result.append(", " if ch in ("、", "・") else " ")
            i += 1
            continue

        # Try 2-char compound first
        if i + 1 < n and (text[i:i+2] in _ALL):
            result.append(_ALL[text[i:i+2]])
            i += 2
            continue

        # Single char
        if ch in _ALL:
            result.append(_ALL[ch])
            i += 1
            continue

        # Non-kana — pass through
        result.append(ch)
        i += 1

    return "".join(result)


def _convert_at(text: str, i: int) -> str:
    """Return romaji for the kana starting at position i (1 or 2 chars)."""
    if i + 1 < len(text) and text[i:i+2] in _ALL:
        return _ALL[text[i:i+2]]
    if text[i] in _ALL:
        return _ALL[text[i]]
    return text[i]
