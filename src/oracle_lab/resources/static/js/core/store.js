/* Per-browser conveniences (drafts, filters, theme) in localStorage, kept apart per account:
   `study:<userId>:<key>`. The theme is the browser's, not the account's: `study:theme`. Never
   required: every access falls back to a default when storage is blocked or empty. */

let namespace = "anon";

const keyOf = key => key === "theme" ? "study:theme" : `study:${namespace}:${key}`;

export function store(key, value) {
  try {
    if (value === undefined) return JSON.parse(localStorage.getItem(keyOf(key)));
    localStorage.setItem(keyOf(key), JSON.stringify(value));
  } catch {
    return value === undefined ? null : value;
  }
  return value;
}

const NAMESPACED = /^study:[\w-]{22}:/;

/** Selects the account's keys. The first account in a browser inherits the keys of the single-user era. */
export function useUser(userId) {
  namespace = userId;
  try {
    if (localStorage.getItem("study:migrated") !== null) return;
    const legacy = [];
    for (let i = 0; i < localStorage.length; i++) {
      const k = localStorage.key(i);
      if (k.startsWith("study:") && !["study:theme", "study:migrated"].includes(k) && !NAMESPACED.test(k)) legacy.push(k);
    }
    for (const k of legacy) {
      localStorage.setItem(`study:${userId}:${k.slice("study:".length)}`, localStorage.getItem(k));
      localStorage.removeItem(k);
    }
    localStorage.setItem("study:migrated", JSON.stringify(userId));
  } catch { /* storage unavailable: nothing to move */ }
}

/** Forgets this account's drafts and filters in this browser (sign-out). */
export function clearUserStore() {
  try {
    const prefix = `study:${namespace}:`;
    const mine = [];
    for (let i = 0; i < localStorage.length; i++) if (localStorage.key(i).startsWith(prefix)) mine.push(localStorage.key(i));
    mine.forEach(k => localStorage.removeItem(k));
  } catch { /* storage unavailable */ }
}
