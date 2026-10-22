/* The app chrome around the views: exam picker, mistakes badge, database status, theme, and
   the navigation drawer on narrow screens. */

import { $, $$, esc } from "./core/dom.js";
import { api } from "./core/api.js";
import { store } from "./core/store.js";
import { t } from "./core/i18n.js";
import { currentUser, signOut } from "./core/session.js";
import { SQL_VIEWS } from "./core/roles.js";
import { C, P, A, mistakes, apply, loadContent, setDatabase, sqlOff, labOff, can, isGuest } from "./core/state.js";
import { route, currentView, refresh, onRoute } from "./core/router.js";
import { toast, toastError, confirmDialog } from "./ui/feedback.js";
import { setSchema } from "./ui/editor.js";
import { premiumTag, accountTag, accountPitch, signInUrl } from "./ui/widgets.js";
import { examPicker } from "./ui/exam-picker.js";

let onExamChange = () => {};

export function refreshNav() {
  const n = mistakes().length;
  const badge = $("#nav-mistakes");
  badge.hidden = !n;
  badge.textContent = n;
  badge.setAttribute("aria-label", t("{n} open", { n }));
}

export function applyTheme(theme) {
  store("theme", theme);
  if (theme === "auto") document.documentElement.removeAttribute("data-theme");
  else document.documentElement.dataset.theme = theme;
  // The browser bar colour: per theme, or back to following the system.
  $$('meta[name="theme-color"]').forEach(m => {
    const dark = theme === "dark" || (theme === "auto" && m.media.includes("dark"));
    m.content = dark ? "#0E1522" : "#EDF1F6";
  });
}

/* ---------------------------------------------------------------- exam track */

export function renderExamSwitch() {
  const usable = A?.usable;  // missing (an older snapshot): nothing is shown locked, the server still decides
  examPicker($("#exam-picker"), { exams: Object.values(C.exams), current: C.exam.code, onPick: switchExam,
    locked: code => Boolean(usable) && !usable.includes(code) });
  $("#topbar-exam").textContent = C.exam.code;
  // What the plan cannot use is marked in the rail: exercises need an account, the SQL lab Pro.
  for (const view of SQL_VIEWS) {
    const link = $(`#rail a[data-view="${view}"]`);
    link.querySelector(".premium-tag")?.remove();
    if (view === "exercises" && !can("exercises")) link.insertAdjacentHTML("beforeend", accountTag());
    if (view === "lab" && !can("sql_lab")) link.insertAdjacentHTML("beforeend", premiumTag());
  }
  renderGuestBar();
}

async function switchExam(code) {
  if (code === C.exam.code) return;
  if (P.active_mock && !await confirmDialog({
    title: t("Switch to {code}?", { code }),
    body: t("A mock exam is running on this exam track. It stays open and resumes when you switch back."),
    confirm: t("Switch exam"),
  })) return;
  try {
    apply(await api("/api/settings", { exam: code }));
    await loadContent();
    onExamChange();
    renderExamSwitch();
    await route();
    checkDatabase();
    toast(t("Now preparing for {code}.", { code: C.exam.code }));
  } catch (err) { toastError(t("Could not switch the exam. {error}", { error: err.message })); }
}

/** A guest sees, on every page, that a free account keeps their progress and unlocks more. */
function renderGuestBar() {
  let bar = $("#guest-bar");
  if (!isGuest()) { bar?.remove(); return; }
  if (bar) return;
  bar = document.createElement("div");
  bar.id = "guest-bar";
  bar.className = "guest-bar";
  bar.setAttribute("role", "note");
  bar.innerHTML = `<span><strong>${esc(t("You're browsing as a guest"))}.</strong> ${esc(accountPitch())}</span>
    <a class="btn small" href="/register">${esc(t("Create a free account"))}</a>`;
  $("#main").before(bar);
}

/** A link or button carrying the "Sign in" lock does not open its locked page for a guest: it goes to sign in,
    and back to that page afterwards. Capturing on the document runs before the router and the views' handlers. */
function guardAccountLocks() {
  document.addEventListener("click", e => {
    const target = e.target.closest("a, button");
    if (!target?.querySelector(".account-tag") || !isGuest()) return;
    e.preventDefault();
    e.stopImmediatePropagation();
    const href = target.tagName === "A" ? target.getAttribute("href") : null;
    location.assign(signInUrl(href?.startsWith("/") ? href : location.pathname));
  }, true);
}

/* ---------------------------------------------------------------- database */

export function checkDatabase() {
  const el = $("#db-status");
  setSchema(null);
  // Without SQL practice there is nothing to probe; "Database offline" stays for a real outage.
  if (labOff()) {  // the schema probe is part of the SQL lab
    setDatabase(null);
    el.className = "db-status";
    el.textContent = sqlOff() ? t("SQL practice unavailable") : t("SQL exercises ready");
    el.title = "";
    return;
  }
  api("/api/schema").then(r => {
    setSchema(r);
    setDatabase(r.ok ? r.database : null);
    el.className = "db-status " + (r.ok ? "ok" : "down");
    el.textContent = r.ok
      ? t("{product} {version} connected", { product: r.database.product, version: r.database.version.split(".").slice(0, 2).join(".") })
      : t("Database offline");
    el.title = r.ok ? `${r.database.dsn}, ${r.database.product} ${r.database.version}` : r.error;
    if (currentView() === "home") refresh();
  }).catch(() => {
    el.className = "db-status down";
    el.textContent = t("Database offline");
  });
}

/* ---------------------------------------------------------------- drawer */

function initDrawer() {
  const shell = $("#shell");
  const openBtn = $("#nav-open");
  const setOpen = open => {
    shell.classList.toggle("nav-open", open);
    openBtn.setAttribute("aria-expanded", open);
    $("#main").inert = open;
    if (open) $("#rail a[aria-current='page']")?.focus();
    else if (document.activeElement?.closest("#rail")) openBtn.focus();
  };
  openBtn.addEventListener("click", () => setOpen(true));
  $("#nav-close").addEventListener("click", () => setOpen(false));
  $("#scrim").addEventListener("click", () => setOpen(false));
  document.addEventListener("keydown", e => { if (e.key === "Escape" && shell.classList.contains("nav-open")) setOpen(false); });
  onRoute(() => { if (shell.classList.contains("nav-open")) setOpen(false); });
}

export function initShell({ onExamChange: handler }) {
  onExamChange = handler;
  renderExamSwitch();
  initDrawer();
  guardAccountLocks();
  const user = currentUser();
  $("#account-name").textContent = user.display_name;
  $("#account-email").textContent = user.role === "guest" ? t("Not registered yet") : user.email;
  $("#rail-account").title = user.role === "guest" ? "" : user.email;
  $("#nav-admin").hidden = user.role !== "admin";
  const signOutBtn = $("#sign-out");
  if (user.role === "guest") {  // a guest has nothing to leave: signing in keeps this session's progress
    signOutBtn.dataset.i18n = "Sign in";
    signOutBtn.textContent = t("Sign in");
    signOutBtn.addEventListener("click", () => location.assign("/login"));
  } else {
    signOutBtn.addEventListener("click", signOut);
  }
  onRoute(refreshNav);
}
