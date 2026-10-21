/* Quiz: setup, practice questions with confidence (kept in this browser, so a reload resumes
   them), timed mock exams (kept on the server, so a reload resumes them), results and mock reports. */

import { $, $$, esc, inlineCode, plural, shuffle, icon, LETTERS } from "../core/dom.js";
import { api } from "../core/api.js";
import { store, forget } from "../core/store.js";
import { C, S, P, Q, CARD, apply, topicLabel, needsNewerDb, mistakes, sqlOff, NO_SQL, todayLeft } from "../core/state.js";
import { main, go, currentView, setLeaveGuard } from "../core/router.js";
import { toast, clearToast, toastError, confirmDialog, closeDialogs } from "../ui/feedback.js";
import { meter, pageHead, section } from "../ui/widgets.js";
import { readinessHtml } from "../ui/charts.js";
import { refreshNav } from "../shell.js";
import { labDraft } from "./lab.js";
import { openDeck } from "./cards.js";

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

/** Drops the quiz in memory. The practice session stored in this browser goes with it only when
    that quiz is a practice session, or when `forgetPractice` (the exam track changed). */
export function resetQuiz({ forgetPractice = false } = {}) {
  stopTimer();
  if (forgetPractice || quiz?.mode === "practice") clearSession();
  quiz = null;
  setExamMode(false);
}

function stopTimer() { clearInterval(timerHandle); timerHandle = null; }

/** How many options the question asks for, and whether a selection has exactly that many. */
const requiredCount = q => q.answer.length;
const isComplete = (q, chosen) => (chosen || []).length === requiredCount(q);

/** "D", "D and E", "D, E and F". */
function joinLetters(letters) {
  return letters.length < 2 ? letters.join("") : `${letters.slice(0, -1).join(", ")} and ${letters.at(-1)}`;
}

function isCorrect(q, chosen) {
  return [...q.answer].sort().join(",") === [...(chosen || [])].sort().join(",");
}

/** The toast asking for a complete selection; clearing it leaves other messages alone. */
const CHOOSE_TOAST = "choose-n";

/* ---------------------------------------------------------------- practice session

   A practice session is kept in this browser (per account), so a reload resumes it. Its items are
   question ids in play order, plus `{id, second: true}` entries for second tries: a question
   missed (or guessed) comes back SECOND_TRY_GAP places later, once per session, with its options
   shuffled again. A second try keeps its own order, answer and confidence in `seconds[id]`, so
   the first answer, which the score counts, stays as it was. */

const SESSION_KEY = "practice-session";
const SESSION_MAX_AGE = 24 * 3600 * 1000;
const SECOND_TRY_GAP = 5;

const idOf = entry => typeof entry === "string" ? entry : entry.id;
const isSecond = entry => typeof entry === "object" && !!entry?.second;

/** Order, answer, check and confidence of one entry of the sequence. */
function slot(entry) {
  const id = idOf(entry);
  if (isSecond(entry)) return quiz.seconds[id];
  return { order: quiz.order[id], chosen: quiz.answers[id] || [], checked: !!quiz.checked[id], confidence: quiz.confidence[id] };
}

function setChosen(entry, chosen) {
  if (isSecond(entry)) quiz.seconds[idOf(entry)].chosen = chosen;
  else quiz.answers[idOf(entry)] = chosen;
}

/** The original questions: second tries do not count toward "x of N". */
const firstCount = () => quiz.items.filter(e => !isSecond(e)).length;
/** 1-based place of entry i among the original questions; a second try gets the one before it. */
const placeOf = i => quiz.items.slice(0, i + 1).filter(e => !isSecond(e)).length;

const openMistake = id => mistakes().some(m => m.id === id);

function saveSession() {
  if (!quiz || quiz.mode !== "practice" || quiz.finished) return;
  const { fromToday, items, order, idx, answers, checked, confidence, retried, seconds, started } = quiz;
  store(SESSION_KEY, { v: 1, saved: Date.now(), fromToday, items, order, idx, answers, checked, confidence, retried, seconds, started });
}

function clearSession() { forget(SESSION_KEY); }

