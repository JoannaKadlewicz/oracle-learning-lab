/* Per-browser conveniences (drafts, filters, theme) in localStorage. Never required: every read
   falls back to a default when storage is blocked or empty. */

export function store(key, value) {
  try {
    if (value === undefined) return JSON.parse(localStorage.getItem("study:" + key));
    localStorage.setItem("study:" + key, JSON.stringify(value));
  } catch {
    return value === undefined ? null : value;
  }
  return value;
}
