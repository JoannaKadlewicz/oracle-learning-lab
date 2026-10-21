# Core Study Loop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the core study loop (practice questions, flashcards, mock exams, the Today session) behave like a real exam-prep tool:

- choose-N enforced;
- flashcards that don't give the answer away, with four ratings and honest due counts;
- sessions and mocks that survive a reload;
- in-session second tries;
- a one-flow Today;
- SQL features hidden when SQL is unavailable.

**Architecture:**
- **Server side (Python, testable):**
  - a new "hard" rating and interval previews in `study/engine.py`;
  - a due/new card queue with a per-user daily cap;
  - a mock `position`;
  - one `sql_available` flag in the progress payload.
- **Everything else** is in the vanilla-JS SPA views (`quiz.js`, `cards.js`, `home.js`, `exercises.js`, `lab.js`, `settings.js`, `shell.js`, `router.js`), verified in a real browser.

**Tech Stack:** Python 3.12 stdlib, python-oracledb, vanilla-JS ES modules, pytest, Playwright (browser checks only).

**Spec:** `docs/superpowers/specs/2026-10-21-core-study-loop-design.md`. Goal numbers (G1…G12) and "settled" numbers (S1…S8) refer to it.

## Global Constraints

- No new runtime dependencies. The CSP forbids inline handlers and inline scripts.
- Every server or user value goes into the DOM through `esc()` or `textContent`. Every POST goes through `api()`, which adds the CSRF header.
- Browser storage goes only through `js/core/store.js` (`store(key, value)`, per-user namespace). Practice session key: `practice-session`.
- **Card ratings:**
  - Stored strings: `again`, `hard`, `good`, `easy`.
  - SM-2 qualities: 1, 3, 4, 5.
  - Hard interval: the first review gives 1 day; after that `max(prev * 1.2, prev + 1)` days.
  - Hard ease: `max(1.3, ease - 0.14)`. This is the existing SM-2 ease formula for quality 3; keep the formula as is.
- **New-card cap:**
  - Setting `new_cards_per_day`, default 15, range 0–100.
  - Global per user.
  - "Introduced today" means the first review falls on `local_day(now)`.
- **Second tries:**
  - Reinserted 5 positions later, or at the end if fewer remain.
  - At most once per question per session.
  - Practice only, never in mocks.
- **Practice session snapshot:** discarded after 24 h.
- **Mock position:**
  - 0-based and validated.
  - Navigation saves are debounced to at most 1 per 2 s.
  - Resume order: stored position, else the first unanswered question, else the review screen.
- **Exact copy:**
  - `"1 of 2 selected"`: the pattern is `"{n} of {N} selected"`.
  - `"Try it in SQL after you answer"`
  - `"What the sample shows:"`
  - `"Again in this session"`
  - `"Second try"`
  - `"Right this time. It stays in your mistakes until you get it right on another day."`
  - `"Leave the exam? The timer keeps running."`
  - `"SQL practice isn't enabled on this server yet."`
  - `"SQL practice unavailable"`
  - `"Your progress is saved to your account."`
  - `"Lesson notes for every topic, and your saved SQL notes."`
  - `"The app could not load. Reload, or try again in a minute."`
  - `"The 1Z0-171 SQL features need Oracle 23ai, which this server does not provide."`
  - `"Continue: {N} flashcards"`
  - `"Continue: today's exercise"`
- **Backward compatibility:**
  - Old reviews (again/good/easy) replay exactly as before.
  - A mock without `position` opens at the first unanswered question.
  - The progress payload keeps `due_cards` for one release (it equals due + allowed new).
- Commands, run from the repo root:
  - tests: `.venv/bin/python -m pytest -q`
  - lint: `.venv/bin/python -m ruff check src tests`
