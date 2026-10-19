/* Quiz: setup, practice questions with confidence, timed mock exams (kept on the server, so a
   reload resumes them), results and mock reports. */

import { $, $$, esc, inlineCode, plural, shuffle, icon, LETTERS } from "../core/dom.js";
import { api } from "../core/api.js";
import { store } from "../core/store.js";
import { C, S, P, Q, apply, topicLabel, blockedOn23ai } from "../core/state.js";
import { main, go } from "../core/router.js";
import { toast, toastError, confirmDialog } from "../ui/feedback.js";
import { meter, pageHead, section } from "../ui/widgets.js";
import { readinessHtml } from "../ui/charts.js";
import { refreshNav } from "../shell.js";
import { labDraft } from "./lab.js";

let quiz = null;
let timerHandle = null;

const CONF = [["sure", "Sure", "S"], ["think", "Think so", "T"], ["guess", "Guessing", "G"]];

const QTYPES = {
  all: ["All types", () => true],
  multi: ["Choose two or three", q => q.answer.length > 1],
  error: ["Which error?", q => !!q.try_error],
  output: ["Predict the output", q => !!q.answer_sql],
  equivalent: ["Equivalent queries", q => !!q.equivalent_sql],
  code: ["Read the code", q => !!q.code],
  concept: ["Concepts (no code)", q => !q.code],
};

export function resetQuiz() { stopTimer(); quiz = null; }

function stopTimer() { clearInterval(timerHandle); timerHandle = null; }

function isCorrect(q, chosen) {
  return [...q.answer].sort().join(",") === [...(chosen || [])].sort().join(",");
}

/* ---------------------------------------------------------------- starting */

export async function startQuiz({ mode, topics, count, minutes, ids, keepOrder }) {
  topics = topics || Object.keys(C.topics);
  if (mode === "exam") return startMock({ topics: topics.length === Object.keys(C.topics).length ? null : topics, count, minutes });
  let items;
  if (ids) items = keepOrder ? [...ids] : shuffle(ids);
  else {
    // Practice: the engine picks mistakes, due reviews and weak objectives first, interleaved.
    try { items = (await api("/api/pick", { topics, count: count || 10 })).ids; }
    catch { items = shuffle(C.questions.filter(q => topics.includes(q.topic)).map(q => q.id)).slice(0, count || 10); }
  }
  const order = {};
  for (const id of items) order[id] = shuffle(Q[id].options.map((_, i) => i));
  quiz = {
    mode, items, order, idx: 0, answers: {}, checked: {}, flags: {}, confidence: {},
    started: Date.now(), deadline: null, finished: false, reviewIdx: null,
  };
  go("/quiz");
}

/* Mock exams live on the server: it picks the questions, keeps the answers and the deadline,
   and scores the exam. */

export async function startMock({ topics, count, minutes, ids } = {}) {
  if (P.active_mock && !await confirmDialog({
    title: "Abandon the running mock exam?",
    body: "It will not be scored, and its questions count as seen.",
    confirm: "Start a new mock", danger: true,
  })) return;
  try {
    const res = await api("/api/mock/start", { topics, count, minutes, ids });
    apply(res);
    openMock(res.mock);
  } catch (err) { toastError(`Could not start the mock exam. ${err.message}`); }
}

export async function resumeMock() {
  try { openMock((await api("/api/mock?id=" + encodeURIComponent(P.active_mock.id))).mock); }
  catch { toastError("Could not load the running mock exam."); }
}

function mockQuiz(mock) {
  const order = {};
  for (const id of mock.items) order[id] = shuffle(Q[id].options.map((_, i) => i));
  const pick = key => Object.fromEntries(Object.entries(mock.answers).map(([id, a]) => [id, a[key]]));
  return {
    mode: "exam", mockId: mock.id, items: mock.items, order, idx: 0, checked: {},
    answers: pick("chosen"), confidence: pick("confidence"), flags: pick("flagged"),
    timeOn: { ...mock.time_on }, shownId: null, shownAt: null,
    started: mock.started * 1000, deadline: (mock.started + mock.minutes * 60) * 1000,
    finished: false, reviewIdx: null, reviewScreen: false, report: null,
  };
}

function openMock(mock) { quiz = mockQuiz(mock); go("/quiz"); }

