"""The optional AI tutor, with a fake Claude client (no API key or network needed)."""

import json
import types

import pytest

import content
import server
import tutor


class FakeClient:
    def __init__(self, text="An explanation.", stop_reason="end_turn"):
        self.calls = []
        self.text, self.stop_reason = text, stop_reason
        self.beta = types.SimpleNamespace(messages=types.SimpleNamespace(create=self.create))

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return types.SimpleNamespace(stop_reason=self.stop_reason,
                                     content=[types.SimpleNamespace(type="text", text=self.text)])


Q = next(q for q in content.QUESTIONS if q["id"] == "q06-on-filter")


def test_why_wrong_sends_the_question_the_choice_and_the_confidence():
    client = FakeClient()
    assert tutor.Tutor(client).why_wrong(Q, [0], "sure") == "An explanation."
    call = client.calls[0]
    assert call["model"] == tutor.MODEL and call["fallbacks"] == "default" and call["betas"] == [tutor.FALLBACK_BETA]
    prompt = call["messages"][0]["content"]
    assert "picked A" in prompt and "'sure'" in prompt and f"Correct answer: {tutor.letters(Q['answer'])}" in prompt


def test_a_correct_guess_asks_how_to_be_sure_next_time():
    prompt = tutor.why_wrong_prompt(Q, Q["answer"], "guess")
    assert "said they were guessing" in prompt


def test_lab_hint_includes_the_real_error_and_forbids_the_solution():
    lab = next(lab for lab in content.LABS if lab["id"] == "lab-headcount-all")
    result = {"passed": False, "error": "ORA-00979: not a GROUP BY expression",
              "explain": {"hint": "d.department_name is not in GROUP BY"}}
    prompt = tutor.lab_hint_prompt(lab, "SELECT ...", result, "departments(department_id NUMBER(4))")
    assert "ORA-00979" in prompt and "d.department_name is not in GROUP BY" in prompt
    assert "Never show it" in prompt and lab["solution"] in prompt


def test_refusals_and_truncation_become_tutor_errors():
    with pytest.raises(tutor.TutorError, match="declined"):
        tutor.Tutor(FakeClient(stop_reason="refusal")).why_wrong(Q, [0], None)
    with pytest.raises(tutor.TutorError, match="cut off"):
        tutor.Tutor(FakeClient(stop_reason="max_tokens")).why_wrong(Q, [0], None)


def test_generate_requests_structured_json():
    client = FakeClient(text=json.dumps({"questions": []}))
    assert tutor.Tutor(client).generate("7.4", "OUTER joins", [Q], "employees(...)", 2) == []
    fmt = client.calls[0]["output_config"]["format"]
    assert fmt["type"] == "json_schema" and fmt["schema"]["properties"]["questions"]["type"] == "array"
    assert "Write 2 new, original" in client.calls[0]["messages"][0]["content"]


def test_status_can_be_switched_off(monkeypatch):
    monkeypatch.setenv("STUDY_TUTOR", "off")
    assert tutor.status() == {"available": False, "reason": "Disabled with STUDY_TUTOR=off."}


def draft(prompt, options, answer, **extra):
    return {"prompt": prompt, "code": "", "options": options, "answer": answer, "explanation": "Because.",
            "answer_sql": "", "try_sql": "", "try_error": "", **extra}


def test_generated_questions_are_verified_on_the_database_before_review(tmp_path, monkeypatch):
    try:
        server.connect().close()
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"database not reachable: {exc}")
    drafts = [
        draft("How many departments are there?", ["3", "4", "5", "9"], [1], answer_sql="SELECT COUNT(*) FROM departments"),
        draft("How many employees are there?", ["8", "9", "10", "11"], [0], answer_sql="SELECT COUNT(*) FROM employees"),
        draft("Which statement is true about outer joins?", ["a", "b", "c", "d"], [0]),
    ]
    monkeypatch.setattr(server, "TUTOR", tutor.Tutor(FakeClient(text=json.dumps({"questions": drafts}))))
    monkeypatch.setattr(server, "QUEUE_FILE", tmp_path / "queue.json")
    monkeypatch.setattr(content, "GENERATED_FILE", tmp_path / "generated.json")
    monkeypatch.setattr(content, "QUESTIONS", list(content.QUESTIONS))
    monkeypatch.setattr(server, "QUESTIONS_BY_ID", dict(server.QUESTIONS_BY_ID))

    result = server.generate_questions("7.4", 3)
    assert [i["question"]["prompt"] for i in result["added"]] == ["How many departments are there?"]
    problems = {i["question"]["prompt"]: i["problems"] for i in result["rejected"]}
    assert "answer_sql returns '9'" in problems["How many employees are there?"][0]
    assert "cannot be checked on the database" in problems["Which statement is true about outer joins?"][0]

    qid = result["added"][0]["question"]["id"]
    assert qid.startswith("q06-gen-") and result["added"][0]["question"]["topic"] == "t06"
    assert server.generate_questions("7.4", 1)["rejected"][0]["problems"][0] == "a question with the same prompt already exists"
    server.accept_question(qid)
    assert server.load_queue() == [] and qid in server.QUESTIONS_BY_ID
    assert json.loads((tmp_path / "generated.json").read_text())[0]["id"] == qid
