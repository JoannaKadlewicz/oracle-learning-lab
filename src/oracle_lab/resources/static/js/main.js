/* Entry point: load progress and content, wire the shell and the views, start routing. */

import { esc } from "./core/dom.js";
import { initI18n, preferredLanguage, rememberedLanguage, explicitLanguage, clearExplicitLanguage, setAccountSaver, t } from "./core/i18n.js";
import { api } from "./core/api.js";
import { loadSession, currentUser } from "./core/session.js";
import { useUser } from "./core/store.js";
import { S, apply, loadProgress, loadContent } from "./core/state.js";
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
  const el = e.target;
  // The exam picker reads Enter, Space and letters itself (typeahead).
  const typing = el.isContentEditable || el.closest?.(".CodeMirror, dialog, .exam-picker")
    || ["TEXTAREA", "SELECT"].includes(el.tagName)
    || (el.tagName === "INPUT" && !["radio", "checkbox"].includes(el.type));
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

/** A language the learner clicked before signing in (by any method) replaces the account's, once. */
async function carryClickedLanguage() {
  const clicked = rememberedLanguage();
  if (!explicitLanguage() || !clicked) return;
  try {
    if (S?.settings?.language !== clicked) apply(await api("/api/settings", { language: clicked }));
    clearExplicitLanguage();
  } catch (err) { console.error(err); }  // the flag stays; the next start tries again
}

/** An account without a language takes the one this browser remembers (picked or used before sign-in). */
async function adoptRememberedLanguage() {
  const remembered = rememberedLanguage();
  if (S?.settings?.language || !remembered) return;
  try { apply(await api("/api/settings", { language: remembered })); }
  catch (err) { console.error(err); }  // the page still shows in the remembered language
}

async function boot() {
  setAccountSaver(async code => { apply(await api("/api/settings", { language: code })); });
  let languageReady = false;
  try {
    await loadSession();
    useUser(currentUser().id);
    await loadProgress();
    await carryClickedLanguage();
    await initI18n(preferredLanguage(S?.settings?.language));
    languageReady = true;
    await adoptRememberedLanguage();
    await loadContent();
  } catch (err) {
    console.error(err);
    if (!languageReady) await initI18n(preferredLanguage());
    main.innerHTML = `<div class="empty"><strong>${esc(t("The study server is not responding"))}</strong>
      <p>${esc(t("The app could not load. Reload, or try again in a minute."))}</p>
      <button class="btn" id="reload-app">${esc(t("Reload"))}</button></div>`;
    document.getElementById("reload-app").addEventListener("click", () => location.reload());
    return;
  }
  initShell({ onExamChange: () => { resetQuiz({ forgetPractice: true }); resetDeck(); resetExercise(); } });
  await startRouting();
  checkDatabase();
}

boot();

