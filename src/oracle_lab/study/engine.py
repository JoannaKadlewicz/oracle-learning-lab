"""Learning engine: spacing, mistakes, mastery, calibration and the daily plan.

Pure functions over the saved progress (`state`) and the study content. They take `now`
(Unix seconds) so they can be tested; calendar days are local days.

State layout (progress.json in the data directory, see config.Settings):
    attempts  {question_id: [{"t", "correct", "chosen", "confidence", "mode"}, ...]}
    cards     {card_id: {"reviews": [[t, "again" | "hard" | "good" | "easy"], ...]}}
    labs      {lab_id: {"tries", "passed", "last", "t"}}
    settings  {"exam_date": "YYYY-MM-DD", "daily_minutes": 30, "new_cards_per_day": 15}
    mocks     [{"id", "started", "minutes", "topics", "items", "seen_before", "answers": {qid: {"chosen",
               "confidence", "flagged"}}, "events": [[t, qid, chosen], ...], "time_on": {qid: seconds},
               "submitted", "abandoned"}]
"""

import datetime
import itertools
import math
import random

DAY = 86400
CONFIDENCE = ("sure", "think", "guess")
CARD_RATINGS = {"again": 1, "hard": 3, "good": 4, "easy": 5}  # SM-2 quality

# Minutes per item, used to fit the daily plan into the time available.
MINUTES = {"card": 0.3, "question": 1.5, "lab": 8}
DEFAULT_DAILY_MINUTES = 30
DEFAULT_NEW_CARDS = 15  # unseen flashcards introduced per day
NEW_CARDS_RANGE = (0, 100)

HALF_LIFE_DAYS = 30  # evidence older than this counts half for mastery
PROOF_DAYS = 2  # confident correct answers on different days needed to clear a mistake


def local_day(t):
    return datetime.date.fromtimestamp(t)


def confidence_of(attempt):
    # Answers saved without a rating (exam mode, or before ratings existed) count as "think".
    return attempt.get("confidence") or "think"


def is_lucky(attempt):
    """A correct guess: right answer, but not knowledge."""
    return attempt["correct"] and confidence_of(attempt) == "guess"


def answer_quality(attempt):
    """SM-2 quality 0-5 of a quiz answer. A correct guess is a lapse, a confident miss is the worst."""
    if attempt["correct"]:
        return {"sure": 5, "think": 4, "guess": 2}[confidence_of(attempt)]
    return 0 if confidence_of(attempt) == "sure" else 1


def sm2(reviews):
    """Replay (t, quality) reviews with SM-2 and return the resulting schedule.

    Intervals are 1 day, 3 days, then the previous interval times the ease factor. Quality 3 is the
    Hard card rating: 1 day first, then max(previous * 1.2, previous + 1) days. Question schedules
    never reach that rule, because `answer_quality` yields only 5/4/2 (correct) and 0/1 (wrong).
    A quality below 3 resets the repetitions and makes the item due again right away.
    """
    reps, interval, ease, lapses = 0, 0.0, 2.5, 0
    last = due = None
    for t, quality in reviews:
        if quality >= 3:
            reps += 1
            if reps == 1:
                interval = 1.0
            elif quality == 3:  # Hard (card rating only, see above)
                interval = max(interval * 1.2, interval + 1)
            elif reps == 2:
                interval = 3.0
            else:
                interval = interval * ease
        else:
            if reps:
                lapses += 1
            reps, interval = 0, 0.0
        ease = max(1.3, ease + 0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02))
        last, due = t, t + interval * DAY
    return {"reps": reps, "interval": interval, "ease": round(ease, 2), "lapses": lapses, "last": last, "due": due}


def question_schedule(history):
    return sm2([(a["t"], answer_quality(a)) for a in history])


def card_schedule(entry):
    return sm2([(t, CARD_RATINGS[rating]) for t, rating in entry.get("reviews", [])])


def card_previews(entry, now):
    """Interval in days each rating would give the card now; "again" brings it back in this session."""
    reviews = [(t, CARD_RATINGS[rating]) for t, rating in (entry or {}).get("reviews", [])]
    previews = {"again": 0}
    for rating in ("hard", "good", "easy"):
        previews[rating] = sm2(reviews + [(now, CARD_RATINGS[rating])])["interval"]
    return previews


