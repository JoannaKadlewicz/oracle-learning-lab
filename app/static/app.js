"use strict";

/* ===================================================================== basics */

const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];
const main = $("#main");
const LETTERS = "ABCDEFGH";

let C = null;          // content: topics, questions, flashcards, labs
let S = null;          // saved progress from the server (attempts, cards, labs, settings)
let P = null;          // computed by app/engine.py: mastery, mistakes, due items, daily plan
const Q = {};          // questions by id
const L = {};          // labs by id
const CARD = {};       // flashcards by id
let TUTOR = { available: false };  // the optional Claude tutor (app/tutor.py)

function apply(snapshot) { S = snapshot.state; P = snapshot.progress; }

function esc(value) {
  return String(value ?? "").replace(/[&<>"']/g, ch => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch]));
}

function inlineCode(text) {
  // `code` spans plus a heuristic for whole-SQL options
  const raw = String(text ?? "");
  if (/^(SELECT |col |employees |DELETE |INSERT |UPDATE )/.test(raw)) return `<code>${esc(raw)}</code>`;
  return esc(raw).replace(/`([^`]+)`/g, "<code>$1</code>");
}

function shuffle(list) {
  const a = [...list];
  for (let i = a.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [a[i], a[j]] = [a[j], a[i]];
  }
  return a;
}

function store(key, value) {
  try {
    if (value === undefined) return JSON.parse(localStorage.getItem("study:" + key));
    localStorage.setItem("study:" + key, JSON.stringify(value));
  } catch { return null; }
  return value;
}

async function api(path, body) {
  const opts = body === undefined ? {} : { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) };
  const res = await fetch(path, opts);
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    if (body?.error && path.startsWith("/api/tutor/")) return body;
    throw new Error(`${path}: HTTP ${res.status}`);
  }
  return res.json();
}

let toastTimer;
function toast(message) {
  const el = $("#toast");
  el.textContent = message;
  el.classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.remove("show"), 2600);
}

function topicName(id) { return C.topics[id] || id; }
function topicNo(id) { return Number(id.slice(1)); }

/* ===================================================================== stats */

function lastAttempt(qid) {
  const list = S.attempts[qid];
  return list && list.length ? list[list.length - 1] : null;
}

function mistakes() { return P.mistakes; }

function dueCards(topic) {
  return P.due_cards.map(id => CARD[id]).filter(c => !topic || c.topic === topic);
}

function cardLearned(id) { return (P.cards[id]?.interval || 0) >= 7; }

const LEVELS = { new: "Not started", weak: "Weak", learning: "Learning", strong: "Strong" };

function levelBadge(m) {
  const title = m.level === "new" ? "Not enough answers yet"
    : `Estimated accuracy ${Math.round(m.estimate * 100)}%, from ${m.evidence} answers' worth of recent evidence`;
  return `<span class="level level-${m.level}" title="${esc(title)}">${LEVELS[m.level]}</span>`;
}

function topicStats(topic) {
  const qs = C.questions.filter(q => q.topic === topic);
  let answered = 0, correct = 0;
  for (const q of qs) {
    const a = lastAttempt(q.id);
    if (a) { answered++; if (a.correct) correct++; }
  }
  const cards = C.flashcards.filter(c => c.topic === topic);
  const learned = cards.filter(c => cardLearned(c.id)).length;
  const labs = C.labs.filter(l => l.topic === topic);
  const passed = labs.filter(l => S.labs[l.id]?.passed).length;
  return { total: qs.length, answered, correct, cards: cards.length, learned, labs: labs.length, passed };
}

function meter(value, total, label, neutral) {
  if (!total) return `<span class="muted small">—</span>`;
  const pct = Math.round((value / total) * 100);
  const cls = neutral ? "neutral" : pct < 50 ? "low" : pct < 75 ? "mid" : "";
  return `<div class="meter" aria-label="${esc(label)}: ${value} of ${total}"><div class="meter-bar"><i class="${cls}" style="width:${pct}%"></i></div><span>${value}/${total}</span></div>`;
}

function refreshNav() {
  const n = mistakes().length;
  const badge = $("#nav-mistakes");
  badge.hidden = !n;
  badge.textContent = n;
}

/* ===================================================================== router */

const views = {};
let currentView = null;

function route() {
  const [, name = "home", arg] = location.hash.split("/");
  const view = views[name] ? name : "home";
  currentView = view;
  $$(".rail a").forEach(a => {
    if (a.dataset.view === view) a.setAttribute("aria-current", "page");
    else a.removeAttribute("aria-current");
  });
  stopTimer();
  views[view](arg ? decodeURIComponent(arg) : undefined);
  refreshNav();
  main.focus({ preventScroll: true });
  window.scrollTo(0, 0);
}

function go(hash) {
  if (location.hash === hash) route(); else location.hash = hash;
}

/* ===================================================================== overview */

views.home = () => {
  const plan = P.plan;
  const settings = P.settings;
  const miss = mistakes().length;
  const lab = plan.lab ? L[plan.lab] : null;
  const cardMinutes = Math.round(plan.cards.length * 0.3);
  const questionMinutes = Math.round(plan.questions.length * 1.5);

  main.innerHTML = `
    <h1>Exam prep for 1Z0-071</h1>
    <p class="lede">${plan.days_left === null
      ? `${C.questions.length} practice questions, ${C.flashcards.length} flashcards and ${C.labs.length} graded SQL exercises. Set your exam date below to get a plan that fits the time you have.`
      : plan.days_left > 0 ? `<b>${plan.days_left} day${plan.days_left === 1 ? "" : "s"}</b> to your exam. Today's session takes about ${plan.estimate} minutes.`
      : plan.days_left === 0 ? "Your exam is today. Skim your mistakes and flashcards, and trust your preparation."
      : "Your exam date has passed. Set a new date below if you are preparing for a retake."}</p>

    <h2>Today</h2>
    <div class="today">
      <a href="#/quiz" data-start="plan">
        <strong>Answer ${plan.questions.length} questions</strong>
        <span>Open mistakes, due reviews and your weakest objectives, mixed. About ${questionMinutes} min.</span>
      </a>
      <a href="#/cards" data-start="cards" ${plan.cards.length ? "" : `aria-disabled="true"`}>
        <strong>${plan.cards.length ? `Review ${plan.cards.length} flashcards` : "No flashcards due"}</strong>
        <span>${plan.cards.length ? `Spaced by how well you know them. About ${cardMinutes} min.` : "Come back tomorrow, or study a topic deck."}</span>
      </a>
      ${lab ? `<a href="#/exercises/${esc(lab.id)}">
        <strong>Exercise: ${esc(lab.title)}</strong>
        <span>${topicNo(lab.topic)}. ${esc(topicName(lab.topic))}, from one of your weakest objectives. About 8 min.</span>
      </a>` : ""}
      <a href="#/review">
        <strong>${miss ? `${miss} open mistake${miss === 1 ? "" : "s"}` : "No open mistakes"}</strong>
        <span>${miss ? `Cleared after confident correct answers on ${P.proof_days} different days.` : "Missed questions and lucky guesses collect here."}</span>
      </a>
      ${P.active_mock ? `<a href="#/quiz" data-start="resume">
        <strong>Resume your mock exam</strong>
        <span>${P.active_mock.answered} of ${P.active_mock.count} answered, ${Math.max(0, Math.round((P.active_mock.deadline - Date.now() / 1000) / 60))} minutes left.</span>
      </a>` : `<a href="#/quiz" data-start="mock">
        <strong>Take a mock exam</strong>
        <span>${C.exam.questions} questions in ${C.exam.minutes} minutes, every objective covered, questions you have not seen first.</span>
      </a>`}
      <a href="#/progress">
        <strong>${P.readiness.status === "ok" ? `${Math.round(P.readiness.pass_probability * 100)}% chance to pass` : "Readiness: not enough data"}</strong>
        <span>${P.readiness.status === "ok" ? `Expected score ${P.readiness.low_pct} to ${P.readiness.high_pct}%, from first answers only.` : "Answer more new questions, or take a mock exam."}</span>
      </a>
    </div>
    ${plan.advice.length ? `<ul class="advice">${plan.advice.map(a => `<li>${esc(a)}</li>`).join("")}</ul>` : ""}

    <h2>Topics</h2>
    <table class="topics">
      <thead><tr><th>Topic</th><th>Mastery</th><th class="hide-s" title="Questions whose most recent answer was correct. Mastery uses all your recent answers, so retrying a question until it is right does not hide earlier misses.">Last answer correct</th><th class="hide-s">Cards learned</th><th class="hide-s">Exercises passed</th><th><span class="sr-only">Actions</span></th></tr></thead>
      <tbody>
        ${Object.keys(C.topics).map(t => {
          const s = topicStats(t);
          return `<tr>
            <td>${topicNo(t)}. ${esc(topicName(t))}</td>
            <td>${levelBadge(P.topics[t])}</td>
            <td class="hide-s">${meter(s.correct, s.total, "Questions correct")}</td>
            <td class="hide-s">${meter(s.learned, s.cards, "Cards learned")}</td>
            <td class="hide-s">${meter(s.passed, s.labs, "Exercises passed")}</td>
            <td class="num"><button class="link-btn" data-topic="${t}">Practice</button></td>
          </tr>`;
        }).join("")}
      </tbody>
    </table>
    <p class="small muted">Mastery combines quiz answers, flashcards and exercises per official objective, weighted by how recent they are and how sure you were. <a href="#/progress">See every objective and your calibration</a>.</p>

    <h2>Settings</h2>
    <div class="settings">
      <label class="field"><span>Exam date</span>
        <input type="date" id="exam-date" value="${esc(settings.exam_date || "")}"></label>
      <label class="field"><span>Study time per day</span>
        <select id="daily-minutes">${[15, 30, 45, 60, 90, 120].map(m => `<option value="${m}" ${m === plan.minutes ? "selected" : ""}>${m} minutes</option>`).join("")}</select></label>
    </div>
    <div class="row">
      <div class="seg" role="group" aria-label="Color theme">
        ${["auto", "light", "dark"].map(t => `<button data-theme="${t}" aria-pressed="${(store("theme") || "auto") === t}">${t[0].toUpperCase() + t.slice(1)}</button>`).join("")}
      </div>
      <span class="spacer"></span>
      <button class="btn danger" id="reset-progress">Reset progress</button>
    </div>
    <p class="small muted">Progress is saved in <code>app/state/progress.json</code>. It does not change <code>app/notes/docs/progress.md</code>.</p>
  `;

  $$("[data-start]", main).forEach(a => a.addEventListener("click", e => {
    e.preventDefault();
    if (a.dataset.start === "mock") startMock();
    else if (a.dataset.start === "resume") resumeMock();
    else if (a.dataset.start === "plan") startQuiz({ mode: "practice", ids: plan.questions, keepOrder: true });
    else if (plan.cards.length) { openDeck(plan.cards.map(id => CARD[id]), true); go("#/cards"); }
  }));
  $$("[data-topic]", main).forEach(b => b.addEventListener("click", () => startQuiz({ mode: "practice", topics: [b.dataset.topic], count: 10 })));
  $$("[data-theme]", main).forEach(b => b.addEventListener("click", () => { applyTheme(b.dataset.theme); views.home(); }));
  const saveSetting = async body => {
    try { apply(await api("/api/settings", body)); views.home(); toast("Saved."); }
    catch { toast("Could not save the setting."); }
  };
  $("#exam-date").addEventListener("change", e => saveSetting({ exam_date: e.target.value }));
  $("#daily-minutes").addEventListener("change", e => saveSetting({ daily_minutes: Number(e.target.value) }));
  $("#reset-progress").addEventListener("click", async () => {
    if (!confirm("Delete all quiz answers, flashcard reviews and exercise results? This cannot be undone.")) return;
    apply(await api("/api/reset-progress", {}));
    toast("Progress reset.");
    route();
  });
};

/* ===================================================================== progress */

views.progress = () => {
  const cal = P.calibration;
  const rated = Object.values(cal).reduce((n, c) => n + c.answers, 0);
  const pct = c => c.answers ? Math.round((c.correct / c.answers) * 100) : null;
  const sections = Object.keys(C.sections);
  main.innerHTML = `
    <div class="row" style="justify-content:space-between;align-items:baseline">
      <h1>Progress</h1>
      <a class="btn secondary" href="/report" target="_blank" rel="noopener">Readiness report</a>
    </div>
    <p class="lede">Your readiness for the exam, your mock exams, your calibration, and mastery per official exam objective.</p>
    ${dashboardHtml()}

    <h2>Readiness</h2>
    ${readinessHtml(P.readiness)}

    <h2>Mock exams</h2>
    ${P.mocks.length ? `<table class="topics"><thead><tr><th>Date</th><th>Kind</th><th>Score</th><th class="hide-s">On new questions</th><th><span class="sr-only">Report</span></th></tr></thead><tbody>
      ${[...P.mocks].reverse().map(m => `<tr>
        <td>${new Date(m.started * 1000).toLocaleDateString()}</td>
        <td>${m.full ? "Full mock" : `Timed set, ${m.score[1]} questions`}</td>
        <td><span class="level ${m.passed ? "level-strong" : "level-weak"}">${m.pct}%</span></td>
        <td class="hide-s">${m.fresh[1] ? `${Math.round((m.fresh[0] / m.fresh[1]) * 100)}% of ${m.fresh[1]}` : `<span class="muted small">all seen before</span>`}</td>
        <td class="num"><a href="#/mock/${esc(m.id)}">Report</a></td></tr>`).join("")}
    </tbody></table>` : `<div class="empty">No mock exams yet. A full mock has ${C.exam.questions} questions in ${C.exam.minutes} minutes and covers every objective.
      <div><button class="btn" id="first-mock">Take a mock exam</button></div></div>`}

    <h2>Mastery</h2>
    <p class="small muted">Mastery per official exam objective, estimated from quiz answers, flashcards and exercises. Recent evidence counts more, a confident wrong answer counts extra, and a correct guess counts as half wrong.</p>

    <h2>Calibration</h2>
    ${rated ? `<table class="topics"><thead><tr><th>When you said</th><th>Answers</th><th>Correct</th><th class="hide-s">Goal</th></tr></thead><tbody>
      ${[["sure", "Sure", "90% or more"], ["think", "Think so", "60 to 90%"], ["guess", "Guessing", "below 60%"]].map(([k, label, goal]) => `<tr>
        <td>${label}</td><td class="num">${cal[k].answers}</td>
        <td>${cal[k].answers ? meter(cal[k].correct, cal[k].answers, "Correct", k !== "sure") : `<span class="muted small">—</span>`}</td>
        <td class="hide-s muted small">${goal}</td></tr>`).join("")}
    </tbody></table>
    <p class="small muted">${pct(cal.sure) !== null && pct(cal.sure) < 90 && cal.sure.answers >= 10
      ? `You are right ${pct(cal.sure)}% of the time when you are sure. On the exam that means overconfident answers you will not double-check; review your confident mistakes first.`
      : "Well calibrated means: when you are sure, you are almost always right. Rate honestly; guesses are kept on your mistakes list until you prove them."}</p>`
    : `<div class="empty">Rate your confidence when you answer practice questions, and your calibration shows up here.</div>`}

    ${sections.map(sec => {
      const objs = Object.keys(C.objectives).filter(o => o.split(".")[0] === sec);
      return `<h3>${sec}. ${esc(C.sections[sec])}</h3>
      <table class="topics objectives"><colgroup><col class="c-no"><col><col class="c-level"><col class="c-meter hide-s"><col class="c-link"></colgroup><tbody>${objs.map(o => {
        const m = P.objectives[o];
        const n = C.questions.filter(q => q.objective === o).length;
        return `<tr><td class="num muted small">${o}</td><td>${esc(C.objectives[o])}</td>
          <td>${levelBadge(m)}</td>
          <td class="hide-s">${m.level === "new" ? `<span class="muted small">—</span>` : meter(Math.round(m.estimate * 100), 100, "Estimated accuracy")}</td>
          <td class="num">${n ? `<button class="link-btn" data-objective="${o}">${n} questions</button>` : `<span class="muted small">no questions</span>`}</td></tr>`;
      }).join("")}</tbody></table>`;
    }).join("")}`;
  $("#first-mock")?.addEventListener("click", () => startMock());
  bindTips(main);
  const cross = $(".trend-chart .crosshair", main);
  $$(".trend-chart .hit", main).forEach(h => {
    h.addEventListener("mouseenter", () => { cross.setAttribute("x1", h.dataset.x); cross.setAttribute("x2", h.dataset.x); cross.setAttribute("visibility", "visible"); });
    h.addEventListener("mouseleave", () => cross.setAttribute("visibility", "hidden"));
  });
  $$("[data-cell-objective]", main).forEach(c => c.addEventListener("click", () => {
    const ids = C.questions.filter(q => q.objective === c.dataset.cellObjective).map(q => q.id);
    startQuiz({ mode: "practice", ids: shuffle(ids).slice(0, 10) });
  }));
  $$("[data-objective]", main).forEach(b => b.addEventListener("click", () => {
    const ids = C.questions.filter(q => q.objective === b.dataset.objective).map(q => q.id);
    startQuiz({ mode: "practice", ids: shuffle(ids).slice(0, 10) });
  }));
};

function applyTheme(theme) {
  store("theme", theme);
  if (theme === "auto") document.documentElement.removeAttribute("data-theme");
  else document.documentElement.dataset.theme = theme;
}

/* ===================================================================== quiz */

let quiz = null;
let timerHandle = null;

function stopTimer() { clearInterval(timerHandle); timerHandle = null; }

const CONF = [["sure", "Sure", "S"], ["think", "Think so", "T"], ["guess", "Guessing", "G"]];

function randomQuestions(topics, count) {
  return shuffle(C.questions.filter(q => topics.includes(q.topic)).map(q => q.id)).slice(0, count);
}

async function startQuiz({ mode, topics, count, minutes, ids, keepOrder }) {
  topics = topics || Object.keys(C.topics);
  if (mode === "exam") return startMock({ topics: topics.length === Object.keys(C.topics).length ? null : topics, count, minutes });
  let items;
  if (ids) items = keepOrder ? [...ids] : shuffle(ids);
  else {
    // Practice: the engine picks mistakes, due reviews and weak objectives first, interleaved.
    try { items = (await api("/api/pick", { topics, count: count || 10 })).ids; }
    catch { items = randomQuestions(topics, count || 10); }
  }
  const order = {};
  for (const id of items) order[id] = shuffle(Q[id].options.map((_, i) => i));
  quiz = {
    mode, items, order, idx: 0, answers: {}, checked: {}, flags: {}, confidence: {},
    started: Date.now(), deadline: null, finished: false, reviewIdx: null,
  };
  go("#/quiz");
}

/* Mock exams live on the server: it picks the questions, keeps the answers and the deadline,
   and scores the exam. A reload resumes a running mock from the Overview. */

async function startMock({ topics, count, minutes } = {}) {
  if (P.active_mock && !confirm("A mock exam is still running. Abandon it and start a new one?")) return;
  let res;
  try { res = await api("/api/mock/start", { topics, count, minutes }); }
  catch { return toast("Could not start the mock exam. Is the server running?"); }
  apply(res);
  openMock(res.mock);
}

async function resumeMock() {
  try { openMock((await api("/api/mock?id=" + encodeURIComponent(P.active_mock.id))).mock); }
  catch { toast("Could not load the running mock exam."); }
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

function openMock(mock) { quiz = mockQuiz(mock); go("#/quiz"); }

function trackTime(id) {
  // Seconds spent per question in a mock, for the post-exam timing report.
  const now = Date.now();
  if (quiz.shownId && quiz.shownAt) quiz.timeOn[quiz.shownId] = (quiz.timeOn[quiz.shownId] || 0) + (now - quiz.shownAt) / 1000;
  quiz.shownId = id;
  quiz.shownAt = id ? now : null;
}

function saveMockAnswer(id, change) {
  api("/api/mock/answer", { mock_id: quiz.mockId, id, time_on: quiz.timeOn, ...change })
    .catch(() => toast("Could not save your answer. Is the server running?"));
}

views.quiz = () => {
  if (!quiz) return renderQuizSetup();
  if (quiz.finished) return quiz.reviewIdx === null ? renderQuizResults() : renderQuestion(quiz.reviewIdx, true);
  if (quiz.reviewScreen) return renderMockReview();
  renderQuestion(quiz.idx, false);
};

function renderQuizSetup() {
  const saved = store("quiz-setup") || { topics: Object.keys(C.topics), count: 10, mode: "practice" };
  main.innerHTML = `
    <h1>Quiz</h1>
    <p class="lede">Original practice questions, not real exam items. Practice mode explains each answer right away. Exam mode is timed and shows results at the end, like the real test.</p>
    <div class="panel">
      <div class="field"><span>Mode</span>
        <div class="seg" role="group" aria-label="Mode">
          <button data-mode="practice" aria-pressed="${saved.mode === "practice"}">Practice</button>
          <button data-mode="exam" aria-pressed="${saved.mode === "exam"}">Exam, timed</button>
        </div>
      </div>
      <div class="field"><span>Topics</span>
        <div class="chips" id="topic-chips">
          ${Object.keys(C.topics).map(t => `<button class="chip" data-t="${t}" aria-pressed="${saved.topics.includes(t)}">${topicNo(t)}. ${esc(topicName(t))}</button>`).join("")}
        </div>
        <div class="row small"><button class="link-btn" id="all-topics">Select all</button><button class="link-btn" id="no-topics">Clear</button></div>
      </div>
      <div class="field"><span>Number of questions</span>
        <select id="q-count">${[5, 10, 20, 30, C.exam.questions, 999].map(n => `<option value="${n}" ${n === saved.count ? "selected" : ""}>${n === 999 ? "All available" : n}</option>`).join("")}</select>
      </div>
      <p class="small muted" id="pool-info"></p>
      <button class="btn" id="start-quiz">Start quiz</button>
    </div>`;

  const state = { ...saved };
  const sync = () => {
    $$("[data-mode]", main).forEach(b => b.setAttribute("aria-pressed", b.dataset.mode === state.mode));
    $$("#topic-chips .chip").forEach(b => b.setAttribute("aria-pressed", state.topics.includes(b.dataset.t)));
    const pool = C.questions.filter(q => state.topics.includes(q.topic)).length;
    const n = Math.min(pool, state.count);
    $("#pool-info").textContent = pool
      ? `${n} of ${pool} matching questions. ` + (state.mode === "exam"
        ? `Every objective covered where possible, questions you have not seen first. Time limit: ${Math.ceil(n * 1.9)} minutes. Results at the end.`
        : "Open mistakes, due reviews and unseen questions from your weakest objectives come first.")
      : "Select at least one topic.";
    $("#start-quiz").disabled = !pool;
  };
  $$("[data-mode]", main).forEach(b => b.addEventListener("click", () => { state.mode = b.dataset.mode; sync(); }));
  $$("#topic-chips .chip").forEach(b => b.addEventListener("click", () => {
    const t = b.dataset.t;
    state.topics = state.topics.includes(t) ? state.topics.filter(x => x !== t) : [...state.topics, t];
    sync();
  }));
  $("#all-topics").addEventListener("click", () => { state.topics = Object.keys(C.topics); sync(); });
  $("#no-topics").addEventListener("click", () => { state.topics = []; sync(); });
  $("#q-count").addEventListener("change", e => { state.count = Number(e.target.value); sync(); });
  $("#start-quiz").addEventListener("click", () => {
    store("quiz-setup", state);
    const n = Math.min(state.count, C.questions.filter(q => state.topics.includes(q.topic)).length);
    startQuiz({ mode: state.mode, topics: state.topics, count: state.count, minutes: state.mode === "exam" ? Math.ceil(n * 1.9) : null });
  });
  sync();
}

function isCorrect(q, chosen) {
  const a = [...q.answer].sort().join(",");
  const b = [...(chosen || [])].sort().join(",");
  return a === b;
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

  main.innerHTML = `
    ${exam ? `<div class="exam-bar"><span class="timer" id="timer"></span><span class="muted small">${quiz.items.filter(q => quiz.answers[q]?.length).length} of ${total} answered</span><span class="spacer"></span><button class="btn secondary" id="submit-exam">Submit exam</button></div>` : ""}
    <div class="q-head">
      <span>Question ${i + 1} of ${total}</span>
      <span>${topicNo(q.topic)}. ${esc(topicName(q.topic))}</span>
    </div>
    <div class="q-progress"><i style="width:${((i + (revealed ? 1 : 0)) / total) * 100}%"></i></div>
    ${multi ? `<span class="q-choose">Choose ${q.answer.length}</span>` : ""}
    <p class="q-prompt" id="q-prompt">${inlineCode(q.prompt)}</p>
    ${q.code ? `<pre class="code"><code>${esc(q.code)}</code></pre>` : ""}
    <ul class="options" role="${multi ? "group" : "radiogroup"}" aria-labelledby="q-prompt">
      ${order.map((orig, pos) => {
        let cls = "";
        if (revealed) {
          if (q.answer.includes(orig)) cls = "correct";
          else if (chosen.includes(orig)) cls = "wrong";
        }
        return `<li><label class="option ${multi ? "multi" : ""} ${cls} ${revealed ? "locked" : ""}">
          <input type="${multi ? "checkbox" : "radio"}" name="opt" value="${orig}" ${chosen.includes(orig) ? "checked" : ""} ${revealed ? "disabled" : ""}>
          <span class="letter" aria-hidden="true">${LETTERS[pos]}</span>
          <span class="text">${inlineCode(q.options[orig])}</span>
        </label></li>`;
      }).join("")}
    </ul>
    ${revealed ? verdictHtml(q, chosen) : ""}
    ${exam ? `<div class="confidence" role="group" aria-label="How sure are you? Optional">
      <span class="small muted">How sure? (optional)</span>
      ${CONF.map(([k, label, key]) => `<button class="chip" data-exam-conf="${k}" aria-pressed="${quiz.confidence[id] === k}">${label} <span class="kbd">${key}</span></button>`).join("")}
    </div>` : ""}
    <div class="row">
      ${reviewing ? `<button class="btn secondary" id="back-results">Back to results</button>
                     ${i > 0 ? `<button class="btn secondary" id="prev">Previous</button>` : ""}
                     ${i < total - 1 ? `<button class="btn" id="next">Next</button>` : ""}`
        : exam ? `${i > 0 ? `<button class="btn secondary" id="prev">Previous</button>` : ""}
                  <button class="btn secondary" id="flag" aria-pressed="${!!quiz.flags[id]}">${quiz.flags[id] ? "Unflag" : "Flag for review"}</button>
                  ${i < total - 1 ? `<button class="btn" id="next">Next <span class="kbd">Enter</span></button>` : `<button class="btn" id="finish">Submit exam</button>`}`
        : revealed ? `<button class="btn" id="next">${i < total - 1 ? "Next question" : "See results"} <span class="kbd">Enter</span></button>`
        : `<div class="confidence" role="group" aria-label="Check the answer: how sure are you?">
             <span class="small muted">Check: how sure are you?</span>
             ${CONF.map(([k, label, key]) => `<button class="btn secondary" data-conf="${k}" ${chosen.length ? "" : "disabled"}>${label} <span class="kbd">${key}</span></button>`).join("")}
           </div>`}
      <span class="spacer"></span>
      ${revealed && (q.try_sql || q.code) ? `<button class="btn secondary" id="try">Run it in the SQL lab</button>` : ""}
      ${!reviewing ? `<button class="link-btn small" id="quit">End quiz</button>` : ""}
    </div>
    ${exam ? `<div class="qgrid" aria-label="Question navigator">${quiz.items.map((qid, n) =>
      `<button data-go="${n}" class="${n === i ? "current" : ""} ${quiz.answers[qid]?.length ? "answered" : ""} ${quiz.flags[qid] ? "flagged" : ""}" aria-label="Question ${n + 1}${quiz.flags[qid] ? ", flagged" : ""}">${n + 1}</button>`).join("")}</div>` : ""}
  `;

  $$("input[name=opt]", main).forEach(inp => inp.addEventListener("change", () => {
    quiz.answers[id] = $$("input[name=opt]:checked", main).map(x => Number(x.value));
    $$("[data-conf]", main).forEach(b => { b.disabled = !quiz.answers[id].length; });
    if (exam) saveMockAnswer(id, { chosen: quiz.answers[id] });
    if (exam) $$(".qgrid button")[i].classList.toggle("answered", quiz.answers[id].length > 0);
  }));

  $$("[data-conf]", main).forEach(b => b.addEventListener("click", () => checkPractice(id, b.dataset.conf)));
  $$("[data-exam-conf]", main).forEach(b => b.addEventListener("click", () => {
    quiz.confidence[id] = quiz.confidence[id] === b.dataset.examConf ? null : b.dataset.examConf;
    saveMockAnswer(id, { confidence: quiz.confidence[id] });
    views.quiz();
  }));
  $("#next")?.addEventListener("click", () => {
    if (reviewing) { quiz.reviewIdx = i + 1; return views.quiz(); }
    if (!exam && i === total - 1) return finishQuiz();
    quiz.idx = i + 1; views.quiz();
  });
  $("#prev")?.addEventListener("click", () => { if (reviewing) quiz.reviewIdx = i - 1; else quiz.idx = i - 1; views.quiz(); });
  $("#flag")?.addEventListener("click", () => { quiz.flags[id] = !quiz.flags[id]; saveMockAnswer(id, { flagged: quiz.flags[id] }); views.quiz(); });
  $("#finish")?.addEventListener("click", confirmSubmit);
  $("#submit-exam")?.addEventListener("click", confirmSubmit);
  $("#back-results")?.addEventListener("click", () => { quiz.reviewIdx = null; views.quiz(); });
  $("#try")?.addEventListener("click", () => { labDraft(q.try_sql || q.code); go("#/lab"); });
  $("#quit")?.addEventListener("click", () => {
    if (quiz.mode === "exam") {
      if (!confirm("Abandon this mock exam? It will not be scored, and its questions count as seen.")) return;
      trackTime(null);
      api("/api/mock/abandon", { mock_id: quiz.mockId }).then(apply).catch(() => {});
    }
    if (quiz.mode === "practice" && Object.keys(quiz.checked).length) return finishQuiz();
    stopTimer();
    quiz = null; views.quiz();
  });
  $$("[data-go]", main).forEach(b => b.addEventListener("click", () => { quiz.idx = Number(b.dataset.go); views.quiz(); }));

  if (exam) { trackTime(id); startTimer(); }
}

function verdictHtml(q, chosen) {
  const ok = isCorrect(q, chosen);
  const order = quiz.order[q.id];
  const letters = q.answer.map(a => LETTERS[order.indexOf(a)]).sort().join(" and ");
  const conf = quiz.confidence[q.id];
  const note = ok && conf === "guess"
    ? `You guessed, so this stays on your mistakes list until you answer it confidently on ${P.proof_days} different days.`
    : !ok && conf === "sure" ? "You were sure: that makes this a misconception, the most valuable kind of mistake to fix." : "";
  return `<div class="verdict ${ok ? "good" : "bad"}" role="status">
    <strong>${ok ? (conf === "guess" ? "Correct, but a guess" : "Correct") : chosen.length ? `Not quite. The answer is ${letters}.` : `Not answered. The answer is ${letters}.`}</strong>
    <p>${inlineCode(q.explanation)}</p>
    ${note ? `<p class="small verdict-note">${note}</p>` : ""}
    ${TUTOR.available && (!ok || conf === "guess") && chosen.length
      ? `<div class="tutor-box"><button class="link-btn" data-tutor-why="${esc(q.id)}">${ok ? "Ask Claude how to be sure next time" : "Ask Claude why my answer is wrong"}</button></div>` : ""}
  </div>`;
}

async function askTutor(button, path, body) {
  const box = button.closest(".tutor-box");
  box.innerHTML = `<p class="muted small">Asking Claude…</p>`;
  try {
    const res = await api(path, body);
    box.innerHTML = res.error ? `<p class="small">${esc(res.error)}</p>`
      : `<div class="tutor-answer"><b>Claude</b>${res.text.split(/\n\s*\n/).map(para => `<p>${inlineCode(para)}</p>`).join("")}</div>`;
  } catch (err) { box.innerHTML = `<p class="small">${esc(err.message)}</p>`; }
}

document.addEventListener("click", e => {
  const why = e.target.closest("[data-tutor-why]");
  if (why) askTutor(why, "/api/tutor/why", { id: why.dataset.tutorWhy, chosen: quiz.answers[why.dataset.tutorWhy] || [], confidence: quiz.confidence[why.dataset.tutorWhy] || null });
});

async function checkPractice(id, confidence) {
  const chosen = quiz.answers[id] || [];
  if (!chosen.length) return;
  quiz.checked[id] = true;
  quiz.confidence[id] = confidence;
  views.quiz();
  try { apply(await api("/api/attempt", { id, chosen, confidence, mode: "practice" })); refreshNav(); }
  catch { toast("Could not save this answer. Is the server running?"); }
}

function confirmSubmit() {
  // Exam mode: show the review screen before submitting, like the real test.
  trackTime(null);
  quiz.reviewScreen = true;
  views.quiz();
}

function renderMockReview() {
  const open = quiz.items.map((id, n) => [id, n]).filter(([id]) => !(quiz.answers[id] || []).length);
  const flagged = quiz.items.map((id, n) => [id, n]).filter(([id]) => quiz.flags[id]);
  const list = (rows, label) => rows.length
    ? `<h2>${label}</h2><div class="qgrid">${rows.map(([, n]) => `<button data-go="${n}">${n + 1}</button>`).join("")}</div>` : "";
  main.innerHTML = `
    <div class="exam-bar"><span class="timer" id="timer"></span><span class="spacer"></span></div>
    <h1>Review before submitting</h1>
    <p class="lede">${quiz.items.length - open.length} of ${quiz.items.length} answered${flagged.length ? `, ${flagged.length} flagged for review` : ""}. ${open.length ? "Unanswered questions score zero; there is no penalty for guessing." : "Every question has an answer."}</p>
    ${list(open, "Unanswered")}
    ${list(flagged, "Flagged")}
    <h2>All questions</h2>
    <div class="qgrid">${quiz.items.map((id, n) =>
      `<button data-go="${n}" class="${quiz.answers[id]?.length ? "answered" : ""} ${quiz.flags[id] ? "flagged" : ""}">${n + 1}</button>`).join("")}</div>
    <div class="row">
      <button class="btn secondary" id="back-to-questions">Back to the questions</button>
      <button class="btn" id="submit-now">Submit exam</button>
    </div>`;
  $$("[data-go]", main).forEach(b => b.addEventListener("click", () => { quiz.reviewScreen = false; quiz.idx = Number(b.dataset.go); views.quiz(); }));
  $("#back-to-questions").addEventListener("click", () => { quiz.reviewScreen = false; views.quiz(); });
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
      el.textContent = `${m}:${String(s).padStart(2, "0")} left`;
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
      toast("Could not submit the exam. Your answers are saved; try again from the Overview.");
      return;
    }
    refreshNav();
  }
  quiz.finished = true;
  quiz.reviewIdx = null;
  quiz.elapsed = Date.now() - quiz.started;
  views.quiz();
}

function renderQuizResults() {
  if (quiz.mode === "exam") return renderMockResults(quiz.report);
  const items = quiz.mode === "practice" ? quiz.items.filter(id => quiz.checked[id]) : quiz.items;
  const right = items.filter(id => isCorrect(Q[id], quiz.answers[id])).length;
  const pct = items.length ? Math.round((right / items.length) * 100) : 0;
  const byTopic = {};
  for (const id of items) {
    const t = Q[id].topic;
    byTopic[t] = byTopic[t] || { n: 0, ok: 0 };
    byTopic[t].n++;
    if (isCorrect(Q[id], quiz.answers[id])) byTopic[t].ok++;
  }
  const minutes = Math.round(quiz.elapsed / 60000);
  const byConfidence = CONF.map(([k, label]) => {
    const ids = items.filter(id => quiz.confidence[id] === k);
    return ids.length ? `<tr><td>${label}</td><td>${meter(ids.filter(id => isCorrect(Q[id], quiz.answers[id])).length, ids.length, "Correct")}</td></tr>` : "";
  }).join("");
  main.innerHTML = `
    <h1>Practice results</h1>
    <div class="score"><b>${pct}%</b><span>${right} of ${items.length} correct in ${minutes} min</span></div>
    <h2>By topic</h2>
    <table class="topics"><tbody>
      ${Object.entries(byTopic).sort((a, b) => topicNo(a[0]) - topicNo(b[0])).map(([t, s]) =>
        `<tr><td>${topicNo(t)}. ${esc(topicName(t))}</td><td>${meter(s.ok, s.n, "Correct")}</td></tr>`).join("")}
    </tbody></table>
    ${byConfidence ? `<h2>By confidence</h2><table class="topics"><tbody>${byConfidence}</tbody></table>` : ""}
    <h2>Review answers</h2>
    <p class="small muted">Select a question to see the explanation.</p>
    <div class="qgrid">${quiz.items.map((id, n) => {
      if (quiz.mode === "practice" && !quiz.checked[id]) return "";
      const ok = isCorrect(Q[id], quiz.answers[id]);
      return `<button data-review="${n}" class="${ok ? "good" : "bad"}" aria-label="Question ${n + 1}, ${ok ? "correct" : "incorrect"}">${n + 1}</button>`;
    }).join("")}</div>
    <div class="row">
      <button class="btn" id="again">New quiz</button>
      ${items.length - right ? `<button class="btn secondary" id="retry-wrong">Retry the ${items.length - right} I missed</button>` : ""}
    </div>`;
  $$("[data-review]", main).forEach(b => b.addEventListener("click", () => { quiz.reviewIdx = Number(b.dataset.review); views.quiz(); }));
  $("#again").addEventListener("click", () => { quiz = null; views.quiz(); });
  $("#retry-wrong")?.addEventListener("click", () => {
    startQuiz({ mode: "practice", ids: items.filter(id => !isCorrect(Q[id], quiz.answers[id])) });
  });
}

function renderMockResults(r) {
  const fresh = r.fresh[1] ? Math.round((r.fresh[0] / r.fresh[1]) * 100) : null;
  const seen = r.score[1] - r.fresh[1];
  const changed = r.changes.right_to_wrong.length + r.changes.wrong_to_right.length + r.changes.wrong_to_wrong.length;
  const n = id => quiz.items.indexOf(id);
  const qButtons = ids => ids.map(id => `<button class="link-btn" data-review="${n(id)}">${n(id) + 1}</button>`).join(", ");
  const minutes = s => s >= 60 ? `${Math.floor(s / 60)} min ${Math.round(s % 60)} s` : `${Math.round(s)} s`;
  main.innerHTML = `
    <h1>${r.full ? "Mock exam results" : "Timed set results"}</h1>
    <div class="score ${r.passed ? "pass" : "fail"}"><b>${r.pct}%</b><span>${r.score[0]} of ${r.score[1]} correct in ${r.minutes_used} min.
      ${r.passed ? `Above the ${C.exam.passing_pct}% passing score.` : `Below the ${C.exam.passing_pct}% passing score.`}
      These are original practice questions, not calibrated to the real exam.</span></div>
    <p>${seen
      ? `${r.fresh[1]} of ${r.score[1]} questions were new to you${fresh !== null ? `, and you scored <b>${fresh}%</b> on those` : ""}. The ${seen} you had seen before make the overall score optimistic.`
      : "Every question was new to you, so this score is a clean measurement."}</p>

    <h2>By exam section</h2>
    <table class="topics"><tbody>
      ${Object.entries(r.by_section).map(([sec, [ok, total]]) =>
        `<tr><td>${sec}. ${esc(C.sections[sec])}</td><td>${meter(ok, total, "Correct")}</td></tr>`).join("")}
    </tbody></table>

    <h2>Question types</h2>
    <table class="topics"><tbody>
      <tr><td>Single answer</td><td>${meter(r.single[0], r.single[1], "Correct")}</td></tr>
      <tr><td>Multiple answers ("choose two/three")</td><td>${meter(r.multi[0], r.multi[1], "Correct")}</td></tr>
    </tbody></table>
    ${r.multi[1] && r.single[1] && r.multi[0] / r.multi[1] < r.single[0] / r.single[1] - 0.15
      ? `<p class="small muted">Multiple-answer questions score all or nothing. Read every option before choosing, and check you picked exactly as many as asked.</p>` : ""}

    <h2>Changed answers</h2>
    ${changed ? `<table class="topics"><tbody>
      <tr><td>Right to wrong</td><td class="num">${r.changes.right_to_wrong.length}</td><td>${qButtons(r.changes.right_to_wrong)}</td></tr>
      <tr><td>Wrong to right</td><td class="num">${r.changes.wrong_to_right.length}</td><td>${qButtons(r.changes.wrong_to_right)}</td></tr>
      <tr><td>Wrong to wrong</td><td class="num">${r.changes.wrong_to_wrong.length}</td><td>${qButtons(r.changes.wrong_to_wrong)}</td></tr>
    </tbody></table>
    <p class="small muted">${r.changes.right_to_wrong.length > r.changes.wrong_to_right.length
      ? "Changing answers cost you points this time. Change an answer only when you find a concrete reason, not a feeling."
      : "Your second thoughts helped or did no harm this time."}</p>`
    : `<p class="muted">You did not change any answers.</p>`}

    <h2>Time</h2>
    <p>${r.minutes_used} of ${r.minutes} minutes used. Target pace: ${minutes(r.pace_seconds)} per question.</p>
    ${r.slowest.length ? `<table class="topics"><thead><tr><th>Slowest questions</th><th>Time</th><th>Result</th></tr></thead><tbody>
      ${r.slowest.map(id => `<tr><td><button class="link-btn" data-review="${n(id)}">Question ${n(id) + 1}</button> <span class="muted small">${esc(C.objectives[Q[id].objective])}</span></td>
        <td class="num">${minutes(r.time_on[id])}</td><td>${r.right.includes(id) ? "Correct" : "Wrong"}</td></tr>`).join("")}
    </tbody></table>` : ""}

    ${Object.values(r.confidence).some(([, total]) => total) ? `<h2>By confidence</h2><table class="topics"><tbody>
      ${CONF.map(([k, label]) => r.confidence[k][1] ? `<tr><td>${label}</td><td>${meter(r.confidence[k][0], r.confidence[k][1], "Correct", k !== "sure")}</td></tr>` : "").join("")}
    </tbody></table>` : ""}

    <h2>Readiness after this exam</h2>
    ${readinessHtml(P.readiness)}

    <h2>Review answers</h2>
    <p class="small muted">Select a question to see the explanation.</p>
    <div class="qgrid">${quiz.items.map((id, i) => {
      const ok = r.right.includes(id);
      return `<button data-review="${i}" class="${ok ? "good" : "bad"}" aria-label="Question ${i + 1}, ${ok ? "correct" : "incorrect"}">${i + 1}</button>`;
    }).join("")}</div>
    <div class="row">
      <button class="btn" id="again">New quiz</button>
      ${r.score[1] - r.score[0] ? `<button class="btn secondary" id="retry-wrong">Practise the ${r.score[1] - r.score[0]} I missed</button>` : ""}
    </div>`;
  $$("[data-review]", main).forEach(b => b.addEventListener("click", () => { quiz.reviewIdx = Number(b.dataset.review); views.quiz(); }));
  $("#again").addEventListener("click", () => { quiz = null; views.quiz(); });
  $("#retry-wrong")?.addEventListener("click", () => startQuiz({ mode: "practice", ids: quiz.items.filter(id => !r.right.includes(id)) }));
}

/* ---- dashboard charts (validated palette: see --series-* and --status-* in app.css) ---- */

function bindTips(root) {
  // One shared tooltip for every [data-tip] mark: chart points, heatmap cells, calendar days.
  let tip = $("#viz-tip");
  if (!tip) { tip = document.createElement("div"); tip.id = "viz-tip"; tip.className = "viz-tip"; tip.hidden = true; document.body.append(tip); }
  const show = (el, x, y) => {
    tip.innerHTML = el.dataset.tip;
    tip.hidden = false;
    const w = tip.offsetWidth, h = tip.offsetHeight;
    tip.style.left = Math.min(window.innerWidth - w - 8, Math.max(8, x + 14)) + "px";
    tip.style.top = Math.max(8, y - h - 12) + "px";
  };
  root.querySelectorAll("[data-tip]").forEach(el => {
    el.addEventListener("mousemove", e => show(el, e.clientX, e.clientY));
    el.addEventListener("mouseleave", () => { tip.hidden = true; });
    el.addEventListener("focus", () => { const r = el.getBoundingClientRect(); show(el, r.right, r.top); });
    el.addEventListener("blur", () => { tip.hidden = true; });
  });
}

function statTile(value, label, note) {
  return `<div class="stat"><b>${value}</b><span>${label}</span>${note ? `<small>${note}</small>` : ""}</div>`;
}

function trendChart(mocks) {
  if (!mocks.length) return `<div class="empty">Your mock exam scores will be charted here.</div>`;
  const W = 640, H = 220, L = 40, R = 110, T = 14, B = 30;
  const x = i => mocks.length === 1 ? L + (W - L - R) / 2 : L + i * (W - L - R) / (mocks.length - 1);
  const y = v => T + (100 - v) * (H - T - B) / 100;
  const fresh = m => m.fresh[1] ? Math.round(100 * m.fresh[0] / m.fresh[1]) : null;
  const series = [
    { key: "overall", label: "Overall", cls: "s1", value: m => m.pct },
    { key: "fresh", label: "New questions", cls: "s2", value: fresh },
  ];
  const date = m => new Date(m.started * 1000).toLocaleDateString([], { month: "short", day: "numeric" });
  const grid = [0, 25, 50, 75, 100].map(v => `<line class="grid-line" x1="${L}" x2="${W - R}" y1="${y(v)}" y2="${y(v)}"/><text class="axis" x="${L - 6}" y="${y(v) + 4}" text-anchor="end">${v}%</text>`).join("");
  const pass = `<line class="pass-line" x1="${L}" x2="${W - R}" y1="${y(C.exam.passing_pct)}" y2="${y(C.exam.passing_pct)}"/><text class="axis" x="${W - R + 6}" y="${y(C.exam.passing_pct) + 4}">pass ${C.exam.passing_pct}%</text>`;
  // Direct labels at the last point, with the value; when the two values are close the labels are
  // stacked 15px apart (the higher value on top) so they never collide.
  const ends = series.map(sr => {
    const pts = mocks.map((m, i) => [x(i), sr.value(m)]).filter(([, v]) => v !== null);
    return { sr, pts, last: pts.at(-1) };
  });
  const placed = ends.filter(e => e.last).sort((a, b) => b.last[1] - a.last[1]);
  placed.forEach((e, i) => { e.labelY = y(e.last[1]) + 4; if (i && e.labelY - placed[i - 1].labelY < 15) e.labelY = placed[i - 1].labelY + 15; });
  const lines = ends.map(({ sr, pts }) => `<polyline class="trend ${sr.cls}" points="${pts.map(([px, v]) => `${px},${y(v)}`).join(" ")}"/>`).join("")
    + ends.map(({ sr, pts }) => pts.map(([px, v]) => `<circle class="dot ${sr.cls}" cx="${px}" cy="${y(v)}" r="4.5"/>`).join("")).join("")
    + placed.map(e => `<text class="direct" x="${e.last[0] + 10}" y="${e.labelY}"><tspan class="${e.sr.cls}-mark">■</tspan> ${e.sr.label} ${e.last[1]}%</text>`).join("");
  const xs = mocks.map((m, i) => `<text class="axis" x="${x(i)}" y="${H - 8}" text-anchor="middle">${mocks.length <= 8 || i % Math.ceil(mocks.length / 8) === 0 ? date(m) : ""}</text>`).join("");
  const hits = mocks.map((m, i) => {
    const w = mocks.length === 1 ? 80 : (W - L - R) / (mocks.length - 1);
    const tip = `<b>${esc(date(m))}</b> · ${m.full ? "full mock" : "timed set"}<br>Overall ${m.pct}%${fresh(m) !== null ? `<br>New questions ${fresh(m)}% (${m.fresh[1]})` : ""}`;
    return `<rect class="hit" x="${x(i) - w / 2}" y="${T}" width="${w}" height="${H - T - B}" data-tip="${esc(tip)}" data-x="${x(i)}" tabindex="0"/>`;
  }).join("");
  return `<div class="legend-row"><span><i class="swatch s1"></i>Overall score</span><span><i class="swatch s2"></i>Score on questions new to you</span></div>
    <svg class="trend-chart" viewBox="0 0 ${W} ${H}" role="img" aria-label="Mock exam scores over time">${grid}${pass}${xs}
      <line class="crosshair" x1="0" x2="0" y1="${T}" y2="${H - B}" visibility="hidden"/>${lines}${hits}</svg>`;
}

function heatmapHtml() {
  const icon = { strong: "✓", learning: "~", weak: "!", new: "·" };
  return `<div class="legend-row">${["strong", "learning", "weak", "new"].map(l => `<span><i class="swatch lvl-${l}"></i>${icon[l]} ${LEVELS[l]}</span>`).join("")}</div>
    <div class="heatmap">${Object.keys(C.sections).map(sec => `<div class="heat-row"><span class="heat-label" title="${esc(C.sections[sec])}">${sec}</span>
      ${Object.keys(C.objectives).filter(o => o.split(".")[0] === sec).map(o => {
        const m = P.objectives[o];
        const tip = `<b>${o} ${esc(C.objectives[o])}</b><br>${LEVELS[m.level]}${m.level === "new" ? "" : ` · estimated ${Math.round(m.estimate * 100)}%`}<br>Click to practise`;
        return `<button class="heat-cell lvl-${m.level}" data-cell-objective="${o}" data-tip="${esc(tip)}" aria-label="${o}: ${LEVELS[m.level]}">${o.split(".")[1]}<i>${icon[m.level]}</i></button>`;
      }).join("")}</div>`).join("")}</div>`;
}

function calendarHtml(days) {
  const max = Math.max(1, ...days.map(d => d.actions));
  const step = n => n === 0 ? 0 : Math.min(4, Math.ceil((n / max) * 4));
  const first = new Date(days[0].date + "T12:00:00").getDay();
  const pad = (first + 6) % 7;  // weeks start on Monday
  const cells = Array(pad).fill(`<span class="cal-cell pad"></span>`).concat(days.map(d =>
    `<span class="cal-cell q${step(d.actions)}" data-tip="${esc(`<b>${new Date(d.date + "T12:00:00").toLocaleDateString([], { weekday: "short", month: "short", day: "numeric" })}</b><br>${d.actions} study action${d.actions === 1 ? "" : "s"}`)}"></span>`));
  return `<div class="calendar" role="img" aria-label="Study actions per day over the last 12 weeks">${cells.join("")}</div>
    <div class="legend-row small"><span>Less</span>${[0, 1, 2, 3, 4].map(q => `<i class="swatch cal-cell q${q}"></i>`).join("")}<span>More</span></div>`;
}

function badgesHtml(list) {
  return `<div class="badges">${list.map(b => `<div class="badge ${b.earned ? "earned" : ""}">
      <strong>${b.earned ? "✓ " : ""}${esc(b.title)}</strong>
      <span>${esc(b.description)}</span>
      ${b.earned ? `<small>Earned</small>` : meter(b.progress[0], b.progress[1], b.title, true)}
    </div>`).join("")}</div>`;
}

function dashboardHtml() {
  const r = P.readiness, a = P.activity, sure = P.calibration.sure;
  const ready = P.ready;
  return `<section class="dashboard">
    <div class="ready ${ready.done ? "done" : ""}">
      <h2 style="margin-top:0">${ready.done ? "✓ Ready to book the exam" : "Ready to book the exam?"}</h2>
      <ul>${ready.items.map(i => `<li class="${i.done ? "done" : ""}"><span aria-hidden="true">${i.done ? "✓" : "○"}</span> ${esc(i.label)} <small>${esc(i.detail)}</small></li>`).join("")}</ul>
    </div>
    <div class="stats">
      ${statTile(r.status === "ok" ? `${Math.round(r.pass_probability * 100)}%` : "–", "chance to pass", r.status === "ok" ? `score ${r.low_pct}–${r.high_pct}%` : "not enough data")}
      ${statTile(a.streak, `day${a.streak === 1 ? "" : "s"} in a row`, `${a.active_days} study days in total`)}
      ${statTile(a.hours, "hours studied", "estimated from your activity")}
      ${statTile(sure.answers ? `${Math.round(100 * sure.correct / sure.answers)}%` : "–", "right when Sure", sure.answers ? `${sure.answers} answers, goal 90%` : "rate your confidence")}
    </div>
    <h2>Mock exam trend</h2>${trendChart(P.mocks)}
    <h2>Objective map</h2>${heatmapHtml()}
    <h2>Activity</h2>${calendarHtml(a.days)}
    <h2>Badges</h2>
    <p class="small muted">Earned only with evidence the app can check. ${P.badges.filter(b => b.earned).length} of ${P.badges.length} earned.</p>
    ${badgesHtml(P.badges)}
  </section>`;
}

function readinessHtml(r) {
  if (r.status !== "ok") {
    return `<p>Not enough data yet: readiness needs first answers to about ${r.needed} questions you have never seen (you have ${r.evidence}). A mock exam is the fastest way to get there.</p>`;
  }
  const gaps = [];
  if (r.untested.length) gaps.push(`${r.untested.length} objective${r.untested.length === 1 ? " has" : "s have"} too little evidence for a mastery level (fewer than about 2 answers)`);
  if (r.weak.length) gaps.push(`${r.weak.length} ${r.weak.length === 1 ? "is" : "are"} weak (${r.weak.join(", ")})`);
  return `<div class="readiness">
      <b>${Math.round(r.pass_probability * 100)}%</b>
      <span>estimated chance to pass. Expected score ${r.expected_pct}%, most likely between ${r.low_pct}% and ${r.high_pct}% (passing: ${r.passing_pct}%).</span>
    </div>
    <p class="small muted">Based only on the first answer you ever gave to each question, so practising the same questions again cannot inflate it. Mock answers count fully, practice answers 60%, and older answers fade.${gaps.length ? ` Also: ${gaps.join(", and ")}.` : ""}</p>`;
}

views.mock = async (id) => {
  try {
    const res = await api("/api/mock?id=" + encodeURIComponent(id));
    if (!res.report) return go("#/progress");
    quiz = mockQuiz(res.mock);
    quiz.finished = true;
    quiz.report = res.report;
    go("#/quiz");
  } catch { toast("Could not load that mock exam."); }
};

/* ===================================================================== flashcards */

let deck = null;

views.cards = () => {
  if (!deck) return renderDeckSetup();
  renderCard();
};

function renderDeckSetup() {
  const due = dueCards();
  main.innerHTML = `
    <h1>Flashcards</h1>
    <p class="lede">Flip a card, then rate it. "Good" schedules it again after 1 day, then 3, then longer and longer intervals; "Easy" stretches them faster. "Again" brings it back in this session and starts its intervals over. A card counts as learned once its interval reaches a week.</p>
    <div class="row" style="margin-bottom:22px">
      <button class="btn" id="study-due" ${due.length ? "" : "disabled"}>Study ${due.length} due cards</button>
      <button class="btn secondary" id="study-all">Study all ${C.flashcards.length} cards</button>
    </div>
    <h2>By topic</h2>
    <table class="topics"><tbody>
      ${Object.keys(C.topics).map(t => {
        const cards = C.flashcards.filter(c => c.topic === t);
        const d = dueCards(t).length;
        const learned = cards.filter(c => cardLearned(c.id)).length;
        return `<tr><td>${topicNo(t)}. ${esc(topicName(t))}</td><td>${meter(learned, cards.length, "Learned")}</td>
          <td class="num muted small">${d} due</td>
          <td class="num"><button class="link-btn" data-deck="${t}">Study</button></td></tr>`;
      }).join("")}
    </tbody></table>`;
  $("#study-due").addEventListener("click", () => openDeck(due));
  $("#study-all").addEventListener("click", () => openDeck(C.flashcards));
  $$("[data-deck]", main).forEach(b => b.addEventListener("click", () => openDeck(C.flashcards.filter(c => c.topic === b.dataset.deck))));
}

function openDeck(cards, keepOrder) {
  const ids = cards.map(c => c.id);
  deck = { queue: keepOrder ? ids : shuffle(ids), done: 0, again: 0, flipped: false, total: cards.length };
  views.cards();
}

function renderCard() {
  if (!deck.queue.length) {
    main.innerHTML = `
      <h1>Deck finished</h1>
      <p class="lede">${deck.done} card${deck.done === 1 ? "" : "s"} done${deck.again ? `, ${deck.again} sent back for another pass` : ""}.</p>
      <div class="row"><button class="btn" id="deck-back">Choose another deck</button></div>`;
    $("#deck-back").addEventListener("click", () => { deck = null; views.cards(); });
    return;
  }
  const card = C.flashcards.find(c => c.id === deck.queue[0]);
  const info = P.cards[card.id];
  const status = !info ? "New card" : info.interval >= 1 ? `Interval ${info.interval} day${info.interval === 1 ? "" : "s"}` : "Relearning";
  main.innerHTML = `
    <div class="deck">
      <div class="deck-stats" aria-live="polite">
        <span><b>${deck.queue.length}</b> left</span><span><b>${deck.done}</b> got it</span><span><b>${deck.again}</b> again</span>
      </div>
      <div class="card-stage">
        <button class="index-card ${deck.flipped ? "flipped" : ""}" id="card" aria-label="${deck.flipped ? "Answer side. Press to show the question." : "Question side. Press to show the answer."}">
          <div class="card-face card-front" aria-hidden="${deck.flipped}">
            <span class="card-box">${status}</span>
            <p class="card-topic">${topicNo(card.topic)}. ${esc(topicName(card.topic))}</p>
            <div class="card-text">${inlineCode(card.front)}</div>
            <p class="card-hint">Space or click to flip</p>
          </div>
          <div class="card-face card-back" aria-hidden="${!deck.flipped}">
            <div class="card-text">${inlineCode(card.back)}</div>
            <p class="card-hint">1 again, 2 good, 3 easy</p>
          </div>
        </button>
      </div>
      <div class="row">
        <button class="btn secondary" data-rating="again" ${deck.flipped ? "" : "disabled"}>Again <span class="kbd">1</span></button>
        <button class="btn" data-rating="good" ${deck.flipped ? "" : "disabled"}>Good <span class="kbd">2</span></button>
        <button class="btn secondary" data-rating="easy" ${deck.flipped ? "" : "disabled"}>Easy <span class="kbd">3</span></button>
      </div>
      <button class="link-btn small" id="deck-quit">Stop studying</button>
    </div>`;
  $("#card").addEventListener("click", flipCard);
  $$("[data-rating]", main).forEach(b => b.addEventListener("click", () => rateCard(b.dataset.rating)));
  $("#deck-quit").addEventListener("click", () => { deck = null; views.cards(); });
}

function flipCard() {
  deck.flipped = !deck.flipped;
  const el = $("#card");
  el.classList.toggle("flipped", deck.flipped);
  $$(".card-face", el).forEach((f, n) => f.setAttribute("aria-hidden", n === 0 ? deck.flipped : !deck.flipped));
  $$("[data-rating]", main).forEach(b => { b.disabled = !deck.flipped; });
}

async function rateCard(rating) {
  if (!deck.flipped) return;
  const id = deck.queue.shift();
  if (rating === "again") { deck.again++; deck.queue.splice(Math.min(deck.queue.length, 3), 0, id); }
  else deck.done++;
  deck.flipped = false;
  try { apply(await api("/api/card", { id, rating })); } catch { toast("Could not save the card result."); }
  renderCard();
}

/* ===================================================================== SQL lab */

function labDraft(sql) {
  if (sql === undefined) return store("lab-sql") ?? "SELECT e.employee_id, e.last_name, e.salary\nFROM   employees e\nORDER  BY e.salary DESC;";
  store("lab-sql", sql);
  return sql;
}

function schemaTables() {
  // Table and column names for autocomplete, from the schema the rail loads at startup.
  const tables = {};
  for (const t of schemaCache?.tables || []) tables[t.name.toLowerCase()] = t.columns.map(c => c.name.toLowerCase());
  return tables;
}

function makeEditor(textarea, { onRun, onChange }) {
  // CodeMirror when available (Oracle SQL highlighting, bracket matching, autocomplete with
  // Ctrl+Space or after a dot); otherwise the plain text area.
  if (!window.CodeMirror) {
    editorKeys(textarea, onRun);
    if (onChange) textarea.addEventListener("input", () => onChange(textarea.value));
    return {
      get: () => textarea.value,
      set: v => { textarea.value = v; onChange?.(v); },
      selection: () => textarea.value.slice(textarea.selectionStart, textarea.selectionEnd),
      onSelection: () => {},
      focus: () => textarea.focus(),
    };
  }
  const hint = cm => cm.showHint({ hint: CodeMirror.hint.sql, tables: schemaTables(), completeSingle: false });
  const cm = CodeMirror.fromTextArea(textarea, {
    mode: "text/x-plsql", lineNumbers: true, matchBrackets: true, autoCloseBrackets: true,
    indentUnit: 2, tabSize: 2, lineWrapping: true, viewportMargin: Infinity,
    extraKeys: { "Ctrl-Enter": () => onRun(), "Cmd-Enter": () => onRun(), "Ctrl-Space": hint, Tab: c => c.replaceSelection("  ") },
  });
  cm.on("inputRead", (c, change) => { if (change.text[0] === ".") hint(c); });
  if (onChange) cm.on("change", () => onChange(cm.getValue()));
  return {
    cm,
    get: () => cm.getValue(),
    set: v => cm.setValue(v),
    selection: () => cm.getSelection(),
    onSelection: fn => cm.on("cursorActivity", () => fn(!!cm.getSelection())),
    focus: () => cm.focus(),
  };
}

function editorKeys(textarea, onRun) {
  textarea.addEventListener("keydown", e => {
    if ((e.ctrlKey || e.metaKey) && e.key === "Enter") { e.preventDefault(); onRun(); }
    else if (e.key === "Tab" && !e.shiftKey) {
      e.preventDefault();
      const { selectionStart: s, selectionEnd: t, value } = textarea;
      textarea.value = value.slice(0, s) + "  " + value.slice(t);
      textarea.selectionStart = textarea.selectionEnd = s + 2;
    }
  });
}

function cellHtml(v) {
  if (v === null) return `<td class="null">null</td>`;
  const isNum = typeof v === "string" && /^-?\d+(\.\d+)?$/.test(v);
  // Leading or trailing spaces are invisible in a table: show them as dots (CHAR padding, TO_CHAR padding).
  const text = typeof v === "string" && v !== v.trim()
    ? `<span class="ws" title="Contains leading or trailing spaces">${esc(v).replace(/^ +| +$/g, m => "·".repeat(m.length))}</span>`
    : esc(v);
  return `<td class="${isNum ? "n" : ""}">${text}</td>`;
}

function gridHtml(columns, rows) {
  return `<div class="grid-wrap"><table class="grid">
    <thead><tr>${columns.map(c => `<th scope="col">${esc(c)}</th>`).join("")}</tr></thead>
    <tbody>${rows.map(r => `<tr>${r.map(cellHtml).join("")}</tr>`).join("")}</tbody>
  </table></div>`;
}

function explainHtml(x) {
  if (!x) return "";
  return `<div class="explain">
    <strong>${esc(x.code)}: ${esc(x.title)}</strong>
    <p>${inlineCode(x.text)}</p>
    ${x.hint ? `<p class="explain-hint">In your statement: ${inlineCode(x.hint)}</p>` : ""}
    <p class="small"><a href="#/notes" data-note-link="${esc(x.note)}">Read the notes on ${esc(topicName(x.topic))}</a></p>
  </div>`;
}

function changesHtml(ch) {
  const LIMIT = 10;
  const more = n => n > LIMIT ? `<p class="small muted">and ${n - LIMIT} more</p>` : "";
  const block = (label, cls, rows) => rows.length ? `<div class="changes ${cls}"><p class="small"><b>${label}</b></p>
    ${gridHtml(ch.columns, rows.slice(0, LIMIT))}${more(rows.length)}</div>` : "";
  // Updated rows: the first column (usually the key) and only the columns that changed.
  const shown = [0, ...new Set(ch.updated.flatMap(u => u.changed))].filter((c, i, all) => all.indexOf(c) === i);
  const updated = ch.updated.length ? `<div class="changes updated"><p class="small"><b>Updated in ${esc(ch.table)}</b> (before → after)</p>
    <div class="grid-wrap"><table class="grid"><thead><tr>${shown.map(i => `<th>${esc(ch.columns[i])}</th>`).join("")}</tr></thead><tbody>
    ${ch.updated.slice(0, LIMIT).map(u => `<tr>${shown.map(i => u.changed.includes(i)
      ? `<td class="changed"><s>${u.before[i] === null ? "null" : esc(u.before[i])}</s> ${u.after[i] === null ? "null" : esc(u.after[i])}</td>`
      : cellHtml(u.after[i])).join("")}</tr>`).join("")}
    </tbody></table></div>${more(ch.updated.length)}</div>` : "";
  return block(`Inserted into ${esc(ch.table)}`, "inserted", ch.inserted) + updated + block(`Deleted from ${esc(ch.table)}`, "deleted", ch.deleted);
}

function txHtml(tx) {
  if (!tx) return "";
  const state = tx.pending ? `${tx.pending} uncommitted row change${tx.pending === 1 ? "" : "s"}` : "No uncommitted changes";
  return `<div class="result-tx">${state}${tx.savepoints.length ? ` · savepoints: ${tx.savepoints.map(esc).join(", ")}` : ""}${tx.note ? `<b>${esc(tx.note)}</b>` : ""}</div>`;
}

function resultsHtml(res) {
  if (!res.ok) return `<div class="result"><div class="result-msg error">Cannot connect to the database.\n${esc(res.connect_error)}\n\nIs the oracle19.3 container running?</div></div>`;
  if (!res.results.length) return `<div class="empty">Nothing to run. Type a statement ending with a semicolon.</div>`;
  const out = res.results.map(r => {
    const sql = `<div class="result-sql">${esc(r.sql)}</div>`;
    if (r.type === "rows") {
      const foot = `${r.rows.length} row${r.rows.length === 1 ? "" : "s"}${r.truncated ? " shown (limit reached)" : ""}, ${r.ms} ms`;
      return `<div class="result">${sql}${r.rows.length ? gridHtml(r.columns, r.rows) : `<div class="result-msg">No rows selected.</div>`}<div class="result-foot">${foot}</div></div>`;
    }
    if (r.type === "error") return `<div class="result">${sql}<div class="result-msg error">${esc(r.error)}</div>${explainHtml(r.explain)}${txHtml(r.tx)}</div>`;
    if (r.type === "prompt") return `<div class="result"><div class="result-msg prompt">${esc(r.message)}</div></div>`;
    return `<div class="result">${sql}<div class="result-msg">${esc(r.message)}</div>${r.changes ? changesHtml(r.changes) : ""}${txHtml(r.tx)}</div>`;
  }).join("");
  const pending = res.results.filter(r => r.tx).at(-1)?.tx.pending;
  const end = res.kept ? "End of run: changes committed." : pending ? `End of run: ${pending} row change${pending === 1 ? "" : "s"} rolled back.` : "";
  return out + (end ? `<p class="small muted">${end}</p>` : "");
}

function vizHtml(v) {
  if (v.error) return `<div class="result"><div class="result-msg">${esc(v.error)}</div></div>`;
  if (v.kind === "set") {
    const what = { "UNION": "rows from either query, duplicates removed", "UNION ALL": "every row of both queries, duplicates kept",
      "INTERSECT": "distinct rows found in both queries", "MINUS": "distinct rows of the first query that the second query does not return" }[v.operator];
    return `<div class="result viz">
      <div class="result-msg"><b>${v.operator}</b> returns ${what}. NULLs count as equal here, unlike in a WHERE comparison.
        First query: ${v.totals[0]} rows, second: ${v.totals[1]}, result: ${v.totals[2]}.</div>
      <div class="grid-wrap"><table class="grid"><thead><tr>${v.columns.map(c => `<th>${esc(c)}</th>`).join("")}<th>In first</th><th>In second</th><th>In result</th></tr></thead>
      <tbody>${v.rows.map(r => `<tr class="${r.result ? "in-result" : "not-in-result"}">${r.cells.map(cellHtml).join("")}
        <td class="n">${r.first}</td><td class="n">${r.second}</td><td class="n"><b>${r.result}</b></td></tr>`).join("")}</tbody></table></div>
    </div>`;
  }
  const label = { matched: "matched", "null-extended": "kept with NULLs", dropped: "dropped" };
  const sideHtml = (side, other) => {
    const counts = Object.fromEntries(Object.keys(label).map(k => [k, side.rows.filter(r => r.status === k).length]));
    return `<div class="viz-side">
      <p class="small"><b>${esc(side.table)}${side.alias !== side.table ? ` ${esc(side.alias.toLowerCase())}` : ""}</b>:
        ${Object.keys(label).filter(k => counts[k]).map(k => `${counts[k]} ${label[k]}`).join(", ")}</p>
      <div class="grid-wrap"><table class="grid"><thead><tr><th></th>${side.columns.map(c => `<th>${esc(c)}</th>`).join("")}</tr></thead><tbody>
      ${side.rows.map(r => `<tr class="viz-${r.status}" data-rowid="${esc(r.rowid)}" data-partners="${esc(r.partners.join(" "))}" data-side="${esc(side.alias)}">
        <td class="viz-status">${r.status === "matched" ? `${r.partners.length}×` : r.status === "null-extended" ? "NULL" : "–"}</td>
        ${r.cells.map(cellHtml).join("")}</tr>`).join("")}
      </tbody></table></div></div>`;
  };
  return `<div class="result viz">
    <div class="result-msg"><b>${esc(v.join)}</b>: ${v.result_rows} joined row${v.result_rows === 1 ? "" : "s"} after the join and WHERE${v.grouped ? ", before GROUP BY or DISTINCT" : ""}.
      <span class="legend"><i class="viz-matched"></i>matched (the number of partner rows) <i class="viz-null-extended"></i>kept with NULLs by an outer join <i class="viz-dropped"></i>not in the result</span>
      <span class="small muted">Point at a row to see its partners.</span></div>
    <div class="viz-sides">${sideHtml(v.sides[0], v.sides[1])}${sideHtml(v.sides[1], v.sides[0])}</div>
  </div>`;
}

function diffHtml(columns, diff) {
  const label = { ok: "", extra: "not expected", missing: "missing", changed: "wrong value", moved: "wrong position" };
  const counts = Object.keys(label).filter(k => k !== "ok").map(k => [k, diff.filter(d => d.status === k).length]).filter(([, n]) => n);
  return `<p class="small">${counts.map(([k, n]) => `<span class="diff-tag diff-${k}">${n} ${label[k]}</span>`).join(" ")}</p>
    <div class="result"><div class="grid-wrap"><table class="grid diff">
    <thead><tr><th></th>${columns.map(c => `<th>${esc(c)}</th>`).join("")}</tr></thead>
    <tbody>${diff.map(d => `<tr class="diff-${d.status}"><td class="diff-mark">${label[d.status]}</td>${d.cells.map((v, i) =>
      d.status === "changed" && d.diff.includes(i)
        ? `<td class="changed" title="Expected: ${esc(d.expected[i] ?? "null")}">${v === null ? "null" : esc(v)} <span class="expected">→ ${d.expected[i] === null ? "null" : esc(d.expected[i])}</span></td>`
        : cellHtml(v)).join("")}</tr>`).join("")}</tbody>
    </table></div></div>`;
}

document.addEventListener("click", e => {
  const link = e.target.closest("[data-note-link]");
  if (!link) return;
  e.preventDefault();
  currentNote = link.dataset.noteLink;
  go("#/notes");
});

function bindViz(root) {
  root.querySelectorAll("tr[data-rowid]").forEach(tr => {
    tr.addEventListener("mouseenter", () => {
      const ids = new Set(tr.dataset.partners.split(" ").filter(Boolean));
      root.querySelectorAll("tr[data-rowid]").forEach(o => o.classList.toggle("hl", o === tr || (o.dataset.side !== tr.dataset.side && ids.has(o.dataset.rowid))));
    });
    tr.addEventListener("mouseleave", () => root.querySelectorAll("tr.hl").forEach(o => o.classList.remove("hl")));
  });
}

let schemaCache = null;
async function schemaHtml() {
  try {
    if (!schemaCache) schemaCache = await api("/api/schema");
    if (!schemaCache.ok) return `<p class="small muted">Schema unavailable: ${esc(schemaCache.error)}</p>`;
    return schemaCache.tables.map(t => `<details><summary>${esc(t.name)}</summary><ul>
      ${t.columns.map(c => `<li class="${c.nullable ? "" : "nn"}"><b>${esc(c.name.toLowerCase())}</b><span>${esc(c.type)}</span></li>`).join("")}
    </ul><button class="link-btn small" data-insert="${esc(t.name.toLowerCase())}">Insert SELECT</button></details>`).join("")
      + `<p class="small muted">* NOT NULL</p>`;
  } catch { return `<p class="small muted">Schema unavailable.</p>`; }
}

views.lab = async () => {
  main.innerHTML = `
    <h1>SQL lab</h1>
    <p class="lede">Runs against the ORASTUDY schema in your oracle19.3 container. Separate statements with semicolons; end PL/SQL blocks with a line containing only /. Select text to run only that part.</p>
    <div class="lab">
      <div>
        <div class="editor-wrap">
          <label class="sr-only" for="sql">SQL</label>
          <textarea class="editor" id="sql" spellcheck="false" autocapitalize="off" autocomplete="off">${esc(labDraft())}</textarea>
          <div class="editor-bar">
            <button class="btn" id="run">Run <span class="kbd">Ctrl+Enter</span></button>
            <button class="btn secondary" id="visualize" title="Show how the rows of two joined tables, or of two combined queries, end up in the result">Visualize</button>
            <label class="toggle"><input type="checkbox" id="keep" ${store("keep") ? "checked" : ""}> Keep changes (commit)</label>
            <span class="spacer"></span>
            <button class="link-btn" id="save-note">Save as note</button>
            <button class="link-btn" id="reset-data">Restore sample data</button>
          </div>
        </div>
        <p class="small muted" id="keep-note"></p>
        <div class="results" id="results"></div>
      </div>
      <aside class="schema panel" aria-label="Schema and history">
        <h3>Tables</h3><div id="schema">Loading…</div>
        <h3 style="margin-top:18px">History</h3><div id="history"></div>
      </aside>
    </div>`;
  const keep = $("#keep");
  const editor = makeEditor($("#sql"), { onRun: () => run(), onChange: v => labDraft(v) });
  editor.onSelection(has => { $("#run").firstChild.textContent = has ? "Run selection " : "Run "; });
  const note = () => { $("#keep-note").textContent = keep.checked
    ? "Changes are committed after each run."
    : "DML is rolled back after each run. DDL (CREATE, DROP, TRUNCATE...) always commits immediately, including DML before it."; };
  note();
  keep.addEventListener("change", () => { store("keep", keep.checked); note(); });

  const showHistory = list => {
    const items = [...(list || [])].reverse().slice(0, 20);
    $("#history").innerHTML = items.length ? `<ul class="history">${items.map((h, n) =>
      `<li><button class="link-btn" data-history="${n}" title="${esc(h.sql)}">${esc(h.sql.trim().split("\n")[0].slice(0, 60))}</button>
        <span class="small muted">${new Date(h.t * 1000).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}${h.errors ? ` · ${h.errors} error${h.errors === 1 ? "" : "s"}` : ""}</span></li>`).join("")}</ul>`
      : `<p class="small muted">Statements you run appear here.</p>`;
    $$("[data-history]", main).forEach(b => b.addEventListener("click", () => { editor.set(items[Number(b.dataset.history)].sql); editor.focus(); }));
  };
  showHistory(S.history);

  const run = async () => {
    const btn = $("#run");
    btn.disabled = true;
    $("#results").innerHTML = `<p class="muted">Running…</p>`;
    try {
      const res = await api("/api/run", { sql: editor.selection() || editor.get(), keep: keep.checked });
      $("#results").innerHTML = resultsHtml(res);
      S.history = res.history;
      showHistory(res.history);
      if (res.results?.some(r => /^\s*(CREATE|DROP|ALTER|RENAME)/i.test(r.sql) && r.type === "message")) {
        schemaCache = null;
        $("#schema").innerHTML = await schemaHtml();
      }
    } catch (err) { $("#results").innerHTML = `<div class="result"><div class="result-msg error">${esc(err.message)}</div></div>`; }
    btn.disabled = false;
  };
  $("#run").addEventListener("click", run);
  $("#visualize").addEventListener("click", async () => {
    $("#results").innerHTML = `<p class="muted">Tracing rows…</p>`;
    try {
      $("#results").innerHTML = vizHtml(await api("/api/visualize", { sql: editor.selection() || editor.get() }));
      bindViz($("#results"));
    } catch (err) { $("#results").innerHTML = `<div class="result"><div class="result-msg error">${esc(err.message)}</div></div>`; }
  });
  $("#save-note").addEventListener("click", async () => {
    const sql = editor.selection() || editor.get();
    if (!sql.trim()) return toast("Nothing to save.");
    const title = prompt("Title for this note:", sql.trim().split("\n")[0].slice(0, 60));
    if (title === null) return;
    try {
      const res = await api("/api/notes/save", { title, sql });
      currentNote = res.path;
      toast("Saved to your notes.");
    } catch { toast("Could not save the note."); }
  });
  $("#reset-data").addEventListener("click", async () => {
    if (!confirm("Drop the sample tables and recreate them with the original data? Other objects you created are kept.")) return;
    const res = await api("/api/reset-data", {});
    schemaCache = null;
    toast(res.ok ? "Sample data restored." : "Restore failed: " + res.error);
    $("#schema").innerHTML = await schemaHtml();
  });
  $("#schema").innerHTML = await schemaHtml();
  $("#schema").addEventListener("click", e => {
    const t = e.target.closest("[data-insert]");
    if (!t) return;
    editor.set(`SELECT *\nFROM   ${t.dataset.insert};`);
    editor.focus();
  });
};

/* ===================================================================== exercises */

let currentLab = null;

views.exercises = (arg) => {
  currentLab = (arg && L[arg]) ? arg : currentLab || C.labs[0].id;
  const lab = L[currentLab];
  const st = S.labs[lab.id];
  const kind = lab.kind || "query";
  const draft = store("ex:" + lab.id) ?? st?.last ?? (kind === "query" ? "SELECT \nFROM   \n" : "");
  const howGraded = {
    query: `Columns: <code>${esc(lab.columns)}</code>. ${lab.ordered ? "Row order is checked." : "Row order is not checked."}`,
    dml: "Write DML statements. They run in a transaction that is rolled back after checking, so the sample data never changes.",
    ddl: "Write DDL statements. DDL commits, so the checker drops the exercise's objects again after comparing them with the data dictionary.",
  }[kind];

  main.innerHTML = `
    <h1>Exercises</h1>
    <p class="lede">Checking runs your SQL and the reference solution against the database and compares the results. For queries, column names are not graded, column count and order are. For DML and DDL exercises, the resulting table state is compared.</p>
    <div class="ex-layout">
      <ul class="ex-list">${C.labs.map(l => {
        const s = S.labs[l.id];
        return `<li><button data-lab="${l.id}" aria-current="${l.id === lab.id}">
          <span class="status-dot ${s?.passed ? "passed" : s?.tries ? "tried" : ""}" aria-label="${s?.passed ? "Passed" : s?.tries ? "Attempted" : "Not attempted"}"></span>
          <span>${esc(l.title)}<small>${topicNo(l.topic)}. ${esc(topicName(l.topic))}</small></span></button></li>`;
      }).join("")}</ul>
      <section>
        <h2 style="margin-top:0">${esc(lab.title)}</h2>
        <p class="task">${inlineCode(lab.task)}</p>
        <p class="cols">${howGraded}</p>
        <div id="hint-box"></div>
        <div class="editor-wrap">
          <label class="sr-only" for="ex-sql">Your SQL</label>
          <textarea class="editor" id="ex-sql" spellcheck="false" autocapitalize="off">${esc(draft)}</textarea>
          <div class="editor-bar">
            <button class="btn" id="check-ex">Check <span class="kbd">Ctrl+Enter</span></button>
            ${kind === "ddl" ? "" : `<button class="btn secondary" id="run-ex">Run without checking</button>`}
            <span class="spacer"></span>
            ${lab.hint ? `<button class="link-btn" id="show-hint">Hint</button>` : ""}
            <button class="link-btn" id="show-solution">Show solution</button>
          </div>
        </div>
        <div class="results" id="ex-results">${st?.passed ? `<div class="verdict good"><strong>Passed earlier</strong><p>You solved this in ${st.tries} attempt${st.tries === 1 ? "" : "s"}.</p></div>` : ""}</div>
      </section>
    </div>`;

  const editor = makeEditor($("#ex-sql"), { onRun: () => check(), onChange: v => store("ex:" + lab.id, v) });
  const check = async () => {
    $("#ex-results").innerHTML = `<p class="muted">Checking…</p>`;
    const res = await api("/api/grade", { id: lab.id, sql: editor.get() });
    apply(await api("/api/progress"));
    let html;
    if (res.error) html = `<div class="verdict bad"><strong>Your ${kind === "query" ? "query" : "SQL"} did not run</strong><p class="mono">${esc(res.error)}</p></div>${explainHtml(res.explain)}`;
    else if (res.passed) html = `<div class="verdict good"><strong>Correct</strong><p>${res.feedback.length ? esc(res.feedback.join(" ")) : "Rows and order match the reference result."}</p></div>${gridHtml(res.columns, res.rows)}`;
    else html = `<div class="verdict bad"><strong>Not yet</strong><p>${esc(res.feedback.join(" "))}</p></div>
      ${res.diff ? `<h3>${kind === "query" ? "Your result compared with the expected one" : "State after your statements, compared with the expected state"}</h3>${diffHtml(res.columns, res.diff)}`
        : `<h3>${kind === "query" ? "Your result" : "State after your statements"}</h3><div class="result">${gridHtml(res.columns, res.rows)}</div>`}
      <details style="margin-top:12px"><summary>Show the expected result</summary><div class="result" style="margin-top:8px">${gridHtml(res.expected_columns, res.expected_rows)}</div></details>`;
    if (!res.passed && TUTOR.available) html += `<div class="tutor-box"><button class="link-btn" id="tutor-hint">Ask Claude for a hint (not the solution)</button></div>`;
    $("#ex-results").innerHTML = html;
    $("#tutor-hint")?.addEventListener("click", e => askTutor(e.target, "/api/tutor/lab", { id: lab.id, sql: editor.get() }));
    const dot = $(`[data-lab="${lab.id}"] .status-dot`);
    dot.className = "status-dot " + (S.labs[lab.id]?.passed ? "passed" : "tried");
  };
  $("#check-ex").addEventListener("click", check);
  $("#run-ex")?.addEventListener("click", async () => {
    $("#ex-results").innerHTML = resultsHtml(await api("/api/run", { sql: editor.get(), keep: false }));
  });
  $("#show-hint")?.addEventListener("click", () => {
    const strong = $("#hint-box .hint") && lab.hint2;
    $("#hint-box").innerHTML = `<p class="hint">${inlineCode(lab.hint)}</p>` + (strong ? `<p class="hint">${inlineCode(lab.hint2)}</p>` : "");
    if (lab.hint2) $("#show-hint").textContent = strong ? "Hints shown" : "Stronger hint";
  });
  $("#show-solution").addEventListener("click", () => {
    if (!S.labs[lab.id]?.tries && !confirm("You have not checked an attempt yet. Show the solution anyway?")) return;
    api("/api/lab-solution", { id: lab.id }).then(apply).catch(() => {});
    $("#hint-box").innerHTML = `<p class="small muted">Reference solution. Other correct queries are just as valid.</p><pre class="code"><code>${esc(lab.solution)}</code></pre>`;
  });
  $$("[data-lab]", main).forEach(b => b.addEventListener("click", () => go("#/exercises/" + b.dataset.lab)));
};

/* ===================================================================== mistakes */

views.review = () => {
  const list = mistakes();
  if (!list.length) {
    main.innerHTML = `<h1>Mistakes</h1>
      <div class="empty">No open mistakes. Wrong answers and lucky guesses collect here until you prove them.
        <div><button class="btn" id="to-quiz">Start a practice quiz</button></div></div>`;
    $("#to-quiz").addEventListener("click", () => go("#/quiz"));
    return;
  }
  const reasons = { confident: "Wrong while sure", wrong: "Wrong", guess: "Lucky guess" };
  main.innerHTML = `
    <h1>Mistakes</h1>
    <p class="lede">${list.length} open mistake${list.length === 1 ? "" : "s"}. One correct answer is not proof: a mistake is cleared after confident correct answers ("Sure" or "Think so") on ${P.proof_days} different days. Mistakes you were sure about come first, because they are misconceptions.</p>
    <div class="row" style="margin-bottom:22px"><button class="btn" id="retry-all">Retry ${Math.min(list.length, 20)}${list.length > 20 ? " most important" : ""}</button></div>
    <table class="topics"><tbody>
      ${list.map(m => {
        const q = Q[m.id];
        return `<tr>
        <td class="muted small" style="white-space:nowrap">${topicNo(q.topic)}. ${esc(topicName(q.topic))}</td>
        <td>${inlineCode(q.prompt)}</td>
        <td class="small"><span class="reason reason-${m.reason}">${reasons[m.reason]}</span></td>
        <td class="num muted small" title="Confident correct days since the last miss">${m.proof}/${P.proof_days}</td>
        <td class="num"><button class="link-btn" data-retry="${m.id}">Retry</button></td></tr>`;
      }).join("")}
    </tbody></table>
    <p class="small muted">To record a misconception in <code>app/notes/docs/mistakes.md</code>, ask Claude in the terminal.</p>`;
  $("#retry-all").addEventListener("click", () => startQuiz({ mode: "practice", ids: list.slice(0, 20).map(m => m.id), keepOrder: true }));
  $$("[data-retry]", main).forEach(b => b.addEventListener("click", () => startQuiz({ mode: "practice", ids: [b.dataset.retry] })));
};

/* ===================================================================== notes */

let currentNote = null;

views.notes = async () => {
  const list = await api("/api/notes");
  currentNote = currentNote && list.some(n => n.path === currentNote) ? currentNote : (list.find(n => n.path.includes("notes.md")) || list[0])?.path;
  main.innerHTML = `
    <h1>Notes</h1>
    <p class="lede">Lesson notes and plans from this repository. Edit the Markdown files and reload to see changes.</p>
    <div class="notes-layout">
      <ul class="ex-list">${list.map(n => `<li><button data-note="${esc(n.path)}" aria-current="${n.path === currentNote}"><span></span><span>${esc(n.title)}</span></button></li>`).join("")}</ul>
      <article class="note-body" id="note">Loading…</article>
    </div>`;
  $$("[data-note]", main).forEach(b => b.addEventListener("click", () => { currentNote = b.dataset.note; views.notes(); }));
  if (!currentNote) { $("#note").textContent = "No notes yet."; return; }
  const note = await api("/api/note?path=" + encodeURIComponent(currentNote));
  const isSql = currentNote.endsWith(".sql");
  if (isSql || !window.marked) $("#note").innerHTML = `<pre class="code"><code>${esc(note.text)}</code></pre>` + (isSql ? `<button class="btn secondary" id="open-lab">Open in SQL lab</button>` : "");
  else $("#note").innerHTML = window.marked.parse(note.text);
  $("#open-lab")?.addEventListener("click", () => { labDraft(note.text); go("#/lab"); });
};

/* ===================================================================== AI tutor */

views.tutor = async () => {
  const queue = await api("/api/tutor/queue").catch(() => []);
  const objectives = Object.keys(C.objectives);
  main.innerHTML = `
    <h1>AI tutor</h1>
    <p class="lede">Optional help from Claude: explanations of wrong answers in the quiz, hints for failed exercises, and new practice questions. Every generated question is run against your Oracle database first; only questions whose answer the database confirms reach the review queue, and only questions you accept join the question bank.</p>
    ${TUTOR.available ? `<p class="small muted">Using ${esc(TUTOR.model)}.</p>` : `<div class="empty">The tutor is not set up. ${esc(TUTOR.reason || "")}<br>
      <code>.venv/bin/pip install -r app/requirements-ai.txt</code>, then set <code>ANTHROPIC_API_KEY</code> and restart the app. Everything else works without it.</div>`}
    <h2>Generate questions</h2>
    <div class="panel">
      <div class="settings">
        <label class="field"><span>Objective</span><select id="gen-objective">${objectives.map(o => `<option value="${o}">${o} ${esc(C.objectives[o])}</option>`).join("")}</select></label>
        <label class="field"><span>How many</span><select id="gen-count">${[1, 2, 3, 4, 5].map(n => `<option ${n === 3 ? "selected" : ""}>${n}</option>`).join("")}</select></label>
      </div>
      <button class="btn" id="generate" ${TUTOR.available ? "" : "disabled"}>Generate and verify</button>
      <div id="gen-result"></div>
    </div>
    <h2>Review queue</h2>
    <div id="queue">${queueHtml(queue)}</div>`;
  const weakest = objectives.slice().sort((a, b) => P.objectives[a].estimate - P.objectives[b].estimate)[0];
  $("#gen-objective").value = weakest;
  $("#generate").addEventListener("click", async e => {
    e.target.disabled = true;
    $("#gen-result").innerHTML = `<p class="muted">Claude is writing questions, then each one is run against the database…</p>`;
    const res = await api("/api/tutor/generate", { objective: $("#gen-objective").value, count: Number($("#gen-count").value) }).catch(err => ({ error: err.message }));
    e.target.disabled = false;
    if (res.error) { $("#gen-result").innerHTML = `<p>${esc(res.error)}</p>`; return; }
    $("#gen-result").innerHTML = `<p>${res.added.length} verified and added to the review queue. ${res.rejected.length ? `${res.rejected.length} rejected:` : ""}</p>
      ${res.rejected.map(r => `<details><summary>${inlineCode(r.question.prompt)}</summary><ul>${r.problems.map(pr => `<li class="small">${esc(pr)}</li>`).join("")}</ul></details>`).join("")}`;
    $("#queue").innerHTML = queueHtml(await api("/api/tutor/queue"));
    bindQueue();
  });
  bindQueue();
};

function queueHtml(queue) {
  if (!queue.length) return `<div class="empty">No questions waiting for review.</div>`;
  return queue.map(({ question: q }) => `<article class="panel queue-item">
    <p class="small muted">${q.objective} ${esc(C.objectives[q.objective])} · ${esc(q.id)}</p>
    <p class="q-prompt">${inlineCode(q.prompt)}</p>
    ${q.code ? `<pre class="code"><code>${esc(q.code)}</code></pre>` : ""}
    <ol class="queue-options">${q.options.map((o, i) => `<li class="${q.answer.includes(i) ? "correct" : ""}">${inlineCode(o)}${q.answer.includes(i) ? " ✓" : ""}</li>`).join("")}</ol>
    <p class="small">${inlineCode(q.explanation)}</p>
    <p class="small muted">Verified on the database with ${q.answer_sql ? `<code>${esc(q.answer_sql)}</code>` : `try_sql raising ${esc(q.try_error)}`}.</p>
    <div class="row"><button class="btn" data-accept="${esc(q.id)}">Accept into the question bank</button><button class="btn secondary" data-reject="${esc(q.id)}">Reject</button></div>
  </article>`).join("");
}

function bindQueue() {
  $$("[data-accept], [data-reject]", main).forEach(b => b.addEventListener("click", async () => {
    const accept = !!b.dataset.accept;
    const res = await api(`/api/tutor/${accept ? "accept" : "reject"}`, { id: b.dataset.accept || b.dataset.reject });
    if (accept) { C = await api("/api/content"); C.questions.forEach(q => { Q[q.id] = q; }); toast("Added to the question bank."); }
    $("#queue").innerHTML = queueHtml(res.queue);
    bindQueue();
  }));
}

/* ===================================================================== keyboard */

document.addEventListener("keydown", e => {
  const tag = (e.target.tagName || "").toLowerCase();
  if (tag === "textarea" || tag === "select" || (tag === "input" && e.target.type !== "radio" && e.target.type !== "checkbox")) return;
  if (e.ctrlKey || e.metaKey || e.altKey) return;

  if (currentView === "cards" && deck && deck.queue.length) {
    if (e.key === " " || e.key === "Enter") { e.preventDefault(); flipCard(); }
    else if (e.key === "1") rateCard("again");
    else if (e.key === "2") rateCard("good");
    else if (e.key === "3") rateCard("easy");
    return;
  }
  if (currentView === "quiz" && quiz && !quiz.finished) {
    const n = Number(e.key);
    if (n >= 1 && n <= 8) {
      const inputs = $$("input[name=opt]", main);
      const inp = inputs[n - 1];
      if (inp && !inp.disabled) {
        inp.checked = inp.type === "checkbox" ? !inp.checked : true;
        inp.dispatchEvent(new Event("change"));
      }
    } else if (["s", "t", "g"].includes(e.key.toLowerCase())) {
      const conf = CONF.find(c => c[2].toLowerCase() === e.key.toLowerCase())[0];
      $(`[data-conf="${conf}"]:not([disabled])`, main)?.click();
      $(`[data-exam-conf="${conf}"]`, main)?.click();
    } else if (e.key === "Enter" && tag !== "button") {
      e.preventDefault();
      const next = $("#next") || $("#finish");
      if (next) next.click();
      else if ($("[data-conf]:not([disabled])", main)) toast("Choose how sure you are: S, T or G.");
    }
  }
});

/* ===================================================================== boot */

async function boot() {
  applyTheme(store("theme") || "auto");
  try {
    let snapshot;
    [C, snapshot] = await Promise.all([api("/api/content"), api("/api/progress")]);
    apply(snapshot);
  } catch {
    main.innerHTML = `<div class="empty">The study server is not responding. Start it with <code>.venv/bin/python app/server.py</code>.</div>`;
    return;
  }
  C.questions.forEach(q => { Q[q.id] = q; });
  C.labs.forEach(l => { L[l.id] = l; });
  C.flashcards.forEach(c => { CARD[c.id] = c; });
  TUTOR = await api("/api/tutor/status").catch(() => ({ available: false, reason: "Status unavailable." }));
  window.addEventListener("hashchange", route);
  route();
  api("/api/schema").then(r => {
    schemaCache = r.ok ? r : null;
    const el = $("#db-status");
    el.className = "rail-foot " + (r.ok ? "ok" : "down");
    el.textContent = r.ok ? "Connected to ORAPDB1" : "Database offline";
    if (!r.ok) el.title = r.error;
  }).catch(() => { $("#db-status").textContent = "Database offline"; });
}

boot();