function trackTime(id) {
  // Seconds spent per question in a mock, for the post-exam timing report.
  const now = Date.now();
  if (quiz.shownId && quiz.shownAt) quiz.timeOn[quiz.shownId] = (quiz.timeOn[quiz.shownId] || 0) + (now - quiz.shownAt) / 1000;
  quiz.shownId = id;
  quiz.shownAt = id ? now : null;
}

function saveMockAnswer(id, change) {
  api("/api/mock/answer", { mock_id: quiz.mockId, id, time_on: quiz.timeOn, ...change })
    .catch(() => toastError("Could not save your answer. Check that the server is running."));
}

/* ---------------------------------------------------------------- view */

function render() {
  if (!quiz) return renderSetup();
  main.classList.add("reading");
  if (quiz.finished) return quiz.reviewIdx === null ? renderResults() : renderQuestion(quiz.reviewIdx, true);
  if (quiz.reviewScreen) return renderMockReview();
  renderQuestion(quiz.idx, false);
}

function renderSetup() {
  const saved = store("quiz-setup") || { topics: Object.keys(C.topics), count: 10, mode: "practice" };
  const counts = [5, 10, 20, 30, C.exam.questions, 999];
  main.innerHTML = `
    ${pageHead("Quiz", "Original practice questions written for these exams, not real exam items. Every answer was checked against Oracle.")}
    <div class="panel">
      <div class="setup-grid">
        <div class="field"><span class="label">Mode</span>
          <div class="choices" role="group" aria-label="Mode">
            <button class="choice" data-mode="practice"><strong>Practice</strong><span>See the explanation after each answer.</span></button>
            <button class="choice" data-mode="exam"><strong>Exam, timed</strong><span>Like the real test: a time limit, results at the end.</span></button>
          </div>
        </div>
        <div class="field"><span class="label">Topics</span>
          <div class="chips" id="topic-chips">
            ${Object.keys(C.topics).map(t => `<button class="chip" data-t="${t}">${esc(topicLabel(t))}</button>`).join("")}
          </div>
          <div class="field-tools"><button class="link-btn" id="all-topics">Select all</button><button class="link-btn" id="no-topics">Clear</button></div>
        </div>
        <div class="field"><span class="label">Question type</span>
          <div class="chips" id="type-chips">
            ${Object.entries(QTYPES).map(([k, [label]]) => `<button class="chip" data-qtype="${k}">${label}</button>`).join("")}
          </div>
          <label class="check small" style="margin-top:6px"><input type="checkbox" id="unseen-only" ${saved.unseen ? "checked" : ""}> Only questions I have not answered yet</label>
        </div>
        <div class="field"><span class="label" id="count-label">Number of questions</span>
          <div class="seg" role="group" aria-labelledby="count-label">
            ${counts.map(n => `<button data-count="${n}">${n === 999 ? "All" : n}</button>`).join("")}
          </div>
        </div>
      </div>
      <div class="panel-foot">
        <button class="btn large" id="start-quiz">Start quiz</button>
        <p class="pool-info small" id="pool-info" aria-live="polite"></p>
      </div>
    </div>`;

  const state = { qtype: "all", unseen: false, ...saved };
  state.topics = state.topics.filter(t => C.topics[t]);
  if (!state.topics.length) state.topics = Object.keys(C.topics);
  if (!counts.includes(state.count)) state.count = 10;
  const filtered = () => C.questions.filter(q => state.topics.includes(q.topic) && QTYPES[state.qtype][1](q)
    && !(state.unseen && S.attempts[q.id]?.length));
  const sync = () => {
    $$("[data-mode]", main).forEach(b => b.setAttribute("aria-pressed", b.dataset.mode === state.mode));
    $$("#topic-chips .chip").forEach(b => b.setAttribute("aria-pressed", state.topics.includes(b.dataset.t)));
    $$("[data-qtype]", main).forEach(b => b.setAttribute("aria-pressed", b.dataset.qtype === state.qtype));
    $$("[data-count]", main).forEach(b => b.setAttribute("aria-pressed", Number(b.dataset.count) === state.count));
    const special = state.qtype !== "all" || state.unseen;
    const pool = filtered().length;
    const n = Math.min(pool, state.count);
    const minutes = Math.ceil(n * 1.9);
    $("#pool-info").textContent = !pool ? "No questions match. Select at least one topic, or another question type."
      : `${n} of ${pool} matching questions. ` + (state.mode === "exam"
        ? (special ? `A timed drill of ${minutes} minutes on these questions. Full mock exams use every question type.`
          : `${minutes} minutes, every objective covered where possible, questions you have not seen first.`)
        : special ? "Picked at random from the matching questions." : "Open mistakes, due reviews and your weakest objectives come first.");
    $("#start-quiz").disabled = !pool;
    $("#start-quiz").textContent = state.mode === "exam" ? "Start timed exam" : "Start practice";
  };
  $$("[data-mode]", main).forEach(b => b.addEventListener("click", () => { state.mode = b.dataset.mode; sync(); }));
  $$("#topic-chips .chip").forEach(b => b.addEventListener("click", () => {
    const t = b.dataset.t;
    state.topics = state.topics.includes(t) ? state.topics.filter(x => x !== t) : [...state.topics, t];
    sync();
  }));
  $("#all-topics").addEventListener("click", () => { state.topics = Object.keys(C.topics); sync(); });
  $("#no-topics").addEventListener("click", () => { state.topics = []; sync(); });
  $$("[data-count]", main).forEach(b => b.addEventListener("click", () => { state.count = Number(b.dataset.count); sync(); }));
  $$("[data-qtype]", main).forEach(b => b.addEventListener("click", () => { state.qtype = b.dataset.qtype; sync(); }));
  $("#unseen-only").addEventListener("change", e => { state.unseen = e.target.checked; sync(); });
  $("#start-quiz").addEventListener("click", () => {
    store("quiz-setup", state);
    const special = state.qtype !== "all" || state.unseen;
    const n = Math.min(state.count, filtered().length);
    if (special) {
      const ids = shuffle(filtered().map(q => q.id)).slice(0, n);
      if (state.mode === "exam") return startMock({ ids, minutes: Math.ceil(n * 1.9) });
      return startQuiz({ mode: "practice", ids });
    }
    startQuiz({ mode: state.mode, topics: state.topics, count: state.count, minutes: state.mode === "exam" ? Math.ceil(n * 1.9) : null });
  });
  sync();
}

