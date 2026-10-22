/* The first visit: before anything else a user picks a workspace (an exam track) from tiles. It becomes their
   workspace and the default; more than one comes with the Pro plan. Tiles for technologies without content yet
   ("coming soon") show where the app is going; they cannot be picked. */

import { $$, esc, icon } from "../core/dom.js";
import { t, tn } from "../core/i18n.js";
import { api } from "../core/api.js";
import { main } from "../core/router.js";
import { confirmDialog, toastError } from "../ui/feedback.js";
import { techLogo } from "../ui/tech-logos.js";

/** Not built yet: shown greyed, with a ribbon. [logo, name, one line] */
const COMING_SOON = () => [
  ["postgresql", "PostgreSQL", t("SQL on the most loved open-source database")],
  ["mysql", "MySQL", t("SQL for the web's favourite database")],
  ["sqlite", "SQLite", t("SQL in a single file")],
  ["pandas", "pandas", t("Data analysis in Python")],
  ["apachespark", "Apache Spark", t("PySpark DataFrames at scale")],
  ["duckdb", "DuckDB", t("Fast analytical SQL, in process")],
  ["snowflake", "Snowflake", t("Cloud data warehouse SQL")],
  ["googlebigquery", "Google BigQuery", t("Serverless SQL over huge tables")],
];

function soon([logo, name, line]) {
  return `<div class="ws-tile ws-soon" aria-disabled="true">
    <span class="ws-ribbon">${esc(t("Coming soon"))}</span>
    <span class="ws-tile-icon">${techLogo(logo)}</span>
    <strong class="ws-tile-title">${esc(name)}</strong>
    <span class="ws-tile-text">${esc(line)}</span>
  </div>`;
}

function tile(w) {
  return `<button type="button" class="ws-tile" data-workspace="${esc(w.code)}">
    <span class="ws-tile-icon">${techLogo(w.logo) || icon("lab")}</span>
    <strong class="ws-tile-title">${esc(w.title)}</strong>
    <span class="ws-tile-engine">${esc(w.engine)}</span>
    <span class="ws-tile-text">${esc(w.tile)}</span>
    <span class="ws-tile-meta">${esc(tn(w.questions, "{n} question on the exam", "{n} questions on the exam"))}</span>
  </button>`;
}

/** Fills the page with the tiles of `overview.workspaces`; picking one reloads the app inside it. */
export function workspacePicker(overview) {
  document.body.classList.add("picking");
  main.innerHTML = `
    <section class="ws-pick" aria-labelledby="ws-pick-title">
      <h1 id="ws-pick-title">${esc(t("Choose your workspace"))}</h1>
      <p class="ws-pick-lead">${esc(t("Pick what you want to learn first. It becomes your workspace; more than one comes with the Pro plan."))}</p>
      <div class="ws-grid">${overview.workspaces.map(tile).join("")}</div>
      <h2 class="ws-soon-title">${esc(t("Coming soon"))}</h2>
      <div class="ws-grid ws-grid-soon">${COMING_SOON().map(soon).join("")}</div>
    </section>`;
  $$("[data-workspace]", main).forEach(button => button.addEventListener("click", async () => {
    const w = overview.workspaces.find(x => x.code === button.dataset.workspace);
    if (!await confirmDialog({ title: t("Start with {title}?", { title: w.title }), confirm: t("Start learning"),
      body: t("{title} becomes your workspace. More workspaces come with the Pro plan.", { title: w.title }) })) return;
    try {
      await api("/api/workspaces/choose", { workspace: w.code });
      location.reload();
    } catch (err) { toastError(err.message); }
  }));
}
