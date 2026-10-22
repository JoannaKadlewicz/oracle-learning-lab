/* Today: the study session for today on an index card, the exam countdown and pass chance,
   what else is open, and mastery per topic. */

import { $$, esc, plural, icon } from "../core/dom.js";
import { C, S, P, L, CARD, DB, mistakes, topicStats, topicLabel } from "../core/state.js";
import { currentUser } from "../core/session.js";
import { t, tn, formatDate } from "../core/i18n.js";
import { main, go } from "../core/router.js";
import { levelBadge, meter, section, premiumTag } from "../ui/widgets.js";
import { startQuiz, startMock, resumeMock, practiceSession, resumePractice } from "./quiz.js";
import { openDeck } from "./cards.js";
import { openNote } from "./notes.js";

function trackWarning() {
  if (!DB || !(C.exam.versions[0] > DB.major)) return "";
  const ending = currentUser().role === "admin"
    ? esc(t("Set {env} to give {code} its own database (see the README).", { code: C.exam.code })).replace("{env}", `<code>${esc(C.exam.database_env)}</code>`)
    : esc(t("This server does not provide {database}.", { database: C.exam.database }));
  return `<div class="callout"><p>${esc(t("You are preparing for {code}, but the SQL lab is connected to {product} {version}.", { code: C.exam.code, product: DB.product, version: DB.version }))}
    ${esc(t("Quizzes and flashcards work as usual; SQL that needs {database} won't run.", { database: C.exam.database }))} ${ending}</p></div>`;
}

function countdownFact(plan, examDate) {
  const date = examDate ? formatDate(examDate + "T12:00:00", { weekday: "long", month: "long", day: "numeric" }) : "";
  if (plan.days_left === null) {
    return `<div class="fact"><span class="fact-value">–</span><span class="fact-label">${esc(t("No exam date yet"))}</span>
      <p>${esc(t("Set it to get a daily plan that fits the time you have."))}</p><a href="/settings">${esc(t("Set your exam date"))}</a></div>`;
  }
  if (plan.days_left > 0) {
    return `<div class="fact"><span class="fact-value">${plan.days_left}<small>${esc(tn(plan.days_left, "day", "days"))}</small></span>
      <span class="fact-label">${esc(t("until your {code} exam", { code: C.exam.code }))}</span><p>${esc(date)}</p></div>`;
  }
  if (plan.days_left === 0) {
    return `<div class="fact"><span class="fact-value">${esc(t("Today"))}</span><span class="fact-label">${esc(t("is your exam"))}</span>
      <p>${esc(t("Skim your mistakes and flashcards, and trust your preparation."))}</p></div>`;
  }
  return `<div class="fact"><span class="fact-value">–</span><span class="fact-label">${esc(t("Your exam date has passed"))}</span>
    <p>${esc(t("Preparing for a retake?"))}</p><a href="/settings">${esc(t("Set a new date"))}</a></div>`;
}

function passFact(r) {
  if (r.status !== "ok") {
    return `<div class="fact"><span class="fact-value">–</span><span class="fact-label">${esc(t("Chance to pass"))}</span>
      <p>${esc(t("Not enough data yet. Answer new questions or take a mock exam."))}</p><a href="/progress">${esc(t("How readiness works"))}</a></div>`;
  }
  const pct = Math.round(r.pass_probability * 100);
  return `<div class="fact ${pct >= 80 ? "pass" : pct < 50 ? "risk" : ""}"><span class="fact-value">${pct}%</span>
    <span class="fact-label">${esc(t("chance to pass"))}</span>
    <p>${esc(t("Expected score {low} to {high}%, from first answers only.", { low: r.low_pct, high: r.high_pct }))}</p><a href="/progress">${esc(t("See your progress"))}</a></div>`;
}

/** `text` escaped, with its first `value` in bold ("<b>63</b> questions"). */
function bold(text, value) {
  const s = String(value);
  const at = text.indexOf(s);
  return at < 0 ? esc(text) : `${esc(text.slice(0, at))}<b>${esc(s)}</b>${esc(text.slice(at + s.length))}`;
}

