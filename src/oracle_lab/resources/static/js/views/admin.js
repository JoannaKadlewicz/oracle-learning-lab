/* Admin: accounts (reset links, locks, roles, practice schemas, deletion), sign-up settings, removing inactive
   accounts, and the security events. The server enforces the role; this page only hides itself from others. */

import { $, $$, esc, plural } from "../core/dom.js";
import { api } from "../core/api.js";
import { main } from "../core/router.js";
import { currentUser } from "../core/session.js";
import { toast, toastError, confirmDialog, openDialog } from "../ui/feedback.js";
import { pageHead, section, empty, loading } from "../ui/widgets.js";

const METHOD_NAMES = { password: "Password", google: "Google" };
const EVENTS = [
  "login", "logout", "register", "password_changed", "password_set", "password_reset", "session_ended",
  "other_sessions_ended", "google_login", "google_link", "google_linked", "google_reauth", "google_unlinked",
  "account_deleted", "admin_bootstrapped", "legacy_import", "schema_provisioned", "schema_failed",
  "schema_drop_failed", "reset_link_created", "user_locked", "user_unlocked", "role_changed", "schema_recreated",
  "registration_settings_changed", "inactive_accounts_deleted",
];
const DAY = 86400;

let users = [];
let filters = { event: "", user_id: "" };
let inactiveDays = 180;
let eventsRequest = 0;  // only the newest events request may fill the table