function navigatorHtml(current) {
  return `<section class="navigator" aria-label="Question navigator">
    <div class="qgrid">${quiz.items.map((qid, n) =>
      `<button data-go="${n}" class="${n === current ? "current" : ""} ${quiz.answers[qid]?.length ? "answered" : ""} ${quiz.flags[qid] ? "flagged" : ""}"
        aria-label="Question ${n + 1}${quiz.answers[qid]?.length ? ", answered" : ""}${quiz.flags[qid] ? ", flagged" : ""}"${n === current ? ` aria-current="true"` : ""}>${n + 1}</button>`).join("")}</div>
    <p class="qgrid-legend"><span><i class="answered"></i>Answered</span><span><i class="flagged"></i>Flagged</span><span><i></i>Not answered</span></p>
  </section>`;
}

function examBar(extra = "") {
  const answered = quiz.items.filter(id => quiz.answers[id]?.length).length;
  return `<div class="exam-bar">
    <span class="timer" id="timer" role="timer" aria-live="off">${icon("timer")}<span></span></span>
    <span class="muted small">${answered} of ${quiz.items.length} answered</span>
    <span class="spacer"></span>${extra}
  </div>`;
}

function renderQuestion(i, reviewing) {
  const id = quiz.items[i];
  const q = Q[id];
  const multi = q.answer.length > 1;
  const chosen = quiz.answers[id] || [];
  const exam = quiz.mode === "exam" && !reviewing;
  const revealed = reviewing || (quiz.mode === "practice" && quiz.checked[id]);
  const order = quiz.order[id];
  const total = quiz.items.length;
  const canTry = revealed && (q.try_sql || q.code);

  let actions;
  if (reviewing) {
    actions = `<button class="btn secondary" id="back-results">Back to results</button>
      ${i > 0 ? `<button class="btn ghost" id="prev">${icon("prev")}Previous</button>` : ""}
      ${i < total - 1 ? `<button class="btn" id="next">Next${icon("next")}</button>` : ""}`;
  } else if (exam) {
    actions = `${i > 0 ? `<button class="btn ghost" id="prev">${icon("prev")}Previous</button>` : ""}
      <button class="btn secondary" id="flag" aria-pressed="${!!quiz.flags[id]}">${quiz.flags[id] ? "Remove flag" : "Flag for review"}</button>
      ${i < total - 1 ? `<button class="btn" id="next">Next <span class="kbd">Enter</span></button>` : `<button class="btn" id="finish">Review and submit</button>`}`;
  } else if (revealed) {
    actions = `<button class="btn" id="next">${i < total - 1 ? "Next question" : "See results"} <span class="kbd">Enter</span></button>`;
  } else {
    actions = `<div class="confidence" role="group" aria-label="Check your answer: how sure are you?">
      <span>Check: how sure are you?</span>
      ${CONF.map(([k, label, key]) => `<button class="btn secondary" data-conf="${k}" ${chosen.length ? "" : "disabled"}>${label} <span class="kbd">${key}</span></button>`).join("")}
    </div>`;
  }

  main.innerHTML = `
    ${exam ? examBar(`<button class="btn secondary small" id="submit-exam">Submit exam</button>`) : ""}
    <div class="q-top">
      <b>Question ${i + 1} of ${total}</b>
      <span>${esc(topicLabel(q.topic))}</span>
      <span class="spacer"></span>
      ${!reviewing ? `<button class="link-btn quiet small" id="quit">${quiz.mode === "exam" ? "Abandon exam" : "End quiz"}</button>` : ""}
    </div>
    <div class="q-progress" role="progressbar" aria-label="Quiz progress" aria-valuemin="0" aria-valuemax="${total}" aria-valuenow="${i + (revealed ? 1 : 0)}"><i style="width:${((i + (revealed ? 1 : 0)) / total) * 100}%"></i></div>
    ${multi ? `<span class="q-choose">Choose ${q.answer.length}</span>` : ""}
    <p class="q-prompt" id="q-prompt">${inlineCode(q.prompt)}</p>
    ${q.code ? `<pre class="code"><code>${esc(q.code)}</code></pre>` : ""}
    <ul class="options" role="${multi ? "group" : "radiogroup"}" aria-labelledby="q-prompt">
      ${order.map((orig, pos) => {
        let cls = "", mark = "";
        if (revealed) {
          if (q.answer.includes(orig)) { cls = "correct"; mark = chosen.includes(orig) ? "Correct, your answer" : "Correct answer"; }
          else if (chosen.includes(orig)) { cls = "wrong"; mark = "Your answer"; }
        }
        return `<li><label class="option ${multi ? "multi" : ""} ${cls} ${revealed ? "locked" : ""}">
          <input type="${multi ? "checkbox" : "radio"}" name="opt" value="${orig}" ${chosen.includes(orig) ? "checked" : ""} ${revealed ? "disabled" : ""}>
          <span class="letter" aria-hidden="true">${LETTERS[pos]}</span>
          <span class="text">${inlineCode(q.options[orig])}</span>
          ${mark ? `<span class="mark-label">${mark}</span>` : ""}
        </label></li>`;
      }).join("")}
    </ul>
    ${revealed ? verdictHtml(q, chosen) : ""}
    ${exam ? `<div class="confidence" role="group" aria-label="How sure are you? Optional" style="margin-bottom:18px">
      <span>How sure are you? (optional)</span>
      ${CONF.map(([k, label, key]) => `<button class="chip" data-exam-conf="${k}" aria-pressed="${quiz.confidence[id] === k}">${label} <span class="kbd">${key}</span></button>`).join("")}
    </div>` : ""}
    <div class="q-actions">
      ${actions}
      <span class="spacer"></span>
      ${canTry ? (blockedOn23ai(q)
        ? `<span class="small muted" title="Set STUDY_DSN_23AI to run 23ai SQL in the lab">Runs on Oracle 23ai only</span>`
        : `<button class="btn ghost" id="try">Run it in the SQL lab</button>`) : ""}
    </div>
    ${exam ? navigatorHtml(i) : ""}
  `;

  $$("input[name=opt]", main).forEach(inp => inp.addEventListener("change", () => {
    quiz.answers[id] = $$("input[name=opt]:checked", main).map(x => Number(x.value));
    $$("[data-conf]", main).forEach(b => { b.disabled = !quiz.answers[id].length; });
    if (exam) {
      saveMockAnswer(id, { chosen: quiz.answers[id] });
      $$(".qgrid button")[i].classList.toggle("answered", quiz.answers[id].length > 0);
    }
  }));
  $$("[data-conf]", main).forEach(b => b.addEventListener("click", () => checkPractice(id, b.dataset.conf)));
  $$("[data-exam-conf]", main).forEach(b => b.addEventListener("click", () => {
    quiz.confidence[id] = quiz.confidence[id] === b.dataset.examConf ? null : b.dataset.examConf;
    saveMockAnswer(id, { confidence: quiz.confidence[id] });
    $$("[data-exam-conf]", main).forEach(c => c.setAttribute("aria-pressed", quiz.confidence[id] === c.dataset.examConf));
  }));
  $("#next")?.addEventListener("click", () => {
    if (reviewing) { quiz.reviewIdx = i + 1; return render(); }
    if (!exam && i === total - 1) return finishQuiz();
    quiz.idx = i + 1;
    render();
  });
  $("#prev")?.addEventListener("click", () => { if (reviewing) quiz.reviewIdx = i - 1; else quiz.idx = i - 1; render(); });
  $("#flag")?.addEventListener("click", () => { quiz.flags[id] = !quiz.flags[id]; saveMockAnswer(id, { flagged: quiz.flags[id] }); render(); });
  $("#finish")?.addEventListener("click", showReviewScreen);
  $("#submit-exam")?.addEventListener("click", showReviewScreen);
  $("#back-results")?.addEventListener("click", () => { quiz.reviewIdx = null; render(); });
  $("#try")?.addEventListener("click", () => { labDraft(q.try_sql || q.code); go("/lab"); });
  $("#quit")?.addEventListener("click", quit);
  $$("[data-go]", main).forEach(b => b.addEventListener("click", () => { quiz.idx = Number(b.dataset.go); render(); }));

  if (exam) { trackTime(id); startTimer(); }
}

