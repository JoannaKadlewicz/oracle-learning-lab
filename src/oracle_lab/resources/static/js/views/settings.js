/* Settings: exam date, daily study time, theme, the account, and resetting progress. */

import { $, $$, esc } from "../core/dom.js";
import { api } from "../core/api.js";
import { lang, t, tn, formatDate, wireLanguageSwitch } from "../core/i18n.js";
import { store } from "../core/store.js";
import { C, P, apply } from "../core/state.js";
import { main } from "../core/router.js";
import { toast, toastError, confirmDialog, passwordDialog } from "../ui/feedback.js";
import { pageHead, section } from "../ui/widgets.js";
import { applyTheme, refreshNav } from "../shell.js";
import { clearUserStore } from "../core/store.js";
import { loadSession, currentUser } from "../core/session.js";

function render() {
  const settings = P.settings;
  const theme = store("theme") || "dark";  // the default before any choice, as in the pages' head script
  main.innerHTML = `
    ${pageHead(esc(t("Settings")), esc(t("You are preparing for {code}, {name}. Switch exams at the top of the menu; progress is kept for each exam.", { name: C.exam.name })).replace("{code}", `<b>${esc(C.exam.code)}</b>`))}
    <div class="settings">
      <div class="panel">
        <div class="setting">
          <div><h3><label for="exam-date">${esc(t("Exam date"))}</label></h3><p>${esc(t("Your daily plan spreads the remaining questions over the days you have left."))}</p></div>
          <input type="date" id="exam-date" value="${esc(settings.exam_date || "")}">
        </div>
        <div class="setting">
          <div><h3><label for="daily-minutes">${esc(t("Study time per day"))}</label></h3><p>${esc(t("How long today's session on the Today page should take."))}</p></div>
          <select id="daily-minutes">${[15, 30, 45, 60, 90, 120].map(m => `<option value="${m}" ${m === P.plan.minutes ? "selected" : ""}>${esc(tn(m, "{n} minute", "{n} minutes"))}</option>`).join("")}</select>
        </div>
        <div class="setting">
          <div><h3><label for="new-cards">${esc(t("New flashcards per day"))}</label></h3><p>${esc(t("How many cards you have not seen yet are added each day, on top of the reviews that are due. From 0 to 100."))}</p></div>
          <input type="number" id="new-cards" min="0" max="100" step="1" inputmode="numeric" value="${esc(settings.new_cards_per_day ?? 15)}">
        </div>
        <div class="setting">
          <div><h3 id="theme-label">${esc(t("Appearance"))}</h3><p>${esc(t("Automatic follows your system setting."))}</p></div>
          <div class="seg" role="group" aria-labelledby="theme-label">
            ${[["auto", t("Automatic")], ["light", t("Light")], ["dark", t("Dark")]].map(([key, label]) => `<button data-theme="${key}" aria-pressed="${theme === key}">${esc(label)}</button>`).join("")}
          </div>
        </div>
        <div class="setting">
          <div><h3 id="language-label">${esc(t("Language"))}</h3><p>${esc(t("The app and its questions switch to this language, and the page reloads."))}</p></div>
          <div class="seg" role="group" aria-labelledby="language-label">
            <button type="button" data-lang="en" lang="en">English</button>
            <button type="button" data-lang="pl" lang="pl">Polski</button>
          </div>
        </div>
      </div>

      <div class="panel" id="account"></div>

      ${section(esc(t("About the exams")), Object.values(C.exams).map(e => `<p class="prose"><b>${esc(e.code)}</b> (${esc(e.name)}): ${esc(e.about)}</p>`).join(""))}

      <div class="panel danger-zone">
        <div class="setting">
          <div><h3>${esc(t("Reset progress"))}</h3><p>${esc(t("Deletes every quiz answer, flashcard review, exercise result and mock exam of every exam. Your settings and SQL history are kept. Your progress is saved to your account."))}</p></div>
          <button class="btn danger" id="reset-progress">${esc(t("Reset progress"))}</button>
        </div>
      </div>
    </div>`;

  const save = async (body, message) => {
    try { apply(await api("/api/settings", body)); toast(message); }
    catch (err) { toastError(t("Could not save the setting. {error}", { error: err.message })); }
  };
  $("#exam-date").addEventListener("change", e => save({ exam_date: e.target.value }, e.target.value ? t("Exam date saved.") : t("Exam date cleared.")));
  $("#daily-minutes").addEventListener("change", e => save({ daily_minutes: Number(e.target.value) }, t("Study time saved.")));
  $("#new-cards").addEventListener("change", e => {
    const count = Number(e.target.value);
    if (e.target.value === "" || !Number.isInteger(count) || count < 0 || count > 100) {
      e.target.value = P.settings.new_cards_per_day ?? 15;
      return toastError(t("New flashcards per day must be a whole number from 0 to 100."));
    }
    save({ new_cards_per_day: count }, t("New flashcards per day saved."));
  });
  $$("[data-theme]", main).forEach(b => b.addEventListener("click", () => {
    applyTheme(b.dataset.theme);
    $$("[data-theme]", main).forEach(x => x.setAttribute("aria-pressed", x === b));
  }));
  wireLanguageSwitch($('[aria-labelledby="language-label"]'));
  $("#reset-progress").addEventListener("click", async () => {
    if (!await confirmDialog({
      title: t("Reset all progress?"),
      body: t("Every quiz answer, flashcard review, exercise result and mock exam is deleted. This cannot be undone."),
      confirm: t("Reset progress"), danger: true,
    })) return;
    try {
      apply(await api("/api/reset-progress", {}));
      refreshNav();
      toast(t("Progress reset."));
    } catch (err) { toastError(err.message); }
  });
  renderAccount();
  const googleError = new URLSearchParams(location.search).get("google_error");
  if (googleError !== null) {
    toastError(googleErrors()[googleError] || t("Google sign-in did not complete. Please try again."));
    history.replaceState(null, "", location.pathname + location.hash);
  }
}