function render() {
  const plan = P.plan;
  const miss = mistakes().length;
  const lab = plan.lab ? L[plan.lab] : null;
  const locked = Boolean(lab && plan.lab_locked);  // shown, but a free account can't run it: not part of the count
  const counted = lab && !locked;
  const done = plan.done;
  const questionsLeft = plan.questions.filter(id => !done.questions.includes(id));
  const cardsLeft = plan.cards.filter(id => !done.cards.includes(id));
  // The same two numbers as the Flashcards page: reviews of cards seen before, and new cards.
  const cardsDue = cardsLeft.filter(id => P.cards[id]).length;
  const cardsNew = cardsLeft.length - cardsDue;
  const cardMinutes = Math.max(1, Math.round(cardsLeft.length * 0.3));
  const questionMinutes = Math.max(1, Math.round(questionsLeft.length * 1.5));
  const total = plan.questions.length + plan.cards.length + (counted ? 1 : 0);
  const finished = done.questions.length + done.cards.length + (counted && done.lab ? 1 : 0);
  const minutesLeft = Math.round(questionsLeft.length * 1.5 + cardsLeft.length * 0.3 + (counted && !done.lab ? 8 : 0));
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
        <h1>${esc(t("Today"))}</h1>
        <ul class="exam-line">
          <li><b>${esc(C.exam.code)}</b> ${esc(C.exam.name)}</li>
          <li>${bold(tn(C.exam.questions, "{n} question", "{n} questions"), C.exam.questions)}</li>
          <li>${bold(tn(C.exam.minutes, "{n} minute", "{n} minutes"), C.exam.minutes)}</li>
          <li>${bold(t("{pct}% to pass", { pct: C.exam.passing_pct }), `${C.exam.passing_pct}%`)}</li>
        </ul>
      </div>
    </header>
    ${trackWarning()}

    ${mock ? `<a class="resume-bar primary" href="/quiz" data-start="resume">${icon("timer")}
      <strong>${esc(t("Resume your mock exam"))}</strong>
      <span>${esc(tn(mockLeft, "{answered} of {count} answered, {n} minute left. The timer is running.", "{answered} of {count} answered, {n} minutes left. The timer is running.", { answered: mock.answered, count: mock.count }))}</span></a>` : ""}
    ${practice ? `<a class="resume-bar" href="/quiz" data-start="practice">${icon("quiz")}
      <strong>${esc(t("Resume practice ({answered} of {total})", { answered: practice.answered, total: practice.total }))}</strong>
      <span>${esc(t("Pick up at the question you were on."))}</span></a>` : ""}

    <div class="today-hero">
      <article class="session-card ${plan.complete ? "complete" : ""}" aria-labelledby="session-title">
        <div class="session-head"><h2 id="session-title">${esc(t("Today's session"))}</h2>
          <span>${esc(plan.complete ? t("All done") : finished
            ? tn(minutesLeft, "{finished} of {total} done, about {n} minute left", "{finished} of {total} done, about {n} minutes left", { finished, total })
            : tn(plan.estimate, "About {n} minute", "About {n} minutes"))}</span></div>
        <div class="session-progress" role="progressbar" aria-label="${esc(t("Today's session"))}" aria-valuemin="0" aria-valuemax="${total}" aria-valuenow="${finished}"
          style="--done: ${total ? finished / total : 0}"></div>
        <ol class="session-steps">
          <li><a href="/quiz" data-start="questions" class="${questionsDone ? "done" : ""}">
            <strong>${esc(tn(plan.questions.length, "Answer {n} question", "Answer {n} questions"))}</strong>
            <small>${esc(questionsDone ? t("All answered") : done.questions.length
              ? t("{done} of {total} answered", { done: done.questions.length, total: plan.questions.length })
              : t("Open mistakes, due reviews and your weakest objectives"))}</small>
            <span class="minutes">${questionsDone ? "" : esc(t("{n} min", { n: questionMinutes }))}</span></a></li>
          <li><a href="/cards" data-start="cards" class="${cardsDone ? "done" : ""}" ${plan.cards.length ? "" : `aria-disabled="true" tabindex="-1"`}>
            <strong>${esc(cardsLeft.length ? t("Review {due} due · {fresh} new", { due: cardsDue, fresh: cardsNew })
              : plan.cards.length ? tn(plan.cards.length, "Review {n} flashcard", "Review {n} flashcards") : t("No flashcards due today"))}</strong>
            <small>${esc(cardsDone ? t("All reviewed") : done.cards.length ? t("{done} of {total} reviewed", { done: done.cards.length, total: plan.cards.length })
              : plan.cards.length ? t("Spaced by how well you know them") : t("Come back tomorrow, or study a topic deck"))}</small>
            <span class="minutes">${cardsLeft.length ? esc(t("{n} min", { n: cardMinutes })) : ""}</span></a></li>
          ${locked ? `<li><a href="/exercises/${esc(lab.id)}" class="locked">
            <strong>${esc(t("Exercise: {title}", { title: lab.title }))} ${premiumTag()}</strong>
            <small>${esc(t("Read it now; running SQL needs a premium account"))}</small>
            <span class="minutes"></span></a></li>` : ""}
          ${counted ? `<li><a href="/exercises/${esc(lab.id)}" class="${done.lab ? "done" : ""}">
            <strong>${esc(t("Exercise: {title}", { title: lab.title }))}</strong>
            <small>${esc(done.lab ? t("Passed") : S.labs[lab.id]?.passed ? t("Passed before: a second go keeps it fresh")
              : t("{topic}, one of your weakest objectives", { topic: topicLabel(lab.topic) }))}</small>
            <span class="minutes">${done.lab ? "" : esc(t("{n} min", { n: 8 }))}</span></a></li>` : ""}
        </ol>
        <div class="session-foot">
          ${plan.complete
            ? `<span class="session-stamp">${esc(t("Done for today"))}</span>
               <button class="btn" data-start="more">${esc(t("Practise 10 more"))}</button>`
            : `<span>${esc(tn(plan.minutes, "{n} minute a day planned", "{n} minutes a day planned"))}</span>
               <button class="btn" data-start="next">${esc(finished ? t("Continue the session") : t("Start the session"))}</button>`}
        </div>
      </article>

      <div class="exam-facts">
        ${countdownFact(plan, P.settings.exam_date)}
        ${passFact(P.readiness)}
      </div>
    </div>

    ${plan.advice.length ? `<ul class="advice">${plan.advice.map(a => `<li>${esc(a)}</li>`).join("")}</ul>` : ""}

    ${section(esc(t("Also open")), `<div class="next-list">
      <a href="/review">${icon("mistakes")}<strong>${esc(miss ? plural(miss, "open mistake") : t("No open mistakes"))}</strong>
        <span>${esc(miss ? t("Cleared after confident correct answers on {days} different days.", { days: P.proof_days }) : t("Missed questions and lucky guesses collect here."))}</span></a>
      ${mock ? `<button data-start="resume">${icon("timer")}<strong>${esc(t("Resume your mock exam"))}</strong>
          <span>${esc(tn(mockLeft, "{answered} of {count} answered, {n} minute left.", "{answered} of {count} answered, {n} minutes left.", { answered: mock.answered, count: mock.count }))}</span></button>`
        : `<button data-start="mock">${icon("timer")}<strong>${esc(t("Take a mock exam"))}</strong>
          <span>${esc(t("{questions} questions in {minutes} minutes, questions you have not seen first.", { questions: C.exam.questions, minutes: C.exam.minutes }))}</span></button>`}
      ${C.home_notes.map((n, i) => `<button data-note="${esc(n.path)}">${icon(i ? "notes" : "doc")}<strong>${esc(n.title)}</strong>
        <span>${esc(n.blurb)}</span></button>`).join("\n      ")}
    </div>`)}

    ${section(esc(t("Topics")), `<div class="table-wrap"><table class="data">
      <thead><tr><th>${esc(t("Topic"))}</th><th>${esc(t("Mastery"))}</th>
        <th class="hide-s" title="${esc(t("Questions whose most recent answer was correct. Mastery uses all your recent answers, so retrying a question until it is right does not hide earlier misses."))}">${esc(t("Questions correct"))}</th>
        <th class="hide-s">${esc(t("Cards learned"))}</th><th class="hide-s">${esc(t("Exercises passed"))}</th><th><span class="sr-only">${esc(t("Actions"))}</span></th></tr></thead>
      <tbody>${Object.keys(C.topics).map(id => {
        const s = topicStats(id);
        return `<tr>
          <td>${esc(topicLabel(id))}</td>
          <td>${levelBadge(P.topics[id])}</td>
          <td class="hide-s">${meter(s.correct, s.total, t("Questions correct"))}</td>
          <td class="hide-s">${meter(s.learned, s.cards, t("Cards learned"))}</td>
          <td class="hide-s">${meter(s.passed, s.labs, t("Exercises passed"))}</td>
          <td class="actions"><button class="btn secondary small" data-topic="${id}">${esc(t("Practise"))}</button></td>
        </tr>`;
      }).join("")}</tbody>
    </table></div>`, { note: `${esc(t("Mastery combines quiz answers, flashcards and exercises per official objective, weighted by how recent they are and how sure you were."))} <a href="/progress">${esc(t("See every objective"))}</a>.` })}
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
    else if (counted) go(`/exercises/${lab.id}`);
  }));
  $$("[data-topic]", main).forEach(b => b.addEventListener("click", () => startQuiz({ mode: "practice", topics: [b.dataset.topic], count: 10 })));
  $$("[data-note]", main).forEach(b => b.addEventListener("click", () => openNote(b.dataset.note)));
}

export const homeView = { get title() { return t("Today"); }, render };
