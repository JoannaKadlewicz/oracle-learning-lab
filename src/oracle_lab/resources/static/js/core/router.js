/* Path router (/quiz, /exercises/<id>; the server answers every such path with index.html).
   A view is { title, render(arg), leave?(), onKey?(event) }; the router owns navigation state,
   the document title, focus and scroll, and calls leave() on the old view. */

import { $, $$, esc } from "./dom.js";
import { t, appName } from "./i18n.js";

export const main = $("#main");
const views = {};
let current = null;
let listeners = [];
let navigation = 0;  // counts route() calls, so a render that finishes after the user moved on is ignored
let leaveGuard = null;
let asking = false;  // a guard question is open: further navigation waits for its answer
let routedPath = location.pathname;

export function registerViews(map) { Object.assign(views, map); }
export const currentView = () => current;
export const onRoute = fn => listeners.push(fn);

/** While set, an in-app navigation away from the current path first awaits fn(); false stays put.
    Pass null to remove it. Leaving the page itself is beforeunload's job, not the router's. */
export function setLeaveGuard(fn) { leaveGuard = fn; }

async function mayLeave() {
  if (!leaveGuard) return true;
  if (asking) return false;
  asking = true;
  try { return !!await leaveGuard(); }
  catch { return false; }
  finally { asking = false; }
}

export function setTitle(title) {
  document.title = title ? `${title} | ${appName()}` : appName();
}

export async function route() {
  if (location.pathname === "/home") history.replaceState(null, "", "/");  // the home page lives at /
  const [, name = "home", arg] = location.pathname.split("/");
  const next = views[name] ? name : "home";
  routedPath = location.pathname;
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
    main.innerHTML = `<div class="empty"><strong>${esc(t("This page could not be loaded"))}</strong>
      <p>${esc(err.message)}</p><button class="btn secondary" id="reload-app">${esc(t("Reload the app"))}</button></div>`;
    $("#reload-app").addEventListener("click", () => location.reload());
  }
  if (id !== navigation) return;
  listeners.forEach(fn => fn(next));
  main.focus({ preventScroll: true });
  window.scrollTo(0, 0);
}

/** Navigate to a path; re-renders when it is already the current one. Like the old hashchange,
    a new path is routed in a task of its own, so views may call go() from their render().
    A leave guard may cancel it. */
export async function go(path) {
  if (location.pathname === path) return route();
  if (!await mayLeave()) return;
  history.pushState(null, "", path);
  setTimeout(route);
}

/** Back/forward: with a leave guard, the address bar goes straight back to the guarded path, and
    the target is pushed again only when the guard lets the learner go. */
async function onPopState() {
  if (!leaveGuard || location.pathname === routedPath) return route();
  const target = location.pathname + location.search;
  history.pushState(null, "", routedPath);
  if (!await mayLeave()) return;
  history.pushState(null, "", target);
  route();
}

/** Start routing: back/forward, in-app links without a page load, and old #/ bookmarks. */
export function startRouting() {
  window.addEventListener("popstate", onPopState);
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