async function quit() {
  if (quiz.mode === "exam") {
    if (!await confirmDialog({
      title: "Abandon this mock exam?",
      body: "It will not be scored, and its questions count as seen.",
      confirm: "Abandon exam", cancel: "Keep going", danger: true,
    })) return;
    trackTime(null);
    api("/api/mock/abandon", { mock_id: quiz.mockId }).then(apply).catch(() => {});
  }
  if (quiz.mode === "practice" && Object.keys(quiz.checked).length) return finishQuiz();
  resetQuiz();
  main.classList.remove("reading");
  render();
}

function verdictHtml(q, chosen) {
  const ok = isCorrect(q, chosen);
  const order = quiz.order[q.id];
  const letters = q.answer.map(a => LETTERS[order.indexOf(a)]).sort().join(" and ");
  const conf = quiz.confidence[q.id];
  const note = ok && conf === "guess"
    ? `You guessed, so this stays on your mistakes list until you answer it confidently on ${P.proof_days} different days.`
    : !ok && conf === "sure" ? "You were sure: that makes this a misconception, the most valuable kind of mistake to fix." : "";
  const title = ok ? (conf === "guess" ? "Correct, but a guess" : "Correct")
    : chosen.length ? `Not quite. The answer is ${letters}.` : `Not answered. The answer is ${letters}.`;
  return `<div class="verdict ${ok ? "good" : "bad"}" role="status">
    <strong>${title}</strong>
    <p>${inlineCode(q.explanation)}</p>
    ${note ? `<p class="small verdict-note">${note}</p>` : ""}
  </div>`;
}