# --------------------------------------------------------------------------- mistakes

def open_mistakes(attempts, questions_by_id):
    """Questions whose last miss is not yet followed by confident correct answers on PROOF_DAYS days.

    A miss is a wrong answer or a correct guess. Ordered by priority: confident wrong answers
    first, then other wrong answers, then lucky guesses; most recent first within each group.
    """
    found = []
    for qid, history in attempts.items():
        if qid not in questions_by_id:
            continue
        misses = [i for i, a in enumerate(history) if not a["correct"] or is_lucky(a)]
        if not misses:
            continue
        miss = history[misses[-1]]
        proof_days = {local_day(a["t"]) for a in history[misses[-1] + 1:]
                      if a["correct"] and confidence_of(a) in ("sure", "think")}
        if len(proof_days) >= PROOF_DAYS:
            continue
        if miss["correct"]:
            reason = "guess"
        elif confidence_of(miss) == "sure":
            reason = "confident"
        else:
            reason = "wrong"
        found.append({
            "id": qid,
            "reason": reason,
            "proof": len(proof_days),
            "misses": sum(1 for a in history if not a["correct"]),
            "t": miss["t"],
        })
    priority = {"confident": 0, "wrong": 1, "guess": 2}
    return sorted(found, key=lambda m: (priority[m["reason"]], -m["t"]))


# --------------------------------------------------------------------------- mastery

def recency(t, now):
    return 0.5 ** (max(0.0, now - t) / DAY / HALF_LIFE_DAYS)


def evidence(content, state, now):
    """Collect weighted (alpha, beta) evidence per objective and per topic.

    Quiz answers: correct adds to alpha, wrong to beta, weighted by recency and confidence;
    a confident wrong answer weighs 1.5, a correct guess counts half right and half wrong.
    Labs: a pass is strong evidence (2), failed tries add to beta. Flashcards count by their
    current state: recalled at least twice in a row adds 0.5, forgotten at the last review adds
    0.5 to beta (a card you relearned no longer counts against you).
    """
    totals = {}

    def add(item, alpha, beta):
        for key in ("o:" + item["objective"], "t:" + item["topic"]):
            entry = totals.setdefault(key, [0.0, 0.0])
            entry[0] += alpha
            entry[1] += beta

    questions = {q["id"]: q for q in content.QUESTIONS}
    for qid, history in state.get("attempts", {}).items():
        q = questions.get(qid)
        if not q:
            continue
        for a in history:
            w = recency(a["t"], now)
            conf = confidence_of(a)
            if is_lucky(a):
                add(q, 0.5 * w, 0.5 * w)
            elif a["correct"]:
                add(q, {"sure": 1.0, "think": 0.8}[conf] * w, 0)
            else:
                add(q, 0, (1.5 if conf == "sure" else 1.0) * w)

    labs = {lab["id"]: lab for lab in content.LABS}
    for lab_id, result in state.get("labs", {}).items():
        lab = labs.get(lab_id)
        if not lab or not result.get("tries"):
            continue
        w = recency(result.get("t", now), now)
        failed = result["tries"] - (1 if result.get("passed") else 0)
        add(lab, 2.0 * w if result.get("passed") else 0, min(failed, 3) * 0.5 * w)

    cards = {c["id"]: c for c in content.FLASHCARDS}
    for card_id, entry in state.get("cards", {}).items():
        card = cards.get(card_id)
        if not card or not entry.get("reviews"):
            continue
        s = card_schedule(entry)
        w = recency(s["last"], now)
        forgotten = entry["reviews"][-1][1] == "again"
        add(card, 0.5 * w if s["reps"] >= 2 else 0, 0.5 * w if forgotten else 0)
    return totals


def mastery_level(alpha, beta):
    """Beta(1, 1) prior updated with the evidence: estimated accuracy and a level."""
    mean = (alpha + 1) / (alpha + beta + 2)
    amount = alpha + beta
    if amount < 2:
        level = "new"
    elif mean < 0.6:
        level = "weak"
    elif mean < 0.8:
        level = "learning"
    else:
        level = "strong"
    return {"estimate": round(mean, 3), "evidence": round(amount, 1), "level": level}


