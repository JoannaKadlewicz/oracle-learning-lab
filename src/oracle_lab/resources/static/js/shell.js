/* The app chrome around the views: exam switcher, mistakes badge, database status, theme, and
   the navigation drawer on narrow screens. */

import { $, $$, esc } from "./core/dom.js";
import { api } from "./core/api.js";
import { store } from "./core/store.js";
import { currentUser, signOut } from "./core/session.js";
import { C, P, mistakes, apply, loadContent, setDatabase, dbLabel, sqlOff } from "./core/state.js";
import { route, currentView, refresh, onRoute } from "./core/router.js";
import { toast, toastError, confirmDialog } from "./ui/feedback.js";
import { setSchema } from "./ui/editor.js";

let onExamChange = () => {};

export function refreshNav() {
  const n = mistakes().length;
  const badge = $("#nav-mistakes");
  badge.hidden = !n;
  badge.textContent = n;
  badge.setAttribute("aria-label", `${n} open`);
}

export function applyTheme(theme) {
  store("theme", theme);
  if (theme === "auto") document.documentElement.removeAttribute("data-theme");
  else document.documentElement.dataset.theme = theme;
}

/* ---------------------------------------------------------------- exam track */

export function renderExamSwitch() {
  $("#exam-switch").innerHTML = Object.values(C.exams).map(x =>
    `<button data-exam="${x.code}" aria-pressed="${x.code === C.exam.code}">${esc(x.code)}<small>${dbLabel(x.code)}</small></button>`).join("");
  $("#topbar-exam").textContent = C.exam.code;
}

async function switchExam(code) {
  if (code === C.exam.code) return;
  if (P.active_mock && !await confirmDialog({
    title: `Switch to ${code}?`,
    body: "A mock exam is running on this exam track. It stays open and resumes when you switch back.",
    confirm: "Switch exam",
  })) return;
  try {
    apply(await api("/api/settings", { exam: code }));
    await loadContent();
    onExamChange();
    renderExamSwitch();
    await route();
    checkDatabase();
    toast(`Now preparing for ${C.exam.code}.`);
  } catch (err) { toastError(`Could not switch the exam. ${err.message}`); }
}

/* ---------------------------------------------------------------- database */

export function checkDatabase() {
  const el = $("#db-status");
  setSchema(null);
  // Without SQL practice there is nothing to probe; "Database offline" stays for a real outage.
  if (sqlOff()) {
    setDatabase(null);
    el.className = "db-status";
    el.textContent = "SQL practice unavailable";
    el.title = "";
    return;
  }
  api("/api/schema").then(r => {
    setSchema(r);
    setDatabase(r.ok ? r.database : null);
    el.className = "db-status " + (r.ok ? "ok" : "down");
    el.textContent = r.ok ? `Oracle ${r.database.version.split(".").slice(0, 2).join(".")} connected` : "Database offline";
    el.title = r.ok ? `${r.database.dsn}, Oracle ${r.database.version}` : r.error;
    if (currentView() === "home") refresh();
  }).catch(() => {
    el.className = "db-status down";
    el.textContent = "Database offline";
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
  $("#exam-switch").addEventListener("click", e => {
    const b = e.target.closest("[data-exam]");
    if (b) switchExam(b.dataset.exam);
  });
  initDrawer();
  const user = currentUser();
  $("#account-name").textContent = user.display_name;
  $("#account-email").textContent = user.email;
  $("#rail-account").title = user.email;
  $("#nav-admin").hidden = user.role !== "admin";
  $("#sign-out").addEventListener("click", signOut);
  onRoute(refreshNav);
}