- Commits end with the line `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- **Browser checks:** use Playwright at `/tmp/claude-1000/-home-phubertstasiuk-PycharmProjects-oracle-learning-lab/4a5750f6-08dd-4084-b286-06e0edb91613/scratchpad/pwlib`.
  - Run with `PYTHONPATH=<that>` and `executable_path="/usr/bin/google-chrome"`.
  - Start an app on port 8082 with a temporary `STUDY_DATA_DIR`, `STUDY_DSN=localhost:1525/ORAPDB1` and `STUDY_PASSWORD_FILE=secrets/study_db_password`. The first registered user is admin and gets SQL.
  - Stop it by port: `ss -ltnp`, then kill the pid. Never use `pkill -f`.
  - Do not touch :8080 or :8071.

## Review Focus

1. **A reload between "Check" and the confidence press** (practice). Expect: the session resumes on that question, still unchecked, with the ticks kept. The browser test lives in Task 6.
2. **A choose-N question with N ticked, then one unticked, in a mock.** Expect: the navigator shows "incomplete", and the partial answer is saved and graded wrong at submit. Tests: Task 7 browser check, plus Task 4 server test `test_partial_answer_is_saved_and_graded_wrong`.
3. **The new-card cap reached mid-deck.** The learner studies 15 new cards, then opens a topic deck. Expect: the topic deck offers only due reviews with "0 new left today". Server test `test_topic_queue_shares_the_daily_new_allowance` in Task 2.
4. **The exam timer runs out while the learner is on the leave-confirm dialog.** Expect: the dialog closes and the mock is submitted and shown as normal. Browser check in Task 7.
5. **A card with no `try_sql`, or with only a comment.** Expect: no "What the sample shows" block, and the collapsed panel says the existing "No sample" text after the flip. Browser check in Task 8.

---

### Task 1: Hard rating and interval previews (engine + API)

**Files:**
- Modify: `src/oracle_lab/study/engine.py` (`CARD_RATINGS`, `sm2`), `src/oracle_lab/study/recording.py` (`record_card` accepts `hard`), `src/oracle_lab/services/study.py`, `src/oracle_lab/web/controllers/study.py`
- Test: `tests/test_engine.py`, `tests/test_recording.py`, `tests/test_web.py` (or the existing study endpoint test file)

**Interfaces (Produces):**
- `CARD_RATINGS = {"again": 1, "hard": 3, "good": 4, "easy": 5}`.
- `sm2(reviews)`: quality 3 now uses the Hard interval rule, with the ease formula unchanged. Question schedules are unaffected because `answer_quality` never yields 3; check this, and add a comment.
- `card_previews(entry: dict | None, now: float) -> dict`: returns `{"again": 0, "hard": d1, "good": d2, "easy": d3}`, where each value is the interval in days (float) of the schedule after appending `(now, quality)`.
- `StudyService.card_previews(card_id) -> dict` raises `NotFoundError` for unknown ids.
- `GET /api/card/preview?id=<card id>` → that dict (private route; add it to `tests/test_isolation.py` PRIVATE).

- [ ] **Step 1: Write the failing tests**
```python
def test_hard_grows_slower_than_good():
    first = engine.sm2([(0, 3)]); assert first["interval"] == 1.0
    s = engine.sm2([(0, 4), (DAY, 4), (4 * DAY, 3)])          # prev 3 d, hard
    assert s["interval"] == max(3.0 * 1.2, 3.0 + 1) and s["reps"] == 3
def test_old_ratings_replay_unchanged():                       # golden values from today's code
    assert engine.sm2([(0, 4), (DAY, 4), (4 * DAY, 4)])["interval"] == 3.0 * 2.5
def test_card_previews_order():
    p = engine.card_previews({"reviews": [[0, "good"], [DAY, "good"]]}, 4 * DAY)
    assert p["again"] == 0 and p["hard"] < p["good"] < p["easy"]
