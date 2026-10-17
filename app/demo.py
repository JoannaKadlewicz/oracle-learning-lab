"""Write a simulated study history to a separate progress file, for screenshots and demos.

    .venv/bin/python app/demo.py /tmp/demo-progress.json
    STUDY_STATE_FILE=/tmp/demo-progress.json .venv/bin/python app/server.py

Simulates five weeks of practice, flashcards, exercises and three mock exams, with skill that
grows over time. It never touches the database or your real progress file.
"""

import random
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import content  # noqa: E402
import engine  # noqa: E402
import server  # noqa: E402

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
            server.record_attempt(state, {"id": qid, "chosen": chosen, "confidence": confidence}, t)
            t += rng.randint(40, 150)
        for cid in engine.due_cards(content, state, t)[:rng.randint(10, 25)]:
            card = next(c for c in content.FLASHCARDS if c["id"] == cid)
            rating = "again" if rng.random() > skill(card["objective"], t) else rng.choice(["good", "good", "easy"])
            server.record_card(state, {"id": cid, "rating": rating}, t)
            t += rng.randint(8, 30)
        for lab in rng.sample(content.LABS, 2):
            entry = state["labs"].setdefault(lab["id"], {"tries": 0, "passed": False})
            entry["tries"] += 1
            entry["passed"] = entry["passed"] or rng.random() < skill(lab["objective"], t)
            entry["t"] = t
            t += rng.randint(200, 600)
        if d in mock_days:
            mock = server.start_mock(state, {}, t)
            for qid in mock["items"]:
                chosen, confidence = answer(questions[qid], t)
                if rng.random() < 0.1:  # first instinct, then a change of mind
                    first, _ = answer(questions[qid], t)
                    server.answer_mock(state, {"mock_id": mock["id"], "id": qid, "chosen": first}, t)
                t += rng.randint(50, 150)
                server.answer_mock(state, {"mock_id": mock["id"], "id": qid, "chosen": chosen, "confidence": confidence,
                                           "time_on": {**mock["time_on"], qid: rng.randint(45, 240)}}, t)
            server.submit_mock(state, mock, t)
    return state


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    target = Path(sys.argv[1])
    if target.resolve() == server.STATE_FILE.resolve():
        sys.exit("Refusing to overwrite your real progress file. Choose another path.")
    import json
    target.write_text(json.dumps(simulate(), indent=1))
    print(f"Wrote a simulated study history to {target}")
