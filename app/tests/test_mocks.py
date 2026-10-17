import random
import types

import pytest

import content
import engine
import server

NOW = 1_800_000_000.0
DAY = engine.DAY


def q(qid, objective, answer=(0,)):
    return {"id": qid, "topic": "t0" + objective[0], "objective": objective, "answer": list(answer),
            "options": ["a", "b", "c", "d"]}


SMALL = types.SimpleNamespace(
    TOPICS={"t06": "Joins", "t07": "Subqueries"},
    OBJECTIVES={"6.1": "x", "7.1": "y", "7.2": "z"},
    QUESTIONS=[q("q06-a", "6.1"), q("q06-b", "6.1"), q("q07-a", "7.1"), q("q07-b", "7.1"),
               q("q07-c", "7.2", (0, 1))],
    FLASHCARDS=[], LABS=[],
    EXAM={"questions": 3, "minutes": 6, "passing_pct": 63},
)


def empty():
    return {"attempts": {}, "cards": {}, "labs": {}, "settings": {}, "mocks": []}


# ---------------------------------------------------------------- building mocks

def test_a_mock_covers_every_objective_before_repeating_one():
    mock = engine.build_mock(SMALL, empty(), NOW, 3, 6, rng=random.Random(4))
    assert sorted(SMALL.QUESTIONS[[x["id"] for x in SMALL.QUESTIONS].index(i)]["objective"] for i in mock["items"]) == ["6.1", "7.1", "7.2"]
    assert mock["seen_before"] == [] and mock["submitted"] is None


def test_fresh_questions_come_before_practised_and_mocked_ones():
    state = empty()
    state["attempts"]["q06-a"] = [{"t": NOW, "correct": True}]
    state["mocks"].append({"items": ["q07-a"], "started": NOW - DAY})
    mock = engine.build_mock(SMALL, state, NOW, 3, 6, rng=random.Random(1))
    assert set(mock["items"]) == {"q06-b", "q07-b", "q07-c"}
    mock = engine.build_mock(SMALL, state, NOW, 5, 6, rng=random.Random(1))
    assert sorted(mock["seen_before"]) == ["q06-a", "q07-a"]


def test_the_real_pool_gives_one_question_per_objective_in_a_full_mock():
    mock = engine.build_mock(content, empty(), NOW, content.EXAM["questions"], content.EXAM["minutes"])
    objectives = {next(x for x in content.QUESTIONS if x["id"] == i)["objective"] for i in mock["items"]}
    assert len(mock["items"]) == 63 and objectives == set(content.OBJECTIVES)


# ---------------------------------------------------------------- reports

def submitted_mock(answers, events=(), seen=()):
    return {"id": "m1", "started": NOW, "minutes": 6, "topics": None, "items": ["q06-a", "q07-a", "q07-c"],
            "seen_before": list(seen), "answers": answers, "events": list(events),
            "time_on": {"q06-a": 30, "q07-a": 200, "q07-c": 90}, "submitted": NOW + 300, "abandoned": None}


def test_report_scores_sections_question_types_and_freshness():
    mock = submitted_mock({"q06-a": {"chosen": [0], "confidence": "sure"}, "q07-c": {"chosen": [0]}}, seen=["q06-a"])
    r = engine.mock_report(SMALL, mock)
    assert r["score"] == [1, 3] and r["pct"] == 33 and not r["passed"] and r["full"]
    assert r["fresh"] == [0, 2]
    assert r["by_section"] == {"6": [1, 1], "7": [0, 2]}
    assert r["single"] == [1, 2] and r["multi"] == [0, 1]
    assert r["unanswered"] == ["q07-a"]
    assert r["confidence"]["sure"] == [1, 1]
    assert r["slowest"][0] == "q07-a" and r["minutes_used"] == 5.0 and r["pace_seconds"] == 120


