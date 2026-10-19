"""Files shipped with the package: the web front end, the sample schema scripts, the built-in notes."""

from pathlib import Path

ROOT = Path(__file__).resolve().parent
STATIC_DIR = ROOT / "static"
SQL_DIR = ROOT / "sql"
NOTES_DIR = ROOT / "notes"
