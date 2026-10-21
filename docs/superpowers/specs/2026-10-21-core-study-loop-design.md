# Core study loop improvements

Date: 2026-10-21
Status: design, approved in conversation, not yet planned
Source: UX assessment of 2026-10-21 (bugs B1–B15, proposals P1, P2, P4, P8, P12, P16, P19, P20, P22, P23 and the core-loop part of P5/P34)

## Why

The learning engine (SM-2 for questions and cards, proof-on-two-days mistakes, readiness, mock reports) is strong. The screens around it still mislead learners or lose their work:

- A "choose two" question can be checked with one option ticked, and the result is recorded as a misconception. That pollutes mistakes, calibration and the pass estimate. About half the question bank is multi-answer.
- The flashcard "Try it" sample is visible before the card is flipped, and its first comment usually states the answer. That defeats retrieval practice for about 90% of cards.
- A reload loses a practice session. During a mock it drops the learner on the setup page. Resuming a mock always opens question 1.
- Flashcards report "298 due" (new cards counted as due, no cap) while Today plans 37.
- Learners without SQL access get a daily plan with an exercise they can never finish.

The owner chose to focus on the core study loop: practising questions, flashcards, mock exams and the Today session.

## Goals

1. **Questions (choose-N).** Answering behaves like the real exam for multi-answer questions.
   - A visible counter appears: "1 of 2 selected".
   - Check and the confidence buttons stay disabled until exactly N options are ticked.
   - Ticking more than N is blocked: the extra tick is refused and the counter pulses.
   - In a mock, a question with fewer than N ticks shows as *incomplete* (not answered) in the navigator and on the review screen. Submitting is still allowed, and the confirmation counts incomplete questions next to unanswered ones.
   - The engine keeps grading exactly as today: any other selection is wrong. The UI simply prevents count slips in practice.
2. **Questions (keys and Enter).**
   - Options can be chosen with the letter shown on them (A–H) as well as with 1–8. A–H do not clash with S/T/G, because confidence keys are only active after the options are complete. If that is not true today, the builder must make it so.
   - Enter checks the answer with "Think so" when no confidence was chosen; it no longer shows a toast.
   - The verdict reads "The answer is D, E and F."
   - The "choose how sure you are" toast is dismissed as soon as the answer is checked.
3. **Flashcards: Try-it after the flip.**
   - Before the flip, the Try-it panel is collapsed to a short line ("Try it in SQL after you answer").
   - After the flip it expands with the sample.
   - The leading `--` comment lines of `try_sql` are shown on the back of the card (under the answer, as "What the sample shows: …"), not in the editor.
   - "Restore the sample" restores the SQL without the comment.
   - On phones the panel stays collapsed behind a "Try it" button even after the flip.
4. **Flashcards: back side and ratings.**
   - The back shows the question, smaller, above the answer.
   - Ratings become Again / Hard / Good / Easy, keys 1–4, with SM-2 qualities 1 / 3 / 4 / 5.
   - Each button shows the next interval it would give ("10 min", "1 d", "3 d", "8 d"), computed by the engine, not duplicated in JavaScript.
5. **One due-card model.**
   - **Due reviews:** cards already reviewed whose SM-2 due time has passed.
   - **New cards:** never reviewed, limited by a daily cap.
   - Settings gets "New flashcards per day" (default 15, range 0–100). Cards introduced today (first review today) count against the cap.
   - Flashcards, Today and the per-topic decks all show the same two numbers ("12 due · 15 new").
   - "Study due cards" studies due reviews plus today's remaining new cards, in that order.
6. **Never lose your place: practice.**
   - The running practice session is kept in the browser per user, using the existing per-user storage. It holds the items, option order, position, ticks, checked results and confidence.
   - Reloading `/quiz` resumes it.
   - Today shows "Resume practice (4 of 10)" while one is unfinished.
   - Finishing or quitting clears it.
   - Sessions older than 24 h are discarded.
7. **Never lose your place: mock.**
   - Opening `/quiz` while the server reports a running mock reopens that mock directly.
   - The mock opens at the last question the learner viewed: the server stores a `position` with each answer/navigation save. With no stored position it opens at the first unanswered question.
   - "Resume your mock exam" on Today does the same.
