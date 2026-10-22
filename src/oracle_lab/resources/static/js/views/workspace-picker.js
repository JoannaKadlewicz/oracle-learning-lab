/* The first visit: before anything else a user picks a workspace (an exam track) from tiles. It becomes their
   free workspace and the default; the others need a subscription, which an admin gives. */

import { $$, esc, icon } from "../core/dom.js";
import { t, tn } from "../core/i18n.js";
import { api } from "../core/api.js";
import { main } from "../core/router.js";
import { confirmDialog, toastError } from "../ui/feedback.js";

function tile(w) {
  return `<button type="button" class="ws-tile" data-workspace="${esc(w.code)}">
    <span class="ws-tile-icon">${icon("lab")}</span>
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
      <p class="ws-pick-lead">${esc(t("Pick what you want to learn first. It becomes your free workspace, with daily quizzes, flashcards and the first lessons. The others need a subscription, which an admin can give you."))}</p>
      <div class="ws-grid">${overview.workspaces.map(tile).join("")}</div>
    </section>`;
  $$("[data-workspace]", main).forEach(button => button.addEventListener("click", async () => {
    const w = overview.workspaces.find(x => x.code === button.dataset.workspace);
    if (!await confirmDialog({ title: t("Start with {title}?", { title: w.title }), confirm: t("Start learning"),
      body: t("{title} becomes your free workspace. Other workspaces need a subscription.", { title: w.title }) })) return;
    try {
      await api("/api/workspaces/choose", { workspace: w.code });
      location.reload();
    } catch (err) { toastError(err.message); }
  }));
}