def mastery(content, state, now):
    totals = evidence(content, state, now)
    by_objective = {o: mastery_level(*totals.get("o:" + o, (0, 0))) for o in content.OBJECTIVES}
    by_topic = {t: mastery_level(*totals.get("t:" + t, (0, 0))) for t in content.TOPICS}
    return by_objective, by_topic


# --------------------------------------------------------------------------- calibration

def calibration(attempts):
    """How often answers rated sure / think / guess were correct."""
    stats = {c: {"answers": 0, "correct": 0} for c in CONFIDENCE}
    for history in attempts.values():
        for a in history:
            if a.get("confidence") in stats:
                stats[a["confidence"]]["answers"] += 1
                stats[a["confidence"]]["correct"] += int(a["correct"])
    return stats


# --------------------------------------------------------------------------- choosing questions

def interleave(items, key):
    """Reorder items so that neighbors differ in key where possible, keeping priority order otherwise."""
    rest = list(items)
    out = []
    while rest:
        prev = key(out[-1]) if out else None
        pick = next((i for i, item in enumerate(rest) if key(item) != prev), 0)
        out.append(rest.pop(pick))
    return out


def pick_questions(content, state, now, count, topics=None, rng=random):
    """Choose practice questions: open mistakes, then due reviews, then unseen questions from the
    weakest objectives, then everything else; interleaved so the same objective does not repeat."""
    attempts = state.get("attempts", {})
    pool = [q for q in content.QUESTIONS if topics is None or q["topic"] in topics]
    by_objective, _ = mastery(content, state, now)
    mistake_rank = {m["id"]: n for n, m in enumerate(open_mistakes(attempts, {q["id"]: q for q in pool}))}

    def rank(q):
        history = attempts.get(q["id"])
        if q["id"] in mistake_rank:
            return (0, mistake_rank[q["id"]])
        if history:
            due = question_schedule(history)["due"]
            if due <= now:
                return (1, due)
            return (4, due)
        m = by_objective[q["objective"]]
        return (2 if m["level"] in ("new", "weak") else 3, m["estimate"])

    shuffled = list(pool)
    rng.shuffle(shuffled)
    chosen = sorted(shuffled, key=rank)[:count]
    return [q["id"] for q in interleave(chosen, key=lambda q: q["objective"])]


def new_cards_today(state, now):
    """Cards whose first review falls on the local day of `now`: they count against the daily cap."""
    today = local_day(now)
    return sum(1 for entry in state.get("cards", {}).values()
               if entry.get("reviews") and local_day(entry["reviews"][0][0]) == today)


def card_queue(content, state, now, topic=None):
    """Flashcards to study now: `due` reviews (by due time) and `new` unseen cards (in content order).

    New cards are capped by the daily allowance, `new_cards_per_day` minus the cards already introduced
    today, so `new_left` is what remains of it. The live queue therefore shrinks as cards are introduced.
    The daily plan is built from the state at midnight, where nothing is introduced yet, so the plan holds
    the day's full allowance and keeps it while those cards are studied."""
    cap = state.get("settings", {}).get("new_cards_per_day")
    cap = DEFAULT_NEW_CARDS if cap is None else cap
    new_left = max(0, cap - new_cards_today(state, now))
    cards = state.get("cards", {})
    due, new = [], []
    for c in content.FLASHCARDS:
        if topic and c["topic"] != topic:
            continue
        if c["id"] not in cards:
            new.append(c["id"])
        elif (when := card_schedule(cards[c["id"]])["due"]) <= now:
            due.append((when, c["id"]))
    return {"due": [cid for _, cid in sorted(due)], "new": new[:new_left], "new_left": new_left}


def due_cards(content, state, now):
    queue = card_queue(content, state, now)
    return queue["due"] + queue["new"]


def due_reviews(content, state, now):
    attempts = state.get("attempts", {})
    return [q["id"] for q in content.QUESTIONS
            if attempts.get(q["id"]) and question_schedule(attempts[q["id"]])["due"] <= now]


# --------------------------------------------------------------------------- daily plan