/** The stored session, or null when there is none, it is older than 24 h, or the questions changed. */
function loadSession() {
  const s = store(SESSION_KEY);
  if (!s) return null;
  let valid = false;
  try {
    const fits = (id, order) => Q[id] && Array.isArray(order) && order.length === Q[id].options.length;
    const ticks = chosen => chosen === undefined || chosen === null || (Array.isArray(chosen) && chosen.every(Number.isInteger));
    const age = Date.now() - s.saved;
    // A save more than 5 minutes "in the future" means a wrong clock or a forged entry.
    valid = s.v === 1 && typeof s.saved === "number" && age < SESSION_MAX_AGE && age > -5 * 60000 && s.items.length > 0
      && s.items.every(e => isSecond(e)
        ? fits(e.id, s.seconds[e.id].order) && ticks(s.seconds[e.id].chosen) && typeof s.seconds[e.id].checked === "boolean"
        : typeof e === "string" && fits(e, s.order[e]) && ticks(s.answers?.[e]))
      && Number.isInteger(s.idx) && s.idx >= 0 && s.idx < s.items.length;
  } catch { /* malformed: discarded below */ }
  if (!valid) { clearSession(); return null; }
  return s;
}

function sessionQuiz(s) {
  return {
    mode: "practice", items: s.items, order: s.order, idx: s.idx, answers: s.answers || {}, checked: s.checked || {},
    confidence: s.confidence || {}, retried: s.retried || {}, seconds: s.seconds || {}, flags: {},
    fromToday: !!s.fromToday, started: s.started || s.saved, deadline: null, finished: false, reviewIdx: null,
  };
}

/** Today's "Resume practice (k of N)": answered and total original questions, their ids, whether Today started it, or null. */
export function practiceSession() {
  const s = loadSession();
  if (!s) return null;
  const firsts = s.items.filter(e => !isSecond(e));
  return { answered: firsts.filter(id => s.checked?.[id]).length, total: firsts.length, ids: firsts, fromToday: !!s.fromToday };
}

export function resumePractice() {
  const s = loadSession();
  if (s) { stopTimer(); quiz = sessionQuiz(s); }
  go("/quiz");
}

/** Brings a missed question back SECOND_TRY_GAP places after entry i (or last), its options reshuffled. */
function queueSecondTry(i) {
  const id = idOf(quiz.items[i]);
  quiz.retried[id] = true;
  const first = quiz.order[id];
  let order = shuffle(first);
  for (let n = 0; n < 5 && order.join() === first.join(); n++) order = shuffle(first);
  quiz.seconds[id] = { order, chosen: [], checked: false, confidence: null };
  quiz.items.splice(Math.min(i + SECOND_TRY_GAP, quiz.items.length), 0, { id, second: true });
}

/* ---------------------------------------------------------------- starting */

export async function startQuiz({ mode, topics, count, minutes, ids, keepOrder, fromToday = false }) {
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
    mode, items, order, idx: 0, answers: {}, checked: {}, flags: {}, confidence: {}, retried: {}, seconds: {},
    fromToday, started: Date.now(), deadline: null, finished: false, reviewIdx: null,
  };
  saveSession();
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

/** Today's "Resume your mock exam": /quiz reopens the running mock (the one in memory when it is
    the same, so its option order stays; otherwise loaded from the server in render()). */
export function resumeMock() {
  if (!(quiz?.mode === "exam" && !quiz.finished && quiz.mockId === P.active_mock?.id)) quiz = null;
  go("/quiz");
}

/** Where a mock opens: the stored position, else the first unanswered question, else the review screen. */
function resumePoint(mock, answers) {
  const p = mock.position;
  if (Number.isInteger(p) && p >= 0 && p < mock.items.length) return { idx: p, reviewScreen: false };
  const open = mock.items.findIndex(id => !(answers[id] || []).length);
  return open >= 0 ? { idx: open, reviewScreen: false } : { idx: 0, reviewScreen: true };
}