async function checkPractice(id, confidence) {
  const chosen = quiz.answers[id] || [];
  if (!chosen.length) return;
  quiz.checked[id] = true;
  quiz.confidence[id] = confidence;
  render();
  $("#next")?.focus({ preventScroll: true });
  try { apply(await api("/api/attempt", { id, chosen, confidence, mode: "practice" })); refreshNav(); }
  catch { toastError("Could not save this answer. Check that the server is running."); }
}

function showReviewScreen() {
  // Exam mode: show the review screen before submitting, like the real test.
  trackTime(null);
  quiz.reviewScreen = true;
  render();
  window.scrollTo(0, 0);
}

function renderMockReview() {
  const open = quiz.items.map((id, n) => [id, n]).filter(([id]) => !(quiz.answers[id] || []).length);
  const flagged = quiz.items.map((id, n) => [id, n]).filter(([id]) => quiz.flags[id]);
  const list = (rows, label) => rows.length
    ? section(label, `<div class="qgrid">${rows.map(([, n]) => `<button data-go="${n}">${n + 1}</button>`).join("")}</div>`) : "";
  main.innerHTML = `
    ${examBar()}
    ${pageHead("Review before submitting", `${quiz.items.length - open.length} of ${quiz.items.length} answered${flagged.length ? `, ${flagged.length} flagged for review` : ""}. ${open.length ? "Unanswered questions score zero, and there is no penalty for guessing." : "Every question has an answer."}`)}
    <div class="row">
      <button class="btn large" id="submit-now">Submit exam</button>
      <button class="btn secondary large" id="back-to-questions">Back to the questions</button>
    </div>
    ${list(open, "Unanswered")}
    ${list(flagged, "Flagged")}
    ${section("All questions", navigatorHtml(-1))}`;
  $$("[data-go]", main).forEach(b => b.addEventListener("click", () => { quiz.reviewScreen = false; quiz.idx = Number(b.dataset.go); render(); }));
  $("#back-to-questions").addEventListener("click", () => { quiz.reviewScreen = false; render(); });
  $("#submit-now").addEventListener("click", finishQuiz);
  startTimer();
}