8. **Full-screen mock.**
   - While a mock runs, the side navigation and top bar are hidden. A slim exam bar shows: exam code, timer, "Question x of 63", Flag, Review, Submit.
   - Leaving the page (closing the tab, reloading, or following a link) asks for confirmation. A reload still resumes (goal 7).
   - Answered questions in the navigator get a ✓ glyph, and flagged ones a flag glyph, not colour only.
9. **Missed questions come back in the session.**
   - In practice, a question answered wrong (or a correct "guess") is reinserted about 5 questions later, or at the end if fewer remain. Its options are shuffled again and it is marked "Second try".
   - It is reinserted at most once per question per session.
   - The second answer is recorded like any other attempt. The engine's proof rule (different days) stays unchanged, so it cannot clear a mistake on the same day.
   - The results screen counts each question once, using its first answer, and lists the second tries separately.
10. **Today as one pipeline.**
    - Today's session is one flow:
      1. Questions.
      2. On their results screen, a primary button "Continue: N flashcards". It shows only while plan cards remain.
      3. Flashcards. At the end of the deck, "Continue: today's exercise" (only if planned and SQL is available).
      4. The exercise. Passing it returns to Today, which shows "Done for today".
    - Steps already completed are skipped.
11. **Core-loop bugs and text.**
    - Showing the solution keeps the hints already shown.
    - SQL result headers show the statement without its leading comment lines. History entries use the first non-comment line.
    - Leftover single-user text in Settings, Notes, the boot error and learner-facing callouts is replaced with user-facing wording:
      - Settings: "Your progress is saved to your account."
      - Notes: "Lesson notes for every topic, and your saved SQL notes."
      - Boot error: "The app could not load. Reload, or try again in a minute."
      - Callouts about `STUDY_DSN_23AI`: learners see "The 1Z0-171 SQL features need Oracle 23ai, which this server does not provide."
    - The "Calibrated" badge bar reflects both criteria: it shows full only when earned.
12. **SQL availability in the loop.**
    - When the signed-in user has no SQL access (practice schemas not configured and the user is not an admin), the server says so in the progress/content payload (`sql_available: false`). Then:
      - the daily plan contains no exercise;
      - "Try it" panels, "Run it in the SQL lab", the Exercises "Check"/"Run" buttons and the lab are shown disabled, with one line: "SQL practice isn't enabled on this server yet.";
      - the sidebar's database status reads "SQL practice unavailable" instead of "Database offline".
    - When practice schemas are configured but the user's schema is still being prepared, nothing changes: the existing "being prepared" message stays.

## Non-goals

- Per-option explanations, linking verdicts to notes/cards/exercises, Mistakes page redesign.
- Onboarding, guided curriculum, Progress page changes, streak placement.
- Phone layout beyond what goals 3 and 8 need, payload size/caching, contrast work.
- Content changes (translations, distractor rewrites), admin features, account features.
- Changing how answers are graded or how mastery, readiness and proof are computed. The exception is the card-quality addition of "Hard" (quality 3), which SM-2 already supports.

## Constraints

- Same stack: Python stdlib server, vanilla-JS ES modules, no new dependencies.
- Security rules from the accounts work stay in force:
  - CSP without inline handlers; `esc()`/`textContent` for all data.
  - CSRF header on every POST.
  - Per-user storage namespace (`store.js`).
- Every behaviour change gets a test where the code is testable:
  - **engine:** due model, Hard rating, interval previews, plan without exercise;
  - **mocks:** position;
  - **web:** endpoints.
- Front-end changes are verified in a real browser (Playwright, at 1366, 1920 and 420 px, light and dark) for the flows they change.
- Progress data stays backward compatible:
  - existing card reviews (again/good/easy) keep their meaning;
  - mocks without a stored position open at the first unanswered question.

## Decisions made (designer's calls, approved scope)

- **Practice session storage:** in the browser (per-user `localStorage`), not on the server. It is simplest, and resuming on the same device covers the reload/short-burst case. Cross-device resume is not a goal.
- **Mock position:** stored on the server, because mocks already live there.
- **Interval previews:** come from a small server endpoint, or from data included when a deck opens. The builder chooses. The SM-2 logic must exist only in `engine.py`.
- **Second tries:** only in practice sessions started from Today or Quiz, never in mocks.
- **Enter with no confidence:** submits as "Think so" with no setting. The calibration data treats "think" as the neutral default, as it already does for answers without a rating.

## Details settled after the builder review (designer's calls)