def test_record_card_accepts_hard(): ...
def test_card_preview_endpoint(serve): ...                     # signed in → 200 dict; unknown id → 404
```
- [ ] **Step 2: Run them.** Expected: FAIL.
- [ ] **Step 3: Implement.** The Hard rule goes inside `sm2` in the `quality >= 3` branch, `quality == 3 and reps > 1` case. Keep `card_schedule` unchanged. Mastery's `forgotten` check stays `== "again"`.
- [ ] **Step 4: Run.** `pytest -q tests/test_engine.py tests/test_recording.py` and the web test. Expected: PASS. Then run the full suite.
- [ ] **Step 5: Commit** `feat(cards): hard rating and interval previews`

---

### Task 2: One due model with a daily new-card cap

**Files:**
- Modify: `src/oracle_lab/study/engine.py` (`due_cards`, `daily_plan`, `progress`), `src/oracle_lab/study/recording.py` (`record_settings`: `new_cards_per_day`)
- Test: `tests/test_engine.py`, `tests/test_recording.py`

**Interfaces (Produces):**
- `DEFAULT_NEW_CARDS = 15`; `NEW_CARDS_RANGE = (0, 100)`.
- `new_cards_today(state, now) -> int`: the number of cards whose first review is on `local_day(now)`.
- `card_queue(content, state, now, topic: str | None = None) -> dict` returns `{"due": [ids], "new": [ids], "new_left": int}`:
  - `due`: reviewed cards with `due <= now`, ordered by due time.
  - `new`: unseen cards in content order (filtered by topic when given), capped at `new_left = max(0, cap - new_cards_today)`.
- `due_cards(content, state, now)` returns `queue["due"] + queue["new"]`, so existing callers keep working.
- `daily_plan`'s card slice is `due` then `new`, cut to the card budget, as today.
- `progress()` adds `"card_queue": {"due": [...], "new": [...], "new_left": n}` and `"card_topic_counts": {topic: {"due": n, "new": m}}`. The per-topic new counts never exceed `new_left`.
- `record_settings` validates `new_cards_per_day` as an int in range; otherwise ValueError.

- [ ] **Step 1: Write the failing tests**
```python
def test_new_cards_are_capped_and_due_reviews_come_first(): ...
def test_cards_first_reviewed_today_count_against_the_cap(): ...   # 15 first reviews today → new == []
def test_topic_queue_shares_the_daily_new_allowance(): ...         # cap 5, 5 introduced → topic new == []
def test_setting_range(): ...                                       # -1 and 101 raise, 0 allowed (only reviews)
def test_plan_cards_follow_the_queue(): ...
```
- [ ] **Step 2: Run.** Expected: FAIL.
- [ ] **Step 3: Implement.** Use one helper so the plan, the progress payload and the topic counts all share the queue.
- [ ] **Step 4: Run** the engine tests and the full suite. Expected: PASS.
- [ ] **Step 5: Commit** `feat(cards): due reviews and capped new cards as one model`

---

### Task 3: `sql_available` in the payload and the plan

**Files:**
- Modify: `src/oracle_lab/services/context.py` (or wherever `UserContext` is built), `src/oracle_lab/services/study.py`, `src/oracle_lab/study/engine.py` (`daily_plan`/`todays_plan`/`progress` gain `sql_available: bool = True`), `src/oracle_lab/bootstrap.py`
- Test: `tests/test_engine.py`, `tests/test_isolation.py` or `tests/test_web.py`

**Interfaces (Produces):**
- `UserContext.sql_available: bool`, computed once as `bool(settings.practice) or principal.role == "admin"`. The builder places this in the contexts factory.
- `engine.daily_plan(..., sql_available=True)`: when False, `lab` is None and its minutes go to questions.
- The `/api/progress` payload gains top-level `"sql_available": bool`.

- [ ] **Step 1: Write the failing tests**
  - `test_plan_without_sql_has_no_exercise`: in the engine.
  - `test_progress_reports_sql_available_for_learners_and_admins`: over HTTP. With no practice targets, an admin gets True and a learner gets False.
- [ ] **Step 2: Run.** Expected: FAIL. **Step 3: Implement.** **Step 4: Run.** Expected: PASS.
- [ ] **Step 5: Commit** `feat: plan and payload know whether SQL practice is available`

---

### Task 4: Mock position

**Files:**
- Modify: `src/oracle_lab/study/mocks.py` (`answer_mock`), `src/oracle_lab/study/engine.py` (`active_mock_summary`), `src/oracle_lab/services/mock_exams.py` (if `get` shapes the mock)
- Test: `tests/test_mocks.py`

**Interfaces (Produces):**
- `answer_mock(state, data, now)` accepts an optional `"position"`: an int with 0 ≤ p < len(items), otherwise ValueError. It is stored as `mock["position"]` and works with or without `id`, as the `time_on`-only path does today.
- `active_mock_summary` and `GET /api/mock` include `"position"`, or None when absent.

- [ ] **Step 1: Write the failing tests**
  - `test_position_is_stored_and_validated`
  - `test_position_without_answer`
  - `test_old_mock_without_position_reports_none`
  - `test_partial_answer_is_saved_and_graded_wrong`: one option of a choose-2 is saved, and it scores wrong at submit.
- [ ] **Step 2–4:** Run (FAIL), implement, run (PASS), then the full suite.
- [ ] **Step 5: Commit** `feat(mock): remember the question the learner was on`

---

### Task 5: Answering questions — choose-N, keys, Enter, verdict text (`quiz.js`)

**Files:**
- Modify: `src/oracle_lab/resources/static/js/views/quiz.js`, `css/quiz.css`

**Interfaces (Produces):**
- `requiredCount(q) -> number`: `q.answer.length`.
- `isComplete(q, chosen)`: `chosen.length === requiredCount(q)`.
- **Practice:**
  - Check and the S/T/G buttons are disabled until `isComplete`.
  - A tick beyond N is refused, with a brief `.pulse` on the counter.
  - The counter `"{n} of {N} selected"` shows only for N > 1, with `aria-live="polite"`.
- **Keys:**
  - A–H toggle options, and so do 1–8 as before.
  - S/T/G are active only when complete. While incomplete, S and G are letters, so options G and H stay reachable by letter.
  - Enter while complete and with no confidence checks as `"think"`.
- **Verdict:** the joined letters read `"D, E and F"`.
- **Toasts:** the confidence toast is dismissed on check (use the toast helper's id or clear function; add one to `ui/feedback.js` if missing).

- [ ] **Step 1:** Implement.
- [ ] **Step 2: Browser check.** Practice with a choose-2 question:
  - one tick: Check disabled and counter "1 of 2 selected";
  - a third tick: refused;
  - press `D`: letter selection works;
  - Enter with no confidence: checks as Think, and no lingering toast;
  - the verdict uses commas.

  Add a screenshot at 1366 and 420.
- [ ] **Step 3:** Run `pytest -q`, which should be unchanged.
- [ ] **Step 4: Commit** `feat(quiz): choose-N like the real exam, letter keys, Enter checks`

---

### Task 6: Practice session resume and second tries (`quiz.js`, `home.js`)

**Files:**
- Modify: `js/views/quiz.js`, `js/views/home.js`

**Interfaces (Produces):**
- **Snapshot:** `saveSession()` / `loadSession()` / `clearSession()` use `store("practice-session", {v: 1, saved, fromToday, items, order, idx, answers, checked, confidence, retried, seconds})`. `seconds` holds the second-try entries.
  - Saved after every tick, check and navigation.
  - Cleared on finish or quit.
  - Ignored when more than 24 h old.
- `render()` on `/quiz`: no in-memory quiz plus a valid snapshot means resume. Mocks take precedence (Task 7).
- **Second tries:** after a practice check that is wrong, or a correct "guess":
  - if the question is not yet in `retried`, insert a copy marked `second: true` at `idx + 5` (or the end);
  - reshuffle its option order;
  - the header shows `"Second try"`;
  - its verdict, when correct and the question is still an open mistake, adds the exact copy line from the constraints;
  - the counter shows "x of N" over the original items only.
- **Results:** first answers only for the score, and a separate list "Second tries: n right of m".
- **Today:** when a snapshot exists, show a `"Resume practice (k of N)"` entry above the session card.

- [ ] **Step 1:** Implement.
- [ ] **Step 2: Browser check.**
  - Answer 3 questions, deliberately missing one. Reload mid-question (Review Focus 1), and the session resumes with ticks kept.
  - The missed one reappears 5 later, with "Second try" and reshuffled options.
  - Quitting removes the snapshot.
  - Today shows "Resume practice" while one exists.
  - Check at 1366 and 420.
- [ ] **Step 3: Commit** `feat(quiz): practice survives a reload; missed questions come back`

---

### Task 7: Mock resume, full-screen exam bar, leave guard, navigator states

**Files:**
- Modify: `js/views/quiz.js`, `js/core/router.js` (a guard hook), `js/shell.js` / `index.html` / `css/shell.css` (an exam-mode body class), `css/quiz.css`

**Interfaces (Produces):**
- `router.setLeaveGuard(fn | null)`: before an in-app route change, `await fn()` must return true to proceed.
- **Exam mode:**
  - `document.body.classList.toggle("exam-mode", bool)` hides the rail and topbar through CSS.
  - The exam bar shows exam code, timer, "Question x of N", Flag, Review, Leave, Submit.
  - "Leave" uses `confirmDialog` with `"Leave the exam? The timer keeps running."` and then goes to Today. The mock keeps running.
- **Unload guard:** a `beforeunload` handler is active only while a mock is open and unsubmitted.
- **Position saves:** debounced position saves via the existing answer endpoint, with `{mock_id, position}`.
- **Resume:** opening `/quiz` (or "Resume your mock exam" on Today) while `P.active_mock` exists resumes at `position`, otherwise the first unanswered question, otherwise the review screen.
- **Navigator:**
  - ✓ glyph for complete answers;
  - "◐" for incomplete answers (some ticks but fewer than N), with `aria-label` "incomplete";
  - ⚑ for flagged.
- **Review screen and submit confirmation:** count unanswered and incomplete questions separately.
- **Timer expiry:** closes any open dialog, then submits as today (Review Focus 4).

- [ ] **Step 1:** Implement.
- [ ] **Step 2: Browser check.**
  - Start a mock and answer 4, one of them a choose-2 with 1 tick, so it shows ◐ in the navigator.
  - Reload: it resumes at the question that was showing.
  - Leave → confirm → Today. "Resume" returns to the same question.
  - Clicking a sidebar link is impossible, because the rail is hidden.
  - Trying `history.back()` triggers the guard.
  - Timer-expiry check: start a mock with `minutes` lowered through the API, or fake the clock with Playwright's `page.clock`.
  - Check at 1366, 1920, 420, plus dark mode.
- [ ] **Step 3: Commit** `feat(mock): full-screen exam, resume where you were, leave guard`

---

### Task 8: Flashcards — Try-it after the flip, back side, four ratings, due/new counts, setting

**Files:**
- Modify: `js/views/cards.js`, `css/cards.css`, `js/views/settings.js`, `js/core/state.js` (`dueCards` reads `P.card_queue`)

**Interfaces (Produces):**
- **Try-it panel:**
  - Before the flip it is collapsed: `"Try it in SQL after you answer"`.
  - After the flip it expands. On narrow screens (<1180 px) it stays behind a "Try it" toggle button.
  - The editor gets `try_sql` without its leading `--` lines.
  - Those lines are shown on the card back as `"What the sample shows:"` followed by the text, escaped.
  - Cards with no `try_sql`, or only comments, show no block (Review Focus 5).
  - "Restore the sample" restores the comment-free SQL.
- **Back side:** shows the front text (smaller) above the answer.
- **Ratings:**
  - Again / Hard / Good / Easy on keys 1–4.
  - The labels show the previews from `GET /api/card/preview`, fetched when the card is flipped: `"Again in this session"`, `"{d} d"` rounded (minimum "1 d").
  - Ratings are POSTed with `rating: "hard"`.
- **Flashcards page:**
  - "Study {due} due · {new} new" uses `P.card_queue`.
  - Topic rows show due/new from `P.card_topic_counts`.
  - "0 new left today" appears when `new_left == 0`.
  - The deck order is due first, then new.
- **Settings:** a "New flashcards per day" number input (0–100), saved through `/api/settings`.

- [ ] **Step 1:** Implement.
- [ ] **Step 2: Browser check.**
  - The front shows no SQL. The flip shows the editor without the comment, and the comment appears on the back.
  - The back shows the question.
  - The four buttons show increasing day labels, and key 2 (Hard) works.
  - Counts are consistent between Today and Flashcards.
  - A topic deck after the cap is reached shows "0 new left today" (Review Focus 3).
  - Change the setting to 5 and confirm the counts update.
  - Check 1366, 420 and dark mode.
- [ ] **Step 3: Commit** `feat(cards): no peeking, four ratings with intervals, honest due counts`

---

### Task 9: Today as one pipeline, and SQL availability in the UI

**Files:**
- Modify: `js/views/home.js`, `js/views/quiz.js` (results screen), `js/views/cards.js` (deck end), `js/views/exercises.js`, `js/views/lab.js`, `js/shell.js` (DB status)

**Interfaces (Produces):**
- **Practice results screen:** started from Today (`fromToday`), it shows a primary button `"Continue: {N} flashcards"` when `P.plan.cards` minus `P.plan.done.cards` is non-empty. That button opens the deck with the remaining plan cards.
- **Deck end:** when started from Today and `P.plan.lab` is set and not done and `P.sql_available`, it shows `"Continue: today's exercise"`.
- **Exercise:** passing the plan's exercise shows a link "Back to Today", where the existing "Done for today" stamp appears.
- **`P.sql_available === false`:**
  - "Try it" Run, "Run it in the SQL lab" (quiz), Exercises Check/Run and the lab Run button are disabled. One line `"SQL practice isn't enabled on this server yet."` appears where the action would be.
  - The rail status reads `"SQL practice unavailable"`, and keeps "Database offline" for a real outage.

- [ ] **Step 1:** Implement.
- [ ] **Step 2: Browser check.**
  - As admin: run the Today flow end to end, questions → Continue → cards → Continue → exercise → back to Today showing "Done for today".
  - As a second registered learner (no practice targets): no exercise in the plan, disabled SQL buttons with the line, and the rail says "SQL practice unavailable".
  - Check at 1366 and 420.
- [ ] **Step 3: Commit** `feat(today): one flow from questions to cards to exercise; SQL-less learners see no dead ends`

---

### Task 10: Core-loop bugs and wording

**Files:**
- Modify:
  - `js/views/exercises.js`: hints kept when the solution is shown.
  - `js/ui/sql.js`: result header without leading comment lines.
  - `src/oracle_lab/study/recording.py`: `record_history` stores the first non-comment line for display. Check what the history list shows and fix it there, or strip in `lab.js`, choosing one place.
  - `js/views/settings.js`, `js/views/notes.js`, `js/main.js`, `js/views/home.js` (`trackWarning`), `js/views/exercises.js`: wording.
  - `src/oracle_lab/study/engine.py` (`badges` "calibrated" progress).
- Test: `tests/test_engine.py` (`test_calibrated_badge_progress_is_capped_until_both_criteria_hold`), and `tests/test_recording.py` if history changes.

**Interfaces (Produces):**
- **Calibrated badge:** progress is `[min(answers, 50), 50]` only when `sure_ok`. Otherwise it is `[min(answers, 49), 50]`, so the bar never shows full while unearned.
- **Copy:** exactly the strings in Global Constraints.
- **Learner-facing 23ai callouts:** use the 23ai sentence. Admins may keep the setup hint, which mentions `STUDY_DSN_23AI`.

- [ ] **Step 1:** Write the failing engine test, then implement everything.
- [ ] **Step 2:** Run `pytest -q`. Browser check: hint → hint → solution keeps both hints; a lab run with a leading comment shows the SQL as the header; the Settings and Notes text.
- [ ] **Step 3: Commit** `fix: core-loop polish (hints kept, result headers, user-facing wording, calibrated badge)`

---

## Self-review notes

- **Spec coverage:**
  - G1/G2 → Task 5 (+ Task 4 for the server side of incomplete)
  - G3/G4 → Tasks 1 and 8
  - G5 → Tasks 2 and 8
  - G6 → Task 6
  - G7/G8 → Tasks 4 and 7
  - G9 → Task 6
  - G10 → Task 9
  - G11 → Task 10
  - G12 → Tasks 3 and 9
  - S1–S8 map to the same tasks.
- **Order:** the server tasks (1–4) come first so the front-end tasks consume stable payloads. Tasks 5–7 all touch `quiz.js`; they run sequentially, never in parallel.
