/* Admin: accounts (reset links, locks, roles, practice schemas, deletion), sign-up settings, removing inactive
   accounts, and the security events. The server enforces the role; this page only hides itself from others. */

import { $, $$, esc, plural } from "../core/dom.js";
import { api } from "../core/api.js";
import { t, tn, formatDate } from "../core/i18n.js";
import { main } from "../core/router.js";
import { currentUser } from "../core/session.js";
import { ROLES, roleLabel, roleSummary } from "../core/roles.js";
import { C } from "../core/state.js";
import { toast, toastError, confirmDialog, openDialog } from "../ui/feedback.js";
import { pageHead, section, empty, loading } from "../ui/widgets.js";

const methodName = method => ({ password: t("Password"), google: "Google" }[method] ?? method);
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

const when = time => time ? formatDate(time * 1000,
  { day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" }) : t("Never");
const emailOf = id => users.find(u => u.id === id)?.email;

async function render() {
  if (currentUser()?.role !== "admin") {
    main.innerHTML = empty(esc(t("Page not found")), esc(t("There is nothing here.")), `<a class="btn secondary" href="/">${esc(t("Go to Today"))}</a>`);
    return;
  }
  main.innerHTML = loading(t("Loading accounts…"));
  let list, settings;
  try {
    [list, settings] = await Promise.all([api("/api/admin/users"), api("/api/admin/settings")]);
  } catch (err) {
    main.innerHTML = empty(esc(t("The admin page could not be loaded")), esc(err.message),
      `<button class="btn secondary" type="button" id="admin-retry">${esc(t("Try again"))}</button>`);
    $("#admin-retry").addEventListener("click", render);
    return;
  }
  users = list.users;
  main.innerHTML = `
    ${pageHead(esc(t("Admin")), esc(t("Accounts, sign-up and the security events of this lab.")))}
    <div class="admin">
      ${section(esc(t("Accounts")), `<div class="table-wrap" id="admin-users"></div>`, { aside: esc(plural(users.length, "account")) })}
      <div class="admin-panels">
        ${section(esc(t("Sign-up")), `<div class="panel" id="admin-registration"></div>`)}
        ${section(esc(t("Inactive accounts")), `<div class="panel danger-zone" id="admin-inactive"></div>`)}
      </div>
      ${section(esc(t("Security events")), `
        <div class="admin-filters fields">
          <label class="field"><span>${esc(t("Event"))}</span><select id="ev-event">
            <option value="">${esc(t("All events"))}</option>
            ${EVENTS.map(e => `<option value="${esc(e)}">${esc(e.replaceAll("_", " "))}</option>`).join("")}
          </select></label>
          <label class="field"><span>${esc(t("Account"))}</span><select id="ev-user"></select></label>
          <button class="btn secondary" type="button" id="ev-refresh">${esc(t("Refresh"))}</button>
        </div>
        <div class="table-wrap" id="admin-events">${loading(t("Loading events…"))}</div>`, { aside: esc(t("Newest first, up to 200")) })}
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
  $("#admin-users").addEventListener("change", async e => {
    const select = e.target.closest("[data-role-of]");
    if (!select) return;
    const user = users.find(u => u.id === select.dataset.roleOf);
    try {
      if (await changeRole(user, select.value)) return;
    } catch (err) { toastError(err.message); }
    select.value = user.role;  // cancelled or refused: show the role the account still has
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
      <thead><tr><th>${esc(t("Account"))}</th><th>${esc(t("Role"))}</th><th>${esc(t("Workspaces"))}</th><th>${esc(t("Status"))}</th><th>${esc(t("Last sign-in"))}</th><th class="num">${esc(t("Sessions"))}</th><th>${esc(t("Practice schemas"))}</th><th class="actions"><span class="sr-only">${esc(t("Actions"))}</span></th></tr></thead>
      <tbody>${users.map(u => `
        <tr>
          <td><div class="acct-cell"><strong>${esc(u.email)}</strong>${u.id === me ? ` <span class="tag tag-here">${esc(t("You"))}</span>` : ""}
            <span class="muted small">${esc(t("{methods}, joined {date}", { methods: u.methods.map(methodName).join(", ") || t("No sign-in method"), date: when(u.created_at) }))}</span></div></td>
          <td>${roleCell(u, u.id === me)}</td>
          <td>${workspaceChips(u)}</td>
          <td><span class="tag ${u.status === "locked" ? "tag-fix" : "tag-ok"}">${esc(u.status === "locked" ? t("Locked") : t("Active"))}</span></td>
          <td class="nowrap">${esc(when(u.last_login_at))}</td>
          <td class="num">${esc(u.sessions)}</td>
          <td>${u.schemas.length ? `<div class="schemas">${u.schemas.map(schemaText).join("")}</div>` : `<span class="muted small">${esc(t("None"))}</span>`}</td>
          <td class="actions"><button class="btn secondary small" type="button" data-manage="${esc(u.id)}" aria-label="${esc(t("Manage {email}", { email: u.email }))}">${esc(t("Manage"))}</button></td>
        </tr>`).join("")}
      </tbody>
    </table>`;
}

/** Another account's role is a picker right in the table; your own is a tag (you can't change it). */
function roleCell(user, self) {
  if (self) return `<span class="tag ${user.role === "admin" ? "tag-admin" : ""}">${esc(roleLabel(user.role))}</span>`;
  return `<select class="role-select role-${esc(user.role)}" data-role-of="${esc(user.id)}" aria-label="${esc(t("Role of {email}", { email: user.email }))}">
    ${ROLES.map(r => `<option value="${esc(r)}"${r === user.role ? " selected" : ""}>${esc(roleLabel(r))}</option>`).join("")}
  </select>`;
}

const workspaceTitle = code => C.exams[code]?.title || code;
const levelLabel = level => ({ free: t("Free"), subscribed: t("Subscribed"), none: t("No access") }[level] ?? level);

/** The workspaces an account can open, each marked Free or Subscribed; admins have all of them. */
function workspaceChips(user) {
  if (user.role === "admin") return `<span class="muted small">${esc(t("All workspaces"))}</span>`;
  if (!user.workspaces.length) return `<span class="muted small">${esc(t("None yet"))}</span>`;
  return `<div class="ws-chips">${user.workspaces.map(w => `<span class="ws-chip ws-${esc(w.level)}">${esc(workspaceTitle(w.code))}
    <b>${esc(levelLabel(w.level))}</b></span>`).join("")}</div>`;
}

/** The actions for one account, as a menu in a dialog (a dropdown would be clipped by the scrolling table). */
async function manage(user) {
  if (!user) return;
  const self = user.id === currentUser().id;
  const items = [["reset", t("Create a password reset link"), ""]];
  if (!self) {
    items.push(user.status === "locked" ? ["unlock", t("Unlock the account"), ""] : ["lock", t("Lock the account"), ""]);
    items.push(["role", t("Change role"), ""]);
    if (user.role !== "admin") items.push(["workspaces", t("Workspaces"), ""]);
  }
  user.schemas.forEach(s => items.push([`schema:${s.key}`, t("Recreate the {key} practice schema", { key: s.key }), ""]));
  if (!self) items.push(["delete", t("Delete the account"), "danger"]);
  const choice = await openDialog(`
    <h2>${esc(user.email)}</h2>
    <p>${esc(t("{role}, {status}. Last sign-in: {date}.", { role: roleLabel(user.role),
      status: user.status === "locked" ? t("locked") : t("active"), date: when(user.last_login_at) }))}</p>
    <div class="action-list">
      ${items.map(([value, label, cls]) => `<button class="btn ${cls || "secondary"}" value="${esc(value)}">${esc(label)}</button>`).join("")}
    </div>
    <div class="row"><button type="button" class="btn ghost" data-close>${esc(t("Close"))}</button></div>`);
  if (!choice || choice === "cancel") return;
  try {
    await act(user, choice);
  } catch (err) { toastError(err.message); }
}

async function act(user, choice) {
  const who = user.email;
  if (choice === "reset") {
    if (!await confirmDialog({ title: t("Create a reset link?"), confirm: t("Create link"),
      body: t("Anyone with the link can set a new password for {who} within 24 hours. It works once. Send it to them privately.", { who }) })) return;
    const { link } = await api("/api/admin/reset-link", { user_id: user.id });
    await showLink(link, who);
  } else if (choice === "lock") {
    if (!await confirmDialog({ title: t("Lock {who}?", { who }), confirm: t("Lock account"), danger: true,
      body: t("They are signed out everywhere and cannot sign in until you unlock the account.") })) return;
    await api("/api/admin/lock", { user_id: user.id });
    toast(t("Account locked."));
  } else if (choice === "unlock") {
    if (!await confirmDialog({ title: t("Unlock {who}?", { who }), confirm: t("Unlock"), body: t("They can sign in again.") })) return;
    await api("/api/admin/unlock", { user_id: user.id });
    toast(t("Account unlocked."));
  } else if (choice === "workspaces") {
    await manageWorkspaces(user);
    return;
  } else if (choice === "role") {
    const role = await pickRole(user);
    if (role) await changeRole(user, role);  // reloads the accounts itself
    return;
  } else if (choice.startsWith("schema:")) {
    const key = choice.slice(7);
    if (!await confirmDialog({ title: t("Recreate the {key} practice schema?", { key }), confirm: t("Recreate"), danger: true,
      body: t("Every table and row {who} created in it is dropped, and a fresh schema with the sample data is created. This can take a minute.", { who }) })) return;
    toast(t("Recreating the practice schema…"));
    const { schema } = await api("/api/admin/recreate-schema", { user_id: user.id, key });
    if (schema.status === "ready") toast(t("Practice schema recreated."));
    else toastError(t("The practice schema could not be created. {error}", { error: schema.error || "" }));
  } else if (choice === "delete") {
    if (!await confirmDialog({ title: t("Delete {who}?", { who }), confirm: t("Delete account"), danger: true,
      body: t("Their account, progress, notes and practice schemas are deleted for good. This cannot be undone.") })) return;
    await api("/api/admin/delete", { user_id: user.id });
    toast(t("Account deleted."));
  }
  await reloadUsers();
  loadEvents();
}

/** The three roles as choices, each with what it allows; the current one is marked. Resolves to the picked role. */
async function pickRole(user) {
  const choice = await openDialog(`
    <h2>${esc(t("Change the role of {who}", { who: user.email }))}</h2>
    <div class="role-choices">
      ${ROLES.map(r => `<button class="role-choice${r === user.role ? " current" : ""}" value="${esc(r)}"${r === user.role ? ` aria-current="true" disabled` : ""}>
        <strong>${esc(roleLabel(r))}${r === user.role ? ` <span class="tag">${esc(t("Current"))}</span>` : ""}</strong>
        <span class="muted small">${esc(roleSummary(r))}</span></button>`).join("")}
    </div>
    <div class="row"><button type="button" class="btn ghost" data-close>${esc(t("Cancel"))}</button></div>`);
  return ROLES.includes(choice) && choice !== user.role ? choice : null;
}

/** Confirms and applies a role change; true when the account now has `role`. */
async function changeRole(user, role) {
  if (!user || role === user.role) return false;
  const who = user.email, name = roleLabel(role);
  const body = {
    admin: t("Admins can see every account, lock and delete them, change sign-up settings, and use every workspace."),
    user: t("They keep their progress and their workspaces, and lose the admin page."),
  }[role];
  if (!await confirmDialog({ title: t("Change the role of {who} to {role}?", { who, role: name }), confirm: t("Change role"),
    danger: role === "admin", body })) return false;
  await api("/api/admin/role", { user_id: user.id, role });
  toast(t("{who} is now {role}.", { who, role: name }));
  await reloadUsers();
  loadEvents();
  return true;
}

/** Every workspace with a three-way choice: No access, Free (one per user) or Subscribed. Changes apply at once. */
async function manageWorkspaces(user) {
  const rows = () => Object.values(C.exams).map(x => {
    const level = user.workspaces.find(w => w.code === x.code)?.level ?? "none";
    return `<div class="ws-access-row">
      <div><strong>${esc(x.title || x.code)}</strong><span class="muted small">${esc(x.database)}</span></div>
      <div class="seg small" role="group" aria-label="${esc(t("Access to {title}", { title: x.title || x.code }))}">
        ${["none", "free", "subscribed"].map(l => `<button type="button" data-ws="${esc(x.code)}" data-level="${l}" aria-pressed="${l === level}">${esc(levelLabel(l))}</button>`).join("")}
      </div></div>`;
  }).join("");
  await openDialog(`
    <h2>${esc(t("Workspaces of {who}", { who: user.email }))}</h2>
    <p>${esc(t("Free gives daily quizzes, flashcards and the first lessons; one workspace per user. Subscribed gives everything, SQL included."))}</p>
    <div class="ws-access" id="ws-access">${rows()}</div>
    <div class="row"><button class="btn" value="done">${esc(t("Done"))}</button></div>`, dialog => {
    const box = $("#ws-access", dialog);
    box.addEventListener("click", async e => {
      const b = e.target.closest("[data-level]");
      if (!b || b.getAttribute("aria-pressed") === "true") return;
      const code = b.dataset.ws, level = b.dataset.level;
      const other = user.workspaces.find(w => w.level === "free" && w.code !== code);
      if (level === "free" && other && !await confirmDialog({ title: t("Move the free workspace?"),
        confirm: t("Move it"), body: t("{who} can have one free workspace. {from} loses its free access.", { who: user.email, from: workspaceTitle(other.code) }) })) return;
      try {
        await api("/api/admin/workspace-access", { user_id: user.id, workspace: code, level });
        await reloadUsers();
        user = users.find(u => u.id === user.id) ?? user;
        box.innerHTML = rows();
        loadEvents();
      } catch (err) { toastError(err.message); }
    });
  });
}

async function showLink(link, who) {
  await openDialog(`
    <h2>${esc(t("Reset link for {who}", { who }))}</h2>
    <p>${esc(t("Copy it now: it is shown only once. It works once, within 24 hours."))}</p>
    <label class="field"><span>${esc(t("Reset link"))}</span><input type="text" id="reset-link" readonly value="${esc(link)}"></label>
    <div class="row">
      <button type="button" class="btn secondary" id="copy-link">${esc(t("Copy link"))}</button>
      <button class="btn" value="done">${esc(t("Done"))}</button>
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
      button.textContent = copied ? t("Copied") : t("Press Ctrl+C to copy");
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
      <div><h3 id="reg-label">${esc(t("Registration"))}</h3><p>${esc(t("Closed stops new sign-ups. Existing accounts keep working."))}</p></div>
      <div class="seg" role="group" aria-labelledby="reg-label">
        <button type="button" data-open="1" aria-pressed="${open}">${esc(t("Open"))}</button>
        <button type="button" data-open="0" aria-pressed="${!open}">${esc(t("Closed"))}</button>
      </div>
    </div>
    <div class="setting">
      <div><h3><label for="max-users">${esc(t("User limit"))}</label></h3><p>${esc(tn(settings.users, "Sign-up closes when this many accounts exist. {n} account now.", "Sign-up closes when this many accounts exist. {n} accounts now."))}</p></div>
      <input type="number" id="max-users" min="1" step="1" inputmode="numeric" value="${esc(settings.max_users)}">
    </div>
    <div class="setting free-plan">
      <div><h3>${esc(t("Free plan"))}</h3><p>${esc(t("What a free workspace gets each day, and how many topics' lessons it can read."))}</p></div>
      <div class="free-limits">
        ${[["questions", t("Questions a day"), 1000], ["cards", t("Flashcards a day"), 1000], ["topics", t("Free topics"), 15]].map(([key, label, max]) =>
          `<label class="field"><span>${esc(label)}</span><input type="number" data-limit="${key}" min="0" max="${max}" step="1" inputmode="numeric" value="${esc(settings.free_limits?.[key] ?? 0)}"></label>`).join("")}
      </div>
    </div>
    <div class="form-actions"><button class="btn" type="button" id="save-registration">${esc(t("Save sign-up settings"))}</button></div>`;
  $$("[data-open]", panel).forEach(b => b.addEventListener("click", () => {
    open = b.dataset.open === "1";
    $$("[data-open]", panel).forEach(x => x.setAttribute("aria-pressed", x === b));
  }));
  $("#save-registration").addEventListener("click", async () => {
    const max = Number($("#max-users").value);
    if (!Number.isInteger(max) || max < 1) { toastError(t("The user limit must be a whole number of at least 1.")); return; }
    const freeLimits = Object.fromEntries($$("[data-limit]", panel).map(input => [input.dataset.limit, Number(input.value)]));
    if (Object.values(freeLimits).some(n => !Number.isInteger(n) || n < 0)) {
      toastError(t("The free plan limits must be whole numbers of at least 0.")); return;
    }
    try {
      renderRegistration(await api("/api/admin/settings", { open, max_users: max, free_limits: freeLimits }));
      toast(open ? t("Registration is open.") : t("Registration is closed."));
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
      <div><h3><label for="inactive-days">${esc(t("Delete accounts inactive for"))}</label></h3>
        <p>${esc(t("Learners who have not signed in for this many days (or never, since they joined). Admins are never deleted."))}</p></div>
      <div class="days-input"><input type="number" id="inactive-days" min="1" step="1" inputmode="numeric" value="${esc(inactiveDays)}"><span>${esc(tn(Number(inactiveDays) || 0, "day", "days"))}</span></div>
    </div>
    <div class="form-actions"><button class="btn danger" type="button" id="delete-inactive">${esc(t("Delete inactive accounts"))}</button>
      <span class="muted small" id="inactive-count" role="status"></span></div>`;
  const count = () => {
    const days = Number($("#inactive-days").value);
    $("#inactive-count").textContent = Number.isInteger(days) && days >= 1 ? tn(inactive(days).length, "{n} account matches.", "{n} accounts match.") : "";
  };
  $("#inactive-days").addEventListener("input", () => { inactiveDays = $("#inactive-days").value; count(); });
  count();
  $("#delete-inactive").addEventListener("click", async () => {
    const days = Number($("#inactive-days").value);
    if (!Number.isInteger(days) || days < 1) { toastError(t("Enter a number of days of at least 1.")); return; }
    const n = inactive(days).length;
    if (!await confirmDialog({ title: tn(days, "Delete accounts inactive for {n} day?", "Delete accounts inactive for {n} days?"), confirm: t("Delete accounts"), danger: true,
      body: n ? tn(n, "About {n} learner account will be deleted with their progress, notes and practice schemas. This cannot be undone.",
        "About {n} learner accounts will be deleted with their progress, notes and practice schemas. This cannot be undone.")
        : t("No learner accounts will be deleted with their progress, notes and practice schemas. This cannot be undone.") })) return;
    try {
      const { deleted } = await api("/api/admin/delete-inactive", { days });
      toast(tn(deleted, "{n} account deleted.", "{n} accounts deleted."));
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
  select.innerHTML = `<option value="">${esc(t("All accounts"))}</option>${users.map(u =>
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
    if (id === eventsRequest && $("#admin-events")) box.innerHTML = empty(esc(t("Could not load the events")), esc(err.message));
    return;
  }
  if (id !== eventsRequest || !$("#admin-events")) return;  // a newer request or another page took over
  if (!events.length) { box.innerHTML = empty(esc(t("No events")), esc(t("Nothing matches these filters."))); return; }
  box.innerHTML = `
    <table class="data admin-events">
      <thead><tr><th>${esc(t("Time"))}</th><th>${esc(t("Event"))}</th><th>${esc(t("Outcome"))}</th><th>${esc(t("Account"))}</th><th>${esc(t("Address"))}</th><th>${esc(t("Details"))}</th></tr></thead>
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

export const adminView = { get title() { return t("Admin"); }, render };
