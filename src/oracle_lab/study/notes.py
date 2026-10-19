"""Study notes: the built-in ones shipped with the app, and personal ones saved from the SQL lab.

Notes are addressed by a path relative to the library, e.g. "docs/cheat-sheet.md",
"topics/06-joins/notes.md" or "personal/2026-10-19-outer-joins.md". Only listed notes can be
read, so a path from the browser can never reach other files.

Personal notes are kept as files (FileNotes) or, without a persistent disk, in Oracle
(database.app_store.OracleNotes).
"""

from __future__ import annotations

import datetime
import re
from pathlib import Path
from typing import Protocol

PERSONAL = "personal"
TITLE_LIMIT = 80
SLUG_LIMIT = 50
HIDDEN_FILES = {"solutions.sql"}


class PersonalNotes(Protocol):
    def entries(self) -> list[tuple[str, str]]:
        """(name, title) of every note, newest first."""

    def read(self, name: str) -> str | None:
        """The text of a listed note, or None."""

    def add(self, stem: str, title: str, text: str) -> str:
        """Save a note as "<stem>.md", or "<stem>-<n>.md" when that is taken; returns its name."""


class FileNotes:
    """Personal notes as Markdown files in one directory."""

    def __init__(self, directory: Path):
        self.directory = directory

    def entries(self) -> list[tuple[str, str]]:
        return [(f.name, _heading(f)) for f in sorted(self.directory.glob("*.md"), reverse=True)]

    def read(self, name: str) -> str | None:
        file = next((f for f in self.directory.glob("*.md") if f.name == name), None)
        return file.read_text(encoding="utf-8") if file else None

    def add(self, stem: str, title: str, text: str) -> str:
        self.directory.mkdir(parents=True, exist_ok=True)
        file = self.directory / f"{stem}.md"
        n = 2
        while file.exists():
            file = self.directory / f"{stem}-{n}.md"
            n += 1
        file.write_text(text, encoding="utf-8")
        return file.name


class NotesLibrary:
    def __init__(self, builtin_dir: Path, personal: PersonalNotes):
        self.builtin_dir = builtin_dir
        self.personal = personal

    def list(self) -> list[dict[str, str]]:
        notes = [{"path": path, "title": title} for path, title, _ in self._builtin()]
        notes += [{"path": f"{PERSONAL}/{name}", "title": f"My notes / {title}"} for name, title in self.personal.entries()]
        return notes

    def read(self, path: str) -> str | None:
        if path.startswith(f"{PERSONAL}/"):
            return self.personal.read(path.removeprefix(f"{PERSONAL}/"))
        file = next((f for p, _, f in self._builtin() if p == path), None)
        return file.read_text(encoding="utf-8") if file else None

    def save(self, title: str, sql: str, now: float) -> str:
        """Save a SQL snippet as a Markdown note; returns its path in the library."""
        title = " ".join(title.split())[:TITLE_LIMIT] or "SQL note"
        slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:SLUG_LIMIT] or "note"
        day = datetime.date.fromtimestamp(now).isoformat()
        text = f"# {title}\n\nSaved from the SQL lab on {day}.\n\n```sql\n{sql.strip()}\n```\n"
        return f"{PERSONAL}/{self.personal.add(f'{day}-{slug}', title, text)}"

    def _builtin(self) -> list[tuple[str, str, Path]]:
        """(library path, title, file) of every built-in note, in display order."""
        root = self.builtin_dir
        entries = [(self._rel(f), f.stem.replace("-", " ").capitalize(), f) for f in sorted((root / "docs").glob("*.md"))]
        entries += [(self._rel(f), f"{f.parent.name} / {f.stem}", f) for f in sorted((root / "topics").glob("*/*.md"))]
        entries += [(self._rel(f), f"{f.parent.name} / {f.name}", f) for f in sorted((root / "topics").glob("*/*.sql"))
                    if f.name not in HIDDEN_FILES]
        return entries

    def _rel(self, file: Path) -> str:
        return file.relative_to(self.builtin_dir).as_posix()


def _heading(file: Path) -> str:
    first = file.read_text(encoding="utf-8").split("\n", 1)[0]
    return first[2:].strip() if first.startswith("# ") else file.stem
