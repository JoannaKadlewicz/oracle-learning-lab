"""Translation overlays of the study content.

The content modules hold each kind of item in its source language (Pack.source_languages). Every
other language reads overlay files from `<lang>/` next to this module:

    <lang>/<topic>.json   {"questions": {id: {field: text}}, "labs": {...}, "flashcards": {...}}
    <lang>/_pack.json     {"topics": {tid: name}, "sections": {sid: name}, "objectives": {oid: name}}

Only the FIELDS of a kind may be translated. The SQL_FIELDS may differ from the source only in their
comments (tools/validate_content.py checks that). A field without a translation keeps the source text.
See AUTHORING.md, "Translations".
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from functools import cache
from pathlib import Path

log = logging.getLogger(__name__)

OVERLAY_DIR = Path(__file__).parent
PACK_FILE = "_pack"

KINDS = ("questions", "labs", "flashcards")
FIELDS = {
    "questions": ("prompt", "options", "explanation", "code", "try_sql"),
    "labs": ("title", "task", "hint", "hint2", "starter", "solution"),
    "flashcards": ("front", "back", "try_sql"),
}
SQL_FIELDS = frozenset({"code", "try_sql", "starter", "solution"})
PACK_KINDS = ("topics", "sections", "objectives")


@dataclass(frozen=True)
class Overlay:
    """The translations of one language: per kind, item id -> {field: text}; per pack kind, id -> name.
    `files` keeps every file as read, by file stem, for the validator; `errors` the files that could not be
    read (they count as empty)."""

    lang: str
    items: dict[str, dict[str, dict]] = field(default_factory=dict)
    names: dict[str, dict[str, str]] = field(default_factory=dict)
    files: dict[str, dict] = field(default_factory=dict)
    errors: dict[str, str] = field(default_factory=dict)

    def item(self, kind: str, item_id: str) -> dict:
        return self.items.get(kind, {}).get(item_id, {})

    def name(self, kind: str, key: str, default: str) -> str:
        return self.names.get(kind, {}).get(key) or default


def read(lang: str, root: Path) -> Overlay:
    """The overlay of `lang` under `root` (empty when it has no directory). A file that is not valid JSON is
    logged and left out, so a broken translation never breaks a page."""
    directory = root / lang
    files, errors = {}, {}
    for file in sorted(directory.glob("*.json")) if directory.is_dir() else []:
        try:
            files[file.stem] = json.loads(file.read_text("utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            errors[file.stem] = f"not valid JSON: {exc}"
            log.error("translation overlay %s left out: %s", file, exc)
    items: dict[str, dict[str, dict]] = {kind: {} for kind in KINDS}
    for stem, data in files.items():
        if stem == PACK_FILE or not isinstance(data, dict):
            continue
        for kind in KINDS:
            entries = data.get(kind)
            if isinstance(entries, dict):
                items[kind].update({k: e for k, e in entries.items() if isinstance(e, dict)})
    pack = files.get(PACK_FILE)
    names = {kind: {k: n for k, n in pack[kind].items() if isinstance(n, str)}
             for kind in PACK_KINDS if isinstance(pack, dict) and isinstance(pack.get(kind), dict)}
    return Overlay(lang, items, names, files, errors)


@cache
def load(lang: str) -> Overlay:
    """The overlay of `lang`, read once."""
    return read(lang, OVERLAY_DIR)


def localize(kind: str, item: dict, overlay: Overlay) -> dict:
    """A copy of `item` with its translated fields applied, or the item itself when it has none."""
    found = overlay.item(kind, item["id"])
    fields = {f: found[f] for f in FIELDS[kind] if f in found and found[f] not in ("", None)}
    if kind == "questions" and not (isinstance(fields.get("options"), list)
                                    and len(fields["options"]) == len(item.get("options", []))):
        fields.pop("options", None)  # a wrong option count would break the answer indexes
    return {**item, **fields} if fields else item
