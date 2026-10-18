/* DOM and text helpers shared by every view. */

export const $ = (sel, root = document) => root.querySelector(sel);
export const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];

export const LETTERS = "ABCDEFGH";

export function esc(value) {
  return String(value ?? "").replace(/[&<>"']/g, ch => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch]));
}

/** Escaped text with `code` spans; whole-SQL options are shown as code. */
export function inlineCode(text) {
  const raw = String(text ?? "");
  if (/^(SELECT |col |employees |DELETE |INSERT |UPDATE )/.test(raw)) return `<code>${esc(raw)}</code>`;
  return esc(raw).replace(/`([^`]+)`/g, "<code>$1</code>");
}

/** "1 question", "3 questions" */
export function plural(n, word, many = word + "s") {
  return `${n} ${n === 1 ? word : many}`;
}

export function shuffle(list) {
  const a = [...list];
  for (let i = a.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [a[i], a[j]] = [a[j], a[i]];
  }
  return a;
}

export function icon(name) {
  return `<svg aria-hidden="true"><use href="#i-${name}"/></svg>`;
}

/** Delegated click handling for `[data-<name>]` elements inside root. */
export function onAction(root, name, handler) {
  root.addEventListener("click", e => {
    const el = e.target.closest(`[data-${name}]`);
    if (el && root.contains(el)) handler(el.dataset[name.replace(/-(\w)/g, (_, c) => c.toUpperCase())], el, e);
  });
}
