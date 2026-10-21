/* Entry point: load progress and content, wire the shell and the views, start routing. */

import { esc } from "./core/dom.js";
import { loadSession, currentUser } from "./core/session.js";
import { useUser } from "./core/store.js";
import { loadProgress, loadContent } from "./core/state.js";
import { main, registerViews, startRouting, dispatchKey } from "./core/router.js";
import { initShell, checkDatabase } from "./shell.js";
import { homeView } from "./views/home.js";
import { quizView, mockView, resetQuiz } from "./views/quiz.js";
import { cardsView, resetDeck } from "./views/cards.js";
import { exercisesView, resetExercise } from "./views/exercises.js";
import { labView } from "./views/lab.js";
import { reviewView } from "./views/review.js";
import { progressView } from "./views/progress.js";
import { notesView, openNote } from "./views/notes.js";
import { settingsView } from "./views/settings.js";
import { adminView } from "./views/admin.js";

registerViews({
  home: homeView,
  quiz: quizView,
  mock: mockView,
  cards: cardsView,
  exercises: exercisesView,
  lab: labView,
  review: reviewView,
  progress: progressView,
  notes: notesView,
  settings: settingsView,
  admin: adminView,
});

// Single-key shortcuts (quiz options, flashcard ratings) never fire while typing.
document.addEventListener("keydown", e => {
  const t = e.target;
  const typing = t.isContentEditable || t.closest?.(".CodeMirror, dialog")
    || ["TEXTAREA", "SELECT"].includes(t.tagName)
    || (t.tagName === "INPUT" && !["radio", "checkbox"].includes(t.type));
  if (typing || e.ctrlKey || e.metaKey || e.altKey) return;
  dispatchKey(e);
});

// Links to notes from error explanations.
document.addEventListener("click", e => {
  const link = e.target.closest("[data-note-link]");
  if (!link) return;
  e.preventDefault();
  openNote(link.dataset.noteLink);
});

async function boot() {
  try {
    await loadSession();
    useUser(currentUser().id);
    await loadProgress();
    await loadContent();
  } catch (err) {
    main.innerHTML = `<div class="empty"><strong>The study server is not responding</strong>
      <p>${esc(err.message)} Start it with <code>.venv/bin/python app/server.py</code>, then reload this page.</p>
      <button class="btn" id="reload-app">Reload</button></div>`;
    document.getElementById("reload-app").addEventListener("click", () => location.reload());
    return;
  }
  initShell({ onExamChange: () => { resetQuiz(); resetDeck(); resetExercise(); } });
  await startRouting();
  checkDatabase();
}

boot();

