"""What the front end needs after every change: the raw state and the computed progress."""

from __future__ import annotations

from typing import Any

from oracle_lab.i18n import DEFAULT_LANGUAGE, translate
from oracle_lab.study import engine
from oracle_lab.study.state import State
from oracle_lab.study.tracks import exam_code, track, track_state


def snapshot(state: State, now: float, sql_available: bool = True, lang: str = DEFAULT_LANGUAGE) -> dict[str, Any]:
    progress = engine.progress(track(state), track_state(state), now, sql_available)
    return {"state": state, "progress": {**localized(progress, lang), "exam": exam_code(state)},
            "sql_available": sql_available}


def localized(progress: dict[str, Any], lang: str) -> dict[str, Any]:
    """The progress with the texts the engine writes for the learner (plan advice, badges, the
    ready-to-book checklist) in `lang`; numbers, ids and everything else stay as they are."""
    if lang == DEFAULT_LANGUAGE:
        return progress

    def tr(text: str) -> str:
        return translate(lang, text)

    plan, ready = progress["plan"], progress["ready"]
    return {
        **progress,
        "plan": {**plan, "advice": [tr(a) for a in plan["advice"]]},
        "badges": [{**b, "title": tr(b["title"]), "description": tr(b["description"])} for b in progress["badges"]],
        "ready": {**ready, "items": [{**i, "label": tr(i["label"]), "detail": tr(i["detail"])} for i in ready["items"]]},
    }