function startTimer() {
  const tick = () => {
    if (!quiz || !quiz.deadline || quiz.finished) return stopTimer();
    const el = $("#timer");
    const left = Math.max(0, quiz.deadline - Date.now());
    if (el) {
      const m = Math.floor(left / 60000), s = Math.floor((left % 60000) / 1000);
      el.lastElementChild.textContent = `${m}:${String(s).padStart(2, "0")}`;
      el.setAttribute("aria-label", `${m} minutes left`);
      el.classList.toggle("warn", left < 5 * 60000);
    }
    if (left <= 0) { stopTimer(); toast("Time is up. Your exam was submitted."); finishQuiz(); }
  };
  stopTimer();
  tick();
  timerHandle = setInterval(tick, 1000);
}

async function finishQuiz() {
  stopTimer();
  if (quiz.mode === "exam") {
    trackTime(null);
    try {
      const res = await api("/api/mock/submit", { mock_id: quiz.mockId, time_on: quiz.timeOn });
      apply(res);
      quiz.report = res.report;
    } catch {
      toastError("Could not submit the exam. Your answers are saved; try again from Today.");
      return;
    }
    refreshNav();
  }
  quiz.finished = true;
  quiz.reviewIdx = null;
  quiz.elapsed = Date.now() - quiz.started;
  render();
  window.scrollTo(0, 0);
}

/* ---------------------------------------------------------------- results */

function reviewGrid(ok) {
  return `<div class="qgrid">${quiz.items.map((id, n) => {
    if (quiz.mode === "practice" && !quiz.checked[id]) return "";
    const good = ok(id);
    return `<button data-review="${n}" class="${good ? "good" : "bad"}" aria-label="Question ${n + 1}, ${good ? "correct" : "incorrect"}">${n + 1}</button>`;
  }).join("")}</div>`;
}

function bindResults(retryIds) {
  $$("[data-review]", main).forEach(b => b.addEventListener("click", () => { quiz.reviewIdx = Number(b.dataset.review); render(); window.scrollTo(0, 0); }));
  $("#again").addEventListener("click", () => { resetQuiz(); main.classList.remove("reading"); render(); });
  $("#retry-wrong")?.addEventListener("click", () => startQuiz({ mode: "practice", ids: retryIds }));
}

