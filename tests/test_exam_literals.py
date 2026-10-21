"""Exam and engine words live in the registry, the Oracle engine and the content."""

from pathlib import Path

import oracle_lab

ROOT = Path(oracle_lab.__file__).parent
LITERALS = ("1Z0-071", "1Z0-171", "19c", "23ai")
SUFFIXES = {".py", ".js", ".css"}
ALLOWED_FILES = {
    "exams.py",
    "engines/oracle.py",
    "analysis/error_hints.py",
    "tools/validate_content.py",
    "config.py",
    "provisioning/schemas.py",
    "provisioning/proxy.py",
}
ALLOWED_DIRS = ("content/", "database/", "analysis/", "grading/", "sqltext/")


def _allowed(rel: str) -> bool:
    return rel in ALLOWED_FILES or rel.startswith(ALLOWED_DIRS)


def test_no_exam_literals_outside_the_registry_and_oracle_engine():
    hits = []
    for path in sorted(ROOT.rglob("*")):
        if path.suffix not in SUFFIXES or not path.is_file():
            continue
        rel = path.relative_to(ROOT).as_posix()
        if _allowed(rel):
            continue
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if any(lit in line for lit in LITERALS):
                hits.append(f"{rel}:{n}: {line.strip()}")
    assert not hits, "exam literals outside the allow-list:\n" + "\n".join(hits)
