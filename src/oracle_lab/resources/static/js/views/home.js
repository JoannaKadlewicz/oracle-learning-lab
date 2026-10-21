/* Today: the study session for today on an index card, the exam countdown and pass chance,
   what else is open, and mastery per topic. */

import { $$, esc, plural, icon } from "../core/dom.js";
import { C, P, L, CARD, DB, mistakes, topicStats, topicLabel } from "../core/state.js";
import { currentUser } from "../core/session.js";
import { main, go } from "../core/router.js";
import { levelBadge, meter, section } from "../ui/widgets.js";
import { startQuiz, startMock, resumeMock, practiceSession, resumePractice } from "./quiz.js";
import { openDeck } from "./cards.js";
import { openNote } from "./notes.js";

function trackWarning() {
  if (!DB || !(C.exam.versions[0] > DB.major)) return "";
  const code = esc(C.exam.code);
  const ending = currentUser().role === "admin"
    ? `Set <code>${esc(C.exam.database_env)}</code> to give ${code} its own database (see the README).`
    : `This server does not provide ${esc(C.exam.database)}.`;
  return `<div class="callout"><p>You are preparing for ${code}, but the SQL lab is connected to ${esc(DB.product)} ${esc(DB.version)}.
    Quizzes and flashcards work as usual; SQL that needs ${esc(C.exam.database)} won't run. ${ending}</p></div>`;
}

function countdownFact(plan, examDate) {
  const date = examDate ? new Date(examDate + "T12:00:00").toLocaleDateString([], { weekday: "long", month: "long", day: "numeric" }) : "";
  if (plan.days_left === null) {
    return `<div class="fact"><span class="fact-value">–</span><span class="fact-label">No exam date yet</span>
      <p>Set it to get a daily plan that fits the time you have.</p><a href="/settings">Set your exam date</a></div>`;
  }
  if (plan.days_left > 0) {
    return `<div class="fact"><span class="fact-value">${plan.days_left}<small>${plan.days_left === 1 ? "day" : "days"}</small></span>
      <span class="fact-label">until your ${esc(C.exam.code)} exam</span><p>${esc(date)}</p></div>`;
  }
  if (plan.days_left === 0) {
    return `<div class="fact"><span class="fact-value">Today</span><span class="fact-label">is your exam</span>
      <p>Skim your mistakes and flashcards, and trust your preparation.</p></div>`;
  }
  return `<div class="fact"><span class="fact-value">–</span><span class="fact-label">Your exam date has passed</span>
    <p>Preparing for a retake?</p><a href="/settings">Set a new date</a></div>`;
}

function passFact(r) {
  if (r.status !== "ok") {
    return `<div class="fact"><span class="fact-value">–</span><span class="fact-label">Chance to pass</span>
      <p>Not enough data yet. Answer new questions or take a mock exam.</p><a href="/progress">How readiness works</a></div>`;
  }
  const pct = Math.round(r.pass_probability * 100);
  return `<div class="fact ${pct >= 80 ? "pass" : pct < 50 ? "risk" : ""}"><span class="fact-value">${pct}%</span>
    <span class="fact-label">chance to pass</span>
    <p>Expected score ${r.low_pct} to ${r.high_pct}%, from first answers only.</p><a href="/progress">See your progress</a></div>`;
}

