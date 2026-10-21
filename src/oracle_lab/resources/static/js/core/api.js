/* JSON calls to the study server. GET without a body, POST with one (and the CSRF token). */

import { csrfToken } from "./session.js";

export class ApiError extends Error {}

async function sessionEnded() {
  try { return (await fetch("/api/auth/me", { credentials: "same-origin" })).status === 401; }
  catch { return false; }
}

export async function api(path, body) {
  const opts = body === undefined ? {} : {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-CSRF-Token": csrfToken() },
    body: JSON.stringify(body),
  };
  let res;
  try {
    res = await fetch(path, opts);
  } catch {
    throw new ApiError("The study server is not responding.");
  }
  const payload = res.ok ? null : await res.json().catch(() => null);
  // A 401 is also "wrong password" on the account endpoints: only a dead session leaves the page.
  if (res.status === 401 && await sessionEnded()) {
    location.assign("/login?next=" + encodeURIComponent(location.pathname + location.search));
    throw new ApiError("Your session has ended. Please sign in again.");
  }
  if (!res.ok) {
    const err = new ApiError(payload?.error || `${path} failed with HTTP ${res.status}.`);
    err.problems = Array.isArray(payload?.problems) ? payload.problems : [];
    err.status = res.status;
    throw err;
  }
  return res.json();
}
