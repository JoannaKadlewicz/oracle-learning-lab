/* Shared by the sign-in pages: JSON posts that never throw, password toggles and error display. */

import { $, $$ } from "/js/core/dom.js";
import {
  initI18n, preferredLanguage, translatePage, wireLanguageSwitch, lang, t, tn,
} from "/js/core/i18n.js";

/** Loads the page's language (remembered, else the browser's), fills the static texts and shows the page. */
export async function initAuthPage() {
  try {
    await initI18n(preferredLanguage(null));
    translatePage();
    wireLanguageSwitch();
  } finally {
    document.documentElement.classList.remove("i18n-pending");
  }
}

export async function postForm(path, data) {
  try {
    const res = await fetch(path, {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json", Accept: "application/json", "X-Language": lang() },
      body: JSON.stringify(data),
    });
    const body = await res.json().catch(() => ({}));
    if (res.ok) return { ok: true, next: body.next };
    const retry = Number.parseInt(res.headers.get("Retry-After") ?? "", 10);
    return {
      ok: false,
      status: res.status,
      error: body.error || t("Something went wrong. Please try again."),
      problems: Array.isArray(body.problems) ? body.problems : [],
      retryAfter: Number.isFinite(retry) ? retry : null,
    };
  } catch {
    return { ok: false, error: t("The study server is not responding."), problems: [], retryAfter: null };
  }
}

export async function getConfig() {
  try {
    const res = await fetch("/api/auth/config", { credentials: "same-origin", headers: { "X-Language": lang() } });
    if (res.ok) return await res.json();
  } catch { /* fall through to the safe defaults */ }
  return { google: false, registration_open: true };
}

/** Fills the page's `.auth-about` line from the exams the server offers; the static text stays on failure. */
export function fillAbout(config) {
  const el = document.querySelector(".auth-about");
  const exams = (config.exams || []).map(e => `${e.code} (${e.database})`);
  if (!el || !exams.length) return;
  // en-GB lists "A, B and C" (no comma before "and"), as the English text always did.
  const list = new Intl.ListFormat(lang() === "en" ? "en-GB" : lang(), { type: "conjunction" }).format(exams);
  el.textContent = t("Practice questions, flashcards and an SQL lab on your own database, for the {exams} exams.", { exams: list });
}

/** "Try again in 3 minutes." from a Retry-After in seconds. */
export function waitText(seconds) {
  if (!seconds) return "";
  const minutes = Math.max(1, Math.ceil(seconds / 60));
  return tn(minutes, "Try again in {n} minute.", "Try again in {n} minutes.");
}

export function showError(message, { focus = true } = {}) {
  const box = $("#form-error");
  box.textContent = message;
  box.hidden = !message;
  if (message && focus) box.focus();
}

export function showProblems(problems) {
  const list = $("#password-problems");
  if (!list) return;
  list.replaceChildren(...problems.map(text => Object.assign(document.createElement("li"), { textContent: text })));
  list.hidden = problems.length === 0;
  const input = $("#password");
  if (problems.length) input.setAttribute("aria-invalid", "true"); else input.removeAttribute("aria-invalid");
}

export function setBusy(form, busy) {
  const button = $("button[type=submit]", form);
  button.disabled = busy;
  form.setAttribute("aria-busy", String(busy));
}

export function disableForm(form) {
  $$("input, button", form).forEach(el => { el.disabled = true; });
}

export function wirePasswordToggles() {
  for (const toggle of $$(".pw-toggle")) {
    toggle.addEventListener("click", () => {
      const input = document.getElementById(toggle.getAttribute("aria-controls"));
      const show = input.type === "password";
      input.type = show ? "text" : "password";
      toggle.setAttribute("aria-pressed", String(show));
      toggle.textContent = show ? t("Hide") : t("Show");
    });
  }
}

/** First empty required field, focused; true when something was missing. */
export function focusFirstMissing(form) {
  const missing = $$("input[required]", form).find(el => !el.value.trim());
  if (missing) missing.focus();
  return Boolean(missing);
}

/** Links to the sibling page and Google keep the `next` the visitor was heading for. */
export function carryNext(next) {
  if (!next) return;
  const google = $("#google-link");
  if (google) {
    const url = new URL(google.getAttribute("href"), location.origin);
    url.searchParams.set("next", next);
    google.href = url.pathname + url.search;
  }
  const alt = $("#alt-link");
  if (alt) alt.href = `${alt.getAttribute("href")}?${new URLSearchParams({ next })}`;
}