const when = t => t ? new Date(t * 1000).toLocaleString(undefined,
  { day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" }) : "Never";
const emailOf = id => users.find(u => u.id === id)?.email;

async function render() {
  if (currentUser()?.role !== "admin") {
    main.innerHTML = empty("Page not found", "There is nothing here.", `<a class="btn secondary" href="/">Go to Today</a>`);
    return;
  }
  main.innerHTML = loading("Loading accounts…");
  let list, settings;
  try {
    [list, settings] = await Promise.all([api("/api/admin/users"), api("/api/admin/settings")]);
  } catch (err) {
    main.innerHTML = empty("The admin page could not be loaded", esc(err.message),
      `<button class="btn secondary" type="button" id="admin-retry">Try again</button>`);
    $("#admin-retry").addEventListener("click", render);
    return;
  }
  users = list.users;
  main.innerHTML = `
    ${pageHead("Admin", "Accounts, sign-up and the security events of this lab.")}
    <div class="admin">
      ${section("Accounts", `<div class="table-wrap" id="admin-users"></div>`, { aside: esc(plural(users.length, "account")) })}
      <div class="admin-panels">
        ${section("Sign-up", `<div class="panel" id="admin-registration"></div>`)}
        ${section("Inactive accounts", `<div class="panel danger-zone" id="admin-inactive"></div>`)}
      </div>
      ${section("Security events", `
        <div class="admin-filters fields">
          <label class="field"><span>Event</span><select id="ev-event">
            <option value="">All events</option>
            ${EVENTS.map(e => `<option value="${esc(e)}">${esc(e.replaceAll("_", " "))}</option>`).join("")}
          </select></label>
          <label class="field"><span>Account</span><select id="ev-user"></select></label>
          <button class="btn secondary" type="button" id="ev-refresh">Refresh</button>
        </div>
        <div class="table-wrap" id="admin-events">${loading("Loading events…")}</div>`, { aside: "Newest first, up to 200" })}
    </div>`;
  renderUsers();
  renderRegistration(settings);
  renderInactive();
  $("#ev-event").value = filters.event;
  $("#ev-event").addEventListener("change", e => { filters.event = e.target.value; loadEvents(); });
  $("#ev-user").addEventListener("change", e => { filters.user_id = e.target.value; loadEvents(); });
  $("#ev-refresh").addEventListener("click", loadEvents);
  $("#admin-users").addEventListener("click", e => {
    const b = e.target.closest("[data-manage]");
    if (b) manage(users.find(u => u.id === b.dataset.manage));
  });
  await loadEvents();
}

async function reloadUsers() {
  users = (await api("/api/admin/users")).users;
  if (!$("#admin-users")) return;
  renderUsers();
  renderInactive();
  const aside = $("#admin-users").closest(".section").querySelector(".section-head p");
  if (aside) aside.textContent = plural(users.length, "account");
}

/* ---------------------------------------------------------------- accounts */

function schemaText(s) {
  const size = s.size_mb == null ? "" : `, ${s.size_mb} MB`;
  return `<span class="schema schema-${esc(s.status)}" title="${esc(s.error || "")}">${esc(s.key)}: ${esc(s.status)}${esc(size)}</span>`;
}

function renderUsers() {
  const me = currentUser().id;
  $("#admin-users").innerHTML = `
    <table class="data admin-users">
      <thead><tr><th>Account</th><th>Role</th><th>Status</th><th>Last sign-in</th><th class="num">Sessions</th><th>Practice schemas</th><th class="actions"><span class="sr-only">Actions</span></th></tr></thead>
      <tbody>${users.map(u => `
        <tr>
          <td><div class="acct-cell"><strong>${esc(u.email)}</strong>${u.id === me ? ` <span class="tag tag-here">You</span>` : ""}
            <span class="muted small">${esc(u.methods.map(m => METHOD_NAMES[m] || m).join(", ") || "No sign-in method")}, joined ${esc(when(u.created_at))}</span></div></td>
          <td><span class="tag ${u.role === "admin" ? "tag-admin" : ""}">${u.role === "admin" ? "Admin" : "Learner"}</span></td>
          <td><span class="tag ${u.status === "locked" ? "tag-fix" : "tag-ok"}">${u.status === "locked" ? "Locked" : "Active"}</span></td>
          <td class="nowrap">${esc(when(u.last_login_at))}</td>
          <td class="num">${esc(u.sessions)}</td>
          <td>${u.schemas.length ? `<div class="schemas">${u.schemas.map(schemaText).join("")}</div>` : `<span class="muted small">None</span>`}</td>
          <td class="actions"><button class="btn secondary small" type="button" data-manage="${esc(u.id)}" aria-label="Manage ${esc(u.email)}">Manage</button></td>
        </tr>`).join("")}
      </tbody>
    </table>`;
}

/** The actions for one account, as a menu in a dialog (a dropdown would be clipped by the scrolling table). */
async function manage(user) {
  if (!user) return;
  const self = user.id === currentUser().id;
  const items = [["reset", "Create a password reset link", ""]];
  if (!self) {
    items.push(user.status === "locked" ? ["unlock", "Unlock the account", ""] : ["lock", "Lock the account", ""]);
    items.push(user.role === "admin" ? ["learner", "Remove admin rights", ""] : ["admin", "Make admin", ""]);
  }
  user.schemas.forEach(s => items.push([`schema:${s.key}`, `Recreate the ${s.key} practice schema`, ""]));
  if (!self) items.push(["delete", "Delete the account", "danger"]);
  const choice = await openDialog(`
    <h2>${esc(user.email)}</h2>
    <p>${user.role === "admin" ? "Admin" : "Learner"}, ${user.status === "locked" ? "locked" : "active"}. Last sign-in: ${esc(when(user.last_login_at))}.</p>
    <div class="action-list">
      ${items.map(([value, label, cls]) => `<button class="btn ${cls || "secondary"}" value="${esc(value)}">${esc(label)}</button>`).join("")}
    </div>
    <div class="row"><button type="button" class="btn ghost" data-close>Close</button></div>`);
  if (!choice || choice === "cancel") return;
  try {
    await act(user, choice);
  } catch (err) { toastError(err.message); }
}

async function act(user, choice) {
  const who = user.email;
  if (choice === "reset") {
    if (!await confirmDialog({ title: "Create a reset link?", confirm: "Create link",
      body: `Anyone with the link can set a new password for ${who} within 24 hours. It works once. Send it to them privately.` })) return;
    const { link } = await api("/api/admin/reset-link", { user_id: user.id });
    await showLink(link, who);
  } else if (choice === "lock") {
    if (!await confirmDialog({ title: `Lock ${who}?`, confirm: "Lock account", danger: true,
      body: "They are signed out everywhere and cannot sign in until you unlock the account." })) return;
    await api("/api/admin/lock", { user_id: user.id });
    toast("Account locked.");
  } else if (choice === "unlock") {
    if (!await confirmDialog({ title: `Unlock ${who}?`, confirm: "Unlock", body: "They can sign in again." })) return;
    await api("/api/admin/unlock", { user_id: user.id });
    toast("Account unlocked.");
  } else if (choice === "admin" || choice === "learner") {
    const promote = choice === "admin";
    if (!await confirmDialog({ title: promote ? `Make ${who} an admin?` : `Remove admin rights from ${who}?`,
      confirm: promote ? "Make admin" : "Remove admin rights", danger: promote,
      body: promote ? "Admins can see every account, lock and delete them, and change sign-up settings." : "They keep their progress and become a learner." })) return;
    await api("/api/admin/role", { user_id: user.id, role: choice });
    toast(promote ? "Admin rights granted." : "Admin rights removed.");
  } else if (choice.startsWith("schema:")) {
    const key = choice.slice(7);
    if (!await confirmDialog({ title: `Recreate the ${key} practice schema?`, confirm: "Recreate", danger: true,
      body: `Every table and row ${who} created in it is dropped, and a fresh schema with the sample data is created. This can take a minute.` })) return;
    toast("Recreating the practice schema…");
    const { schema } = await api("/api/admin/recreate-schema", { user_id: user.id, key });
    if (schema.status === "ready") toast("Practice schema recreated.");
    else toastError(`The practice schema could not be created. ${schema.error || ""}`);
  } else if (choice === "delete") {
    if (!await confirmDialog({ title: `Delete ${who}?`, confirm: "Delete account", danger: true,
      body: "Their account, progress, notes and practice schemas are deleted for good. This cannot be undone." })) return;
    await api("/api/admin/delete", { user_id: user.id });
    toast("Account deleted.");
  }
  await reloadUsers();
  loadEvents();
}

async function showLink(link, who) {
  await openDialog(`
    <h2>Reset link for ${esc(who)}</h2>
    <p>Copy it now: it is shown only once. It works once, within 24 hours.</p>
    <label class="field"><span>Reset link</span><input type="text" id="reset-link" readonly value="${esc(link)}"></label>
    <div class="row">
      <button type="button" class="btn secondary" id="copy-link">Copy link</button>
      <button class="btn" value="done">Done</button>
    </div>`, dialog => {
    const input = $("#reset-link", dialog);
    input.addEventListener("focus", () => input.select());
    const button = $("#copy-link", dialog);  // a toast would sit under the modal: the button says what happened
    button.addEventListener("click", async () => {
      let copied = false;
      try {
        await navigator.clipboard.writeText(input.value);
        copied = true;
      } catch {
        input.focus();
        input.select();
        try { copied = document.execCommand("copy"); } catch { copied = false; }
      }
      button.textContent = copied ? "Copied" : "Press Ctrl+C to copy";
    });
    input.select();
  });
}

/* ---------------------------------------------------------------- sign-up */

function renderRegistration(settings) {
  const panel = $("#admin-registration");
  let open = settings.registration_open;
  panel.innerHTML = `
    <div class="setting">
      <div><h3 id="reg-label">Registration</h3><p>Closed stops new sign-ups. Existing accounts keep working.</p></div>
      <div class="seg" role="group" aria-labelledby="reg-label">
        <button type="button" data-open="1" aria-pressed="${open}">Open</button>
        <button type="button" data-open="0" aria-pressed="${!open}">Closed</button>
      </div>
    </div>
    <div class="setting">
      <div><h3><label for="max-users">User limit</label></h3><p>Sign-up closes when this many accounts exist. ${esc(plural(settings.users, "account"))} now.</p></div>
      <input type="number" id="max-users" min="1" step="1" inputmode="numeric" value="${esc(settings.max_users)}">
    </div>
    <div class="form-actions"><button class="btn" type="button" id="save-registration">Save sign-up settings</button></div>`;
  $$("[data-open]", panel).forEach(b => b.addEventListener("click", () => {
    open = b.dataset.open === "1";
    $$("[data-open]", panel).forEach(x => x.setAttribute("aria-pressed", x === b));
  }));
  $("#save-registration").addEventListener("click", async () => {
    const max = Number($("#max-users").value);
    if (!Number.isInteger(max) || max < 1) { toastError("The user limit must be a whole number of at least 1."); return; }
    try {
      renderRegistration(await api("/api/admin/settings", { open, max_users: max }));
      toast(open ? "Registration is open." : "Registration is closed.");
      loadEvents();
    } catch (err) { toastError(err.message); }
  });
}

/* ---------------------------------------------------------------- inactive accounts */

function inactive(days) {
  const cutoff = Date.now() / 1000 - days * DAY;
  return users.filter(u => u.role !== "admin" && u.id !== currentUser().id && (u.last_login_at ?? u.created_at) < cutoff);
}

function renderInactive() {
  const panel = $("#admin-inactive");
  if (!panel) return;
  panel.innerHTML = `
    <div class="setting">
      <div><h3><label for="inactive-days">Delete accounts inactive for</label></h3>
        <p>Learners who have not signed in for this many days (or never, since they joined). Admins are never deleted.</p></div>
      <div class="days-input"><input type="number" id="inactive-days" min="1" step="1" inputmode="numeric" value="${esc(inactiveDays)}"><span>days</span></div>
    </div>
    <div class="form-actions"><button class="btn danger" type="button" id="delete-inactive">Delete inactive accounts</button>
      <span class="muted small" id="inactive-count" role="status"></span></div>`;
  const count = () => {
    const days = Number($("#inactive-days").value);
    $("#inactive-count").textContent = Number.isInteger(days) && days >= 1 ? `${plural(inactive(days).length, "account")} match.` : "";
  };
  $("#inactive-days").addEventListener("input", () => { inactiveDays = $("#inactive-days").value; count(); });
  count();
  $("#delete-inactive").addEventListener("click", async () => {
    const days = Number($("#inactive-days").value);
    if (!Number.isInteger(days) || days < 1) { toastError("Enter a number of days of at least 1."); return; }
    const n = inactive(days).length;
    if (!await confirmDialog({ title: `Delete accounts inactive for ${days} days?`, confirm: "Delete accounts", danger: true,
      body: `${n ? `About ${plural(n, "learner account")}` : "No learner accounts"} will be deleted with their progress, notes and practice schemas. This cannot be undone.` })) return;
    try {
      const { deleted } = await api("/api/admin/delete-inactive", { days });
      toast(`${plural(deleted, "account")} deleted.`);
      await reloadUsers();
      loadEvents();
    } catch (err) { toastError(err.message); }
  });
}

/* ---------------------------------------------------------------- events */

function detailText(detail) {
  return Object.entries(detail || {}).map(([k, v]) => {
    const email = (k === "target" || k === "actor") && emailOf(v);
    return `${k}=${typeof v === "string" ? v : JSON.stringify(v)}${email ? ` (${email})` : ""}`;
  }).join(" ");
}

async function loadEvents() {
  const box = $("#admin-events");
  if (!box) return;
  const select = $("#ev-user");
  select.innerHTML = `<option value="">All accounts</option>${users.map(u =>
    `<option value="${esc(u.id)}">${esc(u.email)}</option>`).join("")}`;
  select.value = users.some(u => u.id === filters.user_id) ? filters.user_id : "";
  const query = new URLSearchParams({ limit: "200" });
  if (filters.event) query.set("event", filters.event);
  if (select.value) query.set("user_id", select.value);
  const id = ++eventsRequest;
  let events;
  try {
    events = (await api(`/api/admin/events?${query}`)).events;
  } catch (err) {
    if (id === eventsRequest && $("#admin-events")) box.innerHTML = empty("Could not load the events", esc(err.message));
    return;
  }
  if (id !== eventsRequest || !$("#admin-events")) return;  // a newer request or another page took over
  if (!events.length) { box.innerHTML = empty("No events", "Nothing matches these filters."); return; }
  box.innerHTML = `
    <table class="data admin-events">
      <thead><tr><th>Time</th><th>Event</th><th>Outcome</th><th>Account</th><th>Address</th><th>Details</th></tr></thead>
      <tbody>${events.map(e => `
        <tr>
          <td class="nowrap">${esc(when(e.t))}</td>
          <td class="nowrap"><code>${esc(e.event)}</code></td>
          <td><span class="tag ${e.outcome === "ok" ? "tag-ok" : "tag-fix"}">${esc(e.outcome)}</span></td>
          <td class="ev-user">${esc(emailOf(e.user_id) || e.user_id || "-")}</td>
          <td class="nowrap" title="${esc(e.user_agent)}">${esc(e.ip || "-")}</td>
          <td class="ev-detail">${esc(detailText(e.detail))}</td>
        </tr>`).join("")}
      </tbody>
    </table>`;
}

export const adminView = { title: "Admin", render };
