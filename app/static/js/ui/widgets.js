/* Small HTML builders shared by views. */

import { esc } from "../core/dom.js";

export const LEVELS = { new: "Not started", weak: "Weak", learning: "Learning", strong: "Strong" };

export function levelBadge(m) {
  const title = m.level === "new" ? "Not enough answers yet"
    : `Estimated accuracy ${Math.round(m.estimate * 100)}%, from ${m.evidence} answers' worth of recent evidence`;
  return `<span class="level level-${m.level}" title="${esc(title)}">${LEVELS[m.level]}</span>`;
}

export function meter(value, total, label, neutral) {
  if (!total) return `<span class="muted small">None</span>`;
  const pct = Math.round((value / total) * 100);
  const cls = neutral ? "neutral" : pct < 50 ? "low" : pct < 75 ? "mid" : "";
  return `<div class="meter" role="img" aria-label="${esc(label)}: ${value} of ${total}"><div class="meter-bar"><i class="${cls}" style="width:${pct}%"></i></div><span>${value}/${total}</span></div>`;
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
