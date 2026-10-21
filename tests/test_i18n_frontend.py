"""The front end's Polish catalog covers every string the code translates: t("…"), tn(n, "…", "…"),
plural(n, "…"[, "…"]) in the JS modules and data-i18n="…" in the static HTML pages."""

from __future__ import annotations

import html
import json
import re
from pathlib import Path

import pytest

STATIC = Path(__file__).resolve().parents[1] / "src" / "oracle_lab" / "resources" / "static"
CATALOG = STATIC / "i18n" / "pl.json"
PLACEHOLDER = re.compile(r"\{(\w+)\}")
CALL = re.compile(r"(?<![\w$.])(t|tn|plural)\(")
DATA_I18N = re.compile(r"\bdata-i18n(?:-aria-label)?=\"([^\"]*)\"")
# After these characters (or a keyword) a "/" starts a regular expression, not a division.
REGEX_BEFORE = set("(,=:[!&|?{};+-*%<>~^")
REGEX_KEYWORDS = ("return", "typeof", "case", "do", "else", "in", "of", "void", "yield", "await")


def strip_comments(source: str) -> str:
    """The source with // and /* */ comments blanked; strings, template literals and regex literals are kept."""
    out: list[str] = []
    i, n = 0, len(source)
    while i < n:
        ch = source[i]
        if source.startswith("//", i):
            end = source.find("\n", i)
            i = n if end < 0 else end
            continue
        if source.startswith("/*", i):
            end = source.find("*/", i + 2)
            i = n if end < 0 else end + 2
            out.append(" ")
            continue
        if ch in "\"'`":
            end = _string_end(source, i)
            out.append(source[i:end])
            i = end
            continue
        if ch == "/" and _starts_regex(out):
            end = _regex_end(source, i)
            out.append(source[i:end])
            i = end
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def _string_end(source: str, start: int) -> int:
    """Index just past the string or template literal opening at `start` (template ${} nesting included)."""
    quote, i = source[start], start + 1
    while i < len(source):
        ch = source[i]
        if ch == "\\":
            i += 2
            continue
        if ch == quote:
            return i + 1
        if quote == "`" and source.startswith("${", i):
            i = _expression_end(source, i + 2)
            continue
        i += 1
    return len(source)


def _expression_end(source: str, start: int) -> int:
    """Index just past the "}" closing a template ${ expression that starts at `start`."""
    depth, i = 1, start
    while i < len(source):
        ch = source[i]
        if ch in "\"'`":
            i = _string_end(source, i)
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    return len(source)


def _starts_regex(before: list[str]) -> bool:
    text = "".join(before[-12:]).rstrip()
    if not text or text[-1] in REGEX_BEFORE:
        return True
    word = re.search(r"[\w$]+$", text)
    return bool(word) and word.group() in REGEX_KEYWORDS


def _regex_end(source: str, start: int) -> int:
    i, in_class = start + 1, False
    while i < len(source):
        ch = source[i]
        if ch == "\\":
            i += 2
            continue
        if ch == "\n":
            return i
        if ch == "[":
            in_class = True
        elif ch == "]":
            in_class = False
        elif ch == "/" and not in_class:
            i += 1
            while i < len(source) and source[i].isalpha():
                i += 1
            return i
        i += 1
    return len(source)


def split_arguments(source: str, start: int) -> list[str]:
    """The top-level arguments of the call whose "(" is just before `start`."""
    args, depth, i, begin = [], 0, start, start
    while i < len(source):
        ch = source[i]
        if ch in "\"'`":
            i = _string_end(source, i)
            continue
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            if depth == 0:
                args.append(source[begin:i].strip())
                return [a for a in args if a]
            depth -= 1
        elif ch == "," and depth == 0:
            args.append(source[begin:i].strip())
            begin = i + 1
        i += 1
    return []


_ESCAPES = {"n": "\n", "t": "\t", "r": "\r", "0": "\0"}


def literal(arg: str) -> str | None:
    """The value of a plain string literal ("…", '…' or `…` without ${}), else None."""
    if len(arg) < 2 or arg[0] not in "\"'`" or arg[-1] != arg[0] or _string_end(arg, 0) != len(arg):
        return None
    body = arg[1:-1]
    if arg[0] == "`" and "${" in body.replace("\\$", ""):
        return None
    return re.sub(r"\\u([0-9a-fA-F]{4})|\\(.)",
                  lambda m: chr(int(m.group(1), 16)) if m.group(1) else _ESCAPES.get(m.group(2), m.group(2)), body,
                  flags=re.DOTALL)


def extract(source: str) -> tuple[set[str], set[tuple[str, str]]]:
    """Message ids of t() and (one, many) pairs of tn() and plural() with literal arguments."""
    code = strip_comments(source)
    singles: set[str] = set()
    plurals: set[tuple[str, str]] = set()
    for match in CALL.finditer(code):
        if re.search(r"function\s*$", code[:match.start()]):
            continue  # the definition, not a call
        name, args = match.group(1), split_arguments(code, match.end())
        values = [literal(a) for a in args]
        if name == "t" and values and values[0] is not None:
            singles.add(values[0])
        elif name == "tn" and len(values) >= 3 and None not in values[1:3]:
            plurals.add((values[1], values[2]))
        elif name == "plural" and len(values) >= 2 and values[1] is not None:
            many = values[2] if len(values) >= 3 else values[1] + "s"
            if many is not None:
                plurals.add(("{n} " + values[1], "{n} " + many))
    return singles, plurals


