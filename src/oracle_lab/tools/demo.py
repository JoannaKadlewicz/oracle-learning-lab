"""Write a simulated study history to a separate progress file, for screenshots and demos.

    oracle-lab demo /tmp/demo-progress.json
    STUDY_STATE_FILE=/tmp/demo-progress.json oracle-lab serve

Simulates five weeks of practice, flashcards, exercises and three mock exams, with skill that
grows over time. It never touches the database or your real progress file.
"""

import json
import random
import time
from pathlib import Path

from oracle_lab import content
from oracle_lab.study import engine
from oracle_lab.study.mocks import answer_mock, start_mock, submit_mock
from oracle_lab.study.recording import record_attempt, record_card

DAY = engine.DAY


def simulate(days=35, seed=7, now=None):
    rng = random.Random(seed)
    now = now or time.time()
    start = now - days * DAY
    state = {"attempts": {}, "cards": {}, "labs": {}, "mocks": [], "history": [],
             "settings": {"exam_date": time.strftime("%Y-%m-%d", time.localtime(now + 21 * DAY)), "daily_minutes": 45}}
    talent = {o: rng.uniform(0.25, 0.55) for o in content.OBJECTIVES}  # starting skill per objective
    questions = {q["id"]: q for q in content.QUESTIONS}

    def skill(objective, t):
        return min(0.95, talent[objective] + 0.4 * (t - start) / (days * DAY))

    def answer(q, t):
        right = rng.random() < skill(q["objective"], t)
        confidence = rng.choices(["sure", "think", "guess"], [6, 3, 1] if right else [2, 4, 4])[0]
        wrong = [i for i in range(len(q["options"])) if i not in q["answer"]]
        return (q["answer"] if right else rng.sample(wrong, min(len(q["answer"]), len(wrong)))), confidence

    mock_days = {days - 15, days - 8, days - 2}
    for d in range(days):
        if rng.random() < 0.15 and d not in mock_days:
            continue  # a day off
        t = start + d * DAY + 19 * 3600 + rng.randint(0, 3600)
        for qid in engine.pick_questions(content, state, t, rng.randint(12, 24), rng=rng):
            chosen, confidence = answer(questions[qid], t)
            record_attempt(state, {"id": qid, "chosen": chosen, "confidence": confidence}, t)
            t += rng.randint(40, 150)
        for cid in engine.due_cards(content, state, t)[:rng.randint(10, 25)]:
            card = next(c for c in content.FLASHCARDS if c["id"] == cid)
            rating = "again" if rng.random() > skill(card["objective"], t) else rng.choice(["good", "good", "easy"])
            record_card(state, {"id": cid, "rating": rating}, t)
            t += rng.randint(8, 30)
        for lab in rng.sample(content.LABS, 2):
            entry = state["labs"].setdefault(lab["id"], {"tries": 0, "passed": False})
            entry["tries"] += 1
            entry["passed"] = entry["passed"] or rng.random() < skill(lab["objective"], t)
            entry["t"] = t
            t += rng.randint(200, 600)
        if d in mock_days:
            mock = start_mock(state, {}, t)
            for qid in mock["items"]:
                chosen, confidence = answer(questions[qid], t)
                if rng.random() < 0.1:  # first instinct, then a change of mind
                    first, _ = answer(questions[qid], t)
                    answer_mock(state, {"mock_id": mock["id"], "id": qid, "chosen": first}, t)
                t += rng.randint(50, 150)
                answer_mock(state, {"mock_id": mock["id"], "id": qid, "chosen": chosen, "confidence": confidence,
                                    "time_on": {**mock["time_on"], qid: rng.randint(45, 240)}}, t)
            submit_mock(state, mock, t)
    return state



def write_demo(target: Path, real_state_file: Path) -> None:
    """Write a simulated history to `target`; refuses to overwrite the real progress file."""
    if target.resolve() == real_state_file.resolve():
        raise ValueError("Refusing to overwrite your real progress file. Choose another path.")
    target.write_text(json.dumps(simulate(), indent=1), encoding="utf-8")
