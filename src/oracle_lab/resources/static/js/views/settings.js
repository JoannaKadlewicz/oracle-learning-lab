/* Settings: exam date, daily study time, theme, and resetting progress. */

import { $, $$, esc } from "../core/dom.js";
import { api } from "../core/api.js";
import { store } from "../core/store.js";
import { C, P, apply } from "../core/state.js";
import { main } from "../core/router.js";
import { toast, toastError, confirmDialog } from "../ui/feedback.js";
import { pageHead, section } from "../ui/widgets.js";
import { applyTheme, refreshNav } from "../shell.js";

function render() {
  const settings = P.settings;
  const theme = store("theme") || "auto";
  main.innerHTML = `
    ${pageHead("Settings", `You are preparing for <b>${esc(C.exam.code)}</b>, ${esc(C.exam.name)}. Switch exams at the top of the menu; progress is kept for both.`)}
    <div class="settings">
      <div class="panel">
        <div class="setting">
          <div><h3><label for="exam-date">Exam date</label></h3><p>Your daily plan spreads the remaining questions over the days you have left.</p></div>
          <input type="date" id="exam-date" value="${esc(settings.exam_date || "")}">
        </div>
        <div class="setting">
          <div><h3><label for="daily-minutes">Study time per day</label></h3><p>How long today's session on the Today page should take.</p></div>
          <select id="daily-minutes">${[15, 30, 45, 60, 90, 120].map(m => `<option value="${m}" ${m === P.plan.minutes ? "selected" : ""}>${m} minutes</option>`).join("")}</select>
        </div>
        <div class="setting">
          <div><h3 id="theme-label">Appearance</h3><p>Automatic follows your system setting.</p></div>
          <div class="seg" role="group" aria-labelledby="theme-label">
            ${[["auto", "Automatic"], ["light", "Light"], ["dark", "Dark"]].map(([t, label]) => `<button data-theme="${t}" aria-pressed="${theme === t}">${label}</button>`).join("")}
          </div>
        </div>
      </div>

      ${section("About the two exams", `<p class="prose">1Z0-071 tests Oracle Database 19c behavior. 1Z0-171 (Oracle AI Database SQL Associate) tests the same SQL on 23ai and adds topic 15, the SQL features new in 23ai. Questions whose answer changed in 23ai are shown on 1Z0-071 only.</p>`)}

      <div class="panel danger-zone">
        <div class="setting">
          <div><h3>Reset progress</h3><p>Deletes every quiz answer, flashcard review, exercise result and mock exam of both exams. Your settings and SQL history are kept. Progress is saved in <code>app/state/progress.json</code>.</p></div>
          <button class="btn danger" id="reset-progress">Reset progress</button>
        </div>
      </div>
    </div>`;

  const save = async (body, message) => {
    try { apply(await api("/api/settings", body)); toast(message); }
    catch (err) { toastError(`Could not save the setting. ${err.message}`); }
  };
  $("#exam-date").addEventListener("change", e => save({ exam_date: e.target.value }, e.target.value ? "Exam date saved." : "Exam date cleared."));
  $("#daily-minutes").addEventListener("change", e => save({ daily_minutes: Number(e.target.value) }, "Study time saved."));
  $$("[data-theme]", main).forEach(b => b.addEventListener("click", () => {
    applyTheme(b.dataset.theme);
    $$("[data-theme]", main).forEach(x => x.setAttribute("aria-pressed", x === b));
  }));
  $("#reset-progress").addEventListener("click", async () => {
    if (!await confirmDialog({
      title: "Reset all progress?",
      body: "Every quiz answer, flashcard review, exercise result and mock exam is deleted. This cannot be undone.",
      confirm: "Reset progress", danger: true,
    })) return;
    try {
      apply(await api("/api/reset-progress", {}));
      refreshNav();
      toast("Progress reset.");
    } catch (err) { toastError(err.message); }
  });
}

export const settingsView = { title: "Settings", render };