function renderResults() {
  if (quiz.mode === "exam") return renderMockResults(quiz.report);
  const items = quiz.items.filter(id => quiz.checked[id]);
  const right = items.filter(id => isCorrect(Q[id], quiz.answers[id])).length;
  const pct = items.length ? Math.round((right / items.length) * 100) : 0;
  const byTopic = {};
  for (const id of items) {
    const t = Q[id].topic;
    byTopic[t] = byTopic[t] || { n: 0, ok: 0 };
    byTopic[t].n++;
    if (isCorrect(Q[id], quiz.answers[id])) byTopic[t].ok++;
  }
  const minutes = Math.max(1, Math.round(quiz.elapsed / 60000));
  const byConfidence = CONF.map(([k, label]) => {
    const ids = items.filter(id => quiz.confidence[id] === k);
    return ids.length ? `<tr><td>${label}</td><td>${meter(ids.filter(id => isCorrect(Q[id], quiz.answers[id])).length, ids.length, "Correct")}</td></tr>` : "";
  }).join("");
  const wrong = items.filter(id => !isCorrect(Q[id], quiz.answers[id]));
  main.innerHTML = `
    ${pageHead("Practice results")}
    <div class="score"><b>${pct}%</b><div><strong>${right} of ${items.length} correct</strong><span>in about ${plural(minutes, "minute")}. Answers you missed or guessed are on your mistakes list.</span></div></div>
    <div class="row" style="margin-top:18px">
      ${wrong.length ? `<button class="btn" id="retry-wrong">Retry the ${wrong.length} I missed</button>` : ""}
      <button class="btn ${wrong.length ? "secondary" : ""}" id="again">New quiz</button>
    </div>
    <div class="result-grid section">
      <section><h2>By topic</h2><div class="table-wrap"><table class="data"><tbody>
        ${Object.entries(byTopic).sort((a, b) => a[0].localeCompare(b[0])).map(([t, s]) =>
          `<tr><td>${esc(topicLabel(t))}</td><td>${meter(s.ok, s.n, "Correct")}</td></tr>`).join("")}
      </tbody></table></div></section>
      ${byConfidence ? `<section><h2>By confidence</h2><div class="table-wrap"><table class="data"><tbody>${byConfidence}</tbody></table></div></section>` : ""}
    </div>
    ${section("Review answers", reviewGrid(id => isCorrect(Q[id], quiz.answers[id])), { aside: "Select a question to see its explanation." })}`;
  bindResults(wrong);
}