def test_report_tracks_answers_changed_from_right_to_wrong():
    events = [[NOW + 1, "q06-a", [0]], [NOW + 50, "q06-a", [2]],   # right -> wrong
              [NOW + 2, "q07-a", [3]], [NOW + 60, "q07-a", [0]]]   # wrong -> right
    mock = submitted_mock({"q06-a": {"chosen": [2]}, "q07-a": {"chosen": [0]}}, events)
    changes = engine.mock_report(SMALL, mock)["changes"]
    assert changes == {"right_to_wrong": ["q06-a"], "wrong_to_right": ["q07-a"], "wrong_to_wrong": []}


# ---------------------------------------------------------------- readiness

def first_answers(n_right, n_wrong, mode="exam"):
    ids = [x["id"] for x in content.QUESTIONS]
    attempts = {}
    for i in range(n_right + n_wrong):
        attempts[ids[i]] = [{"t": NOW, "correct": i < n_right, "mode": mode},
                            {"t": NOW, "correct": True, "mode": "practice"}]  # repeats must not count
    return {**empty(), "attempts": attempts}


def test_readiness_needs_enough_first_answers():
    r = engine.readiness(content, first_answers(5, 5), NOW)
    assert r["status"] == "insufficient" and r["evidence"] == 10.0


def test_readiness_uses_first_answers_only():
    strong = engine.readiness(content, first_answers(45, 15), NOW)
    weak = engine.readiness(content, first_answers(25, 35), NOW)
    assert strong["status"] == "ok" and strong["expected_pct"] == 74
    assert strong["pass_probability"] > 0.8 > 0.2 > weak["pass_probability"]
    assert strong["low_pct"] < strong["expected_pct"] < strong["high_pct"]


def test_first_answers_in_practice_count_less():
    exam = engine.readiness(content, first_answers(20, 10, "exam"), NOW)["evidence"]
    practice = engine.readiness(content, first_answers(20, 10, "practice"), NOW)["evidence"]
    assert (exam, practice) == (30.0, 18.0)


def test_beta_binomial_sums_to_one():
    assert abs(sum(engine.beta_binomial_pmf(63, 3.5, 2.0)) - 1) < 1e-9


# ---------------------------------------------------------------- server flow

def test_start_answer_and_submit_a_mock():
    state = empty()
    mock = server.start_mock(state, {"count": 3, "minutes": 10}, NOW)
    first, second = mock["items"][:2]
    right = content_answer(first)
    server.answer_mock(state, {"mock_id": mock["id"], "id": first, "chosen": right, "confidence": "sure"}, NOW + 5)
    server.answer_mock(state, {"mock_id": mock["id"], "id": second, "flagged": True,
                               "time_on": {first: 12, second: 7, "q99-other": 3}}, NOW + 9)
    assert mock["answers"][second] == {"chosen": [], "confidence": None, "flagged": True}
    assert mock["time_on"] == {first: 12.0, second: 7.0}
    server.submit_mock(state, mock, NOW + 20)
    assert mock["submitted"] == NOW + 20
    assert state["attempts"][first][0] | {"chosen": None} == {"t": NOW + 20, "correct": True, "chosen": None,
                                                              "confidence": "sure", "mode": "exam"}
    assert second not in state["attempts"]  # unanswered: scores zero, but is not recorded as an answer
    assert engine.mock_report(content, mock)["score"] == [1, 3]
    with pytest.raises(ValueError):
        server.answer_mock(state, {"mock_id": mock["id"], "id": first, "chosen": [0]}, NOW + 21)


def test_starting_a_mock_abandons_the_running_one():
    state = empty()
    old = server.start_mock(state, {"count": 3}, NOW)
    new = server.start_mock(state, {"count": 3}, NOW + 60)
    assert old["abandoned"] == NOW + 60 and new["abandoned"] is None
    assert engine.active_mock(state, NOW + 61)["id"] == new["id"]


def test_expired_mocks_are_submitted_at_their_deadline():
    state = empty()
    mock = server.start_mock(state, {"count": 3, "minutes": 10}, NOW)
    server.finalize_expired(state, NOW + 10 * 60 + engine.MOCK_GRACE - 1)
    assert mock["submitted"] is None
    server.finalize_expired(state, NOW + 3600)
    assert mock["submitted"] == NOW + 600 and state["attempts"] == {}


def content_answer(qid):
    return next(x for x in content.QUESTIONS if x["id"] == qid)["answer"]