def daily_plan(content, state, now, rng=random, sql_available=True):
    """Today's session, sized to the daily minutes: due flashcards (a quarter of the time),
    one lab from the weakest objective when there is time (none without SQL practice), and the rest as practice questions."""
    settings = state.get("settings", {})
    minutes = settings.get("daily_minutes") or DEFAULT_DAILY_MINUTES
    today = local_day(now)
    days_left = None
    if settings.get("exam_date"):
        days_left = (datetime.date.fromisoformat(settings["exam_date"]) - today).days

    queue = card_queue(content, state, now)
    card_budget = int(minutes * 0.25 / MINUTES["card"])
    cards = (queue["due"] + queue["new"])[:card_budget]

    left = minutes - len(cards) * MINUTES["card"]
    lab = None
    if left >= 20 and sql_available:
        by_objective, _ = mastery(content, state, now)
        open_labs = [lab for lab in content.LABS if not state.get("labs", {}).get(lab["id"], {}).get("passed")]
        if open_labs:
            lab = min(open_labs, key=lambda lab: (by_objective[lab["objective"]]["estimate"], lab["id"]))["id"]
            left -= MINUTES["lab"]
    questions = pick_questions(content, state, now, max(5, int(left / MINUTES["question"])), rng=rng)

    answered = len(state.get("attempts", {}))
    unseen = len(content.QUESTIONS) - answered
    exams = [m["submitted"] for m in state.get("mocks", []) if m["submitted"]]
    advice = []
    if days_left is not None and days_left > 0 and unseen:
        advice.append(f"{unseen} questions not seen yet: about {-(-unseen // days_left)} new questions a day "
                      "to see them all before the exam.")
    if days_left is not None and days_left <= 21 and (not exams or now - max(exams) > 7 * DAY):
        advice.append("Take a timed mock exam this week.")
    return {
        "minutes": minutes,
        "days_left": days_left,
        "cards": cards,
        "questions": questions,
        "lab": lab,
        "estimate": round(len(cards) * MINUTES["card"] + len(questions) * MINUTES["question"]
                          + (MINUTES["lab"] if lab else 0)),
        "advice": advice,
    }


def day_start(now):
    return datetime.datetime.combine(local_day(now), datetime.time()).timestamp()


def as_of(state, t):
    """The progress as it was at time t: answers, card reviews and exercise checks from t on left out.
    An exercise checked after t is left out entirely (its entry only keeps the last check)."""
    attempts = {qid: kept for qid, history in state.get("attempts", {}).items()
                if (kept := [a for a in history if a["t"] < t])}
    cards = {cid: {**entry, "reviews": kept} for cid, entry in state.get("cards", {}).items()
             if (kept := [r for r in entry.get("reviews", []) if r[0] < t])}
    labs = {lid: entry for lid, entry in state.get("labs", {}).items() if entry.get("t", 0) < t}
    return {**state, "attempts": attempts, "cards": cards, "labs": labs}


def todays_plan(content, state, now, sql_available=True):
    """The daily plan as set at the start of the day, with what is done since.

    The plan is built from the progress at midnight, so finishing an item ticks it off instead of
    replacing it with the next one. Everything due by the end of the day is part of it."""
    start = day_start(now)
    end = day_start(start + 1.5 * DAY)
    plan = daily_plan(content, as_of(state, start), end - 1, rng=random.Random(local_day(now).toordinal()),
                      sql_available=sql_available)
    attempts, cards, labs = state.get("attempts", {}), state.get("cards", {}), state.get("labs", {})
    questions = [qid for qid in plan["questions"] if any(a["t"] >= start for a in attempts.get(qid, []))]
    reviewed = [cid for cid in plan["cards"] if any(r[0] >= start for r in cards.get(cid, {}).get("reviews", []))]
    lab = labs.get(plan["lab"], {})
    lab_done = bool(lab.get("passed") and lab.get("t", 0) >= start)
    plan["done"] = {"questions": questions, "cards": reviewed, "lab": lab_done}
    plan["complete"] = (len(questions) == len(plan["questions"]) and len(reviewed) == len(plan["cards"])
                        and (lab_done or not plan["lab"]))
    return plan


# --------------------------------------------------------------------------- mock exams

MOCK_GRACE = 60  # seconds after the deadline in which answers and the submit are still accepted


def previously_seen(state):
    """Questions answered in any mode, or shown in an earlier mock."""
    seen = set(state.get("attempts", {}))
    for mock in state.get("mocks", []):
        seen.update(mock["items"])
    return seen


