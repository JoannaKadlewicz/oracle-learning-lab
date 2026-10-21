/* Exercises: graded SQL tasks. Queries are compared on their rows, DML on the resulting table
   state, DDL over the data dictionary. */

import { $, $$, esc, inlineCode, icon, plural } from "../core/dom.js";
import { api } from "../core/api.js";
import { store } from "../core/store.js";
import { C, S, P, L, DB, apply, loadProgress, topicLabel, blockedOn23ai, sqlOff, NO_SQL } from "../core/state.js";
import { main, go, setTitle } from "../core/router.js";
import { confirmDialog } from "../ui/feedback.js";
import { pageHead, loading } from "../ui/widgets.js";
import { makeEditor } from "../ui/editor.js";
import { gridHtml, explainHtml, diffHtml, resultsHtml, errorBox } from "../ui/sql.js";

let currentLab = null;
let search = "";

export function resetExercise() { currentLab = null; search = ""; }

const KINDS = [["all", "All kinds"], ["query", "Query"], ["dml", "DML"], ["ddl", "DDL"], ["fix", "Fix the bug"]];
const STATUSES = [["all", "Any status"], ["open", "Not passed"], ["passed", "Passed"]];

const kindOf = lab => lab.kind || "query";
const kindLabel = lab => lab.starter ? "Fix the bug" : { query: "Query", dml: "DML", ddl: "DDL" }[kindOf(lab)];

function filtered(f) {
  const words = search.toLowerCase().split(/\s+/).filter(Boolean);
  return C.labs.filter(l => (f.topic === "all" || l.topic === f.topic)
    && (f.kind === "all" || (f.kind === "fix" ? !!l.starter : kindOf(l) === f.kind))
    && (f.status === "all" || (f.status === "passed") === !!S.labs[l.id]?.passed)
    && words.every(w => (l.title + " " + l.task).toLowerCase().includes(w)));
}

function statusOf(id) {
  const s = S.labs[id];
  return s?.passed ? "passed" : s?.tries ? "tried" : "";
}

function listHtml(shown, lab) {
  if (!shown.length) return `<p class="list-empty">No exercise matches. Clear the search or the filters.</p>`;
  return `<ul class="item-list">${shown.map(l => {
    const st = statusOf(l.id);
    return `<li><button data-lab="${l.id}" aria-current="${l.id === lab.id}">
      <span class="status-dot ${st}" role="img" aria-label="${st === "passed" ? "Passed" : st ? "Attempted" : "Not attempted"}"></span>
      <span>${esc(l.title)}<small>${esc(topicLabel(l.topic))}, ${kindLabel(l)}</small></span></button></li>`;
  }).join("")}</ul>`;
}

function pickerHtml(shown, lab) {
  const list = shown.some(l => l.id === lab.id) ? shown : [lab, ...shown];
  return list.map(l => `<option value="${l.id}" ${l.id === lab.id ? "selected" : ""}>${statusOf(l.id) === "passed" ? "✓ " : ""}${esc(l.title)}</option>`).join("");
}

