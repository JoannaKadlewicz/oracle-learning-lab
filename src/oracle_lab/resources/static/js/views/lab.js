/* SQL lab: free SQL against the learning schema, with explanations, DML changes, the visualizer,
   history and the schema browser. */

import { $, $$, esc, plural, icon } from "../core/dom.js";
import { api } from "../core/api.js";
import { t, formatDate } from "../core/i18n.js";
import { store } from "../core/store.js";
import { S, DB, labOff, noLab, can, isGuest } from "../core/state.js";
import { main } from "../core/router.js";
import { toast, toastError, confirmDialog, promptDialog } from "../ui/feedback.js";
import { pageHead, loading, signInUrl } from "../ui/widgets.js";
import { makeEditor, schemaHtml, invalidateSchema } from "../ui/editor.js";
import { displaySql, resultsHtml, vizHtml, bindViz, errorBox } from "../ui/sql.js";
import { openNote } from "./notes.js";

const DEFAULT_SQL = "SELECT e.employee_id, e.last_name, e.salary\nFROM   employees e\nORDER  BY e.salary DESC;";

/** The lab's draft: read it, or replace it (other views open SQL in the lab this way). */
export function labDraft(sql) {
  if (sql === undefined) return store("lab-sql") ?? DEFAULT_SQL;
  store("lab-sql", sql);
  return sql;
}

/** Without the Pro plan the lab stays closed: a greyed-out preview of it, behind a lock that says what Pro adds.
    (The server refuses the lab's requests anyway.) */
function renderLocked() {
  const guest = isGuest();
  const sample = { ok: true, results: [{ type: "rows", sql: DEFAULT_SQL, ms: 4, columns: ["EMPLOYEE_ID", "LAST_NAME", "SALARY"],
    rows: [[100, "King", 24000], [101, "Kochhar", 17000], [102, "De Haan", 17000], [145, "Russell", 14000]] }] };
  main.innerHTML = `
    ${pageHead(esc(t("SQL lab")), esc(t("Run any SQL you like against your own copy of the sample schema.")))}
    <div class="paywall">
      <div class="paywall-preview" inert aria-hidden="true">
        <div class="editor-wrap">
          <textarea class="editor" id="sql" tabindex="-1">${esc(DEFAULT_SQL)}</textarea>
          <div class="editor-bar"><span class="btn">${esc(t("Run"))}</span><span class="btn secondary">${esc(t("Visualize rows"))}</span></div>
        </div>
        <div class="results">${resultsHtml(sample)}</div>
      </div>
      <section class="paywall-card" aria-labelledby="paywall-title">
        ${icon("lock")}
        <h2 id="paywall-title">${esc(t("The SQL lab needs a Pro subscription"))}</h2>
        <p>${esc(t("Write any query and see its rows, what your INSERT, UPDATE or DELETE changed, and how a join combines the rows of two tables."))}</p>
        <p class="paywall-note">${esc(guest
          ? t("Sign in to an account with the Pro plan. New here? A free account comes first and already checks 10 SQL exercises a day.")
          : t("Pro is assigned by an admin for now: ask yours to upgrade your account. Your free account checks 10 SQL exercises a day."))}</p>
        <div class="row">${guest
          ? `<a class="btn" href="${esc(signInUrl("/lab"))}">${esc(t("Sign in"))}</a>
             <a class="btn secondary" href="/register?${new URLSearchParams({ next: "/lab" })}">${esc(t("Create an account"))}</a>`
          : `<a class="btn" href="/exercises">${esc(t("Go to SQL exercises"))}</a>`}</div>
      </section>
    </div>`;
  makeEditor($("#sql"), { onRun: () => {} });
}