def build_mock(content, state, now, count, minutes, topics=None, rng=random):
    """A new mock: one question per objective first (Oracle publishes no section weights, so every
    objective is covered), the rest from the freshest remaining questions. Fresh means never answered
    and never shown in a mock; then answered in practice only; then shown in the oldest mock."""
    pool = [q for q in content.QUESTIONS if topics is None or q["topic"] in topics]
    count = min(count, len(pool))
    attempts = state.get("attempts", {})
    last_mock = {}
    for mock in state.get("mocks", []):
        for qid in mock["items"]:
            last_mock[qid] = max(last_mock.get(qid, 0), mock["started"])

    def staleness(q):
        if q["id"] in last_mock:
            return (2, last_mock[q["id"]])
        if q["id"] in attempts:
            return (1, len(attempts[q["id"]]))
        return (0, 0)

    shuffled = list(pool)
    rng.shuffle(shuffled)
    shuffled.sort(key=staleness)
    chosen, covered = [], set()
    for q in shuffled:  # freshest question of each objective, objectives in random order
        if len(chosen) < count and q["objective"] not in covered:
            chosen.append(q)
            covered.add(q["objective"])
    rest = [q for q in shuffled if q not in chosen]
    chosen += rest[:count - len(chosen)]
    rng.shuffle(chosen)
    seen = previously_seen(state)
    return {
        "id": f"m{int(now * 1000)}",
        "started": now,
        "minutes": minutes,
        "topics": topics,
        "items": [q["id"] for q in chosen],
        "seen_before": [q["id"] for q in chosen if q["id"] in seen],
        "answers": {},
        "events": [],
        "time_on": {},
        "submitted": None,
        "abandoned": None,
    }


def mock_deadline(mock):
    return mock["started"] + mock["minutes"] * 60


def is_full_mock(content, mock):
    return not mock.get("topics") and len(mock["items"]) == content.EXAM["questions"]


def active_mock(state, now):
    for mock in state.get("mocks", []):
        if not mock["submitted"] and not mock["abandoned"] and now <= mock_deadline(mock) + MOCK_GRACE:
            return mock
    return None


def mock_report(content, mock):
    """Score and analytics of a submitted mock."""
    questions = {q["id"]: q for q in content.QUESTIONS}
    items = [qid for qid in mock["items"] if qid in questions]

    def correct(qid, chosen):
        return sorted(chosen) == sorted(questions[qid]["answer"])

    final = {qid: mock["answers"].get(qid, {}).get("chosen", []) for qid in items}
    right = {qid for qid in items if correct(qid, final[qid])}

    def tally(ids):
        ids = list(ids)
        return [sum(1 for qid in ids if qid in right), len(ids)]

    seen = set(mock["seen_before"])
    by_section = {}
    for qid in items:
        by_section.setdefault(questions[qid]["objective"].split(".")[0], []).append(qid)

    first = {}
    for _, qid, chosen in mock["events"]:
        if chosen and qid not in first:
            first[qid] = chosen
    changes = {"right_to_wrong": [], "wrong_to_right": [], "wrong_to_wrong": []}
    for qid, chosen in first.items():
        if qid in final and sorted(chosen) != sorted(final[qid]):
            was, now_ok = correct(qid, chosen), correct(qid, final[qid])
            key = "right_to_wrong" if was else "wrong_to_right" if now_ok else "wrong_to_wrong"
            changes[key].append(qid)

    time_on = mock.get("time_on", {})
    pace = mock["minutes"] * 60 / max(len(items), 1)
    end = mock["submitted"] or mock_deadline(mock)
    pct = round(100 * len(right) / len(items)) if items else 0
    return {
        "id": mock["id"],
        "started": mock["started"],
        "submitted": mock["submitted"],
        "full": is_full_mock(content, mock),
        "score": tally(items),
        "pct": pct,
        "passed": pct >= content.EXAM["passing_pct"],
        "fresh": tally(qid for qid in items if qid not in seen),
        "by_section": {sec: tally(ids) for sec, ids in sorted(by_section.items(), key=lambda kv: int(kv[0]))},
        "single": tally(qid for qid in items if len(questions[qid]["answer"]) == 1),
        "multi": tally(qid for qid in items if len(questions[qid]["answer"]) > 1),
        "unanswered": [qid for qid in items if not final[qid]],
        "flagged": [qid for qid in items if mock["answers"].get(qid, {}).get("flagged")],
        "changes": changes,
        "confidence": {c: tally(qid for qid in items if mock["answers"].get(qid, {}).get("confidence") == c)
                       for c in CONFIDENCE},
        "minutes": mock["minutes"],
        "minutes_used": round((min(end, mock_deadline(mock)) - mock["started"]) / 60, 1),
        "pace_seconds": round(pace),
        "slowest": sorted((qid for qid in items if time_on.get(qid)), key=lambda qid: -time_on[qid])[:5],
        "time_on": {qid: round(time_on[qid]) for qid in items if time_on.get(qid)},
        "right": sorted(right),
    }


