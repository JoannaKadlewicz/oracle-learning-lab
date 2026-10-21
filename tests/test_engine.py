import datetime
import random
import types

from oracle_lab.study import engine

DAY = engine.DAY
NOW = datetime.datetime(2026, 10, 17, 12, 0).timestamp()


def answer(days_ago, correct, confidence="think", mode="practice"):
    return {"t": NOW - days_ago * DAY, "correct": correct, "chosen": [], "confidence": confidence, "mode": mode}


def q(qid, topic="t06", objective="7.4"):
    return {"id": qid, "topic": topic, "objective": objective}


CONTENT = types.SimpleNamespace(
    TOPICS={"t05": "Aggregation", "t06": "Joins"},
    OBJECTIVES={"6.1": "Group functions", "7.4": "Outer joins", "7.2": "Self-joins"},
    QUESTIONS=[q("q06-a"), q("q06-b"), q("q06-c", objective="7.2"), q("q05-a", "t05", "6.1"), q("q05-b", "t05", "6.1")],
    FLASHCARDS=[{"id": "c001", "topic": "t06", "objective": "7.4"}, {"id": "c002", "topic": "t05", "objective": "6.1"}],
    LABS=[{"id": "lab-x", "topic": "t06", "objective": "7.4"}, {"id": "lab-y", "topic": "t05", "objective": "6.1"}],
)
QUESTIONS = {x["id"]: x for x in CONTENT.QUESTIONS}


# ---------------------------------------------------------------- spacing

def test_sm2_intervals_grow_and_reset_on_failure():
    s = engine.sm2([(0, 4)])
    assert (s["reps"], s["interval"]) == (1, 1.0)
    s = engine.sm2([(0, 4), (DAY, 4)])
    assert (s["reps"], s["interval"]) == (2, 3.0)
    s = engine.sm2([(0, 4), (DAY, 4), (4 * DAY, 4)])
    assert s["interval"] == 3.0 * 2.5
    s = engine.sm2([(0, 4), (DAY, 4), (4 * DAY, 1)])
    assert (s["reps"], s["interval"], s["lapses"], s["due"]) == (0, 0.0, 1, 4 * DAY)


def test_ease_never_drops_below_1_3():
    assert engine.sm2([(i, 0) for i in range(10)])["ease"] == 1.3


def test_answer_quality_treats_a_correct_guess_as_a_lapse():
    assert engine.answer_quality(answer(0, True, "sure")) == 5
    assert engine.answer_quality(answer(0, True, "guess")) < 3
    assert engine.answer_quality(answer(0, False, "sure")) == 0
    assert engine.answer_quality({"t": 0, "correct": True}) == 4  # no rating: counts as "think"


def test_cards_are_due_until_reviewed_and_after_their_interval():
    state = {"cards": {"c001": {"reviews": [[NOW - 2 * DAY, "good"]]}}}
    assert engine.due_cards(CONTENT, state, NOW) == ["c001", "c002"]  # interval 1 day: due again
    state = {"cards": {"c001": {"reviews": [[NOW - 2 * DAY, "good"], [NOW - DAY, "good"]]}}}
    assert engine.due_cards(CONTENT, state, NOW) == ["c002"]  # interval now 3 days


# ---------------------------------------------------------------- mistakes

def test_wrong_answer_needs_two_confident_correct_answers_on_different_days():
    history = [answer(3, False)]
    assert engine.open_mistakes({"q06-a": history}, QUESTIONS)[0]["proof"] == 0
    history.append(answer(2, True, "sure"))
    history.append(answer(2, True, "sure"))  # same day does not count twice
    assert engine.open_mistakes({"q06-a": history}, QUESTIONS)[0]["proof"] == 1
    history.append(answer(1, True, "guess"))  # a guess is a new miss
    assert engine.open_mistakes({"q06-a": history}, QUESTIONS)[0] == {
        "id": "q06-a", "reason": "guess", "proof": 0, "misses": 1, "t": NOW - DAY}
    history += [answer(1, True, "think"), answer(0, True, "sure")]
    assert engine.open_mistakes({"q06-a": history}, QUESTIONS) == []


def test_mistakes_are_ordered_confident_first():
    attempts = {
        "q06-a": [answer(1, True, "guess")],
        "q06-b": [answer(2, False, "think")],
        "q06-c": [answer(3, False, "sure")],
    }
    assert [m["id"] for m in engine.open_mistakes(attempts, QUESTIONS)] == ["q06-c", "q06-b", "q06-a"]


def test_questions_removed_from_content_are_ignored():
    assert engine.open_mistakes({"q99-gone": [answer(0, False)]}, QUESTIONS) == []


# ---------------------------------------------------------------- mastery

