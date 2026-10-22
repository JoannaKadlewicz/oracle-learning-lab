/* Small HTML builders shared by views. */

import { esc, icon } from "../core/dom.js";
import { t, tn } from "../core/i18n.js";

/** The mastery level's name: new, weak, learning or strong. */
export function levelName(level) {
  return { new: t("Not started"), weak: t("Weak"), learning: t("Learning"), strong: t("Strong") }[level] ?? level;
}

export function levelBadge(m) {
  const title = m.level === "new" ? t("Not enough answers yet")
    : tn(m.evidence, "Estimated accuracy {pct}%, from {n} answer's worth of recent evidence",
      "Estimated accuracy {pct}%, from {n} answers' worth of recent evidence", { pct: Math.round(m.estimate * 100) });
  return `<span class="level level-${m.level}" title="${esc(title)}">${esc(levelName(m.level))}</span>`;
}

export function meter(value, total, label, neutral) {
  if (!total) return `<span class="muted small">${esc(t("None"))}</span>`;
  const pct = Math.round((value / total) * 100);
  const cls = neutral ? "neutral" : pct < 50 ? "low" : pct < 75 ? "mid" : "";
  return `<div class="meter" role="img" aria-label="${esc(t("{label}: {value} of {total}", { label, value, total }))}"><div class="meter-bar"><i class="${cls}" style="width:${pct}%"></i></div><span>${value}/${total}</span></div>`;
}

export function pageHead(title, lede = "", actions = "") {
  return `<header class="page-head">
    <div><h1>${title}</h1>${lede ? `<p class="lede">${lede}</p>` : ""}</div>
    ${actions ? `<div class="page-actions">${actions}</div>` : ""}
  </header>`;
}

export function section(title, body, { note = "", aside = "" } = {}) {
  return `<section class="section">
    <div class="section-head"><h2>${title}</h2>${aside ? `<p>${aside}</p>` : ""}</div>
    ${body}
    ${note ? `<p class="section-note">${note}</p>` : ""}
  </section>`;
}

export function empty(title, text = "", action = "") {
  return `<div class="empty"><strong>${title}</strong>${text ? `<p>${text}</p>` : ""}${action}</div>`;
}

export const loading = text => `<p class="loading">${esc(text)}</p>`;

/** The small lock that marks what free accounts can see but not use. */
export const premiumTag = (label = t("Pro"), title = t("Part of the Pro plan"), cls = "") =>
  `<span class="premium-tag${cls ? ` ${cls}` : ""}" title="${esc(title)}">${icon("lock")}<span>${esc(label)}</span></span>`;
/* Two locks only, the same words everywhere: "Sign in" (a guest gets it with an account, at no cost) and
   "Pro" (the paid plan). Whatever carries the "Sign in" lock takes a guest to sign in (see shell.js). */
export const accountTag = () => premiumTag(t("Sign in"), t("Sign in or create a free account to use this"), "account-tag");

/** Where a guest's lock leads: sign in (or register from there), then back to `next`. */
export const signInUrl = (next = location.pathname) => `/login?${new URLSearchParams({ next })}`;

/** Why to register, in one sentence: the same on every guest lock. */
export const accountPitch = () => t("A free account takes 30 seconds: unlimited quizzes, flashcards and lessons, plus 10 SQL exercises a day. Your progress comes with you.");

/** The banner on a page whose SQL a free account cannot run: the page stays readable, the buttons stay off. */
export const premiumCallout = (title, text, action = "") =>
  `<div class="callout premium-callout">${icon("lock")}<p><strong>${esc(title)}</strong> ${esc(text)}</p>${action}</div>`;

/** The call to action of a lock: a guest registers (keeping their progress); an account asks for Pro. */
export const registerButton = () => `<a class="btn small" href="/register">${esc(t("Create a free account"))}</a>`;

/** A guest's lock on a page: `title` says what the free account unlocks here. */
export const accountCallout = title => premiumCallout(title, accountPitch(), registerButton());


/** Shown instead of the next question or card once a free plan's daily allowance of `kind` is used up. */
export function limitPanel(kind, n, guest = false) {
  const title = { cards: t("That's today's flashcards"), exercises: t("That's today's exercises") }[kind] ?? t("That's today's questions");
  const text = kind === "exercises"
    ? t("You solved all {n} exercises included for today. Come back tomorrow, or ask an admin for the Pro plan to practise without limits.", { n })
    : guest ? `${t("A guest gets {n} a day.", { n })} ${accountPitch()}`
      : t("You used all {n} for today. Come back tomorrow.", { n });
  return `<div class="empty limit-panel">${icon("lock")}<strong>${esc(title)}</strong><p>${esc(text)}</p>
    <div class="row">${guest ? `<a class="btn" href="/register">${esc(t("Create a free account"))}</a>` : ""}
      <a class="btn ${guest ? "secondary" : ""}" href="/">${esc(t("Back to Today"))}</a><a class="btn secondary" href="/progress">${esc(t("See your progress"))}</a></div></div>`;
}
