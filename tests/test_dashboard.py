import datetime

from oracle_lab import content
from oracle_lab.study import engine

NOW = datetime.datetime(2026, 10, 17, 20, 0).timestamp()
DAY = engine.DAY
QIDS = [q["id"] for q in content.QUESTIONS]


def answer(t, correct=True, confidence="sure"):
    return {"t": t, "correct": correct, "chosen": [], "confidence": confidence, "mode": "practice"}


def test_streak_counts_back_from_today_or_yesterday():
    state = {"attempts": {"q": [answer(NOW - d * DAY) for d in (1, 2, 3, 5)]}}
    a = engine.activity(state, NOW)
    assert a["streak"] == 3 and a["active_days"] == 4
    assert len(a["days"]) == engine.ACTIVITY_DAYS and a["days"][-1]["date"] == "2026-10-17"
    assert engine.activity({}, NOW)["streak"] == 0


def test_hours_cap_long_pauses():
    # three actions one minute apart, then one more an hour later: 2 min + 1 min per session start (2)
    times = [NOW, NOW + 60, NOW + 120, NOW + 3720]
    state = {"attempts": {"q": [answer(t) for t in times]}}
    assert engine.activity(state, NOW + 4000)["hours"] == round((120 + 120) / 3600, 1)


def test_clean_run_resets_on_wrong_answers_and_guesses():
    attempts = {"a": [answer(NOW + i) for i in range(5)] + [answer(NOW + 10, True, "guess")] +
                     [answer(NOW + 20 + i * DAY) for i in range(3)]}
    assert engine.best_clean_run(attempts) == (5, 1)
    attempts["b"] = [answer(NOW + 15, False)]
    assert engine.best_clean_run(attempts) == (5, 1)


def test_badges_show_progress_and_need_real_evidence():
    by_objective, _ = engine.mastery(content, {}, NOW)
    empty = {b["id"]: b for b in engine.badges(content, {}, NOW, by_objective)}
    assert not any(b["earned"] for b in empty.values())
    assert empty["coverage"]["progress"] == [0, len(content.OBJECTIVES)]

    state = {"attempts": {QIDS[i]: [answer(NOW - (i % 4) * DAY + i)] for i in range(30)}}
    earned = {b["id"]: b for b in engine.badges(content, state, NOW, engine.mastery(content, state, NOW)[0])}
    assert earned["clean-run"]["earned"]  # 30 correct "sure" answers over 4 days
    guessed = {"attempts": {QIDS[i]: [answer(NOW - (i % 4) * DAY + i, True, "guess")] for i in range(30)}}
    assert not {b["id"]: b for b in engine.badges(content, guessed, NOW, by_objective)}["clean-run"]["earned"]


def test_calibrated_badge_progress_is_capped_until_both_criteria_hold():
    def calibrated(wrong):
        state = {"attempts": {QIDS[i]: [answer(NOW - i, i >= wrong)] for i in range(60)}}
        by_objective, _ = engine.mastery(content, state, NOW)
        return {b["id"]: b for b in engine.badges(content, state, NOW, by_objective)}["calibrated"]
    weak = calibrated(wrong=20)  # 60 sure answers, only 67% correct
    assert not weak["earned"] and weak["progress"] == [49, 50]
    strong = calibrated(wrong=2)
    assert strong["earned"] and strong["progress"] == [50, 50]


def test_opening_the_solution_blocks_the_schema_builder_badge():
    ddl = [lab["id"] for lab in content.LABS if lab.get("kind") == "ddl"]
    state = {"labs": {lid: {"tries": 1, "passed": True, "t": NOW} for lid in ddl}}
    by_objective, _ = engine.mastery(content, state, NOW)
    assert {b["id"]: b for b in engine.badges(content, state, NOW, by_objective)}["ddl-own-work"]["earned"]
    state["labs"][ddl[0]]["solution_seen"] = True
    assert not {b["id"]: b for b in engine.badges(content, state, NOW, by_objective)}["ddl-own-work"]["earned"]


def full_mock(started, fresh_right, fresh=63):
    items = QIDS[:63]
    answers = {qid: {"chosen": next(q for q in content.QUESTIONS if q["id"] == qid)["answer"] if i < fresh_right else []}
               for i, qid in enumerate(items)}
    return {"id": f"m{started}", "started": started, "minutes": 120, "topics": None, "items": items,
            "seen_before": items[fresh:], "answers": answers, "events": [], "time_on": {},
            "submitted": started + 3600, "abandoned": None}


def test_fresh_mock_passes_need_80_percent_on_new_questions_and_3_days_between():
    state = {"mocks": [full_mock(NOW - 9 * DAY, 55), full_mock(NOW - 8 * DAY, 60), full_mock(NOW - 5 * DAY, 30),
                       full_mock(NOW - 2 * DAY, 52)]}
    assert engine.fresh_mock_passes(content, state) == 2  # day 9 and day 2; day 8 too close, day 5 too low
    assert engine.fresh_mock_passes(content, {"mocks": [full_mock(NOW, 40, fresh=40)]}) == 0  # under 50 new questions


def test_ready_to_book_lists_the_definition_of_done():
    by_objective, _ = engine.mastery(content, {}, NOW)
    ready = engine.ready_to_book(content, {}, by_objective)
    assert len(ready["items"]) == 4 and not ready["done"]
    assert ready["items"][2]["detail"] == "no answers rated Sure yet"


def test_report_renders_for_empty_and_used_progress():
    from oracle_lab.web import report

    empty = report.render(content, {}, engine.progress(content, {}, NOW), NOW)
    assert "Not enough evidence yet" in empty and "No mock exams yet." in empty
    state = {"attempts": {QIDS[i]: [answer(NOW - i)] for i in range(40)},
             "labs": {content.LABS[0]["id"]: {"tries": 1, "passed": True, "t": NOW}},
             "mocks": [full_mock(NOW - DAY, 50)]}
    html = report.render(content, state, engine.progress(content, state, NOW), NOW)
    assert "estimated chance to pass" in html and "Full mock" in html and "<svg" in html
    assert f"1 of {sum(1 for lab in content.LABS if lab.get('kind', 'query') == 'query')} query" in html


def test_demo_history_is_consistent_and_feeds_every_dashboard_part():
    from oracle_lab.tools import demo

    state = demo.simulate(days=20, seed=3, now=NOW)
    progress = engine.progress(content, state, NOW)
    assert len(progress["mocks"]) == 3 and progress["activity"]["active_days"] >= 10
    assert progress["readiness"]["status"] == "ok"
    assert all(a["t"] <= NOW for h in state["attempts"].values() for a in h)