def test_mastery_starts_new_and_moves_with_evidence():
    by_objective, by_topic = engine.mastery(CONTENT, {}, NOW)
    assert by_objective["7.4"] == {"estimate": 0.5, "evidence": 0, "level": "new"}
    strong = {"attempts": {"q06-a": [answer(0, True, "sure")] * 6}}
    assert engine.mastery(CONTENT, strong, NOW)[0]["7.4"]["level"] == "strong"
    weak = {"attempts": {"q06-a": [answer(0, False)] * 4}}
    assert engine.mastery(CONTENT, weak, NOW)[1]["t06"]["level"] == "weak"


def test_correct_guesses_do_not_build_mastery():
    guesses = {"attempts": {"q06-a": [answer(0, True, "guess")] * 10}}
    assert engine.mastery(CONTENT, guesses, NOW)[0]["7.4"]["estimate"] == 0.5


def test_old_evidence_counts_less():
    recent = engine.evidence(CONTENT, {"attempts": {"q06-a": [answer(0, True)]}}, NOW)["o:7.4"][0]
    old = engine.evidence(CONTENT, {"attempts": {"q06-a": [answer(30, True)]}}, NOW)["o:7.4"][0]
    assert round(old / recent, 6) == 0.5


def test_a_passed_lab_is_strong_evidence():
    state = {"labs": {"lab-x": {"tries": 1, "passed": True, "t": NOW}}}
    assert engine.evidence(CONTENT, state, NOW)["o:7.4"] == [2.0, 0.0]


# ---------------------------------------------------------------- calibration

def test_calibration_counts_rated_answers_only():
    attempts = {"q06-a": [answer(0, True, "sure"), answer(0, False, "sure"), {"t": NOW, "correct": True}]}
    assert engine.calibration(attempts)["sure"] == {"answers": 2, "correct": 1}
    assert engine.calibration(attempts)["think"] == {"answers": 0, "correct": 0}


# ---------------------------------------------------------------- choosing questions

def test_interleave_avoids_repeating_a_key():
    items = ["a1", "a2", "a3", "b1", "c1"]
    assert engine.interleave(items, key=lambda x: x[0]) == ["a1", "b1", "a2", "c1", "a3"]


def test_pick_questions_puts_mistakes_and_due_reviews_first():
    state = {"attempts": {
        "q06-b": [answer(1, False, "sure")],               # open mistake
        "q05-a": [answer(5, True, "sure")],                # due review (interval 1 day)
        "q05-b": [answer(0, True, "sure")],                # answered today, not due
    }}
    picked = engine.pick_questions(CONTENT, state, NOW, 2, rng=random.Random(1))
    assert set(picked) == {"q06-b", "q05-a"}


def test_pick_questions_respects_topics():
    picked = engine.pick_questions(CONTENT, {}, NOW, 10, topics=["t05"], rng=random.Random(1))
    assert sorted(picked) == ["q05-a", "q05-b"]


# ---------------------------------------------------------------- daily plan

def test_daily_plan_fits_the_time_and_counts_days_left():
    state = {"settings": {"exam_date": "2026-10-27", "daily_minutes": 30}}
    plan = engine.daily_plan(CONTENT, state, NOW, rng=random.Random(1))
    assert plan["days_left"] == 10
    assert plan["cards"] == ["c001", "c002"]
    assert plan["lab"] in ("lab-x", "lab-y")
    assert len(plan["questions"]) == 5  # all questions, the pool is small
    assert "Take a timed mock exam this week." in plan["advice"]


def test_daily_plan_skips_the_lab_when_time_is_short():
    plan = engine.daily_plan(CONTENT, {"settings": {"daily_minutes": 10}}, NOW, rng=random.Random(1))
    assert plan["lab"] is None and plan["days_left"] is None


def test_plan_without_sql_has_no_exercise():
    state = {"settings": {"daily_minutes": 30}}
    with_sql = engine.daily_plan(CONTENT, state, NOW, rng=random.Random(1))
    without = engine.daily_plan(CONTENT, state, NOW, rng=random.Random(1), sql_available=False)
    assert with_sql["lab"] and without["lab"] is None
    assert engine.todays_plan(CONTENT, state, NOW, sql_available=False)["lab"] is None
    assert engine.progress(CONTENT, state, NOW, sql_available=False)["plan"]["lab"] is None


def test_todays_plan_ticks_items_off_instead_of_replacing_them():
    state = {"settings": {"daily_minutes": 30}, "attempts": {}, "cards": {}, "labs": {}}
    before = engine.todays_plan(CONTENT, state, NOW)
    assert before["done"] == {"questions": [], "cards": [], "lab": False} and not before["complete"]

    for qid in before["questions"]:
        state["attempts"][qid] = [{**answer(0, True), "t": NOW + 60}]
    state["cards"]["c001"] = {"reviews": [[NOW + 60, "good"]]}
    after = engine.todays_plan(CONTENT, state, NOW + 120)
    assert after["questions"] == before["questions"] and after["cards"] == before["cards"]
    assert after["done"]["questions"] == before["questions"]
    assert after["done"]["cards"] == ["c001"] and not after["complete"]

    state["cards"]["c002"] = {"reviews": [[NOW + 60, "again"]]}
    state["labs"][before["lab"]] = {"tries": 2, "passed": True, "t": NOW + 90}
    assert engine.todays_plan(CONTENT, state, NOW + 120)["complete"]