# --------------------------------------------------------------------------- readiness

READINESS_MIN_EVIDENCE = 15
PRACTICE_FIRST_WEIGHT = 0.6  # a first answer in untimed practice is weaker evidence than one in a mock


def beta_binomial_pmf(n, a, b):
    def log_beta(x, y):
        return math.lgamma(x) + math.lgamma(y) - math.lgamma(x + y)
    return [math.exp(math.lgamma(n + 1) - math.lgamma(k + 1) - math.lgamma(n - k + 1)
                     + log_beta(k + a, n - k + b) - log_beta(a, b)) for k in range(n + 1)]


def readiness(content, state, now):
    """Chance of passing, from the first answer you ever gave to each question.

    Repeated answers are left out, so practising the same questions cannot inflate the estimate.
    First answers in mocks count fully, first answers in practice count 0.6, and both fade with a
    30-day half-life. The accuracy estimate (Beta posterior) is turned into a score distribution
    for a full exam (beta-binomial): the pass probability and the 10th to 90th percentile range.
    """
    questions = {q["id"] for q in content.QUESTIONS}
    alpha = beta = 0.0
    for qid, history in state.get("attempts", {}).items():
        if qid not in questions or not history:
            continue
        first = history[0]
        w = recency(first["t"], now) * (1.0 if first.get("mode") == "exam" else PRACTICE_FIRST_WEIGHT)
        if first["correct"]:
            alpha += w
        else:
            beta += w
    evidence_amount = alpha + beta
    by_objective, _ = mastery(content, state, now)
    gaps = {
        "untested": sorted(o for o, m in by_objective.items() if m["level"] == "new"),
        "weak": sorted(o for o, m in by_objective.items() if m["level"] == "weak"),
    }
    if evidence_amount < READINESS_MIN_EVIDENCE:
        return {"status": "insufficient", "evidence": round(evidence_amount, 1),
                "needed": READINESS_MIN_EVIDENCE, **gaps}

    n = content.EXAM["questions"]
    need = math.ceil(n * content.EXAM["passing_pct"] / 100)
    pmf = beta_binomial_pmf(n, alpha + 1, beta + 1)

    def quantile(q):
        total = 0.0
        for k, p in enumerate(pmf):
            total += p
            if total >= q:
                return k
        return n

    return {
        "status": "ok",
        "pass_probability": round(sum(pmf[need:]), 2),
        "expected_pct": round(100 * (alpha + 1) / (alpha + beta + 2)),
        "low_pct": round(100 * quantile(0.1) / n),
        "high_pct": round(100 * quantile(0.9) / n),
        "evidence": round(evidence_amount, 1),
        "passing_pct": content.EXAM["passing_pct"],
        **gaps,
    }


# --------------------------------------------------------------------------- activity, badges, definition of done

ACTIVITY_DAYS = 84  # twelve weeks in the activity calendar
SESSION_GAP = 15 * 60  # a pause longer than this starts a new study session
STEP_CAP = 5 * 60  # time counted between two actions is capped, so a coffee break does not count


def activity_times(state):
    times = [a["t"] for h in state.get("attempts", {}).values() for a in h]
    times += [t for entry in state.get("cards", {}).values() for t, _ in entry.get("reviews", [])]
    times += [lab["t"] for lab in state.get("labs", {}).values() if lab.get("t")]
    times += [h["t"] for h in state.get("history", [])]
    for mock in state.get("mocks", []):
        times += [e[0] for e in mock.get("events", [])]
    return sorted(times)


