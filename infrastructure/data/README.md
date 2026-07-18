kanji_ids.tsv — provenance & license
=====================================

Source: `ids.txt` from the [cjkvi/cjkvi-ids](https://github.com/cjkvi/cjkvi-ids)
project, which is itself derived from the CHISE IDS Database
(http://www.chise.org/). Per that project's README, `ids.txt` follows
the CHISE project's license terms (GPLv2).

If this app is ever distributed/published (not just used locally), keep
this attribution alongside the data file to stay compliant.

What was done to it
--------------------
The original `ids.txt` (~89k entries, all of CJK) was filtered and
reshaped for this app's offline lookup:

- Kept only CJK Unified Ideographs + Extension A (U+3400–U+9FFF) — this
  covers every Jōyō and Jinmeiyō kanji (i.e. everything a Japanese
  learner app needs) plus a wide margin of rarer characters.
- Each character in the source file can have several IDS (Ideographic
  Description Sequence) variants tagged by region ([G]hina, [T]aiwan,
  [J]apan, [K]orea, [V]ietnam...). One variant was kept per character:
  the Japan-tagged `[J]` variant if present, else the untagged/default
  variant, else the first one listed.
- Format: `character<TAB>ids_string`, one entry per line, ~27.5k
  entries, ~390KB.

An entry whose `ids_string` equals the character itself (e.g. `日\t日`)
means CHISE records no further breakdown — i.e. it's treated as an
atomic component (a basic radical/stroke shape) by
domain/kanji_decomposition.py.
