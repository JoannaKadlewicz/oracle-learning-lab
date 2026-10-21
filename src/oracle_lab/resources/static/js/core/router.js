/* Path router (/quiz, /exercises/<id>; the server answers every such path with index.html).
   A view is { title, render(arg), leave?(), onKey?(event) }; the router owns navigation state,
   the document title, focus and scroll, and calls leave() on the old view. */

import { $, $$, esc } from "./dom.js";

export const main = $("#main");
const views = {};
let current = null;
let listeners = [];
let navigation = 0;  // counts route() calls, so a render that finishes after the user moved on is ignored

export function registerViews(map) { Object.assign(views, map); }
export const currentView = () => current;
export const onRoute = fn => listeners.push(fn);

export function setTitle(title) {
  document.title = title ? `${title} | Oracle Learning Lab` : "Oracle Learning Lab";
}

export async function route() {
  if (location.pathname === "/home") history.replaceState(null, "", "/");  // the home page lives at /
  const [, name = "home", arg] = location.pathname.split("/");
  const next = views[name] ? name : "home";
  if (current && current !== next) views[current].leave?.();
  current = next;
  $$(".nav a").forEach(a => {
    if (a.dataset.view === next) a.setAttribute("aria-current", "page");
    else a.removeAttribute("aria-current");
  });
  main.className = "";
  setTitle(views[next].title);
  const id = ++navigation;
  try {
    await views[next].render(arg ? decodeURIComponent(arg) : undefined);
  } catch (err) {
    // A view still loading when the user left fails on elements that are gone; the new page stays.
    if (id !== navigation) return;
    console.error(err);
    main.innerHTML = `<div class="empty"><strong>This page could not be loaded</strong>
      <p>${esc(err.message)}</p><button class="btn secondary" id="reload-app">Reload the app</button></div>`;
    $("#reload-app").addEventListener("click", () => location.reload());
  }
  if (id !== navigation) return;
  listeners.forEach(fn => fn(next));
  main.focus({ preventScroll: true });
  window.scrollTo(0, 0);
}

/** Navigate to a path; re-renders when it is already the current one. Like the old hashchange,
    a new path is routed in a task of its own, so views may call go() from their render(). */
export function go(path) {
  if (location.pathname === path) return route();
  history.pushState(null, "", path);
  setTimeout(route);
}

/** Start routing: back/forward, in-app links without a page load, and old #/ bookmarks. */
export function startRouting() {
  window.addEventListener("popstate", route);
  document.addEventListener("click", e => {
    const a = e.target.closest("a[href^='/']");
    if (!a || e.defaultPrevented || e.button !== 0 || e.ctrlKey || e.metaKey || e.shiftKey || e.altKey
        || a.target || a.hasAttribute("download")) return;
    e.preventDefault();
    go(a.getAttribute("href"));
  });
  if (location.hash.startsWith("#/")) history.replaceState(null, "", location.hash.slice(1));
  return route();
}

/** Re-render the current view without touching scroll or focus. */
export function refresh() {
  return views[current]?.render();
}

export function dispatchKey(e) {
  views[current]?.onKey?.(e);
}
