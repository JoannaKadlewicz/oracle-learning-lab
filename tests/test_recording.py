import time

import pytest

from oracle_lab import content
from oracle_lab.study import engine, mocks, recording
from oracle_lab.study.progress import snapshot
from oracle_lab.study.tracks import track_state

Q = next(q for q in content.QUESTIONS if len(q["answer"]) == 2)


def empty():
    return {"attempts": {}, "cards": {}, "labs": {}, "settings": {}}


def test_the_server_decides_whether_an_answer_is_correct():
    state = empty()
    recording.record_attempt(state, {"id": Q["id"], "chosen": list(reversed(Q["answer"])), "correct": False,
                                     "confidence": "sure", "mode": "exam"}, 100.0)
    recording.record_attempt(state, {"id": Q["id"], "chosen": Q["answer"][:1], "correct": True}, 200.0)
    first, second = state["attempts"][Q["id"]]
    assert first == {"t": 100.0, "correct": True, "chosen": sorted(Q["answer"]), "confidence": "sure", "mode": "exam"}
    assert second["correct"] is False and second["confidence"] is None and second["mode"] == "practice"


def test_out_of_range_choices_and_unknown_ratings_are_dropped():
    state = empty()
    recording.record_attempt(state, {"id": Q["id"], "chosen": [99, -1], "confidence": "very"}, 1.0)
    assert state["attempts"][Q["id"]][0]["chosen"] == []
    assert state["attempts"][Q["id"]][0]["confidence"] is None


def test_card_reviews_are_appended():
    state = empty()
    card = content.FLASHCARDS[0]["id"]
    recording.record_card(state, {"id": card, "rating": "good"}, 1.0)
    recording.record_card(state, {"id": card, "rating": "again"}, 2.0)
    assert state["cards"][card] == {"reviews": [[1.0, "good"], [2.0, "again"]]}
    with pytest.raises(ValueError):
        recording.record_card(state, {"id": card, "rating": "maybe"}, 3.0)


def test_settings_are_validated():
    state = empty()
    recording.record_settings(state, {"exam_date": "2026-12-01", "daily_minutes": "45"})
    assert state["settings"] == {"exam_date": "2026-12-01", "daily_minutes": 45}
    recording.record_settings(state, {"exam_date": ""})
    assert state["settings"]["exam_date"] is None
    with pytest.raises(ValueError):
        recording.record_settings(state, {"exam_date": "next week"})
    with pytest.raises(ValueError):
        recording.record_settings(state, {"daily_minutes": 0})
    recording.record_settings(state, {"new_cards_per_day": "20"})
    assert state["settings"]["new_cards_per_day"] == 20
    recording.record_settings(state, {"new_cards_per_day": 0})
    for bad in (-1, 101, "many"):
        with pytest.raises(ValueError):
            recording.record_settings(state, {"new_cards_per_day": bad})
    recording.record_settings(state, {"exam": "1Z0-171"})
    assert state["settings"]["exam"] == "1Z0-171"
    with pytest.raises(ValueError):
        recording.record_settings(state, {"exam": "1Z0-999"})


def test_the_language_setting_is_one_of_the_languages():
    state = empty()
    for lang in ("pl", "en"):
        recording.record_settings(state, {"language": lang})
        assert state["settings"]["language"] == lang
    for bad in ("de", "", None, "PL", 1):
        with pytest.raises(ValueError, match="language must be one of en, pl"):
            recording.record_settings(state, {"language": bad})
    assert state["settings"]["language"] == "en"


def test_progress_snapshot_works_on_an_empty_state():
    snap = snapshot(empty(), time.time())
    progress = snap["progress"]
    track = content.for_exam(content.DEFAULT_EXAM)
    assert progress["exam"] == content.DEFAULT_EXAM
    assert set(progress["objectives"]) == set(track.OBJECTIVES)
    assert progress["mistakes"] == [] and progress["due_reviews"] == 0
    assert len(progress["due_cards"]) == min(engine.DEFAULT_NEW_CARDS, len(track.FLASHCARDS))
    assert progress["plan"]["questions"] and progress["plan"]["lab"]


def test_each_exam_track_only_sees_its_own_mock_exams():
    state = empty()
    state["settings"]["exam"] = "1Z0-171"
    mock = mocks.start_mock(state, {"count": 5, "minutes": 10}, time.time())
    assert mock["exam"] == "1Z0-171"
    assert track_state(state)["mocks"] == [mock]
    state["settings"]["exam"] = "1Z0-071"
    assert track_state(state)["mocks"] == []
    assert set(snapshot(state, time.time())["progress"]["objectives"]) == set(content.for_exam("1Z0-071").OBJECTIVES)


def test_record_card_accepts_hard():
    state = empty()
    card = content.FLASHCARDS[0]["id"]
    recording.record_card(state, {"id": card, "rating": "hard"}, 1.0)
    assert state["cards"][card] == {"reviews": [[1.0, "hard"]]}