/* ---------------------------------------------------------------- account */

// Why connecting or confirming with Google failed (google_error=<code>): fixed texts only.
const googleErrors = () => ({
  already_linked: t("This account is already connected to a Google account."),
  linked_elsewhere: t("This Google account is already connected to another account."),
  throttled: t("Too many attempts. Try again in a few minutes."),
});

const methodName = method => ({ password: t("Email and password"), google: "Google" }[method] ?? method);

/** "Chrome on Linux" from a user agent string; the rest of it is noise. */
export function deviceName(ua) {
  if (!ua) return t("Unknown device");
  const browser = /Edg\//.test(ua) ? "Edge" : /OPR\/|Opera/.test(ua) ? "Opera" : /Firefox\//.test(ua) ? "Firefox"
    : /Chrome\/|CriOS/.test(ua) ? "Chrome" : /Safari\//.test(ua) ? "Safari" : t("Browser");
  const os = /Android/.test(ua) ? "Android" : /iPhone|iPad|iOS/.test(ua) ? "iOS" : /Windows/.test(ua) ? "Windows"
    : /Mac OS X|Macintosh/.test(ua) ? "macOS" : /CrOS/.test(ua) ? "ChromeOS" : /Linux/.test(ua) ? "Linux" : "";
  return os ? t("{browser} on {os}", { browser, os }) : browser;
}

function ago(epochSeconds) {
  const s = Math.max(0, Date.now() / 1000 - epochSeconds);
  if (s < 90) return t("just now");
  if (s < 3600) return tn(Math.max(2, Math.round(s / 60)), "{n} minute ago", "{n} minutes ago");
  if (s < 86400) return tn(Math.round(s / 3600), "{n} hour ago", "{n} hours ago");
  return formatDate(epochSeconds * 1000, { day: "numeric", month: "short", year: "numeric" });
}

/** Shows a message (and password problems) in a form's alert area, as text only. */
function showFormError(box, err) {
  box.replaceChildren(Object.assign(document.createElement("span"), { textContent: err.message }));
  if (err.problems?.length) {
    const ul = document.createElement("ul");
    ul.append(...err.problems.map(p => Object.assign(document.createElement("li"), { textContent: p })));
    box.append(ul);
  }
  box.hidden = false;
}

