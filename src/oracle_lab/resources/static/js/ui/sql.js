/* Rendering of SQL results: grids, errors with explanations, DML changes, transaction state,
   the join/set visualizer and the exercise diff. */

import { esc, inlineCode, plural } from "../core/dom.js";
import { topicName } from "../core/state.js";
import { stepCaption } from "./sample.js";

/** The statement without its leading `--` comment lines (the original if nothing else is left). */
export function displaySql(sql) {
  const lines = String(sql).split("\n");
  const at = lines.findIndex(l => l.trim() && !l.trim().startsWith("--"));
  return at < 0 ? String(sql) : lines.slice(at).join("\n").trim();
}

export function cellHtml(v) {
  if (v === null) return `<td class="null">null</td>`;
  const isNum = typeof v === "string" && /^-?\d+(\.\d+)?$/.test(v);
  // Leading or trailing spaces are invisible in a table: show them as dots (CHAR padding, TO_CHAR padding).
  const text = typeof v === "string" && v !== v.trim()
    ? `<span class="ws" title="Contains leading or trailing spaces">${esc(v).replace(/^ +| +$/g, m => "·".repeat(m.length))}</span>`
    : esc(v);
  return `<td class="${isNum ? "n" : ""}">${text}</td>`;
}

export function gridHtml(columns, rows) {
  return `<div class="grid-wrap"><table class="grid">
    <thead><tr>${columns.map(c => `<th scope="col">${esc(c)}</th>`).join("")}</tr></thead>
    <tbody>${rows.map(r => `<tr>${r.map(cellHtml).join("")}</tr>`).join("")}</tbody>
  </table></div>`;
}

export function explainHtml(x) {
  if (!x) return "";
  return `<div class="explain">
    <strong>${esc(x.code)}: ${esc(x.title)}</strong>
    <p>${inlineCode(x.text)}</p>
    ${x.hint ? `<p class="explain-hint">In your statement: ${inlineCode(x.hint)}</p>` : ""}
    <p class="small"><a href="/notes" data-note-link="${esc(x.note)}">Read the notes on ${esc(topicName(x.topic))}</a></p>
  </div>`;
}

function changesHtml(ch) {
  const LIMIT = 10;
  const more = n => n > LIMIT ? `<p class="small muted">and ${n - LIMIT} more</p>` : "";
  const block = (label, cls, rows) => rows.length ? `<div class="changes ${cls}"><p class="small"><b>${label}</b></p>
    ${gridHtml(ch.columns, rows.slice(0, LIMIT))}${more(rows.length)}</div>` : "";
  // Updated rows: the first column (usually the key) and only the columns that changed.
  const shown = [0, ...new Set(ch.updated.flatMap(u => u.changed))].filter((c, i, all) => all.indexOf(c) === i);
  const updated = ch.updated.length ? `<div class="changes updated"><p class="small"><b>Updated in ${esc(ch.table)}</b> (before, then after)</p>
    <div class="grid-wrap"><table class="grid"><thead><tr>${shown.map(i => `<th>${esc(ch.columns[i])}</th>`).join("")}</tr></thead><tbody>
    ${ch.updated.slice(0, LIMIT).map(u => `<tr>${shown.map(i => u.changed.includes(i)
      ? `<td class="changed"><s>${u.before[i] === null ? "null" : esc(u.before[i])}</s> ${u.after[i] === null ? "null" : esc(u.after[i])}</td>`
      : cellHtml(u.after[i])).join("")}</tr>`).join("")}
    </tbody></table></div>${more(ch.updated.length)}</div>` : "";
  return block(`Inserted into ${esc(ch.table)}`, "inserted", ch.inserted) + updated + block(`Deleted from ${esc(ch.table)}`, "deleted", ch.deleted);
}

function txHtml(tx) {
  if (!tx) return "";
  const state = tx.pending ? `${plural(tx.pending, "uncommitted row change")}` : "No uncommitted changes";
  const savepoints = tx.savepoints.length ? `. Savepoints: ${tx.savepoints.map(esc).join(", ")}` : "";
  return `<div class="result-tx">${state}${savepoints}${tx.note ? `<b>${esc(tx.note)}</b>` : ""}</div>`;
}

export const errorBox = message => `<div class="result"><div class="result-msg error">${esc(message)}</div></div>`;

/** Whether an error is the one the statement is meant to show: the card's `expectError`, or a code
    named in the statement's own comment. */
function expectedError(error, caption, expectError) {
  const code = String(error).match(/\b[A-Z]{2,4}-\d{5}\b/)?.[0];
  return !!code && (code === expectError || caption.includes(code));
}

/** Results of a run, one block per statement. With several statements each block is a numbered
    step headed by its comment; `expectError` (a card's try_error) marks that error as intended. */
