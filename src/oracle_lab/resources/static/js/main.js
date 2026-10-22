/* Entry point: load progress and content, wire the shell and the views, start routing. */

import { esc } from "./core/dom.js";
import {
  initI18n, preferredLanguage, rememberedLanguage, rememberLanguage, explicitLanguage, clearExplicitLanguage,
  setAccountSaver, translatePage, lang, t, DEFAULT_LANGUAGE,
} from "./core/i18n.js";
import { api } from "./core/api.js";
import { loadSession, currentUser } from "./core/session.js";
import { useUser } from "./core/store.js";
import { canRunSql, SQL_VIEWS } from "./core/roles.js";
import { empty } from "./ui/widgets.js";
import { S, apply, loadProgress, loadContent, noSql } from "./core/state.js";
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

const views = {
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
};

/** A free account reaching the SQL lab or the exercises by URL sees why, not a page it cannot use. */
const sqlOnly = view => Object.create(view, {
  render: { value: arg => canRunSql(currentUser()) ? view.render(arg)
    : void (main.innerHTML = empty(esc(t("Not included in your account")), esc(noSql()),
      `<a class="btn secondary" href="/">${esc(t("Go to Today"))}</a>`)) },
});
SQL_VIEWS.forEach(name => { views[name] = sqlOnly(views[name]); });
registerViews(views);

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

/** Fills the static texts of index.html in the chosen language and reveals the page (see the head script). */
function showPage() {
  translatePage();
  document.documentElement.classList.remove("i18n-pending");
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
    rememberLanguage(lang());  // the head script's hint for the next load, so it never flashes the other language
    // The first progress came before the language was known, so its texts (plan advice, badges) are English.
    if (lang() !== DEFAULT_LANGUAGE) await loadProgress();
    await loadContent();
  } catch (err) {
    console.error(err);
    if (!languageReady) await initI18n(preferredLanguage());
    showPage();
    main.innerHTML = `<div class="empty"><strong>${esc(t("The study server is not responding"))}</strong>
      <p>${esc(t("The app could not load. Reload, or try again in a minute."))}</p>
      <button class="btn" id="reload-app">${esc(t("Reload"))}</button></div>`;
    document.getElementById("reload-app").addEventListener("click", () => location.reload());
    return;
  }
  showPage();
  initShell({ onExamChange: () => { resetQuiz({ forgetPractice: true }); resetDeck(); resetExercise(); } });
  await startRouting();
  checkDatabase();
}

boot();

