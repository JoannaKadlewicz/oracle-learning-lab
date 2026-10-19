"""Study notes: the built-in ones shipped with the app, and personal ones saved from the SQL lab.

Notes are addressed by a path relative to the library, e.g. "docs/cheat-sheet.md",
"topics/06-joins/notes.md" or "personal/2026-10-19-outer-joins.md". Only listed notes can be
read, so a path from the browser can never reach other files.
"""

from __future__ import annotations

import datetime
import re
from pathlib import Path

PERSONAL = "personal"
TITLE_LIMIT = 80
SLUG_LIMIT = 50
HIDDEN_FILES = {"solutions.sql"}


class NotesLibrary:
    def __init__(self, builtin_dir: Path, personal_dir: Path):
        self.builtin_dir = builtin_dir
        self.personal_dir = personal_dir

    def list(self) -> list[dict[str, str]]:
        return [{"path": path, "title": title} for path, title, _ in self._entries()]

    def read(self, path: str) -> str | None:
        file = next((f for p, _, f in self._entries() if p == path), None)
        return file.read_text(encoding="utf-8") if file else None

    def save(self, title: str, sql: str, now: float) -> str:
        """Write a SQL snippet as a Markdown note; returns its path in the library."""
        title = " ".join(title.split())[:TITLE_LIMIT] or "SQL note"
        slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:SLUG_LIMIT] or "note"
        self.personal_dir.mkdir(parents=True, exist_ok=True)
        day = datetime.date.fromtimestamp(now).isoformat()
        file = self.personal_dir / f"{day}-{slug}.md"
        n = 2
        while file.exists():
            file = self.personal_dir / f"{day}-{slug}-{n}.md"
            n += 1
        file.write_text(f"# {title}\n\nSaved from the SQL lab on {day}.\n\n```sql\n{sql.strip()}\n```\n",
                        encoding="utf-8")
        return f"{PERSONAL}/{file.name}"

    def _entries(self) -> list[tuple[str, str, Path]]:
        """(library path, title, file) of every note, in display order."""
        root = self.builtin_dir
        entries = [(self._rel(f), f.stem.replace("-", " ").capitalize(), f) for f in sorted((root / "docs").glob("*.md"))]
        entries += [(self._rel(f), f"{f.parent.name} / {f.stem}", f) for f in sorted((root / "topics").glob("*/*.md"))]
        entries += [(self._rel(f), f"{f.parent.name} / {f.name}", f) for f in sorted((root / "topics").glob("*/*.sql"))
                    if f.name not in HIDDEN_FILES]
        entries += [(f"{PERSONAL}/{f.name}", f"My notes / {self._heading(f)}", f)
                    for f in sorted(self.personal_dir.glob("*.md"), reverse=True)]
        return entries

    def _rel(self, file: Path) -> str:
        return file.relative_to(self.builtin_dir).as_posix()

    @staticmethod
    def _heading(file: Path) -> str:
        first = file.read_text(encoding="utf-8").split("\n", 1)[0]
        return first[2:].strip() if first.startswith("# ") else file.stem