function render(arg) {
  currentLab = (arg && L[arg]) ? arg : currentLab && L[currentLab] ? currentLab : C.labs[0].id;
  const lab = L[currentLab];
  setTitle(lab.title);
  const st = S.labs[lab.id];
  const kind = kindOf(lab);
  const off = sqlOff();
  const draft = store("ex:" + lab.id) ?? st?.last ?? lab.starter ?? (kind === "query" ? "SELECT \nFROM   \n" : "");
  const f = { topic: "all", kind: "all", status: "all", ...(store("ex-filter") || {}) };
  const shown = filtered(f);
  const pos = shown.findIndex(l => l.id === lab.id);
  const prev = pos > 0 ? shown[pos - 1] : null;
  const next = pos >= 0 && pos < shown.length - 1 ? shown[pos + 1] : null;
  const passedCount = C.labs.filter(l => S.labs[l.id]?.passed).length;
  const howGraded = {
    query: `Columns: <code>${esc(lab.columns)}</code>. ${lab.ordered ? "Row order is checked." : "Row order is not checked."}`,
    dml: "Write DML statements. They run in a transaction that is rolled back after checking, so the sample data never changes.",
    ddl: "Write DDL statements. DDL commits, so the checker drops the exercise's objects again after comparing them with the data dictionary.",
  }[kind];
  const select = (id, value, options) => `<select id="${id}" aria-label="${id.slice(2)}">${options.map(([v, label]) =>
    `<option value="${v}" ${value === v ? "selected" : ""}>${esc(label)}</option>`).join("")}</select>`;

  main.innerHTML = `
    ${pageHead("Exercises", `Your SQL and the reference solution both run on the database, and the results are compared. ${passedCount} of ${C.labs.length} passed.`)}
    <label class="list-picker field"><span>Exercise</span><select id="ex-picker">${pickerHtml(shown, lab)}</select></label>
    <div class="split">
      <nav class="split-list" aria-label="Exercises">
        <div class="split-tools">
          <input type="search" id="ex-search" placeholder="Search exercises" aria-label="Search exercises" value="${esc(search)}">
          <div class="filters">
            ${select("f-topic", f.topic, [["all", "All topics"], ...Object.keys(C.topics).map(t => [t, topicLabel(t)])])}
            ${select("f-kind", f.kind, KINDS)}
            ${select("f-status", f.status, STATUSES)}
          </div>
          <p class="split-count" id="ex-count" aria-live="polite">${plural(shown.length, "exercise")}</p>
        </div>
        <div class="split-scroll" id="ex-list">${listHtml(shown, lab)}</div>
      </nav>

      <section aria-labelledby="ex-title">
        <div class="ex-head">
          <h2 id="ex-title">${esc(lab.title)}</h2>
          <div class="ex-nav">
            <button class="icon-btn" id="ex-prev" ${prev ? "" : "disabled"} aria-label="Previous exercise" title="Previous exercise">${icon("prev")}</button>
            <button class="icon-btn" id="ex-next" ${next ? "" : "disabled"} aria-label="Next exercise" title="Next exercise">${icon("next")}</button>
          </div>
        </div>
        <p class="lab-tags">
          <span class="tag ${lab.starter ? "tag-fix" : ""}">${kindLabel(lab)}</span>
          <span class="tag">${esc(topicLabel(lab.topic))}</span>
          <span class="tag">Objective ${esc(lab.objective)}</span>
          ${st?.passed ? `<span class="level level-strong">Passed</span>` : ""}
        </p>
        ${lab.starter ? `<p class="small muted">The editor starts with a statement that has a mistake in it. Find it, fix it, and check.</p>` : ""}
        ${blockedOn23ai(lab) ? `<p class="callout">This exercise uses Oracle 23ai syntax, and your database is Oracle ${esc(DB.version)}. Run the app with <code>STUDY_DSN_23AI</code> set (see the README) to check it.</p>` : ""}
        <p class="task">${inlineCode(lab.task)}</p>
        <p class="cols">${howGraded}</p>
        <div id="hint-box"></div>
        <div class="editor-wrap">
          <textarea class="editor" id="ex-sql" aria-label="Your SQL" spellcheck="false" autocapitalize="off">${esc(draft)}</textarea>
          <div class="editor-bar">
            <button class="btn" id="check-ex" ${off ? "disabled" : ""}>Check <span class="kbd">Ctrl+Enter</span></button>
            ${kind === "ddl" ? "" : `<button class="btn secondary" id="run-ex" ${off ? "disabled" : ""}>Run without checking</button>`}
            <span class="links">
              ${lab.hint ? `<button class="link-btn" id="show-hint">Show a hint</button>` : ""}
              ${lab.starter ? `<button class="link-btn quiet" id="reset-starter">Restore the starter</button>` : ""}
              <button class="link-btn quiet" id="show-solution">Show solution</button>
            </span>
          </div>
        </div>
        ${off ? `<p class="editor-note">${NO_SQL}</p>` : ""}
        <div class="results" id="ex-results" aria-live="polite">${st?.passed ? `<div class="verdict good"><strong>Passed earlier</strong><p>You solved this in ${plural(st.tries, "attempt")}.</p></div>` : ""}</div>
      </section>
    </div>`;

  const editor = makeEditor($("#ex-sql"), { onRun: () => check(), onChange: v => store("ex:" + lab.id, v) });
  const results = $("#ex-results");

  const check = async () => {
    if (off) return;
    results.innerHTML = loading("Checking against the reference solution");
    let res;
    try {
      res = await api("/api/grade", { id: lab.id, sql: editor.get() });
      await loadProgress();
    } catch (err) { results.innerHTML = errorBox(err.message); return; }
    const what = kind === "query" ? "query" : "SQL";
    let html;
    if (res.error) {
      html = `<div class="verdict bad"><strong>Your ${what} did not run</strong><p class="mono">${esc(res.error)}</p></div>${explainHtml(res.explain) ? `<div class="result">${explainHtml(res.explain)}</div>` : ""}`;
    } else if (res.passed) {
      // Today's exercise: passing it ends today's session, so the way back to Today comes first.
      const today = P.plan.lab === lab.id;
      html = `<div class="verdict good"><strong>Correct</strong><p>${res.feedback.length ? esc(res.feedback.join(" ")) : "Rows and order match the reference result."}</p>
        ${today || next ? `<div class="row">${today ? `<a class="btn" href="/">Back to Today</a>` : ""}
          ${next ? `<button class="btn ${today ? "secondary" : ""}" id="go-next">Next exercise${icon("next")}</button>` : ""}</div>` : ""}</div>
        <div class="result">${gridHtml(res.columns, res.rows)}</div>`;
    } else {
      html = `<div class="verdict bad"><strong>Not yet</strong><p>${esc(res.feedback.join(" "))}</p></div>
        ${res.diff ? `<h3>${kind === "query" ? "Your result compared with the expected one" : "State after your statements, compared with the expected state"}</h3>${diffHtml(res.columns, res.diff)}`
          : `<h3>${kind === "query" ? "Your result" : "State after your statements"}</h3><div class="result">${gridHtml(res.columns, res.rows)}</div>`}
        <details class="disclosure"><summary>Show the expected result</summary><div class="result" style="margin-top:10px">${gridHtml(res.expected_columns, res.expected_rows)}</div></details>`;
    }
    results.innerHTML = html;
    $("#go-next")?.addEventListener("click", () => go("/exercises/" + next.id));
    const dot = $(`[data-lab="${lab.id}"] .status-dot`, main);
    if (dot) dot.className = "status-dot " + statusOf(lab.id);
  };

  $("#check-ex").addEventListener("click", check);
  $("#run-ex")?.addEventListener("click", async () => {
    results.innerHTML = loading("Running");
    try { results.innerHTML = resultsHtml(await api("/api/run", { sql: editor.get(), keep: false })); }
    catch (err) { results.innerHTML = errorBox(err.message); }
  });
  $("#show-hint")?.addEventListener("click", e => {
    const strong = $("#hint-box .hint") && lab.hint2;
    $("#hint-box").innerHTML = `<div class="hint"><p>${inlineCode(lab.hint)}</p></div>` + (strong ? `<div class="hint"><p>${inlineCode(lab.hint2)}</p></div>` : "");
    if (!lab.hint2 || strong) e.target.remove();
    else e.target.textContent = "Show a stronger hint";
  });
  $("#show-solution").addEventListener("click", async () => {
    if (!S.labs[lab.id]?.tries && !await confirmDialog({
      title: "Show the solution?",
      body: "You have not checked an attempt yet. Trying first makes the solution stick.",
      confirm: "Show solution", cancel: "Keep trying",
    })) return;
    api("/api/lab-solution", { id: lab.id }).then(apply).catch(() => {});
    $("#hint-box").innerHTML = `<p class="small muted">Reference solution. Other correct queries are just as valid.</p><pre class="code"><code>${esc(lab.solution)}</code></pre>`;
  });
  $("#reset-starter")?.addEventListener("click", () => { editor.set(lab.starter); store("ex:" + lab.id, lab.starter); editor.focus(); });
  $("#ex-prev").addEventListener("click", () => go("/exercises/" + prev.id));
  $("#ex-next").addEventListener("click", () => go("/exercises/" + next.id));
  $("#ex-picker").addEventListener("change", e => go("/exercises/" + e.target.value));

  const list = $("#ex-list");
  list.addEventListener("click", e => {
    const b = e.target.closest("[data-lab]");
    if (b) go("/exercises/" + b.dataset.lab);
  });
  $("[aria-current='true']", list)?.scrollIntoView({ block: "center" });

  // Search and filters update the list in place, so typing keeps focus.
  const refreshList = () => {
    const now = filtered({ topic: "all", kind: "all", status: "all", ...(store("ex-filter") || {}) });
    list.innerHTML = listHtml(now, lab);
    $("#ex-count").textContent = plural(now.length, "exercise");
    $("#ex-picker").innerHTML = pickerHtml(now, lab);
  };
  $("#ex-search").addEventListener("input", e => { search = e.target.value; refreshList(); });
  [["#f-topic", "topic"], ["#f-kind", "kind"], ["#f-status", "status"]].forEach(([sel, key]) => $(sel).addEventListener("change", e => {
    store("ex-filter", { ...f, ...(store("ex-filter") || {}), [key]: e.target.value });
    if (key === "topic" && e.target.value !== "all" && lab.topic !== e.target.value) {
      const first = C.labs.find(l => l.topic === e.target.value);
      if (first) return go("/exercises/" + first.id);
    }
    refreshList();
  }));
}

export const exercisesView = { title: "Exercises", render };
