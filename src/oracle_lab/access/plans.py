"""Account plans: what a guest, user, pro or admin may do, and their daily limits. A plan's defaults live in the
app settings; an admin can override any limit for one account (the override wins, in either direction)."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, fields
from typing import Any

from oracle_lab.i18n import Msg

PLANS = ("guest", "user", "pro", "admin")
# Who may use what. "learner" is the role of an account whose migration failed: it keeps what it had.
FEATURES = {
    "sql_lab": {"pro", "admin", "learner"},
    "mock": {"user", "pro", "admin", "learner"},
    "exercises": {"user", "pro", "admin", "learner"},
    "many_workspaces": {"pro", "admin", "learner"},
}
LIMIT_NAMES = ("questions", "cards", "exercises", "topics")
MAXIMUM = {"questions": 1000, "cards": 1000, "exercises": 1000, "topics": 15}


def can(role: str, feature: str) -> bool:
    return role in FEATURES[feature]


@dataclass(frozen=True)
class Limits:
    """Per day (questions, cards, exercises) and how many topics' lessons; None is unlimited."""

    questions: int | None = None
    cards: int | None = None
    exercises: int | None = None
    topics: int | None = None

    def public(self) -> dict[str, int | None]:
        return asdict(self)


UNLIMITED = Limits()


def _whole(name: str, value: Any, maximum: int) -> int:
    if isinstance(value, bool) or not (isinstance(value, int) or (isinstance(value, str) and value.isdigit())):
        raise ValueError(Msg.of("{name} must be a whole number.", name=name))
    value = int(value)
    if not 0 <= value <= maximum:
        raise ValueError(Msg.of("{name} must be between 0 and {max}.", name=name, max=maximum))
    return value


@dataclass(frozen=True)
class PlanDefaults:
    guest_questions: int = 20
    guest_cards: int = 20
    guest_topics: int = 2
    user_exercises: int = 10

    @classmethod
    def parse(cls, data: dict[str, Any]) -> PlanDefaults:
        """The defaults in `data` (missing or None ones keep their default); ValueError when one is out of range."""
        values = {}
        for f in fields(cls):
            value = data.get(f.name)
            values[f.name] = f.default if value is None else _whole(f.name, value, MAXIMUM[f.name.split("_")[1]])
        return cls(**values)

    @classmethod
    def load(cls, settings) -> PlanDefaults:
        saved = {f.name: settings.get(f"plan_{f.name}") for f in fields(cls)}
        try:
            return cls.parse(saved)
        except ValueError:
            return cls()

    def save(self, settings) -> None:
        for f in fields(self):
            settings.set(f"plan_{f.name}", str(getattr(self, f.name)))

    def public(self) -> dict[str, int]:
        return asdict(self)


def override(settings, user_id: str) -> dict[str, int]:
    """The account's own limits (only the ones an admin set)."""
    try:
        data = json.loads(settings.get(f"limits:{user_id}") or "{}")
    except ValueError:
        return {}
    return {k: v for k, v in data.items() if k in LIMIT_NAMES and isinstance(v, int)}


def set_override(settings, user_id: str, limits: dict[str, Any] | None) -> dict[str, int]:
    """Sets (None or {} clears) the account's limits; keys missing or None follow the plan. Returns what was saved."""
    clean = {name: _whole(name, value, MAXIMUM[name]) for name, value in (limits or {}).items()
             if name in LIMIT_NAMES and value is not None and value != ""}
    settings.set(f"limits:{user_id}", json.dumps(clean))
    return clean


def limits_for(role: str, user_id: str, settings) -> Limits:
    """The plan's limits for `role`, overlaid with the account's own."""
    defaults = PlanDefaults.load(settings)
    base = {
        "guest": Limits(defaults.guest_questions, defaults.guest_cards, 0, defaults.guest_topics),
        "user": Limits(None, None, defaults.user_exercises, None),
    }.get(role, UNLIMITED)
    own = override(settings, user_id)
    return Limits(**{name: own.get(name, getattr(base, name)) for name in LIMIT_NAMES})