def activity(state, now):
    """Study days, the current streak, and an estimate of hours studied from the time between actions."""
    times = activity_times(state)
    per_day = {}
    for t in times:
        day = local_day(t)
        per_day[day] = per_day.get(day, 0) + 1
    today = local_day(now)
    streak, day = 0, today if today in per_day else today - datetime.timedelta(days=1)
    while day in per_day:
        streak += 1
        day -= datetime.timedelta(days=1)
    seconds = 0.0
    for prev, cur in itertools.pairwise(times):
        gap = cur - prev
        if gap <= SESSION_GAP:
            seconds += min(gap, STEP_CAP)
    seconds += 60 * sum(1 for prev, cur in zip([None] + times, times, strict=False) if prev is None or cur - prev > SESSION_GAP)
    first = today - datetime.timedelta(days=ACTIVITY_DAYS - 1)
    return {
        "days": [{"date": (first + datetime.timedelta(days=i)).isoformat(),
                  "actions": per_day.get(first + datetime.timedelta(days=i), 0)} for i in range(ACTIVITY_DAYS)],
        "streak": streak,
        "active_days": len(per_day),
        "hours": round(seconds / 3600, 1),
    }


def best_clean_run(attempts):
    """Longest run of correct, non-guessed answers (in time order) and the days it spans."""
    answers = sorted((a for h in attempts.values() for a in h), key=lambda a: a["t"])
    best, run, days, best_days = 0, 0, set(), 0
    for a in answers:
        if a["correct"] and not is_lucky(a):
            run += 1
            days.add(local_day(a["t"]))
            if (run, len(days)) > (best, best_days):
                best, best_days = run, len(days)
        else:
            run, days = 0, set()
    return best, best_days


def fresh_mock_passes(content, state, threshold=80, min_fresh=50, gap_days=3):
    """Full mocks scoring at least `threshold`% on questions new to you, at least `gap_days` apart."""
    good = []
    for mock in state.get("mocks", []):
        if not mock.get("submitted") or not is_full_mock(content, mock):
            continue
        right, fresh = mock_report(content, mock)["fresh"]
        passed = fresh >= min_fresh and 100 * right >= threshold * fresh
        if passed and (not good or mock["submitted"] - good[-1] >= gap_days * DAY):
            good.append(mock["submitted"])
    return len(good)


def badges(content, state, now, by_objective):
    attempts = state.get("attempts", {})
    labs = state.get("labs", {})
    questions = {q["id"]: q for q in content.QUESTIONS}

    def labs_of(kind):
        return [lab for lab in content.LABS if lab.get("kind", "query") == kind]

    run, run_days = best_clean_run(attempts)
    dml = labs_of("dml")
    ddl = labs_of("ddl")
    cal = calibration(attempts)["sure"]
    covered = {questions[qid]["objective"] for qid, h in attempts.items() if qid in questions and any(a["correct"] for a in h)}
    open_ids = {m["id"] for m in open_mistakes(attempts, questions)}
    fixed = sum(1 for qid, h in attempts.items() if qid in questions and qid not in open_ids
                and any(not a["correct"] and confidence_of(a) == "sure" for a in h))
    long_cards = sum(1 for entry in state.get("cards", {}).values() if card_schedule(entry)["interval"] >= 21)
    strong = sum(1 for m in by_objective.values() if m["level"] == "strong")
    sure_ok = cal["answers"] >= 50 and cal["correct"] >= 0.9 * cal["answers"]

    def badge(key, title, description, current, target, earned=None):
        earned = current >= target if earned is None else earned
        return {"id": key, "title": title, "description": description,
                "progress": [min(current, target), target], "earned": earned}

    return [
        badge("clean-run", "Clean run", "25 correct answers in a row, none of them guessed, spread over at least 3 days.",
              run, 25, run >= 25 and run_days >= 3),
        badge("coverage", "Full coverage", "At least one correct answer for every official objective.",
              len(covered), len(content.OBJECTIVES)),
        badge("all-green", "All green", "Every official objective at the Strong mastery level.", strong, len(content.OBJECTIVES)),
        badge("calibrated", "Calibrated", "At least 50 answers rated Sure, and 90% or more of them correct.",
              cal["answers"], 50, sure_ok),
        badge("misconceptions", "Misconceptions fixed",
              "10 questions you once got wrong while sure, now proven on two days.", fixed, 10),
        badge("dml-first-try", "DML first try", "Every DML exercise passed on the first check.",
              sum(1 for lab in dml if labs.get(lab["id"], {}).get("passed") and labs[lab["id"]]["tries"] == 1),
              len(dml)),
        badge("ddl-own-work", "Schema builder", "Every DDL exercise passed without opening the solution.",
              sum(1 for lab in ddl if labs.get(lab["id"], {}).get("passed") and not labs[lab["id"]].get("solution_seen")),
              len(ddl)),
        badge("lab-master", "Lab master", "Every exercise passed.",
              sum(1 for lab in content.LABS if labs.get(lab["id"], {}).get("passed")), len(content.LABS)),
        badge("long-memory", "Long memory", "100 flashcards with an interval of three weeks or more.", long_cards, 100),
        badge("fresh-mocks", "Exam ready", "3 full mocks at 80% or more on questions new to you, at least 3 days apart.",
              fresh_mock_passes(content, state), 3),
    ]


