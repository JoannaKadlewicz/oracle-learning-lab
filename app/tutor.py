"""Optional AI tutor using the Claude API.

Three uses, each grounded in data the app has already verified against Oracle:
  why_wrong()   explain the misconception behind a wrong (or guessed) quiz answer
  lab_hint()    one hint for a failed exercise, built from the real error or row diff; never the solution
  generate()    draft new questions as JSON; the caller verifies them against the database

The app works fully without it. It is enabled when the `anthropic` package is installed and
credentials are configured (ANTHROPIC_API_KEY, ANTHROPIC_AUTH_TOKEN, or an `ant auth login`
profile). STUDY_TUTOR=off disables it; STUDY_TUTOR_MODEL overrides the model.
"""

import json
import os
from pathlib import Path

MODEL = os.environ.get("STUDY_TUTOR_MODEL", "claude-opus-5-5")
# If Claude declines a request, the API re-runs it on a fallback model chosen by the server.
FALLBACK_BETA = "server-side-fallback-2026-07-01"
LETTERS = "ABCDEFGH"

SYSTEM = (
    "You are a precise Oracle Database 19c SQL tutor helping someone prepare for the "
    "Oracle Database SQL (1Z0-071) certification exam. The questions, answers and expected "
    "results you are given were verified by running them on a real Oracle 19c database: treat "
    "them as correct. Be concrete and brief. Plain text only: no headings, no bullet lists, "
    "no markdown, at most two short paragraphs."
)


class TutorError(Exception):
    """A tutor request failed in a way the user should see."""


def status():
    """Whether the tutor can be used, and why not."""
    if os.environ.get("STUDY_TUTOR", "").lower() in ("off", "0", "false"):
        return {"available": False, "reason": "Disabled with STUDY_TUTOR=off."}
    try:
        import anthropic  # noqa: F401
    except ImportError:
        return {"available": False, "reason": "Install it with: .venv/bin/pip install -r app/requirements-ai.txt"}
    has_credentials = (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")
                       or (Path.home() / ".config" / "anthropic").exists())
    if not has_credentials:
        return {"available": False, "reason": "Set ANTHROPIC_API_KEY, or run `ant auth login`, then restart the app."}
    return {"available": True, "model": MODEL}


class Tutor:
    def __init__(self, client=None, model=MODEL):
        self._client = client
        self.model = model

    @property
    def client(self):
        if self._client is None:
            import anthropic
            self._client = anthropic.Anthropic()
        return self._client

    def ask(self, prompt, schema=None, effort="medium"):
        output_config = {"effort": effort}
        if schema:
            output_config["format"] = {"type": "json_schema", "schema": schema}
        try:
            response = self.client.beta.messages.create(
                model=self.model,
                max_tokens=16000,
                system=SYSTEM,
                messages=[{"role": "user", "content": prompt}],
                output_config=output_config,
                betas=[FALLBACK_BETA],
                fallbacks="default",
            )
        except Exception as exc:  # noqa: BLE001  shown to the user; the SDK already retried what is retryable
            raise TutorError(f"The Claude API request failed: {type(exc).__name__}: {exc}") from exc
        if response.stop_reason == "refusal":
            raise TutorError("Claude declined this request.")
        if response.stop_reason == "max_tokens":
            raise TutorError("The answer was cut off. Try again.")
        return "".join(block.text for block in response.content if block.type == "text").strip()

    # ------------------------------------------------------------------ quiz

    def why_wrong(self, question, chosen, confidence):
        prompt = why_wrong_prompt(question, chosen, confidence)
        return self.ask(prompt, effort="low")

    # ------------------------------------------------------------------ exercises

    def lab_hint(self, lab, sql, result, schema_text):
        return self.ask(lab_hint_prompt(lab, sql, result, schema_text))

    # ------------------------------------------------------------------ question generator

    def generate(self, objective_id, objective_title, examples, schema_text, count):
        text = self.ask(generate_prompt(objective_id, objective_title, examples, schema_text, count),
                        schema=GENERATED_SCHEMA, effort="high")
        try:
            return json.loads(text)["questions"]
        except (ValueError, KeyError) as exc:
            raise TutorError("Claude returned questions in an unexpected format.") from exc


def option_lines(question):
    return "\n".join(f"{LETTERS[i]}. {opt}" for i, opt in enumerate(question["options"]))


