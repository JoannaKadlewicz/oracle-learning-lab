/* The signed-in person and their CSRF token, loaded once at start-up from /api/auth/me. */

import { clearUserStore } from "./store.js";
import { lang } from "./i18n.js";

let session = { user: null, csrf: "" };

export async function loadSession() {
  const res = await fetch("/api/auth/me", { credentials: "same-origin", headers: { "X-Language": lang() } });
  if (res.status === 401) {
    location.assign("/login?next=" + encodeURIComponent(location.pathname + location.search));
    return new Promise(() => {});  // the page is leaving; never boot the app
  }
  if (!res.ok) throw new Error(`The study server answered HTTP ${res.status}.`);
  const body = await res.json();
  session = { user: body.user, csrf: body.csrf_token };
  return session;
}

export const csrfToken = () => session.csrf;
export const currentUser = () => session.user;

export async function signOut() {
  try {
    await fetch("/api/auth/logout", { method: "POST", credentials: "same-origin", headers: { "X-CSRF-Token": session.csrf, "X-Language": lang() } });
  } catch { /* the cookie may already be gone; leave anyway */ }
  clearUserStore();
  location.assign("/login");
}