function render() {
  const plan = P.plan;
  const miss = mistakes().length;
  const lab = plan.lab ? L[plan.lab] : null;
  const done = plan.done;
  const questionsLeft = plan.questions.filter(id => !done.questions.includes(id));
  const cardsLeft = plan.cards.filter(id => !done.cards.includes(id));
  // The same two numbers as the Flashcards page: reviews of cards seen before, and new cards.
  const cardsDue = cardsLeft.filter(id => P.cards[id]).length;
  const cardsNew = cardsLeft.length - cardsDue;
  const cardMinutes = Math.max(1, Math.round(cardsLeft.length * 0.3));
  const questionMinutes = Math.max(1, Math.round(questionsLeft.length * 1.5));
  const total = plan.questions.length + plan.cards.length + (lab ? 1 : 0);
  const finished = done.questions.length + done.cards.length + (done.lab ? 1 : 0);
  const minutesLeft = Math.round(questionsLeft.length * 1.5 + cardsLeft.length * 0.3 + (lab && !done.lab ? 8 : 0));
  const questionsDone = !questionsLeft.length;
  const cardsDone = plan.cards.length && !cardsLeft.length;
  const mock = P.active_mock;
  const mockLeft = mock ? Math.max(0, Math.round((mock.deadline - Date.now() / 1000) / 60)) : 0;
  // A session Today started on an earlier day (its questions are not all in today's plan) is
  // replaced by Start, so it is neither offered for resuming nor resumed.
  const stored = practiceSession();
  const staleToday = s => s?.fromToday && !s.ids.every(id => plan.questions.includes(id));
  const practice = staleToday(stored) ? null : stored;

  main.innerHTML = `
    <header class="page-head">
      <div>
        <h1>Today</h1>
        <ul class="exam-line">
          <li><b>${esc(C.exam.code)}</b> ${esc(C.exam.name)}</li>
          <li><b>${C.exam.questions}</b> questions</li>
          <li><b>${C.exam.minutes}</b> minutes</li>
          <li><b>${C.exam.passing_pct}%</b> to pass</li>
        </ul>
      </div>
    </header>
    ${trackWarning()}

    ${mock ? `<a class="resume-bar primary" href="/quiz" data-start="resume">${icon("timer")}
      <strong>Resume your mock exam</strong>
      <span>${mock.answered} of ${mock.count} answered, ${plural(mockLeft, "minute")} left. The timer is running.</span></a>` : ""}
    ${practice ? `<a class="resume-bar" href="/quiz" data-start="practice">${icon("quiz")}
      <strong>Resume practice (${practice.answered} of ${practice.total})</strong>
      <span>Pick up at the question you were on.</span></a>` : ""}

    <div class="today-hero">
      <article class="session-card ${plan.complete ? "complete" : ""}" aria-labelledby="session-title">
        <div class="session-head"><h2 id="session-title">Today's session</h2>
          <span>${plan.complete ? "All done" : finished ? `${finished} of ${total} done, about ${plural(minutesLeft, "minute")} left` : `About ${plan.estimate} minutes`}</span></div>
        <div class="session-progress" role="progressbar" aria-label="Today's session" aria-valuemin="0" aria-valuemax="${total}" aria-valuenow="${finished}"
          style="--done: ${total ? finished / total : 0}"></div>
        <ol class="session-steps">
          <li><a href="/quiz" data-start="questions" class="${questionsDone ? "done" : ""}">
            <strong>Answer ${plural(plan.questions.length, "question")}</strong>
            <small>${questionsDone ? "All answered" : done.questions.length ? `${done.questions.length} of ${plan.questions.length} answered` : "Open mistakes, due reviews and your weakest objectives"}</small>
            <span class="minutes">${questionsDone ? "" : `${questionMinutes} min`}</span></a></li>
          <li><a href="/cards" data-start="cards" class="${cardsDone ? "done" : ""}" ${plan.cards.length ? "" : `aria-disabled="true" tabindex="-1"`}>
            <strong>${cardsLeft.length ? `Review ${cardsDue} due · ${cardsNew} new` : plan.cards.length ? `Review ${plural(plan.cards.length, "flashcard")}` : "No flashcards due today"}</strong>
            <small>${cardsDone ? "All reviewed" : done.cards.length ? `${done.cards.length} of ${plan.cards.length} reviewed`
              : plan.cards.length ? "Spaced by how well you know them" : "Come back tomorrow, or study a topic deck"}</small>
            <span class="minutes">${cardsLeft.length ? `${cardMinutes} min` : ""}</span></a></li>
          ${lab ? `<li><a href="/exercises/${esc(lab.id)}" class="${done.lab ? "done" : ""}">
            <strong>Exercise: ${esc(lab.title)}</strong>
            <small>${done.lab ? "Passed" : `${esc(topicLabel(lab.topic))}, one of your weakest objectives`}</small>
            <span class="minutes">${done.lab ? "" : "8 min"}</span></a></li>` : ""}
        </ol>
        <div class="session-foot">
          ${plan.complete
            ? `<span class="session-stamp">Done for today</span>
               <button class="btn" data-start="more">Practise 10 more</button>`
            : `<span>${plan.minutes} minutes a day planned</span>
               <button class="btn" data-start="next">${finished ? "Continue the session" : "Start the session"}</button>`}
        </div>
      </article>

      <div class="exam-facts">
        ${countdownFact(plan, P.settings.exam_date)}
        ${passFact(P.readiness)}
      </div>
    </div>

    ${plan.advice.length ? `<ul class="advice">${plan.advice.map(a => `<li>${esc(a)}</li>`).join("")}</ul>` : ""}

    ${section("Also open", `<div class="next-list">
      <a href="/review">${icon("mistakes")}<strong>${miss ? plural(miss, "open mistake") : "No open mistakes"}</strong>
        <span>${miss ? `Cleared after confident correct answers on ${P.proof_days} different days.` : "Missed questions and lucky guesses collect here."}</span></a>
      ${mock ? `<button data-start="resume">${icon("timer")}<strong>Resume your mock exam</strong>
          <span>${mock.answered} of ${mock.count} answered, ${plural(mockLeft, "minute")} left.</span></button>`
        : `<button data-start="mock">${icon("timer")}<strong>Take a mock exam</strong>
          <span>${C.exam.questions} questions in ${C.exam.minutes} minutes, questions you have not seen first.</span></button>`}
      ${C.home_notes.map((n, i) => `<button data-note="${esc(n.path)}">${icon(i ? "notes" : "doc")}<strong>${esc(n.title)}</strong>
        <span>${esc(n.blurb)}</span></button>`).join("\n      ")}
    </div>`)}

    ${section("Topics", `<div class="table-wrap"><table class="data">
      <thead><tr><th>Topic</th><th>Mastery</th>
        <th class="hide-s" title="Questions whose most recent answer was correct. Mastery uses all your recent answers, so retrying a question until it is right does not hide earlier misses.">Questions correct</th>
        <th class="hide-s">Cards learned</th><th class="hide-s">Exercises passed</th><th><span class="sr-only">Actions</span></th></tr></thead>
      <tbody>${Object.keys(C.topics).map(t => {
        const s = topicStats(t);
        return `<tr>
          <td>${esc(topicLabel(t))}</td>
          <td>${levelBadge(P.topics[t])}</td>
          <td class="hide-s">${meter(s.correct, s.total, "Questions correct")}</td>
          <td class="hide-s">${meter(s.learned, s.cards, "Cards learned")}</td>
          <td class="hide-s">${meter(s.passed, s.labs, "Exercises passed")}</td>
          <td class="actions"><button class="btn secondary small" data-topic="${t}">Practise</button></td>
        </tr>`;
      }).join("")}</tbody>
    </table></div>`, { note: `Mastery combines quiz answers, flashcards and exercises per official objective, weighted by how recent they are and how sure you were. <a href="/progress">See every objective</a>.` })}
  `;

  $$("[data-start]", main).forEach(a => a.addEventListener("click", e => {
    e.preventDefault();
    const kind = a.dataset.start;
    if (kind === "practice") resumePractice();
    else if (kind === "mock") startMock();
    else if (kind === "resume") resumeMock();
    else if (kind === "more") startQuiz({ mode: "practice", count: 10 });
    // The next unfinished step: questions, then flashcards, then the exercise.
    else if (kind === "questions" || (kind === "next" && questionsLeft.length)) {
      // Today's own session, still stored, picks up where it was; one from the Quiz page, or a stale one, is replaced.
      const now = practiceSession();
      if (now?.fromToday && !staleToday(now)) return resumePractice();
      startQuiz({ mode: "practice", ids: questionsLeft.length ? questionsLeft : plan.questions, keepOrder: true, fromToday: true });
    } else if (kind === "cards" || cardsLeft.length) openDeck((cardsLeft.length ? cardsLeft : plan.cards).map(id => CARD[id]).filter(Boolean), true, { fromToday: true });
    else if (lab) go(`/exercises/${lab.id}`);
  }));
  $$("[data-topic]", main).forEach(b => b.addEventListener("click", () => startQuiz({ mode: "practice", topics: [b.dataset.topic], count: 10 })));
  $$("[data-note]", main).forEach(b => b.addEventListener("click", () => openNote(b.dataset.note)));
}

export const homeView = { title: "Today", render };
