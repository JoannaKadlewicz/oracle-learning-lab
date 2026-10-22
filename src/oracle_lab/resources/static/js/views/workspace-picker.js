/* The first visit: before anything else a user picks a workspace (an exam track) from tiles. It becomes their
   workspace and the default; more than one comes with the Pro plan. Tiles for technologies without content yet
   ("coming soon") show where the app is going; they cannot be picked. */

import { $$, esc } from "../core/dom.js";
import { t } from "../core/i18n.js";
import { api } from "../core/api.js";
import { main } from "../core/router.js";
import { confirmDialog, toastError } from "../ui/feedback.js";
import { workspaceTile, soonTile, COMING_SOON } from "../ui/workspace-tiles.js";

/** Fills the page with the tiles of `overview.workspaces`; picking one reloads the app inside it. */
export function workspacePicker(overview) {
  document.body.classList.add("picking");
  main.innerHTML = `
    <section class="ws-pick" aria-labelledby="ws-pick-title">
      <h1 id="ws-pick-title">${esc(t("Choose your workspace"))}</h1>
      <p class="ws-pick-lead">${esc(t("Pick what you want to learn first. It becomes your workspace; more than one comes with the Pro plan."))}</p>
      <div class="ws-grid">${overview.workspaces.map(w => workspaceTile(w, t("Start learning"))).join("")}</div>
      <h2 class="ws-soon-title">${esc(t("Coming soon"))}</h2>
      <div class="ws-grid ws-grid-soon">${COMING_SOON().map(soonTile).join("")}</div>
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