def test_todays_plan_ignores_work_from_earlier_days():
    state = {"settings": {"daily_minutes": 30}, "cards": {"c001": {"reviews": [[NOW - 3 * DAY, "again"]]}},
             "attempts": {"q06-a": [answer(1, False)]}, "labs": {}}
    plan = engine.todays_plan(CONTENT, state, NOW)
    assert "c001" in plan["cards"] and "q06-a" in plan["questions"]
    assert plan["done"] == {"questions": [], "cards": [], "lab": False}


def test_hard_grows_slower_than_good():
    assert engine.sm2([(0, 3)])["interval"] == 1.0
    s = engine.sm2([(0, 4), (DAY, 4), (4 * DAY, 3)])  # previous interval 3 days, then hard
    assert s["interval"] == max(3.0 * 1.2, 3.0 + 1) and s["reps"] == 3


def test_old_ratings_replay_unchanged():  # golden value from the code before Hard existed
    assert engine.sm2([(0, 4), (DAY, 4), (4 * DAY, 4)])["interval"] == 3.0 * 2.5


def test_card_previews_order():
    p = engine.card_previews({"reviews": [[0, "good"], [DAY, "good"]]}, 4 * DAY)
    assert p["again"] == 0 and p["hard"] < p["good"] <= p["easy"]  # easy only differs from good through later ease


def test_card_previews_of_a_new_card():
    assert engine.card_previews(None, 0) == {"again": 0, "hard": 1.0, "good": 1.0, "easy": 1.0}


# ---------------------------------------------------------------- new-card cap

def many_cards(n, topic="t06"):
    cards = [{"id": f"n{i:03d}", "topic": topic, "objective": "7.4"} for i in range(n)]
    return types.SimpleNamespace(**{**vars(CONTENT), "FLASHCARDS": cards})


def test_new_cards_are_capped_and_due_reviews_come_first():
    content = many_cards(30)
    state = {"cards": {"n020": {"reviews": [[NOW - 3 * DAY, "good"]]}}}
    queue = engine.card_queue(content, state, NOW)
    assert queue["due"] == ["n020"]
    assert queue["new"] == [f"n{i:03d}" for i in range(15) if i != 20]
    assert queue["new_left"] == 15
    assert engine.due_cards(content, state, NOW) == queue["due"] + queue["new"]


def test_cards_first_reviewed_today_count_against_the_cap():
    content = many_cards(30)
    state = {"cards": {f"n{i:03d}": {"reviews": [[NOW - 60, "again"]]} for i in range(15)}}
    assert engine.new_cards_today(state, NOW) == 15
    queue = engine.card_queue(content, state, NOW)
    assert queue["new"] == [] and queue["new_left"] == 0
    # a card first reviewed yesterday does not count
    state["cards"]["n000"] = {"reviews": [[NOW - DAY, "good"], [NOW - 60, "good"]]}
    assert engine.new_cards_today(state, NOW) == 14


def test_topic_queue_shares_the_daily_new_allowance():
    content = many_cards(30)
    state = {"settings": {"new_cards_per_day": 5},
             "cards": {f"n{i:03d}": {"reviews": [[NOW - 60, "good"]]} for i in range(5)}}
    assert engine.card_queue(content, state, NOW, topic="t06")["new"] == []
    counts = engine.progress(content, state, NOW)["card_topic_counts"]
    assert counts["t06"]["new"] == 0
    state["settings"]["new_cards_per_day"] = 8
    counts = engine.progress(content, state, NOW)["card_topic_counts"]
    assert counts["t06"]["new"] == 3


def test_zero_cap_shows_only_reviews():
    content = many_cards(5)
    state = {"settings": {"new_cards_per_day": 0}, "cards": {"n001": {"reviews": [[NOW - 3 * DAY, "good"]]}}}
    assert engine.due_cards(content, state, NOW) == ["n001"]


def test_plan_cards_follow_the_queue():
    content = many_cards(40)
    state = {"settings": {"daily_minutes": 60, "new_cards_per_day": 4}}
    plan = engine.daily_plan(content, state, NOW, rng=random.Random(1))
    assert plan["cards"] == ["n000", "n001", "n002", "n003"]
    # today's plan keeps its allowance after those cards are introduced; the live queue shows what is left
    state["cards"] = {cid: {"reviews": [[NOW - 60, "good"]]} for cid in plan["cards"]}
    today = engine.todays_plan(content, state, NOW)
    assert today["cards"] == plan["cards"] and today["done"]["cards"] == plan["cards"]
    assert engine.progress(content, state, NOW)["card_queue"] == {"due": [], "new": [], "new_left": 0}