async function render() {
  if (!can("sql_lab")) return renderLocked();
  const off = labOff();
  const where = DB ? `${DB.product} ${DB.version.split(".").slice(0, 2).join(".")}` : t("your database");
  main.innerHTML = `
    ${pageHead(esc(t("SQL lab")), esc(t("Run any SQL against the learning schema on {where}. Separate statements with semicolons, end PL/SQL blocks with a line holding only {slash}, and select text to run only that part.", { where })).replace("{slash}", "<code>/</code>"))}
    <div class="lab">
      <div>
        <div class="editor-wrap">
          <textarea class="editor" id="sql" aria-label="SQL" spellcheck="false" autocapitalize="off" autocomplete="off">${esc(labDraft())}</textarea>
          <div class="editor-bar">
            <button class="btn" id="run" ${off ? "disabled" : ""}><span>${esc(t("Run"))}</span> <span class="kbd">Ctrl+Enter</span></button>
            <button class="btn secondary" id="visualize" ${off ? "disabled" : ""} title="${esc(t("Show how the rows of two joined tables, or of two combined queries, end up in the result"))}">${esc(t("Visualize rows"))}</button>
            <label class="check small"><input type="checkbox" id="keep" ${store("keep") ? "checked" : ""} ${off ? "disabled" : ""}> ${esc(t("Commit changes"))}</label>
            <span class="links">
              <button class="link-btn" id="save-note">${esc(t("Save as note"))}</button>
              <button class="link-btn quiet" id="reset-data" ${off ? "disabled" : ""}>${esc(t("Restore sample data"))}</button>
            </span>
          </div>
        </div>
        <p class="editor-note" id="keep-note"></p>
        <div class="results" id="results" aria-live="polite"></div>
      </div>
      <aside class="lab-side panel side-panel" aria-label="${esc(t("Tables and history"))}">
        <h3 ${off ? "hidden" : ""}>${esc(t("Tables"))}</h3><div class="schema" id="schema" ${off ? "hidden" : ""}>${off ? "" : loading(t("Loading tables"))}</div>
        <h3>${esc(t("History"))}</h3><div id="history"></div>
      </aside>
    </div>`;

  const keep = $("#keep");
  const results = $("#results");
  const editor = makeEditor($("#sql"), { onRun: () => run(), onChange: v => labDraft(v) });
  editor.onSelection(has => { $("#run span").textContent = has ? t("Run selection") : t("Run"); });
  const note = () => {
    $("#keep-note").textContent = off ? noLab() : keep.checked
      ? t("Changes are committed after each run.")
      : t("Changes are rolled back after each run. DDL (CREATE, DROP, TRUNCATE…) always commits at once, including any DML before it.");
  };
  note();
  keep.addEventListener("change", () => { store("keep", keep.checked); note(); });

  const showHistory = list => {
    const items = [...(list || [])].reverse().slice(0, 20);
    $("#history").innerHTML = items.length ? `<ul class="history">${items.map((h, n) =>
      `<li><button class="link-btn" data-history="${n}" title="${esc(h.sql)}">${esc(displaySql(h.sql).split("\n")[0].slice(0, 60))}</button>
        <span class="xsmall muted">${esc(formatDate(h.t * 1000, { hour: "2-digit", minute: "2-digit" }))}${h.errors ? `, ${esc(plural(h.errors, "error"))}` : ""}</span></li>`).join("")}</ul>`
      : `<p class="small muted">${esc(t("Statements you run appear here."))}</p>`;
    $$("[data-history]", main).forEach(b => b.addEventListener("click", () => { editor.set(items[Number(b.dataset.history)].sql); editor.focus(); }));
  };
  showHistory(S.history);

  const refreshSchema = async () => { invalidateSchema(); $("#schema").innerHTML = await schemaHtml(); };

  const run = async () => {
    if (off) return;
    const btn = $("#run");
    btn.disabled = true;
    results.innerHTML = loading(t("Running"));
    try {
      const res = await api("/api/run", { sql: editor.selection() || editor.get(), keep: keep.checked });
      results.innerHTML = resultsHtml(res);
      S.history = res.history;
      showHistory(res.history);
      if (res.results?.some(r => /^\s*(CREATE|DROP|ALTER|RENAME)/i.test(r.sql) && r.type === "message")) await refreshSchema();
    } catch (err) { results.innerHTML = errorBox(err.message); }
    btn.disabled = false;
  };
  $("#run").addEventListener("click", run);
  $("#visualize").addEventListener("click", async () => {
    if (off) return;
    results.innerHTML = loading(t("Tracing rows"));
    try {
      results.innerHTML = vizHtml(await api("/api/visualize", { sql: editor.selection() || editor.get() }));
      bindViz(results);
    } catch (err) { results.innerHTML = errorBox(err.message); }
  });
  $("#save-note").addEventListener("click", async () => {
    const sql = editor.selection() || editor.get();
    if (!sql.trim()) return toast(t("Type some SQL first."));
    const title = await promptDialog({
      title: t("Save as note"),
      body: t("The SQL is saved as a Markdown note under My notes."),
      label: t("Title"), value: sql.trim().split("\n")[0].slice(0, 60), confirm: t("Save note"),
    });
    if (title === null) return;
    try {
      const res = await api("/api/notes/save", { title, sql });
      openNote(res.path, false);
      toast(t("Saved to My notes."));
    } catch { toastError(t("Could not save the note.")); }
  });
  $("#reset-data").addEventListener("click", async () => {
    if (off) return;
    if (!await confirmDialog({
      title: t("Restore the sample data?"),
      body: t("The sample tables are dropped and created again with their original rows. Other objects you created are kept."),
      confirm: t("Restore sample data"), danger: true,
    })) return;
    try {
      const res = await api("/api/reset-data", {});
      if (res.ok) toast(t("Sample data restored.")); else toastError(t("Restore failed: {error}", { error: res.error }));
    } catch (err) { toastError(err.message); }
    await refreshSchema();
  });
  $("#schema").addEventListener("click", e => {
    const insert = e.target.closest("[data-insert]");
    if (!insert) return;
    editor.set(`SELECT *\nFROM   ${insert.dataset.insert};`);
    editor.focus();
  });
  if (!off) $("#schema").innerHTML = await schemaHtml();
}

export const labView = { get title() { return t("SQL lab"); }, render };
