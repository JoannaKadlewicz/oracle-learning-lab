/* The app chrome around the views: exam picker, mistakes badge, database status, theme, and
   the navigation drawer on narrow screens. */

import { $, $$ } from "./core/dom.js";
import { api } from "./core/api.js";
import { store } from "./core/store.js";
import { t } from "./core/i18n.js";
import { currentUser, signOut } from "./core/session.js";
import { SQL_VIEWS } from "./core/roles.js";
import { C, P, A, mistakes, apply, loadContent, setDatabase, sqlOff, subscribed } from "./core/state.js";
import { route, currentView, refresh, onRoute } from "./core/router.js";
import { toast, toastError, confirmDialog } from "./ui/feedback.js";
import { setSchema } from "./ui/editor.js";
import { premiumTag } from "./ui/widgets.js";
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
  // The SQL pages are marked Premium in a free workspace: redrawn on every switch.
  for (const view of SQL_VIEWS) {
    const link = $(`#rail a[data-view="${view}"]`);
    link.querySelector(".premium-tag")?.remove();
    if (!subscribed()) link.insertAdjacentHTML("beforeend", premiumTag());
  }
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

/* ---------------------------------------------------------------- database */

export function checkDatabase() {
  const el = $("#db-status");
  setSchema(null);
  // Without SQL practice there is nothing to probe; "Database offline" stays for a real outage.
  if (sqlOff()) {
    setDatabase(null);
    el.className = "db-status";
    el.textContent = t("SQL practice unavailable");
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
  const user = currentUser();
  $("#account-name").textContent = user.display_name;
  $("#account-email").textContent = user.email;
  $("#rail-account").title = user.email;
  $("#nav-admin").hidden = user.role !== "admin";
  $("#sign-out").addEventListener("click", signOut);
  onRoute(refreshNav);
}
