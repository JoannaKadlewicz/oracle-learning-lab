/* Hash router. A view is { title, render(arg), leave?(), onKey?(event) }; the router owns
   navigation state, the document title, focus and scroll, and calls leave() on the old view. */

import { $, $$, esc } from "./dom.js";

export const main = $("#main");
const views = {};
let current = null;
let listeners = [];

export function registerViews(map) { Object.assign(views, map); }
export const currentView = () => current;
export const onRoute = fn => listeners.push(fn);

export function setTitle(title) {
  document.title = title ? `${title} | Oracle Learning Lab` : "Oracle Learning Lab";
}

export async function route() {
  const [, name = "home", arg] = location.hash.split("/");
  const next = views[name] ? name : "home";
  if (current && current !== next) views[current].leave?.();
  current = next;
  $$(".nav a").forEach(a => {
    if (a.dataset.view === next) a.setAttribute("aria-current", "page");
    else a.removeAttribute("aria-current");
  });
  main.className = "";
  setTitle(views[next].title);
  try {
    await views[next].render(arg ? decodeURIComponent(arg) : undefined);
  } catch (err) {
    console.error(err);
    main.innerHTML = `<div class="empty"><strong>This page could not be loaded</strong>
      <p>${esc(err.message)}</p><button class="btn secondary" onclick="location.reload()">Reload the app</button></div>`;
  }
  listeners.forEach(fn => fn(next));
  main.focus({ preventScroll: true });
  window.scrollTo(0, 0);
}

/** Navigate to a hash; re-renders when it is already the current one. */
export function go(hash) {
  if (location.hash === hash) route();
  else location.hash = hash;
}

/** Re-render the current view without touching scroll or focus. */
export function refresh() {
  return views[current]?.render();
}

export function dispatchKey(e) {
  views[current]?.onKey?.(e);
}