function mockQuiz(mock) {
  const order = {};
  for (const id of mock.items) order[id] = shuffle(Q[id].options.map((_, i) => i));
  const pick = key => Object.fromEntries(Object.entries(mock.answers).map(([id, a]) => [id, a[key]]));
  const answers = pick("chosen");
  return {
    mode: "exam", mockId: mock.id, items: mock.items, order, checked: {},
    answers, confidence: pick("confidence"), flags: pick("flagged"), ...resumePoint(mock, answers),
    timeOn: { ...mock.time_on }, shownId: null, shownAt: null,
    started: mock.started * 1000, deadline: (mock.started + mock.minutes * 60) * 1000,
    finished: false, reviewIdx: null, report: null, submitting: false,
    savedPosition: Number.isInteger(mock.position) ? mock.position : null, pendingPosition: null, positionTimer: null, positionAt: 0,
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

/** Every answer save also stores the question the learner is on. */
function saveMockAnswer(id, change) {
  quiz.savedPosition = quiz.idx;
  api("/api/mock/answer", { mock_id: quiz.mockId, id, position: quiz.idx, time_on: quiz.timeOn, ...change })
    .catch(() => toastError("Could not save your answer. Check that the server is running."));
}

/* Moving between questions without answering saves the position too, at most once per
   POSITION_GAP: the latest position wins, and Leave, Review and Submit send it at once. */
const POSITION_GAP = 2000;

function savePosition(i) {
  const q = quiz;
  q.pendingPosition = i;
  if (q.positionTimer) return;
  q.positionTimer = setTimeout(() => sendPosition(q), Math.max(0, q.positionAt + POSITION_GAP - Date.now()));
}

/** Sends the pending position now; `force` sends even without one, so time_on reaches the server. */
function sendPosition(q = quiz, force = false) {
  if (!q || q.mode !== "exam") return Promise.resolve();
  clearTimeout(q.positionTimer);
  q.positionTimer = null;
  const position = q.pendingPosition;
  q.pendingPosition = null;
  if (q.finished || (!force && (position === null || position === q.savedPosition))) return Promise.resolve();
  q.positionAt = Date.now();
  if (position !== null) q.savedPosition = position;
  // A position that did not save only costs the place on resume; no message for it.
  return api("/api/mock/answer", { mock_id: q.mockId, time_on: q.timeOn, ...(position !== null ? { position } : {}) })
    .catch(() => {});
}

/* ---------------------------------------------------------------- exam mode

   While a mock is open and unsubmitted, the rail and top bar are hidden, the router asks before
   leaving /quiz, and closing or reloading the tab asks the browser's own question. */

let examMode = false;

function onBeforeUnload(e) {
  e.preventDefault();
  e.returnValue = "";
}

function setExamMode(on) {
  if (on === examMode) return;
  examMode = on;
  document.body.classList.toggle("exam-mode", on);
  setLeaveGuard(on ? guardLeave : null);
  if (on) window.addEventListener("beforeunload", onBeforeUnload);
  else window.removeEventListener("beforeunload", onBeforeUnload);
}

const LEAVE = {
  title: "Leave the exam? The timer keeps running.",
  body: "Your answers are saved. Resume it from Today.",
  confirm: "Leave", cancel: "Stay in the exam", focus: "cancel",
};

/** The router's leave guard: true lets the navigation go on (leave() then turns exam mode off). */
async function guardLeave() {
  if (quiz?.submitting) return false;  // the results are on their way
  if (!await confirmDialog(LEAVE) || quiz?.submitting) return false;
  if (quiz?.mode === "exam" && !quiz.finished) { trackTime(null); await sendPosition(quiz, true); }
  return true;
}

/** The exam bar's Leave: the mock keeps running, and Today offers to resume it. */
async function leaveExam() {
  if (quiz?.submitting) return;
  if (!await confirmDialog(LEAVE)) return;
  if (!quiz || quiz.finished || quiz.submitting) return;
  stopTimer();
  trackTime(null);
  await sendPosition(quiz, true);
  setExamMode(false);
  go("/");
}

/** Question ids with no ticks, and with some ticks but fewer than asked for. */
function openAnswers() {
  const ticks = id => (quiz.answers[id] || []).length;
  return {
    unanswered: quiz.items.filter(id => !ticks(id)),
    incomplete: quiz.items.filter(id => ticks(id) && !isComplete(Q[id], quiz.answers[id])),
  };
}

async function confirmSubmit() {
  const { unanswered, incomplete } = openAnswers();
  const body = unanswered.length || incomplete.length
    ? `Unanswered: ${unanswered.length}. Incomplete (fewer options ticked than asked for): ${incomplete.length}. Both score zero, and answers cannot be changed after submitting.`
    : "Every question has a complete answer. Answers cannot be changed after submitting.";
  if (!await confirmDialog({ title: "Submit the exam?", body, confirm: "Submit exam", cancel: "Keep working", focus: "cancel" })) return;
  if (currentView() !== "quiz") return;  // the learner left the exam while the question was open
  if (quiz?.mode === "exam" && !quiz.finished) finishQuiz();
}

/* ---------------------------------------------------------------- view */

async function render() {
  // A running mock exam reopens first; otherwise a practice session stored in this browser resumes.
  if (!quiz && P.active_mock) {
    try {
      const { mock } = await api("/api/mock?id=" + encodeURIComponent(P.active_mock.id));
      if (currentView() !== "quiz") return;  // the learner moved on while it loaded
      if (!quiz) quiz = mockQuiz(mock);
    } catch { toastError("Could not load the running mock exam."); }
  }
  if (!quiz && !P.active_mock) { const s = loadSession(); if (s) quiz = sessionQuiz(s); }
  setExamMode(quiz?.mode === "exam" && !quiz.finished);
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
    ${pageHead("Quiz", `Original practice questions written for these exams, not real exam items. Every answer was checked against ${esc(C.engine.label)}.`)}
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

/** "complete", "incomplete" (some ticks, fewer than asked for) or "open" (no ticks). */
function answerState(id) {
  const chosen = quiz.answers[id] || [];
  return !chosen.length ? "open" : isComplete(Q[id], chosen) ? "complete" : "incomplete";
}

const STATE_GLYPH = { complete: "✓", incomplete: "◐", open: "" };

/** One navigator button: the state is a glyph and a word in the label, not only a colour. */
function qButton(qid, n, current) {
  const state = answerState(qid);
  const flag = !!quiz.flags[qid];
  const label = `Question ${n + 1}${state === "complete" ? ", answered" : state === "incomplete" ? ", incomplete" : ""}${flag ? ", flagged" : ""}`;
  return `<button data-go="${n}" class="${n === current ? "current" : ""} ${state === "complete" ? "answered" : state === "incomplete" ? "incomplete" : ""} ${flag ? "flagged" : ""}"
    aria-label="${label}"${n === current ? ` aria-current="true"` : ""}>${n + 1}<span class="qmark" aria-hidden="true">${STATE_GLYPH[state]}</span>${flag ? `<span class="qflag" aria-hidden="true">⚑</span>` : ""}</button>`;
}

function navigatorHtml(current) {
  return `<section class="navigator" aria-label="Question navigator">
    <div class="qgrid">${quiz.items.map((qid, n) => qButton(qid, n, current)).join("")}</div>
    <p class="qgrid-legend"><span><b aria-hidden="true">✓</b>Answered</span><span><b aria-hidden="true">◐</b>Incomplete</span><span><b aria-hidden="true">⚑</b>Flagged</span><span><b aria-hidden="true">·</b>Not answered</span></p>
  </section>`;
}

/** Redraws the navigator in place after an answer changes, keeping focus on the options. */
function refreshNavigator(current) {
  const nav = $(".navigator", main);
  if (!nav) return;
  nav.outerHTML = navigatorHtml(current);
  bindGo();
}

function bindGo() {
  $$("[data-go]", main).forEach(b => b.addEventListener("click", () => { quiz.reviewScreen = false; quiz.idx = Number(b.dataset.go); render(); }));
}

/** The slim bar of a running mock; `i` is the question shown, or null on the review screen. */
function examBar(i) {
  const id = i === null ? null : quiz.items[i];
  return `<div class="exam-bar">
    <span class="exam-code">${esc(C.exam.code)}</span>
    <span class="timer" id="timer" role="timer" aria-live="off">${icon("timer")}<span></span></span>
    <span class="exam-where">${i === null ? "Review" : `Question ${i + 1} of ${quiz.items.length}`}</span>
    <span class="spacer"></span>
    <span class="exam-tools">
      ${i === null ? "" : `<button class="btn ghost small" id="bar-flag" aria-pressed="${!!quiz.flags[id]}"><span aria-hidden="true">⚑</span> Flag</button>
      <button class="btn ghost small" id="bar-review">Review</button>`}
      <button class="btn ghost small" id="bar-leave">Leave</button>
      <button class="btn small" id="bar-submit">Submit</button>
    </span>
  </div>`;
}

function bindExamBar(i) {
  $("#bar-flag")?.addEventListener("click", () => {
    const id = quiz.items[i];
    quiz.flags[id] = !quiz.flags[id];
    saveMockAnswer(id, { flagged: quiz.flags[id] });
    render();
    $("#bar-flag")?.focus();
  });
  $("#bar-review")?.addEventListener("click", showReviewScreen);
  $("#bar-leave").addEventListener("click", leaveExam);
  $("#bar-submit").addEventListener("click", confirmSubmit);
}

function renderQuestion(i, reviewing) {
  const entry = quiz.items[i];
  const id = idOf(entry);
  const second = isSecond(entry);
  const q = Q[id];
  const multi = q.answer.length > 1;
  const { order, chosen = [], checked, confidence } = slot(entry);
  const exam = quiz.mode === "exam" && !reviewing;
  const revealed = reviewing || (quiz.mode === "practice" && checked);
  const total = quiz.items.length;
  const firsts = firstCount();
  const done = placeOf(i) - (revealed || second ? 0 : 1);
  const canTry = revealed && (q.try_sql || q.code);

  let actions;
  if (reviewing) {
    actions = `<button class="btn secondary" id="back-results">Back to results</button>
      ${i > 0 ? `<button class="btn ghost" id="prev">${icon("prev")}Previous</button>` : ""}
      ${i < total - 1 ? `<button class="btn" id="next">Next${icon("next")}</button>` : ""}`;
  } else if (exam) {
    actions = `${i > 0 ? `<button class="btn ghost" id="prev">${icon("prev")}Previous</button>` : ""}
      ${i < total - 1 ? `<button class="btn" id="next">Next <span class="kbd">Enter</span></button>` : `<button class="btn" id="finish">Review and submit</button>`}`;
  } else if (revealed) {
    actions = `<button class="btn" id="next">${i < total - 1 ? "Next question" : "See results"} <span class="kbd">Enter</span></button>`;
  } else {
    actions = `<div class="confidence" role="group" aria-label="Check your answer: how sure are you?">
      <span>Check: how sure are you?</span>
      ${CONF.map(([k, label, key]) => `<button class="btn secondary" data-conf="${k}" ${isComplete(q, chosen) ? "" : "disabled"}>${label} <span class="kbd">${key}</span></button>`).join("")}
    </div>`;
  }

  main.innerHTML = `
    ${exam ? examBar(i) : ""}
    <div class="q-top">
      ${exam ? "" : `<b>${second ? "Second try" : `Question ${placeOf(i)} of ${firsts}`}</b>`}
      <span>${esc(topicLabel(q.topic))}</span>
      <span class="spacer"></span>
      ${!reviewing && !exam ? `<button class="link-btn quiet small" id="quit">End quiz</button>` : ""}
    </div>
    <div class="q-progress" role="progressbar" aria-label="Quiz progress" aria-valuemin="0" aria-valuemax="${firsts}" aria-valuenow="${done}"><i style="width:${(done / firsts) * 100}%"></i></div>
    ${multi ? `<span class="q-choose">Choose ${q.answer.length}</span>` : ""}
    <p class="q-prompt" id="q-prompt">${inlineCode(q.prompt)}</p>
    ${q.code ? `<pre class="code"><code>${esc(q.code)}</code></pre>` : ""}
    ${multi && !revealed ? `<p class="q-count small" id="q-count" aria-live="polite">${chosen.length} of ${requiredCount(q)} selected</p>` : ""}
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
    ${revealed ? verdictHtml(q, chosen, order, confidence, second) : ""}
    ${exam ? `<div class="confidence" role="group" aria-label="How sure are you? Optional" style="margin-bottom:18px">
      <span>How sure are you? (optional)</span>
      ${CONF.map(([k, label, key]) => `<button class="chip" data-exam-conf="${k}" aria-pressed="${quiz.confidence[id] === k}">${label} <span class="kbd">${key}</span></button>`).join("")}
    </div>` : ""}
    <div class="q-actions">
      ${actions}
      <span class="spacer"></span>
      ${canTry ? (sqlOff()
        ? `<span class="small muted">${NO_SQL}</span><button class="btn ghost" disabled>Run it in the SQL lab</button>`
        : needsNewerDb(q)
        ? `<span class="small muted" title="${esc(C.exam.code)}'s SQL features need ${esc(q.needs.label)}, which this server does not provide.">Runs on ${esc(q.needs.label)} only</span>`
        : `<button class="btn ghost" id="try">Run it in the SQL lab</button>`) : ""}
    </div>
    ${exam ? navigatorHtml(i) : ""}
  `;

  $$("input[name=opt]", main).forEach(inp => inp.addEventListener("change", () => {
    // Like the real exam: a tick beyond the number asked for is refused.
    if (inp.checked && inp.type === "checkbox" && $$("input[name=opt]:checked", main).length > requiredCount(q)) {
      inp.checked = false;
      const count = $("#q-count");
      if (count) {
        // Said, not only shown: the live counter announces why the tick did not take.
        count.textContent = `${requiredCount(q)} of ${requiredCount(q)} selected — untick one first`;
        count.classList.remove("pulse"); void count.offsetWidth; count.classList.add("pulse");
      }
      return;
    }
    const now = $$("input[name=opt]:checked", main).map(x => Number(x.value));
    setChosen(entry, now);
    $$("[data-conf]", main).forEach(b => { b.disabled = !isComplete(q, now); });
    if (isComplete(q, now)) clearToast(CHOOSE_TOAST);
    const count = $("#q-count");
    if (count) count.textContent = `${now.length} of ${requiredCount(q)} selected`;
    saveSession();
    if (exam) {
      saveMockAnswer(id, { chosen: quiz.answers[id] });
      refreshNavigator(i);
    }
  }));
  $$("[data-conf]", main).forEach(b => b.addEventListener("click", () => checkPractice(i, b.dataset.conf)));
  $$("[data-exam-conf]", main).forEach(b => b.addEventListener("click", () => {
    quiz.confidence[id] = quiz.confidence[id] === b.dataset.examConf ? null : b.dataset.examConf;
    saveMockAnswer(id, { confidence: quiz.confidence[id] });
    $$("[data-exam-conf]", main).forEach(c => c.setAttribute("aria-pressed", quiz.confidence[id] === c.dataset.examConf));
  }));
  $("#next")?.addEventListener("click", () => {
    if (reviewing) { quiz.reviewIdx = i + 1; return render(); }
    if (!exam && i === total - 1) return finishQuiz();
    quiz.idx = i + 1;
    saveSession();
    render();
  });
  $("#prev")?.addEventListener("click", () => { if (reviewing) quiz.reviewIdx = i - 1; else quiz.idx = i - 1; render(); });
  $("#finish")?.addEventListener("click", showReviewScreen);
  $("#back-results")?.addEventListener("click", () => { quiz.reviewIdx = null; render(); });
  $("#try")?.addEventListener("click", () => { labDraft(q.try_sql || q.code); go("/lab"); });
  $("#quit")?.addEventListener("click", quit);
  bindGo();

  if (exam) { bindExamBar(i); trackTime(id); savePosition(i); startTimer(); }
}

async function quit() {
  if (quiz.mode === "exam") {
    if (!await confirmDialog({
      title: "Abandon this mock exam?",
      body: "It will not be scored, and its questions count as seen.",
      confirm: "Abandon exam", cancel: "Keep going", danger: true,
    })) return;
    if (!quiz || quiz.finished) return;  // time ran out while the question was open
    stopTimer();
    trackTime(null);
    // Wait for the server, so the next render does not reopen the mock it still reports as running.
    try { apply(await api("/api/mock/abandon", { mock_id: quiz.mockId })); }
    catch { toastError("Could not abandon the mock exam. Check that the server is running."); startTimer(); return; }
  }
  if (quiz.mode === "practice" && Object.keys(quiz.checked).length) return finishQuiz();
  resetQuiz();
  main.classList.remove("reading");
  render();
}

function verdictHtml(q, chosen, order, conf, second) {
  const ok = isCorrect(q, chosen);
  const letters = joinLetters(q.answer.map(a => LETTERS[order.indexOf(a)]).sort());
  // A right second try cannot clear a mistake: the proof needs another day. That line replaces
  // the usual note while the question is an open mistake; checkPractice swaps them once the
  // server has the answer.
  const secondTry = second && ok;
  const open = secondTry && openMistake(q.id);
  const note = ok && conf === "guess"
    ? `You guessed, so this stays on your mistakes list until you answer it confidently on ${P.proof_days} different days.`
    : !ok && conf === "sure" ? "You were sure: that makes this a misconception, the most valuable kind of mistake to fix." : "";
  const title = ok ? (conf === "guess" ? "Correct, but a guess" : "Correct")
    : chosen.length ? `Not quite. The answer is ${letters}.` : `Not answered. The answer is ${letters}.`;
  return `<div class="verdict ${ok ? "good" : "bad"}" role="status">
    <strong>${title}</strong>
    <p>${inlineCode(q.explanation)}</p>
    ${note ? `<p class="small verdict-note" id="usual-note" ${open ? "hidden" : ""}>${note}</p>` : ""}
    ${secondTry ? `<p class="small verdict-note" id="second-note" ${open ? "" : "hidden"}>Right this time. It stays in your mistakes until you get it right on another day.</p>` : ""}
  </div>`;
}

async function checkPractice(i, confidence) {
  const entry = quiz.items[i];
  const id = idOf(entry);
  const chosen = slot(entry).chosen || [];
  if (!isComplete(Q[id], chosen)) return;
  clearToast(CHOOSE_TOAST);
  if (isSecond(entry)) Object.assign(quiz.seconds[id], { checked: true, confidence });
  else {
    quiz.checked[id] = true;
    quiz.confidence[id] = confidence;
    if ((!isCorrect(Q[id], chosen) || confidence === "guess") && !quiz.retried[id]) queueSecondTry(i);
  }
  saveSession();
  render();
  $("#next")?.focus({ preventScroll: true });
  // A second try is recorded like any other answer.
  try { apply(await api("/api/attempt", { id, chosen, confidence, mode: "practice" })); refreshNav(); }
  catch { toastError("Could not save this answer. Check that the server is running."); return; }
  const note = $("#second-note");
  if (note && quiz?.items[quiz.idx] === entry) {
    note.hidden = !openMistake(id);
    const usual = $("#usual-note");
    if (usual) usual.hidden = !note.hidden;
  }
}

function showReviewScreen() {
  // Exam mode: show the review screen before submitting, like the real test.
  trackTime(null);
  sendPosition(quiz, true);
  quiz.reviewScreen = true;
  render();
  window.scrollTo(0, 0);
}

function renderMockReview() {
  const { unanswered, incomplete } = openAnswers();
  const flagged = quiz.items.filter(id => quiz.flags[id]);
  const complete = quiz.items.length - unanswered.length - incomplete.length;
  const list = (ids, label, note = "") => ids.length
    ? section(label, `<div class="qgrid">${ids.map(id => qButton(id, quiz.items.indexOf(id), -1)).join("")}</div>`, note ? { note } : {}) : "";
  const counts = [`${complete} of ${quiz.items.length} answered`,
    unanswered.length && `${unanswered.length} unanswered`,
    incomplete.length && `${incomplete.length} incomplete`,
    flagged.length && `${flagged.length} flagged for review`].filter(Boolean).join(", ");
  main.innerHTML = `
    ${examBar(null)}
    ${pageHead("Review before submitting", `${counts}. ${unanswered.length || incomplete.length
      ? "Unanswered and incomplete questions score zero, and there is no penalty for guessing." : "Every question has a complete answer."}`)}
    <div class="row">
      <button class="btn large" id="submit-now">Submit exam</button>
      <button class="btn secondary large" id="back-to-questions">Back to the questions</button>
    </div>
    ${list(unanswered, "Unanswered")}
    ${list(incomplete, "Incomplete", "Fewer options ticked than the question asks for. They score zero as they are.")}
    ${list(flagged, "Flagged")}
    ${section("All questions", navigatorHtml(-1))}
    <p class="abandon-line"><button class="link-btn quiet small" id="quit">Abandon exam</button></p>`;
  bindGo();
  bindExamBar(null);
  $("#back-to-questions").addEventListener("click", () => { quiz.reviewScreen = false; render(); });
  $("#submit-now").addEventListener("click", confirmSubmit);
  $("#quit").addEventListener("click", quit);
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
    if (left <= 0) {
      // A question still open (Leave, Submit, Abandon) no longer applies: time decides.
      stopTimer();
      closeDialogs();
      toast("Time is up. Your exam was submitted.");
      finishQuiz();
    }
  };
  stopTimer();
  tick();
  timerHandle = setInterval(tick, 1000);
}

async function finishQuiz() {
  stopTimer();
  if (quiz.mode === "practice") clearSession();
  if (quiz.mode === "exam") {
    if (quiz.submitting) return;
    quiz.submitting = true;
    trackTime(null);
    await sendPosition(quiz);
    try {
      const res = await api("/api/mock/submit", { mock_id: quiz.mockId, time_on: quiz.timeOn });
      apply(res);
      quiz.report = res.report;
    } catch {
      quiz.submitting = false;
      toastError("Could not submit the exam. Your answers are saved; try again from Today.");
      return;
    }
    refreshNav();
  }
  quiz.finished = true;
  quiz.reviewIdx = null;
  quiz.elapsed = Date.now() - quiz.started;
  // Submitted while the learner was elsewhere: the results wait on /quiz, not over that page.
  if (currentView() !== "quiz") { refreshNav(); return; }
  render();
  window.scrollTo(0, 0);
}

/* ---------------------------------------------------------------- results */

/** Buttons for the answered entries that `show` keeps, numbered by their original question. */
function reviewGrid(ok, show = e => !isSecond(e)) {
  return `<div class="qgrid">${quiz.items.map((entry, n) => {
    if (!show(entry) || (quiz.mode === "practice" && !slot(entry).checked)) return "";
    const good = ok(idOf(entry), entry);
    const shown = placeOf(isSecond(entry) ? quiz.items.indexOf(entry.id) : n);
    const label = isSecond(entry) ? `Second try at question ${shown}` : `Question ${shown}`;
    return `<button data-review="${n}" class="${good ? "good" : "bad"}" aria-label="${label}, ${good ? "correct" : "incorrect"}">${shown}</button>`;
  }).join("")}</div>`;
}

function bindResults(retryIds, next) {
  $("#today-next")?.addEventListener("click", () => {
    if (next.cards.length) openDeck(next.cards.map(id => CARD[id]), true, { fromToday: true });
    else go(`/exercises/${next.lab}`);
  });
  $$("[data-review]", main).forEach(b => b.addEventListener("click", () => { quiz.reviewIdx = Number(b.dataset.review); render(); window.scrollTo(0, 0); }));
  $("#again").addEventListener("click", () => { resetQuiz(); main.classList.remove("reading"); render(); });
  $("#retry-wrong")?.addEventListener("click", () => startQuiz({ mode: "practice", ids: retryIds }));
}

function renderResults() {
  if (quiz.mode === "exam") return renderMockResults(quiz.report);
  // The score counts first answers only; second tries are listed apart.
  const items = quiz.items.filter(e => !isSecond(e) && quiz.checked[e]);
  const seconds = quiz.items.filter(e => isSecond(e) && quiz.seconds[e.id].checked);
  const secondsRight = seconds.filter(e => isCorrect(Q[e.id], quiz.seconds[e.id].chosen)).length;
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
  // Started from Today: the next step of today's session comes first, completed steps skipped.
  const next = quiz.fromToday ? todayLeft() : { cards: [], lab: null };
  const cont = next.cards.length ? `Continue: ${plural(next.cards.length, "flashcard")}` : next.lab ? "Continue: today's exercise" : "";
  main.innerHTML = `
    ${pageHead("Practice results")}
    <div class="score"><b>${pct}%</b><div><strong>${right} of ${items.length} correct</strong><span>in about ${plural(minutes, "minute")}. Answers you missed or guessed are on your mistakes list.</span></div></div>
    <div class="row" style="margin-top:18px">
      ${cont ? `<button class="btn" id="today-next">${cont}</button>` : ""}
      ${wrong.length ? `<button class="btn ${cont ? "secondary" : ""}" id="retry-wrong">Retry the ${wrong.length} I missed</button>` : ""}
      <button class="btn ${wrong.length || cont ? "secondary" : ""}" id="again">New quiz</button>
    </div>
    <div class="result-grid section">
      <section><h2>By topic</h2><div class="table-wrap"><table class="data"><tbody>
        ${Object.entries(byTopic).sort((a, b) => a[0].localeCompare(b[0])).map(([t, s]) =>
          `<tr><td>${esc(topicLabel(t))}</td><td>${meter(s.ok, s.n, "Correct")}</td></tr>`).join("")}
      </tbody></table></div></section>
      ${byConfidence ? `<section><h2>By confidence</h2><div class="table-wrap"><table class="data"><tbody>${byConfidence}</tbody></table></div></section>` : ""}
    </div>
    ${section("Review answers", reviewGrid(id => isCorrect(Q[id], quiz.answers[id])), { aside: "Select a question to see its explanation." })}
    ${seconds.length ? section("Second tries", `<p>Second tries: ${secondsRight} right of ${seconds.length}</p>
      ${reviewGrid((id, e) => isCorrect(Q[id], slot(e).chosen), isSecond)}`, { aside: "Not part of the score above." }) : ""}`;
  bindResults(wrong, next);
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

/* Keys: 1-8 and A-H toggle the options (by display position). S, T and G set the confidence,
   but G is also option G: while the selection is incomplete (practice Check, or a mock question),
   a letter that has an option is that option; once complete, S/T/G are the confidence keys.
   S and T never collide, as options stop at H. Enter checks a complete practice answer as
   "think" when no confidence was chosen. */
function onKey(e) {
  if (e.repeat) return;
  if (!quiz || quiz.finished || quiz.reviewScreen) return;
  const inputs = $$("input[name=opt]", main);
  const toggle = pos => {
    const inp = inputs[pos];
    if (!inp || inp.disabled) return false;
    inp.checked = inp.type === "checkbox" ? !inp.checked : true;
    inp.dispatchEvent(new Event("change"));
    return true;
  };
  const key = e.key.length === 1 ? e.key.toUpperCase() : e.key;
  const n = Number(e.key);
  const entry = quiz.items[quiz.idx];
  const q = entry && Q[idOf(entry)];
  const complete = !!q && isComplete(q, slot(entry).chosen);
  if (n >= 1 && n <= 8) toggle(n - 1);
  else if (key.length === 1 && "STG".includes(key) && (complete || !inputs[LETTERS.indexOf(key)])) {
    const conf = CONF.find(c => c[2] === key)[0];
    $(`[data-conf="${conf}"]:not([disabled])`, main)?.click();
    $(`[data-exam-conf="${conf}"]`, main)?.click();
  } else if (key.length === 1 && LETTERS.includes(key)) {
    toggle(LETTERS.indexOf(key));
  } else if (e.key === "Enter" && e.target.tagName !== "BUTTON") {
    e.preventDefault();
    const next = $("#next") || $("#finish");
    if (next) next.click();
    else if ($("[data-conf]:not([disabled])", main)) checkPractice(quiz.idx, "think");
    else if (q && $("[data-conf]", main)) toast(`Choose ${plural(requiredCount(q), "answer")} first.`, { tag: CHOOSE_TOAST });
  }
}

export const quizView = {
  title: "Quiz",
  render,
  onKey,
  leave() {
    closeDialogs();  // a Submit or Leave question left open no longer applies to this page
    stopTimer();
    if (quiz?.mode === "exam" && !quiz.finished) { trackTime(null); sendPosition(quiz); }
    setExamMode(false);
  },
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
