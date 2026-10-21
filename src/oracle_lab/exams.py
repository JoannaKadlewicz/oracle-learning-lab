"""The exam registry: the one source of exam facts (code, engine, database, size, pass mark).

Dependency-free on purpose: config, content, engines and the UI all build on it.
A database key names a database; "default" is the primary one and has no env suffix.
"""

from __future__ import annotations

from collections.abc import Collection, Mapping
from dataclasses import dataclass

DEFAULT_DATABASE = "default"


@dataclass(frozen=True)
class Exam:
    code: str
    name: str
    product: str
    engine: str
    database: str  # database key
    database_label: str
    fallback: str | None
    versions: tuple[int, int | None]  # engine major versions, min inclusive, max exclusive
    pack: str
    questions: int
    minutes: int
    passing_pct: int
    about: str

    @property
    def database_env(self) -> str:
        return "STUDY_DSN" + env_suffix(self.database)

    def public(self) -> dict:
        return {
            "code": self.code, "name": self.name, "product": self.product,
            "database": self.database_label, "database_env": self.database_env,
            "versions": list(self.versions), "questions": self.questions, "minutes": self.minutes,
            "passing_pct": self.passing_pct, "about": self.about,
        }


EXAMS: dict[str, Exam] = {
    "1Z0-071": Exam(
        code="1Z0-071", name="Oracle Database SQL", product="Oracle", engine="oracle",
        database=DEFAULT_DATABASE, database_label="Oracle Database 19c", fallback=None,
        versions=(19, 23), pack="oracle-sql", questions=63, minutes=120, passing_pct=63,
        about="Tests Oracle Database 19c behavior. Questions whose answer changed in 23ai "
              "are shown on this exam only."),
    "1Z0-171": Exam(
        code="1Z0-171", name="Oracle AI Database SQL Associate", product="Oracle", engine="oracle",
        database="23ai", database_label="Oracle AI Database 23ai", fallback=DEFAULT_DATABASE,
        versions=(23, None), pack="oracle-sql", questions=60, minutes=120, passing_pct=65,
        about="Tests the same SQL on Oracle 23ai and adds topic 15, the SQL features new in 23ai."),
}
DEFAULT_EXAM = "1Z0-071"


def get(code: str | None) -> Exam:
    return EXAMS.get(code, EXAMS[DEFAULT_EXAM]) if isinstance(code, str) else EXAMS[DEFAULT_EXAM]


def database_keys() -> list[str]:
    keys = [DEFAULT_DATABASE]
    for exam in EXAMS.values():
        for key in (exam.database, exam.fallback):
            if key and key not in keys:
                keys.append(key)
    return keys


def engine_of_key(key: str) -> str:
    for exam in EXAMS.values():
        if exam.database == key:
            return exam.engine
    raise KeyError(key)


def env_suffix(key: str) -> str:
    return "" if key == DEFAULT_DATABASE else "_" + key.upper()


def matching(engine: str, major: int) -> list[Exam]:
    return [e for e in EXAMS.values()
            if e.engine == engine and e.versions[0] <= major and (e.versions[1] is None or major < e.versions[1])]


def problems(exams: Mapping[str, Exam], engine_names: Collection[str]) -> list[str]:
    """Registry mistakes, one message each; empty when the registry is sound."""
    found: list[str] = []
    if DEFAULT_EXAM not in exams:
        found.append(f"default exam {DEFAULT_EXAM} is missing")
    key_engine: dict[str, str] = {}
    for exam in exams.values():
        if exam.engine not in engine_names:
            found.append(f"{exam.code}: unknown engine {exam.engine!r}")
        if key_engine.setdefault(exam.database, exam.engine) != exam.engine:
            found.append(f"{exam.code}: database key {exam.database!r} is used by two engines")
    for exam in exams.values():
        if exam.fallback is None:
            continue
        if exam.fallback == exam.database:
            found.append(f"{exam.code}: fallback {exam.fallback!r} is the exam's own database key")
        elif exam.fallback not in key_engine:
            found.append(f"{exam.code}: fallback {exam.fallback!r} is not used by any exam of engine {exam.engine}")
        elif key_engine[exam.fallback] != exam.engine:
            found.append(f"{exam.code}: fallback {exam.fallback!r} belongs to another engine")
    return found