function renderMockResults(r) {
  const fresh = r.fresh[1] ? Math.round((r.fresh[0] / r.fresh[1]) * 100) : null;
  const seen = r.score[1] - r.fresh[1];
  const changed = r.changes.right_to_wrong.length + r.changes.wrong_to_right.length + r.changes.wrong_to_wrong.length;
  const n = id => quiz.items.indexOf(id);
  const qButtons = ids => ids.map(id => `<button class="link-btn" data-review="${n(id)}">${n(id) + 1}</button>`).join(", ");
  const duration = s => s >= 60 ? `${Math.floor(s / 60)} min ${Math.round(s % 60)} s` : `${Math.round(s)} s`;
  const missed = quiz.items.filter(id => !r.right.includes(id));
  const table = rows => `<div class="table-wrap"><table class="data"><tbody>${rows}</tbody></table></div>`;

  main.innerHTML = `
    ${pageHead(r.full ? "Mock exam results" : "Timed set results")}
    <div class="score ${r.passed ? "pass" : "fail"}"><b>${r.pct}%</b><div>
      <strong>${r.passed ? `Passed: above the ${C.exam.passing_pct}% passing score` : `Below the ${C.exam.passing_pct}% passing score`}</strong>
      <span>${r.score[0]} of ${r.score[1]} correct in ${r.minutes_used} minutes. These are original practice questions, not calibrated to the real exam.</span>
    </div></div>
    <p class="section-note">${seen
      ? `${r.fresh[1]} of ${r.score[1]} questions were new to you${fresh !== null ? `, and you scored <b>${fresh}%</b> on those` : ""}. The ${seen} you had seen before make the overall score optimistic.`
      : "Every question was new to you, so this score is a clean measurement."}</p>
    <div class="row" style="margin-top:18px">
      ${missed.length ? `<button class="btn" id="retry-wrong">Practise the ${missed.length} I missed</button>` : ""}
      <button class="btn ${missed.length ? "secondary" : ""}" id="again">New quiz</button>
    </div>

    <div class="result-grid section">
      <section><h2>By exam section</h2>${table(Object.entries(r.by_section).map(([sec, [ok, total]]) =>
        `<tr><td>${sec}. ${esc(C.sections[sec])}</td><td>${meter(ok, total, "Correct")}</td></tr>`).join(""))}</section>
      <section><h2>Question types</h2>${table(`
        <tr><td>Single answer</td><td>${meter(r.single[0], r.single[1], "Correct")}</td></tr>
        <tr><td>Multiple answers</td><td>${meter(r.multi[0], r.multi[1], "Correct")}</td></tr>`)}
        ${r.multi[1] && r.single[1] && r.multi[0] / r.multi[1] < r.single[0] / r.single[1] - 0.15
          ? `<p class="section-note">Multiple-answer questions score all or nothing. Read every option before choosing, and check you picked exactly as many as asked.</p>` : ""}
        ${Object.values(r.confidence).some(([, total]) => total) ? `<h2 style="margin-top:28px">By confidence</h2>${table(
          CONF.map(([k, label]) => r.confidence[k][1] ? `<tr><td>${label}</td><td>${meter(r.confidence[k][0], r.confidence[k][1], "Correct", k !== "sure")}</td></tr>` : "").join(""))}` : ""}
      </section>
    </div>

    ${section("Changed answers", changed ? `${table(`
      <tr><td>Right to wrong</td><td class="num">${r.changes.right_to_wrong.length}</td><td>${qButtons(r.changes.right_to_wrong)}</td></tr>
      <tr><td>Wrong to right</td><td class="num">${r.changes.wrong_to_right.length}</td><td>${qButtons(r.changes.wrong_to_right)}</td></tr>
      <tr><td>Wrong to wrong</td><td class="num">${r.changes.wrong_to_wrong.length}</td><td>${qButtons(r.changes.wrong_to_wrong)}</td></tr>`)}
      <p class="section-note">${r.changes.right_to_wrong.length > r.changes.wrong_to_right.length
        ? "Changing answers cost you points this time. Change an answer only when you find a concrete reason, not a feeling."
        : "Your second thoughts helped or did no harm this time."}</p>`
      : `<p class="muted">You did not change any answers.</p>`)}

    ${section("Time", `<p>${r.minutes_used} of ${r.minutes} minutes used. Target pace: ${duration(r.pace_seconds)} per question.</p>
      ${r.slowest.length ? `<div class="table-wrap"><table class="data"><thead><tr><th>Slowest questions</th><th class="num">Time</th><th>Result</th></tr></thead><tbody>
        ${r.slowest.map(id => `<tr><td><button class="link-btn" data-review="${n(id)}">Question ${n(id) + 1}</button> <span class="muted small">${esc(C.objectives[Q[id].objective])}</span></td>
          <td class="num">${duration(r.time_on[id])}</td><td>${r.right.includes(id) ? `<span class="level level-strong">Correct</span>` : `<span class="level level-weak">Wrong</span>`}</td></tr>`).join("")}
      </tbody></table></div>` : ""}`)}

    ${section("Readiness after this exam", readinessHtml(P.readiness))}
    ${section("Review answers", reviewGrid(id => r.right.includes(id)), { aside: "Select a question to see its explanation." })}`;
  bindResults(missed);
}

/* ---------------------------------------------------------------- keyboard */

function onKey(e) {
  if (!quiz || quiz.finished || quiz.reviewScreen) return;
  const n = Number(e.key);
  if (n >= 1 && n <= 8) {
    const inp = $$("input[name=opt]", main)[n - 1];
    if (inp && !inp.disabled) {
      inp.checked = inp.type === "checkbox" ? !inp.checked : true;
      inp.dispatchEvent(new Event("change"));
    }
  } else if (["s", "t", "g"].includes(e.key.toLowerCase())) {
    const conf = CONF.find(c => c[2].toLowerCase() === e.key.toLowerCase())[0];
    $(`[data-conf="${conf}"]:not([disabled])`, main)?.click();
    $(`[data-exam-conf="${conf}"]`, main)?.click();
  } else if (e.key === "Enter" && e.target.tagName !== "BUTTON") {
    e.preventDefault();
    const next = $("#next") || $("#finish");
    if (next) next.click();
    else if ($("[data-conf]:not([disabled])", main)) toast("Choose how sure you are: S, T or G.");
  }
}

export const quizView = {
  title: "Quiz",
  render,
  onKey,
  leave() { stopTimer(); if (quiz?.mode === "exam" && !quiz.finished) trackTime(null); },
};

/** /mock/<id>: the report of a finished mock exam. */
export const mockView = {
  title: "Mock exam report",
  async render(id) {
    const res = await api("/api/mock?id=" + encodeURIComponent(id));
    if (!res.report) return go("/progress");
    quiz = mockQuiz(res.mock);
    quiz.finished = true;
    quiz.report = res.report;
    go("/quiz");
  },
};