export function resultsHtml(res, { expectError } = {}) {
  if (!res.ok) return errorBox(`Cannot connect to the database.\n${res.connect_error}\n\nCheck that the database server is running.`);
  if (!res.results.length) return `<div class="empty"><strong>Nothing to run</strong><p>Type a statement ending with a semicolon.</p></div>`;
  const steps = res.results.length > 1;
  const out = res.results.map((r, n) => {
    const caption = r.sql ? stepCaption(r.sql) : "";
    const head = steps || caption
      ? `<div class="result-step">${steps ? `<b>Step ${n + 1}</b>` : ""}${steps && caption ? " · " : ""}${esc(caption)}</div>` : "";
    const sql = `${head}<div class="result-sql">${esc(displaySql(r.sql))}</div>`;
    if (r.type === "rows") {
      const foot = `${plural(r.rows.length, "row")}${r.truncated ? " shown (limit reached)" : ""} in ${r.ms} ms`;
      return `<div class="result">${sql}${r.rows.length ? gridHtml(r.columns, r.rows) : `<div class="result-msg">No rows selected.</div>`}<div class="result-foot">${foot}</div></div>`;
    }
    if (r.type === "error") {
      const expected = expectedError(r.error, caption, expectError);
      const note = expected ? `<p class="result-expected">Expected: the sample fails here on purpose.</p>` : "";
      return `<div class="result">${sql}<div class="result-msg ${expected ? "expected" : "error"}">${note}${esc(r.error)}</div>${explainHtml(r.explain)}${txHtml(r.tx)}</div>`;
    }
    if (r.type === "prompt") return `<div class="result">${head}<div class="result-msg prompt">${esc(r.message)}</div></div>`;
    return `<div class="result">${sql}<div class="result-msg">${esc(r.message)}</div>${r.changes ? changesHtml(r.changes) : ""}${txHtml(r.tx)}</div>`;
  }).join("");
  const pending = res.results.filter(r => r.tx).at(-1)?.tx.pending;
  const end = res.kept ? "End of run: changes committed."
    : pending ? `End of run: ${plural(pending, "row change")} rolled back.` : "";
  return out + (end ? `<p class="run-end">${end}</p>` : "");
}

export function vizHtml(v) {
  if (v.error) return `<div class="result"><div class="result-msg">${esc(v.error)}</div></div>`;
  if (v.kind === "set") {
    const what = {
      "UNION": "rows from either query, duplicates removed",
      "UNION ALL": "every row of both queries, duplicates kept",
      "INTERSECT": "distinct rows found in both queries",
      "MINUS": "distinct rows of the first query that the second query does not return",
    }[v.operator];
    return `<div class="result viz">
      <div class="result-msg"><b>${v.operator}</b> returns ${what}. NULLs count as equal here, unlike in a WHERE comparison.
        First query: ${plural(v.totals[0], "row")}, second: ${v.totals[1]}, result: ${v.totals[2]}.</div>
      <div class="grid-wrap"><table class="grid"><thead><tr>${v.columns.map(c => `<th>${esc(c)}</th>`).join("")}<th>In first</th><th>In second</th><th>In result</th></tr></thead>
      <tbody>${v.rows.map(r => `<tr class="${r.result ? "in-result" : "not-in-result"}">${r.cells.map(cellHtml).join("")}
        <td class="n">${r.first}</td><td class="n">${r.second}</td><td class="n"><b>${r.result}</b></td></tr>`).join("")}</tbody></table></div>
    </div>`;
  }
  const label = { matched: "matched", "null-extended": "kept with NULLs", dropped: "dropped" };
  const sideHtml = side => {
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
    <div class="result-msg"><b>${esc(v.join)}</b>: ${plural(v.result_rows, "joined row")} after the join and WHERE${v.grouped ? ", before GROUP BY or DISTINCT" : ""}.
      <span class="legend"><span><i class="viz-matched"></i>Matched (number of partner rows)</span><span><i class="viz-null-extended"></i>Kept with NULLs by an outer join</span><span><i class="viz-dropped"></i>Not in the result</span></span>
      <span class="small muted">Point at a row to see its partners.</span></div>
    <div class="viz-sides">${sideHtml(v.sides[0])}${sideHtml(v.sides[1])}</div>
  </div>`;
}

export function bindViz(root) {
  root.querySelectorAll("tr[data-rowid]").forEach(tr => {
    tr.addEventListener("mouseenter", () => {
      const ids = new Set(tr.dataset.partners.split(" ").filter(Boolean));
      root.querySelectorAll("tr[data-rowid]").forEach(o => o.classList.toggle("hl", o === tr || (o.dataset.side !== tr.dataset.side && ids.has(o.dataset.rowid))));
    });
    tr.addEventListener("mouseleave", () => root.querySelectorAll("tr.hl").forEach(o => o.classList.remove("hl")));
  });
}

export function diffHtml(columns, diff) {
  const label = { ok: "", extra: "not expected", missing: "missing", changed: "wrong value", moved: "wrong position" };
  const counts = Object.keys(label).filter(k => k !== "ok").map(k => [k, diff.filter(d => d.status === k).length]).filter(([, n]) => n);
  return `<p class="diff-tags">${counts.map(([k, n]) => `<span class="diff-tag diff-${k}">${n} ${label[k]}</span>`).join("")}</p>
    <div class="result"><div class="grid-wrap"><table class="grid diff">
    <thead><tr><th></th>${columns.map(c => `<th>${esc(c)}</th>`).join("")}</tr></thead>
    <tbody>${diff.map(d => `<tr class="diff-${d.status}"><td class="diff-mark">${label[d.status]}</td>${d.cells.map((v, i) =>
      d.status === "changed" && d.diff.includes(i)
        ? `<td class="changed" title="Expected: ${esc(d.expected[i] ?? "null")}">${v === null ? "null" : esc(v)} <span class="expected">expected ${d.expected[i] === null ? "null" : esc(d.expected[i])}</span></td>`
        : cellHtml(v)).join("")}</tr>`).join("")}</tbody>
    </table></div></div>`;
}
