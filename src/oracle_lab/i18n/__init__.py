"""The server's languages: picking one per request and translating the messages shown to the user.

Catalogs are keyed by the English source text (gettext style): `<lang>.json` next to this file maps
each English message, or template, to its translation. English needs no catalog. A plural entry
holds a list of forms (Polish: three, chosen by `polish_form`). A missing entry falls back to English.

Services keep raising plain English. A message with variable parts is a `Msg`: a str whose value is
the English text, carrying its template and parameters so the web layer can translate it.
"""

from __future__ import annotations

import json
from functools import cache
from importlib.resources import files
from typing import Any

LANGUAGES: tuple[str, ...] = ("en", "pl")
DEFAULT_LANGUAGE = "en"


class Msg(str):
    """The formatted English text, with the `template` and `params` it was built from."""

    template: str
    params: dict[str, Any]

    @classmethod
    def of(cls, template: str, **params: Any) -> Msg:
        msg = cls(template.format(**params))
        msg.template = template
        msg.params = params
        return msg


@cache
def catalog(lang: str) -> dict[str, str | list[str]]:
    """The catalog of `lang`, loaded once; {} for English or a language without one."""
    if lang == DEFAULT_LANGUAGE or lang not in LANGUAGES:
        return {}
    resource = files(__name__).joinpath(f"{lang}.json")
    return json.loads(resource.read_text("utf-8")) if resource.is_file() else {}


def translate(lang: str, text: str) -> str:
    """`text` in `lang`; a Msg is translated by its template and then formatted with its parameters."""
    if isinstance(text, Msg):
        found = catalog(lang).get(text.template)
        return found.format(**text.params) if isinstance(found, str) else str(text)
    found = catalog(lang).get(text)
    return found if isinstance(found, str) else text


def polish_form(n: int) -> int:
    """Which of the three Polish plural forms `n` takes: 0 (1 pytanie), 1 (2 pytania), 2 (5 pytań)."""
    if n == 1:
        return 0
    if n % 10 in (2, 3, 4) and n % 100 not in (12, 13, 14):
        return 1
    return 2


_PLURAL_FORMS = {"pl": polish_form}


def ntranslate(lang: str, n: int, one: str, many: str, /, **params: Any) -> str:
    """The form of one/many that fits `n` in `lang`, formatted with `params`. The catalog key is `many`."""
    forms = catalog(lang).get(many)
    choose = _PLURAL_FORMS.get(lang)
    if isinstance(forms, list) and choose is not None:
        return forms[min(choose(n), len(forms) - 1)].format(**params)
    return (one if n == 1 else many).format(**params)


def _accepted(accept_language: str) -> list[str]:
    """The primary language tags of an Accept-Language header, best first (q=0 left out)."""
    ranked = []
    for position, part in enumerate(accept_language.split(",")):
        tag, *options = (piece.strip() for piece in part.split(";"))
        quality = 1.0
        for option in options:
            if option.startswith("q="):
                try:
                    quality = float(option[2:])
                except ValueError:
                    quality = 0.0
        if tag and quality > 0:
            ranked.append((-quality, position, tag.split("-")[0].lower()))
    return [tag for *_, tag in sorted(ranked)]


def negotiate(header: str | None, accept_language: str | None) -> str:
    """A valid X-Language header, else the best Accept-Language match, else English."""
    chosen = (header or "").strip().lower()
    if chosen in LANGUAGES:
        return chosen
    return next((tag for tag in _accepted(accept_language or "") if tag in LANGUAGES), DEFAULT_LANGUAGE)


def message_of(exc: BaseException) -> str:
    """The message of an exception, keeping a Msg (str(exc) would turn it into a plain str)."""
    if len(exc.args) == 1 and isinstance(exc.args[0], Msg):
        return exc.args[0]
    return str(exc)
