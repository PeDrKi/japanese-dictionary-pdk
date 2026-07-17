"""
infrastructure/anki_export.py — Export cards to Anki .apkg format.
Requires: pip install genanki. Moved from utils/ (Stage: utils/ cleanup)
since this does real file I/O.

Card format:
  Front: character + reading
  Back:  meaning_vi, meaning_en, example_jp, example_vi, JLPT, type
"""
import logging
import html

logger = logging.getLogger(__name__)

# Fixed model/deck IDs (must be stable across exports for Anki sync)
_MODEL_ID = 1_607_392_319
_DECK_ID  = 2_059_400_110


def export_apkg(cards: list, deck_name: str, output_path: str) -> tuple[int, str]:
    """
    Export a list of card dicts to an Anki .apkg file.
    Returns (count, error_message). error_message is empty string on success.
    """
    try:
        import genanki
    except ImportError:
        return 0, ("Thiếu thư viện genanki.\n"
                   "Chạy lệnh:  pip install genanki\n"
                   "rồi thử lại.")

    try:
        model = _build_model(genanki)
        deck  = genanki.Deck(_DECK_ID, deck_name)
        count = 0

        for c in cards:
            note = _card_to_note(c, model, genanki)
            if note:
                deck.add_note(note)
                count += 1

        package = genanki.Package(deck)
        package.write_to_file(output_path)
        logger.info(f"Exported {count} cards to Anki: {output_path}")
        return count, ""

    except Exception as e:
        logger.error(f"Anki export failed: {e}")
        return 0, str(e)


def _build_model(genanki):
    """Build the Anki note model with Front/Back template."""
    return genanki.Model(
        _MODEL_ID,
        "Japanese Study Card",
        fields=[
            {"name": "Front"},
            {"name": "Back"},
            {"name": "Character"},
            {"name": "Reading"},
            {"name": "HanViet"},
            {"name": "Romaji"},
            {"name": "MeaningVI"},
            {"name": "MeaningEN"},
            {"name": "ExampleJP"},
            {"name": "ExampleVI"},
            {"name": "JLPT"},
            {"name": "Type"},
            {"name": "Notes"},
        ],
        templates=[{
            "name": "Card 1",
            "qfmt": _FRONT_TEMPLATE,
            "afmt": _BACK_TEMPLATE,
        }],
        css=_CSS,
    )


def _card_to_note(c: dict, model, genanki):
    """Convert a card dict to a genanki Note."""
    char    = c.get("character", "").strip()
    if not char:
        return None

    # Build reading string
    t = c.get("type", "")
    if t == "kanji":
        parts = [x for x in (c.get("reading_on"), c.get("reading_kun")) if x]
        reading = "  /  ".join(parts)
    else:
        reading = c.get("reading_kana") or ""

    meaning_vi = c.get("meaning_vi") or ""
    meaning_en = c.get("meaning_en") or ""
    example_jp = c.get("example_jp") or ""
    example_vi = c.get("example_vi") or ""
    romaji     = c.get("romaji") or ""
    hanviet    = c.get("reading_hanviet") or ""
    jlpt       = c.get("jlpt_level") or ""
    notes      = c.get("notes") or ""

    TYPE_LABELS = {
        "kanji": "漢字", "hiragana": "ひらがな",
        "katakana": "カタカナ", "vocab": "語彙",
    }
    type_label = TYPE_LABELS.get(t, t)

    # Front: just character (+ JLPT tag)
    front = _e(char)

    # Back: full details
    back = front  # shown on back too for context

    def _h(val):
        return _e(val) if val else ""

    return genanki.Note(
        model=model,
        fields=[
            front,
            back,
            _h(char),
            _h(reading),
            _h(hanviet),
            _h(romaji),
            _h(meaning_vi),
            _h(meaning_en),
            _h(example_jp),
            _h(example_vi),
            _h(jlpt),
            _h(type_label),
            _h(notes),
        ],
        tags=_build_tags(c),
        guid=genanki.guid_for(f"jp-study-{c.get('id', char)}"),
    )


def _build_tags(c: dict) -> list:
    tags = []
    if c.get("type"):
        tags.append(c["type"])
    if c.get("jlpt_level"):
        tags.append(c["jlpt_level"])
    if c.get("status"):
        tags.append(c["status"])
    if c.get("is_favorite"):
        tags.append("favorite")
    return tags


def _e(s: str) -> str:
    """HTML-escape a string."""
    return html.escape(str(s))


# ── Anki card templates ───────────────────────────────────────────────────────

_CSS = """
.card {
  font-family: 'Noto Sans JP', 'Segoe UI', sans-serif;
  font-size: 18px;
  text-align: center;
  color: #1a1a2e;
  background-color: #f5f5f5;
  padding: 20px;
}
.char {
  font-size: 72px;
  font-weight: bold;
  color: #1a1a2e;
  line-height: 1.2;
}
.reading {
  font-size: 20px;
  color: #3ecfcf;
  margin: 6px 0;
}
.hanviet {
  font-size: 16px;
  color: #f0b429;
  font-style: italic;
  margin: 2px 0;
}
.romaji {
  font-size: 14px;
  color: #6b7280;
  margin-bottom: 10px;
}
.meaning-vi {
  font-size: 22px;
  font-weight: bold;
  color: #4ecb85;
  margin: 8px 0;
}
.meaning-en {
  font-size: 14px;
  color: #6b7280;
  margin-bottom: 10px;
}
.example {
  font-size: 16px;
  background: #e8eaf0;
  border-radius: 8px;
  padding: 8px 14px;
  margin: 8px auto;
  max-width: 480px;
  text-align: left;
}
.example-vi {
  font-size: 13px;
  color: #6b7280;
}
.badge {
  display: inline-block;
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 10px;
  background: #9b7fe8;
  color: white;
  margin: 4px 2px;
}
.notes {
  font-size: 13px;
  color: #9b7fe8;
  font-style: italic;
  margin-top: 8px;
}
hr { border: none; border-top: 1px solid #dde0e8; margin: 10px 0; }
"""

_FRONT_TEMPLATE = """
<div class="card">
  <div class="char">{{Character}}</div>
  {{#JLPT}}<span class="badge">{{JLPT}}</span>{{/JLPT}}
  {{#Type}}<span class="badge" style="background:#4a90d9">{{Type}}</span>{{/Type}}
</div>
"""

_BACK_TEMPLATE = """
{{FrontSide}}
<hr>
<div class="card">
  {{#Reading}}<div class="reading">{{Reading}}</div>{{/Reading}}
  {{#HanViet}}<div class="hanviet">{{HanViet}}</div>{{/HanViet}}
  {{#Romaji}}<div class="romaji">{{Romaji}}</div>{{/Romaji}}
  {{#MeaningVI}}<div class="meaning-vi">{{MeaningVI}}</div>{{/MeaningVI}}
  {{#MeaningEN}}<div class="meaning-en">{{MeaningEN}}</div>{{/MeaningEN}}
  {{#ExampleJP}}
  <div class="example">
    {{ExampleJP}}
    {{#ExampleVI}}<div class="example-vi">{{ExampleVI}}</div>{{/ExampleVI}}
  </div>
  {{/ExampleJP}}
  {{#Notes}}<div class="notes">📝 {{Notes}}</div>{{/Notes}}
</div>
"""
