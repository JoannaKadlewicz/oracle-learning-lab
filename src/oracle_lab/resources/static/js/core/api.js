/* JSON calls to the study server. GET without a body, POST with one (and the CSRF token). */

import { csrfToken } from "./session.js";
import { lang, t } from "./i18n.js";

export class ApiError extends Error {}

async function sessionEnded() {
  try { return (await fetch("/api/auth/me", { credentials: "same-origin", headers: { "X-Language": lang() } })).status === 401; }
  catch { return false; }
}

/** `language` asks for the answer in that language instead of the page's (e.g. one flashcard in the other language). */
export async function api(path, body, { language } = {}) {
  const opts = body === undefined ? {} : {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-CSRF-Token": csrfToken() },
    body: JSON.stringify(body),
  };
  let res;
  try {
    res = await fetch(path, { ...opts, headers: { ...opts.headers, "X-Language": language ?? lang() } });
  } catch {
    throw new ApiError(t("The study server is not responding."));
  }
  const payload = res.ok ? null : await res.json().catch(() => null);
  // A 401 is also "wrong password" on the account endpoints: only a dead session leaves the page.
  if (res.status === 401 && await sessionEnded()) {
    location.assign("/login?next=" + encodeURIComponent(location.pathname + location.search));
    throw new ApiError(t("Your session has ended. Please sign in again."));
  }
  if (!res.ok) {
    const err = new ApiError(payload?.error || t("{path} failed with HTTP {status}.", { path, status: res.status }));
    err.problems = Array.isArray(payload?.problems) ? payload.problems : [];
    err.status = res.status;
    throw err;
  }
  return res.json();
}