async function renderAccount() {
  const panel = $("#account");
  if (!panel) return;
  let user = currentUser();
  let config = { google: false };
  let sessions = [];
  try {
    [config, sessions] = await Promise.all([
      fetch("/api/auth/config", { headers: { "X-Language": lang() } }).then(r => r.json()).catch(() => ({ google: false })),
      api("/api/account/sessions").then(r => r.sessions),
    ]);
  } catch (err) { toastError(t("Could not load your sessions. {error}", { error: err.message })); }
  if (!$("#account")) return;  // the person left the page meanwhile

  const hasPassword = user.methods.includes("password");
  const hasGoogle = user.methods.includes("google");
  const reauth = `/auth/google/start?intent=reauth&next=${encodeURIComponent("/settings")}`;
  const link = `/auth/google/start?intent=link&next=${encodeURIComponent("/settings")}`;

  panel.innerHTML = `
    <div class="setting">
      <div><h3>${esc(t("Account"))}</h3><p>${esc(user.display_name)}, <span class="acct-email">${esc(user.email)}</span></p></div>
      <span class="tag">${esc(user.role === "admin" ? t("Administrator") : t("Learner"))}</span>
    </div>
    <div class="setting">
      <div><h3>${esc(t("Sign-in methods"))}</h3><p>${esc(user.methods.map(methodName).join(", ") || t("None"))}</p></div>
      ${config.google && !hasGoogle ? `<a class="btn secondary" href="${esc(link)}">${esc(t("Connect Google"))}</a>` : ""}
      ${hasGoogle && hasPassword ? `<button class="btn secondary" id="google-unlink" type="button">${esc(t("Disconnect Google"))}</button>` : ""}
    </div>
    <div class="setting setting-form">
      <div><h3>${esc(hasPassword ? t("Change password") : t("Set a password"))}</h3>
        <p>${esc(hasPassword ? t("Changing it signs you out everywhere else.") : t("Your account signs in with Google only. A password lets you sign in with your email too. Confirm with Google first."))}</p></div>
      <form class="stack" id="password-form" autocomplete="off">
        ${hasPassword ? `<label class="field"><span>${esc(t("Current password"))}</span><input type="password" id="pw-current" autocomplete="current-password" required></label>` : ""}
        <label class="field"><span>${esc(t("New password"))}</span><input type="password" id="pw-new" autocomplete="new-password" required></label>
        <div class="form-error" id="pw-error" role="alert" hidden></div>
        <div class="form-actions">
          <button class="btn" type="submit">${esc(hasPassword ? t("Change password") : t("Set password"))}</button>
          ${!hasPassword && config.google ? `<a class="btn secondary" href="${esc(reauth)}">${esc(t("Confirm with Google"))}</a>` : ""}
        </div>
      </form>
    </div>
    <div class="setting setting-form">
      <div><h3>${esc(t("Active sessions"))}</h3><p>${esc(t("Browsers and devices signed in to this account."))}</p></div>
      <div class="sessions" id="sessions">
        ${sessions.map(s => `
          <div class="session">
            <div><strong>${esc(deviceName(s.user_agent))}</strong>${s.current ? `<span class="tag tag-here">${esc(t("This device"))}</span>` : ""}
              <span class="session-meta">${esc(t("{address}, active {when}", { address: s.ip || t("unknown address"), when: ago(s.last_seen) }))}</span></div>
            ${s.current ? "" : `<button class="btn secondary small" type="button" data-end="${esc(s.id)}">${esc(t("Sign out"))}</button>`}
          </div>`).join("")}
        ${sessions.length > 1 ? `<button class="btn secondary small" type="button" id="end-others">${esc(t("Sign out everywhere else"))}</button>` : ""}
      </div>
    </div>
    <div class="setting danger-row">
      <div><h3>${esc(t("Delete my account"))}</h3><p>${esc(hasPassword ? t("Deletes your account, progress, notes and practice schema for good.")
        : t("Deletes your account, progress, notes and practice schema for good. You will need to confirm with Google first."))}</p></div>
      <button class="btn danger" id="delete-account" type="button">${esc(t("Delete my account"))}</button>
    </div>`;

  const refresh = async () => {
    try { await loadSession(); } catch { toastError(t("Your session changed. Reload the page to continue.")); }
    await renderAccount();
  };

  $("#password-form").addEventListener("submit", async e => {
    e.preventDefault();
    const box = $("#pw-error");
    box.hidden = true;
    try {
      if (hasPassword) await api("/api/account/password", { current: $("#pw-current").value, new: $("#pw-new").value });
      else await api("/api/account/set-password", { new: $("#pw-new").value });
      await refresh();  // the session rotated: the CSRF token is new
      toast(hasPassword ? t("Password changed. Other devices were signed out.") : t("Password set."));
    } catch (err) { showFormError(box, err); }
  });
  $("#google-unlink")?.addEventListener("click", async () => {
    if (!await confirmDialog({ title: t("Disconnect Google?"), body: t("You will sign in with your email and password only."), confirm: t("Disconnect") })) return;
    try { await api("/api/account/google/unlink", {}); await refresh(); toast(t("Google disconnected.")); }
    catch (err) { toastError(err.message); }
  });
  $("#sessions").addEventListener("click", async e => {
    const end = e.target.closest("[data-end]");
    const others = e.target.closest("#end-others");
    if (!end && !others) return;
    try {
      if (end) await api("/api/account/sessions/end", { id: end.dataset.end });
      else await api("/api/account/sessions/end-others", {});
      await renderAccount();
      toast(end ? t("Session ended.") : t("Signed out everywhere else."));
    } catch (err) { toastError(err.message); }
  });
  $("#delete-account").addEventListener("click", async () => {
    const opts = { title: t("Delete your account?"), confirm: t("Delete my account"), danger: true,
      body: t("Your progress, notes and practice schema are deleted. This cannot be undone.") };
    let password = "";
    if (hasPassword) {
      password = await passwordDialog({ ...opts, body: `${opts.body} ${t("Enter your password to confirm.")}` });
      if (password === null) return;
    } else if (!await confirmDialog(opts)) return;
    try {
      await api("/api/account/delete", { password });
      clearUserStore();
      location.assign("/login");
    } catch (err) { toastError(err.message); }
  });
}

export const settingsView = { get title() { return t("Settings"); }, render };
