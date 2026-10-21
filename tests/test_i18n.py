import ast
import json
import re
from importlib.resources import files
from pathlib import Path

from oracle_lab import i18n
from oracle_lab.web.http import Request, Response
from oracle_lab.web.middleware import error_boundary, language

SRC = Path(i18n.__file__).resolve().parents[1]


def test_negotiate():
    assert i18n.negotiate("pl", None) == "pl"
    assert i18n.negotiate("xx", "pl-PL,pl;q=0.9,en;q=0.8") == "pl"
    assert i18n.negotiate(None, "de-DE,en;q=0.5") == "en"
    assert i18n.negotiate(None, None) == "en"


def test_negotiate_honours_quality_and_ignores_junk():
    assert i18n.negotiate("", "en;q=0.9,pl;q=0.8") == "en"
    assert i18n.negotiate("", "en;q=0.5,pl") == "pl"
    assert i18n.negotiate(" PL ", None) == "pl"
    assert i18n.negotiate(None, "pl;q=0,en;q=0.1") == "en"
    assert i18n.negotiate(None, ";;,q=,pl;q=abc") == "en"


def test_polish_plural_forms():
    assert [i18n.polish_form(n) for n in (1, 2, 4, 5, 12, 14, 21, 22, 25, 112)] == [0, 1, 1, 2, 2, 2, 2, 1, 2, 2]


def test_translate_plain_and_templated():
    assert i18n.translate("en", "Login required") == "Login required"
    assert i18n.translate("pl", "Login required") != "Login required"
    m = i18n.Msg.of("daily_minutes must be between {low} and {high}", low=10, high=240)
    assert str(m) == "daily_minutes must be between 10 and 240"
    assert "10" in i18n.translate("pl", m) and "240" in i18n.translate("pl", m) and i18n.translate("pl", m) != str(m)
    assert i18n.translate("pl", "A message nobody translated") == "A message nobody translated"


def test_msg_is_plain_english_for_logs_and_untranslated_templates_fall_back():
    m = i18n.Msg.of("Nobody translated {thing}", thing="this")
    assert m == "Nobody translated this" and m.template == "Nobody translated {thing}" and m.params == {"thing": "this"}
    assert i18n.translate("pl", m) == "Nobody translated this"
    assert i18n.translate("en", m) == "Nobody translated this"
    assert i18n.message_of(ValueError(m)) is m
    assert i18n.message_of(KeyError("x")) == str(KeyError("x"))


def test_ntranslate():
    one, many = "{n} question", "{n} questions"
    assert i18n.ntranslate("en", 1, one, many, n=1) == "1 question"
    assert i18n.ntranslate("en", 5, one, many, n=5) == "5 questions"
    assert i18n.ntranslate("pl", 5, one, many, n=5) == "5 questions"  # no catalog entry: English
    i18n.catalog("pl")[many] = ["{n} pytanie", "{n} pytania", "{n} pytań"]
    try:
        assert [i18n.ntranslate("pl", n, one, many, n=n) for n in (1, 3, 5)] == ["1 pytanie", "3 pytania", "5 pytań"]
    finally:
        del i18n.catalog("pl")[many]


def test_catalog_placeholders_match():
    cat = json.loads(files("oracle_lab.i18n").joinpath("pl.json").read_text("utf-8"))
    for key, value in cat.items():
        forms = value if isinstance(value, list) else [value]
        assert all(set(re.findall(r"{\w+}", f)) == set(re.findall(r"{\w+}", key)) for f in forms), key


def test_catalog_has_polish_copy():
    for key, value in i18n.catalog("pl").items():
        for form in value if isinstance(value, list) else [value]:
            assert form.strip() and "!" not in form, key


# The exceptions whose message is shown to the user (error_boundary, respond(), the admin controller).
_SHOWN = {"HttpError", "AuthError", "InvalidCredentials", "LoginRequired", "RegistrationClosed", "EmailTaken",
          "WeakPassword", "Throttled", "ReauthRequired", "NotFound", "NotFoundError", "PracticeUnavailable"}
# Modules whose ValueError reaches the learner as a 400 through respond() or the admin controller.
_VALUE_ERRORS_SHOWN = {"study/recording.py", "study/mocks.py", "services/admin.py", "services/study.py"}