def frontend_strings() -> tuple[set[str], set[tuple[str, str]]]:
    singles: set[str] = set()
    plurals: set[tuple[str, str]] = set()
    for path in sorted((STATIC / "js").rglob("*.js")):
        found_singles, found_plurals = extract(path.read_text(encoding="utf-8"))
        singles |= found_singles
        plurals |= found_plurals
    return singles, plurals


def html_strings() -> set[str]:
    found: set[str] = set()
    for path in sorted(STATIC.glob("*.html")):
        page = re.sub(r"<!--.*?-->", "", path.read_text(encoding="utf-8"), flags=re.DOTALL)
        found |= {html.unescape(value) for value in DATA_I18N.findall(page)}
    return found


def catalog() -> dict:
    return json.loads(CATALOG.read_text(encoding="utf-8"))


def placeholders(text: str) -> set[str]:
    return set(PLACEHOLDER.findall(text))


# --- the extraction itself ---------------------------------------------------------------------------------------

def test_extraction_finds_every_call_form_and_skips_comments_and_dynamic_text():
    source = r'''
      import { t, tn } from "./i18n.js";
      export function t(msgid, params = {}) { return msgid; }
      const a = t("Double \"quoted\""), b = t('Single'), c = t(`Template`), d = t(`Dynamic ${x}`);
      const e = tn(list.filter(x => f(x, 2)).length, "{n} item", "{n} items", { n: 1 });
      const g = plural(count, "question"), h = plural(n, "child", "children"), k = t(variable);
      const re = /["'(]t\("/g, y = 4 / 2;  // t("In a comment")
      /* t("In a block comment") plural(n, "ghost") */
      obj.t("Method call"), list.plural(n, "nope");
      const url = "https://example.org/x"; const m = t("After the url {name}", { name });
    '''
    singles, plurals = extract(source)
    assert singles == {'Double "quoted"', "Single", "Template", "After the url {name}"}
    assert plurals == {("{n} item", "{n} items"), ("{n} question", "{n} questions"), ("{n} child", "{n} children")}


def test_html_extraction_reads_data_i18n_outside_comments(tmp_path):
    page = '<p data-i18n="Sign in &amp; more">x</p><!-- <p data-i18n="Hidden"></p> -->'
    stripped = re.sub(r"<!--.*?-->", "", page, flags=re.DOTALL)
    assert {html.unescape(v) for v in DATA_I18N.findall(stripped)} == {"Sign in & more"}


# --- the catalog -------------------------------------------------------------------------------------------------

def test_the_seed_strings_are_extracted():
    singles, plurals = frontend_strings()
    assert "The study server is not responding" in singles
    assert ("{n} question", "{n} questions") in plurals


def test_every_translated_string_has_a_polish_entry_with_the_same_placeholders():
    pl = catalog()
    singles, _ = frontend_strings()
    missing = sorted((singles | html_strings()) - pl.keys())
    assert missing == [], f"add these to {CATALOG.name}: {missing}"
    for msgid in singles | html_strings():
        assert isinstance(pl[msgid], str), msgid
        assert placeholders(pl[msgid]) == placeholders(msgid), msgid


def test_every_plural_has_a_polish_entry_keyed_by_its_many_form():
    pl = catalog()
    _, plurals = frontend_strings()
    missing = sorted(many for _, many in plurals if many not in pl)
    assert missing == [], f"add these to {CATALOG.name}: {missing}"
    for one, many in plurals:
        forms = pl[many]
        assert isinstance(forms, list), many
        english = placeholders(one) | placeholders(many)
        assert all(placeholders(form) <= english for form in forms), many
        assert set().union(*(placeholders(form) for form in forms)) == english, many


def test_plural_entries_have_three_forms():
    for msgid, value in catalog().items():
        if isinstance(value, list):
            assert len(value) == 3 and all(isinstance(f, str) and f for f in value), msgid
        else:
            assert isinstance(value, str) and value, msgid


def test_the_catalog_and_the_i18n_module_are_public(serve):
    http = serve()
    status, headers, body = http("/i18n/pl.json")
    assert status == 200 and headers["Content-Type"].startswith("application/json")
    assert json.loads(body) == catalog()
    assert http("/js/core/i18n.js")[0] == 200
    assert http("/i18n/xx.json")[0] == 404


@pytest.mark.parametrize("module", ["js/core/api.js", "js/core/session.js", "js/auth/form.js", "js/views/settings.js"])
def test_every_fetch_sends_the_language(module):
    code = strip_comments((STATIC / module).read_text(encoding="utf-8"))
    calls = [m.end() for m in re.finditer(r"(?<![\w$.])fetch\(", code)]
    assert calls
    for start in calls:
        args = split_arguments(code, start)
        assert len(args) == 2 and "X-Language" in args[1], f"{module}: fetch({', '.join(args)})"


def test_no_fetch_elsewhere_skips_the_language():
    unchecked = {"js/core/api.js", "js/core/session.js", "js/auth/form.js", "js/views/settings.js", "js/core/i18n.js"}
    for path in (STATIC / "js").rglob("*.js"):
        rel = path.relative_to(STATIC).as_posix()
        if rel not in unchecked:
            assert not re.search(r"(?<![\w$.])fetch\(", strip_comments(path.read_text(encoding="utf-8"))), rel