def letters(indexes):
    return ", ".join(LETTERS[i] for i in sorted(indexes)) or "nothing"


def why_wrong_prompt(question, chosen, confidence):
    correct = sorted(chosen) == sorted(question["answer"])
    situation = (f"The learner picked the right answer ({letters(chosen)}) but said they were guessing. "
                 "Explain how to recognise the right answer with confidence next time."
                 if correct else
                 f"The learner picked {letters(chosen)} and rated their confidence as "
                 f"'{confidence or 'not rated'}'. Explain the specific misconception that makes "
                 f"{letters(chosen)} look right, and the rule that makes {letters(question['answer'])} correct.")
    return f"""Exam practice question:
{question['prompt']}
{('Code:' + chr(10) + question['code']) if question.get('code') else ''}
Options:
{option_lines(question)}

Correct answer: {letters(question['answer'])}
Verified explanation: {question['explanation']}

{situation} If a confident wrong answer is involved, say what to check to avoid the trap. At most 150 words."""


def lab_hint_prompt(lab, sql, result, schema_text):
    if result.get("error"):
        outcome = f"It failed with: {result['error']}"
        if (result.get("explain") or {}).get("hint"):
            outcome += f"\nThe app's own analysis: {result['explain']['hint']}"
    else:
        outcome = "It ran, but the result is wrong. " + " ".join(result.get("feedback", []))
        diff = [d for d in result.get("diff") or [] if d["status"] != "ok"][:8]
        if diff:
            outcome += "\nDifferences from the expected result (row status: cells):\n" + "\n".join(
                f"- {d['status']}: {d['cells']}" + (f" expected {d['expected']}" if d.get("expected") else "") for d in diff)
    return f"""SQL exercise ({lab.get('kind', 'query')} exercise):
{lab['task']}

Learner's SQL:
{sql}

{outcome}

Relevant schema:
{schema_text}

Reference solution, for your understanding only. Never show it, quote it, or write a corrected
version of the learner's statement: {lab['solution']}

Give exactly one hint that moves the learner forward from what they wrote: name the specific
part of their statement that causes the problem and the concept to apply, without writing the
fixed SQL. At most 100 words."""


GENERATED_SCHEMA = {
    "type": "object",
    "properties": {
        "questions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "prompt": {"type": "string"},
                    "code": {"type": "string", "description": "SQL shown with the question, or an empty string"},
                    "options": {"type": "array", "items": {"type": "string"}},
                    "answer": {"type": "array", "items": {"type": "integer"}},
                    "explanation": {"type": "string"},
                    "answer_sql": {"type": "string", "description": "A query returning one row with one column whose "
                                   "text equals the correct option exactly, or an empty string"},
                    "try_sql": {"type": "string", "description": "A runnable SELECT or DML demo, or an empty string"},
                    "try_error": {"type": "string", "description": "The ORA- code try_sql raises, e.g. ORA-00904, "
                                  "or an empty string"},
                },
                "required": ["prompt", "code", "options", "answer", "explanation", "answer_sql", "try_sql", "try_error"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["questions"],
    "additionalProperties": False,
}


def generate_prompt(objective_id, objective_title, examples, schema_text, count):
    shown = "\n\n".join(json.dumps({k: q[k] for k in ("prompt", "code", "options", "answer", "explanation", "answer_sql",
                                                       "try_sql", "try_error") if k in q}, ensure_ascii=False)
                        for q in examples)
    return f"""Write {count} new, original multiple-choice practice questions for official 1Z0-071 exam
objective {objective_id} "{objective_title}". Never copy real exam questions.

Rules:
- Oracle Database 19c behaviour. Use the sample schema below.
- 4 or 5 options. If more than one option is correct, the prompt must say "Which two" or "Which three".
- Every question must be checkable on the database: provide answer_sql (one row, one column, text equal to
  the correct option exactly) when the answer is a single value, or try_sql plus try_error when the point
  is which error a statement raises. try_sql may only use SELECT, WITH, INSERT, UPDATE, DELETE, MERGE,
  SAVEPOINT or ROLLBACK (it is rolled back). Use empty strings for fields you do not use.
- The explanation says why the right answer is right and why the tempting wrong options are wrong.
- Do not repeat the existing questions below.

Sample schema:
{schema_text}

Existing questions for this objective:
{shown or '(none)'}"""