def _strings_of(node: ast.AST, constants: dict[str, str]) -> list[str]:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return [node.value]
    if isinstance(node, ast.Name):
        return [constants[node.id]] if node.id in constants else []
    if isinstance(node, ast.IfExp):  # PREPARING if ... else FAILED
        return _strings_of(node.body, constants) + _strings_of(node.orelse, constants)
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "of" and node.args:
        return _strings_of(node.args[0], constants)
    return []


def _message_args(node: ast.Call, rel: str) -> list[ast.expr]:
    """The arguments of a call that carry a message shown to the user (none for other calls)."""
    func, args = node.func, node.args
    name = func.id if isinstance(func, ast.Name) else func.attr if isinstance(func, ast.Attribute) else ""
    if name == "of" and getattr(func, "value", None) is not None and getattr(func.value, "id", "") == "Msg":
        return args[:1]
    if name == "HttpError" or (name == "fail" and rel == "auth/google.py"):  # fail(): a GoogleOutcome's message
        return args[1:2]
    if name == "tr" and rel == "web/report.py":  # the printable report's texts
        return args[:1]
    if name == "_tr" and rel == "web/report.py":
        return args[1:2]
    if name == "ntranslate":  # the catalog key of a plural is its `many` form
        return args[3:4]
    if name in _SHOWN or (name == "ValueError" and rel in _VALUE_ERRORS_SHOWN):
        return args[:1]
    return []


def _password_problems(tree: ast.Module) -> list[ast.Constant]:
    """The texts in PasswordPolicy.problems."""
    return [sub for node in ast.walk(tree) if isinstance(node, ast.FunctionDef) and node.name == "problems"
            for sub in ast.walk(node) if isinstance(sub, ast.Constant) and isinstance(sub.value, str) and sub.value]


def _shown_messages() -> dict[str, str]:
    """Every literal message a user can get in an `error` or `problems` field, with where it comes from."""
    found: dict[str, str] = {}
    for path in sorted(SRC.rglob("*.py")):
        rel = path.relative_to(SRC).as_posix()
        if rel.startswith(("content/", "tools/")):
            continue
        tree = ast.parse(path.read_text("utf-8"))
        constants = {t.id: n.value.value for n in tree.body if isinstance(n, ast.Assign)
                     and isinstance(n.value, ast.Constant) and isinstance(n.value.value, str)
                     for t in n.targets if isinstance(t, ast.Name)}
        for node in ast.walk(tree):
            for arg in _message_args(node, rel) if isinstance(node, ast.Call) else []:
                for text in _strings_of(arg, constants):
                    found[text] = f"{rel}:{node.lineno}"
        if rel == "auth/passwords.py":
            found.update({c.value: f"{rel}:{c.lineno}" for c in _password_problems(tree)})
    return found


def test_every_shown_server_message_has_a_polish_entry():
    shown = _shown_messages()
    assert len(shown) > 40  # the scan found the messages
    for template in ("Use at least {count} characters.", "daily_minutes must be between {low} and {high}",
                     "Your practice database is being prepared. Try again in a minute.", "Not found"):
        assert template in shown, template
    missing = {text: where for text, where in shown.items() if text not in i18n.catalog("pl")}
    assert not missing


def test_fixed_texts_have_polish_entries():
    from oracle_lab.auth import google

    for text in ("Internal server error", "Request body too large", google.GENERIC):
        assert i18n.translate("pl", text) != text


def test_language_middleware_sets_the_request_language():
    seen = []

    def handler(request):
        seen.append(request.language)
        return Response.json({})

    for headers, expected in (({}, "en"), ({"x-language": "pl"}, "pl"), ({"accept-language": "pl-PL"}, "pl"),
                              ({"x-language": "en", "accept-language": "pl"}, "en")):
        language(Request("GET", "/", headers), handler)
        assert seen[-1] == expected


def test_error_boundary_translates_for_the_request_language():
    def boom(_):
        raise RuntimeError("secret detail")

    response = language(Request("GET", "/", {"x-language": "pl"}), lambda r: error_boundary(r, boom))
    assert response.status == 500 and json.loads(response.body)["error"] == i18n.translate("pl", "Internal server error")
    response = error_boundary(Request("GET", "/", {}), boom)
    assert json.loads(response.body) == {"error": "Internal server error"}