1. **Ratings and previews.**
   - **Again (quality 1):** keeps today's behaviour. The card is due immediately and comes back in the same deck 3 cards later, as it does now. Preview label: "Again in this session".
   - **Good (4) and Easy (5):** unchanged SM-2.
   - **Hard (quality 3):** a new rating.
     - Stored as the string `"hard"`.
     - Interval: the previous interval × 1.2, at least previous + 1 day; its first review gives 1 day.
     - Ease: the standard SM-2 change for quality 3 (−0.14), not below 1.3.
     - This is a new rating with its own rule. Existing again/good/easy reviews replay exactly as before.
   - **Previews:** for Hard, Good and Easy, show the resulting interval rounded to days (or "1 d" at minimum), computed by the engine.
   - **Mastery and readiness:** count Hard as remembered, like Good.
   - **Other readers:** places that check `== "again"` for "forgotten" keep treating only Again as forgotten. `tools/demo.py` may keep producing again/good/easy.
2. **New-card cap.**
   - **Scope:** global per user, not per topic. It is stored as the setting `new_cards_per_day` in the user's state and returned with the other settings.
   - **What counts:** "introduced today" means cards whose first review falls on today's local day (`engine.local_day`), whatever the rating.
   - **Today's plan:** its card slice is due reviews first, then new cards up to the remaining allowance, and still fits the time budget as before.
   - **Topic decks:** use the same rule, so a topic deck's new cards are drawn from the same global allowance.
3. **Mock position.**
   - **Value:** a 0-based index into the mock's item order, validated as 0 ≤ position < len(items).
   - **When it is saved:** with every answer save (the existing call gets an optional `position`), and when the learner navigates without answering. Navigation saves are debounced on the client, so moving between questions sends at most one save per 2 s, and the latest position wins.
   - **On resume:**
     - with a stored position: open at that position;
     - otherwise, at the first unanswered question;
     - if every question is answered: open the review screen.
4. **Incomplete choose-N in a mock.**
   - **Saving:** partial selections are saved to the server as they are today, so a reload keeps them.
   - **Grading:** they grade as wrong at submit.
   - **"Incomplete":** purely a client-side view. The question's choice count is below its answer count.
   - **Submit confirmation:** counts unanswered and incomplete questions separately.
   - **Server:** grading and reports don't change.
5. **SQL availability.**
   - **The flag:** `sql_available = practice targets configured OR user is admin`, computed in one place on the server and returned with the progress payload.
   - **Sidebar status:**
     - "Database offline" stays for a database that does not answer;
     - "SQL practice unavailable" when `sql_available` is false;
     - "being prepared" is unchanged and shown where SQL runs.
   - **Today's plan:** computed server-side on every progress load, so a learner without SQL simply never gets an exercise. Today's plan is fixed per day (from the accounts work) and is built with the flag.
6. **Today pipeline state.**
   - **Where it comes from:** derived from the server. Today's plan already reports what is done today (questions answered, cards reviewed, exercise passed), so no client flag is needed and a reload is harmless.
   - **Continue buttons:**
     - on the question results: "Continue: N flashcards", where N is the plan cards not yet reviewed today;
     - at the end of the deck: "Continue: today's exercise".
   - **Practice resume:** a practice session resumed from storage keeps a flag saying it came from Today, so its results screen still offers "Continue".
7. **Second tries and the stored session.**
   - **What the snapshot holds:** the reinserted items and the per-question "already reinserted" flags.
   - **Counting:** second tries do not count toward "N of 10". The counter shows the original items; second tries show as "Second try" without changing the total.
   - **Quitting early:** second tries not yet answered are simply dropped. They were never answered, so nothing is recorded.
   - **Verdict wording:** a correct second try says "Right this time. It stays in your mistakes until you get it right on another day." when the question is an open mistake.
8. **Leaving a running mock.**
   - **Leaving the page:** `beforeunload` covers closing, reloading and real navigations.
   - **Leaving inside the app:** a router guard asks the custom confirm dialog ("Leave the exam? The timer keeps running.").
   - **Exam bar:** has an explicit "Leave" button (the same confirm; the mock keeps running and can be resumed) next to Submit. Abandoning stays available on the review screen as today.

## What's left to the builder

- Exact markup and CSS of the counter, exam bar and collapsed Try-it panel, within the existing design language.
- How `sql_available` is computed and exposed (one place, reused by plan and UI).
- How the practice session snapshot is versioned in storage.
- Test file layout.