def ready_to_book(content, state, by_objective):
    """The definition of done from plan.md, as a checklist."""
    attempts = state.get("attempts", {})
    labs = state.get("labs", {})
    cal = calibration(attempts)["sure"]
    strong = sum(1 for m in by_objective.values() if m["level"] == "strong")
    mocks = fresh_mock_passes(content, state)
    passed = sum(1 for lab in content.LABS if labs.get(lab["id"], {}).get("passed"))
    own = sum(1 for lab in content.LABS if lab.get("kind", "query") != "query"
              and labs.get(lab["id"], {}).get("passed") and not labs[lab["id"]].get("solution_seen"))
    state_labs = sum(1 for lab in content.LABS if lab.get("kind", "query") != "query")
    sure_pct = round(100 * cal["correct"] / cal["answers"]) if cal["answers"] else None
    items = [
        {"label": "Every official objective is Strong", "detail": f"{strong} of {len(by_objective)}",
         "done": strong == len(by_objective)},
        {"label": "3 full mocks at 80%+ on new questions, 3+ days apart", "detail": f"{mocks} of 3", "done": mocks >= 3},
        {"label": "Right at least 90% of the time when Sure (30+ answers)",
         "detail": f"{sure_pct}% of {cal['answers']}" if sure_pct is not None else "no answers rated Sure yet",
         "done": cal["answers"] >= 30 and sure_pct >= 90},
        {"label": "Every exercise passed; DML and DDL ones without the solution",
         "detail": f"{passed} of {len(content.LABS)} passed, {own} of {state_labs} DML/DDL on your own",
         "done": passed == len(content.LABS) and own == state_labs},
    ]
    return {"items": items, "done": all(i["done"] for i in items)}


# --------------------------------------------------------------------------- summary for the front end

def progress(content, state, now, sql_available=True):
    by_objective, by_topic = mastery(content, state, now)
    questions = {q["id"]: q for q in content.QUESTIONS}
    cards = {cid: card_schedule(entry) for cid, entry in state.get("cards", {}).items()}
    return {
        "objectives": by_objective,
        "topics": by_topic,
        "mistakes": open_mistakes(state.get("attempts", {}), questions),
        "due_cards": due_cards(content, state, now),
        "card_queue": card_queue(content, state, now),
        "card_topic_counts": {t: {k: len(v) for k, v in card_queue(content, state, now, topic=t).items() if k != "new_left"}
                              for t in {c["topic"] for c in content.FLASHCARDS}},
        "due_reviews": len(due_reviews(content, state, now)),
        "cards": {cid: {"interval": round(s["interval"], 1), "due": s["due"], "reps": s["reps"]} for cid, s in cards.items()},
        "calibration": calibration(state.get("attempts", {})),
        "plan": todays_plan(content, state, now, sql_available),
        "settings": state.get("settings", {}),
        "proof_days": PROOF_DAYS,
        "readiness": readiness(content, state, now),
        "mocks": [mock_report(content, m) for m in state.get("mocks", []) if m["submitted"]],
        "active_mock": active_mock_summary(state, now),
        "activity": activity(state, now),
        "badges": badges(content, state, now, by_objective),
        "ready": ready_to_book(content, state, by_objective),
    }


def active_mock_summary(state, now):
    mock = active_mock(state, now)
    if not mock:
        return None
    return {"id": mock["id"], "deadline": mock_deadline(mock), "count": len(mock["items"]),
            "answered": sum(1 for a in mock["answers"].values() if a.get("chosen"))}
