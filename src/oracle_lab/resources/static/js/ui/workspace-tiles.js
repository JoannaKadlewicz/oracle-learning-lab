/* Workspace tiles, shared by the landing page (signed out) and the first-visit picker (signed in): a technology
   logo in its brand colour, the facts, how much material there is, and one action. Public: the landing page
   loads it before anyone signs in, so it imports only public modules. */

import { esc } from "/js/core/dom.js";
import { t, tn } from "/js/core/i18n.js";
import { techLogo } from "/js/ui/tech-logos.js";

/* Brand colours of the logo badges: [background, logo]. A badge is the brand colour with the logo on it, so it
   reads the same in light and dark themes. */
const BRANDS = {
  oracle: ["#C74634", "#FFFFFF"],
  postgresql: ["#336791", "#FFFFFF"],
  mysql: ["#00758F", "#FFFFFF"],
  sqlite: ["#0F80CC", "#FFFFFF"],
  pandas: ["#150458", "#FFCA00"],
  apachespark: ["#E25A1C", "#FFFFFF"],
  duckdb: ["#FFF000", "#1B1B1B"],
  snowflake: ["#29B5E8", "#FFFFFF"],
  googlebigquery: ["#4285F4", "#FFFFFF"],
};

/** Not built yet: shown greyed, with a "Coming soon" badge. [logo, name, one line] */
export const COMING_SOON = () => [
  ["postgresql", "PostgreSQL", t("SQL on the most loved open-source database")],
  ["mysql", "MySQL", t("SQL for the web's favourite database")],
  ["sqlite", "SQLite", t("SQL in a single file")],
  ["pandas", "pandas", t("Data analysis in Python")],
  ["apachespark", "Apache Spark", t("PySpark DataFrames at scale")],
  ["duckdb", "DuckDB", t("Fast analytical SQL, in process")],
  ["snowflake", "Snowflake", t("Cloud data warehouse SQL")],
  ["googlebigquery", "Google BigQuery", t("Serverless SQL over huge tables")],
];

/** The logo on its brand-coloured badge (a plain badge for an unknown technology). */
export function logoBadge(logo, size = "") {
  const [bg, fg] = BRANDS[logo] ?? ["var(--paper-3)", "var(--ink)"];
  return `<span class="logo-badge ${size}" style="--brand:${bg};--brand-ink:${fg}">${techLogo(logo)}</span>`;
}

function stats(w) {
  const c = w.counts;
  if (!c) return "";
  return `<ul class="ws-stats">
    <li>${esc(tn(c.questions, "{n} question", "{n} questions"))}</li>
    <li>${esc(tn(c.flashcards, "{n} flashcard", "{n} flashcards"))}</li>
    <li>${esc(tn(c.exercises, "{n} SQL exercise", "{n} SQL exercises"))}</li>
    ${w.minutes ? `<li>${esc(t("{n} min exam", { n: w.minutes }))}</li>` : ""}
  </ul>`;
}

/** A real workspace. `action` is the button text; the tile carries data-workspace for the caller's handler. */
export function workspaceTile(w, action) {
  const [bg] = BRANDS[w.logo] ?? ["var(--link)"];
  return `<button type="button" class="ws-tile" data-workspace="${esc(w.code)}" style="--brand:${bg}">
    <span class="ws-tile-head">${logoBadge(w.logo)}<span class="ws-tile-db">${esc(w.database ?? w.engine ?? "")}</span></span>
    <strong class="ws-tile-title">${esc(w.title)}</strong>
    <span class="ws-tile-text">${esc(w.tile)}</span>
    ${stats(w)}
    <span class="ws-tile-action">${esc(action)} <span aria-hidden="true">→</span></span>
  </button>`;
}

/** A technology without content yet. */
export function soonTile([logo, name, line]) {
  return `<div class="ws-tile ws-soon" aria-disabled="true">
    <span class="ws-tile-head">${logoBadge(logo, "small")}<span class="ws-ribbon">${esc(t("Coming soon"))}</span></span>
    <strong class="ws-tile-title">${esc(name)}</strong>
    <span class="ws-tile-text">${esc(line)}</span>
  </div>`;
}
