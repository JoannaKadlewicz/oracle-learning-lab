/* Progress dashboard: readiness, stat tiles, mock trend, objective map, activity, badges.
   Colors come from the validated palette tokens (--series-*, --status-*, --seq-*) in tokens.css. */

import { $, $$, esc, plural } from "../core/dom.js";
import { C, P } from "../core/state.js";
import { t, tn, formatDate } from "../core/i18n.js";
import { levelName, meter, empty } from "./widgets.js";

/** One shared tooltip for every [data-tip] mark: chart points, heatmap cells, calendar days. */
export function bindTips(root) {
  let tip = $("#viz-tip");
  if (!tip) {
    tip = document.createElement("div");
    tip.id = "viz-tip";
    tip.className = "viz-tip";
    tip.hidden = true;
    document.body.append(tip);
  }
  const show = (el, x, y) => {
    tip.innerHTML = el.dataset.tip;
    tip.hidden = false;
    const w = tip.offsetWidth, h = tip.offsetHeight;
    tip.style.left = Math.min(window.innerWidth - w - 8, Math.max(8, x + 14)) + "px";
    tip.style.top = Math.max(8, y - h - 12) + "px";
  };
  root.querySelectorAll("[data-tip]").forEach(el => {
    el.addEventListener("mousemove", e => show(el, e.clientX, e.clientY));
    el.addEventListener("mouseleave", () => { tip.hidden = true; });
    el.addEventListener("focus", () => { const r = el.getBoundingClientRect(); show(el, r.right, r.top); });
    el.addEventListener("blur", () => { tip.hidden = true; });
  });
  const cross = $(".trend-chart .crosshair", root);
  if (cross) $$(".trend-chart .hit", root).forEach(h => {
    h.addEventListener("mouseenter", () => { cross.setAttribute("x1", h.dataset.x); cross.setAttribute("x2", h.dataset.x); cross.setAttribute("visibility", "visible"); });
    h.addEventListener("mouseleave", () => cross.setAttribute("visibility", "hidden"));
  });
}

export function hideTip() {
  const tip = $("#viz-tip");
  if (tip) tip.hidden = true;
}

const statTile = (value, label, note) =>
  `<div class="stat"><b>${value}</b><span>${label}</span>${note ? `<small>${note}</small>` : ""}</div>`;

function trendChart(mocks) {
  if (!mocks.length) return empty(esc(t("No mock exams yet")), esc(t("Your mock exam scores are charted here, next to your score on questions you had never seen.")));
  const W = 640, H = 220, L = 40, R = 110, T = 14, B = 30;
  const x = i => mocks.length === 1 ? L + (W - L - R) / 2 : L + i * (W - L - R) / (mocks.length - 1);
  const y = v => T + (100 - v) * (H - T - B) / 100;
  const fresh = m => m.fresh[1] ? Math.round(100 * m.fresh[0] / m.fresh[1]) : null;
  const series = [
    { label: t("Overall"), cls: "s1", value: m => m.pct },
    { label: t("New questions"), cls: "s2", value: fresh },
  ];
  const date = m => formatDate(m.started * 1000, { month: "short", day: "numeric" });
  const grid = [0, 25, 50, 75, 100].map(v => `<line class="grid-line" x1="${L}" x2="${W - R}" y1="${y(v)}" y2="${y(v)}"/><text class="axis" x="${L - 6}" y="${y(v) + 4}" text-anchor="end">${v}%</text>`).join("");
  const pass = `<line class="pass-line" x1="${L}" x2="${W - R}" y1="${y(C.exam.passing_pct)}" y2="${y(C.exam.passing_pct)}"/><text class="axis" x="${W - R + 6}" y="${y(C.exam.passing_pct) + 4}">${esc(t("pass {pct}%", { pct: C.exam.passing_pct }))}</text>`;
  // Direct labels at the last point; when the two values are close the labels are stacked 15px
  // apart (the higher value on top) so they never collide.
  const ends = series.map(sr => {
    const pts = mocks.map((m, i) => [x(i), sr.value(m)]).filter(([, v]) => v !== null);
    return { sr, pts, last: pts.at(-1) };
  });
  const placed = ends.filter(e => e.last).sort((a, b) => b.last[1] - a.last[1]);
  placed.forEach((e, i) => { e.labelY = y(e.last[1]) + 4; if (i && e.labelY - placed[i - 1].labelY < 15) e.labelY = placed[i - 1].labelY + 15; });
  const lines = ends.map(({ sr, pts }) => `<polyline class="trend ${sr.cls}" points="${pts.map(([px, v]) => `${px},${y(v)}`).join(" ")}"/>`).join("")
    + ends.map(({ sr, pts }) => pts.map(([px, v]) => `<circle class="dot ${sr.cls}" cx="${px}" cy="${y(v)}" r="4.5"/>`).join("")).join("")
    + placed.map(e => `<text class="direct" x="${e.last[0] + 10}" y="${e.labelY}"><tspan class="${e.sr.cls}-mark">■</tspan> ${esc(e.sr.label)} ${e.last[1]}%</text>`).join("");
  const xs = mocks.map((m, i) => `<text class="axis" x="${x(i)}" y="${H - 8}" text-anchor="middle">${mocks.length <= 8 || i % Math.ceil(mocks.length / 8) === 0 ? date(m) : ""}</text>`).join("");
  const hits = mocks.map((m, i) => {
    const w = mocks.length === 1 ? 80 : (W - L - R) / (mocks.length - 1);
    const tip = `<b>${esc(date(m))}</b>, ${esc(m.full ? t("full mock") : t("timed set"))}<br>${esc(t("Overall {pct}%", { pct: m.pct }))}${fresh(m) !== null ? `<br>${esc(t("New questions {pct}% ({n})", { pct: fresh(m), n: m.fresh[1] }))}` : ""}`;
    return `<rect class="hit" x="${x(i) - w / 2}" y="${T}" width="${w}" height="${H - T - B}" data-tip="${esc(tip)}" data-x="${x(i)}" tabindex="0" aria-label="${esc(t("{date}: overall {pct}%", { date: date(m), pct: m.pct }))}"/>`;
  }).join("");
  return `<div class="legend-row"><span><i class="swatch s1"></i>${esc(t("Overall score"))}</span><span><i class="swatch s2"></i>${esc(t("Score on questions new to you"))}</span></div>
    <svg class="trend-chart" viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(t("Mock exam scores over time"))}">${grid}${pass}${xs}
      <line class="crosshair" x1="0" x2="0" y1="${T}" y2="${H - B}" visibility="hidden"/>${lines}${hits}</svg>`;
}

function heatmapHtml() {
  const icon = { strong: "✓", learning: "~", weak: "!", new: "·" };
  return `<div class="legend-row">${["strong", "learning", "weak", "new"].map(l => `<span><i class="swatch lvl-${l}"></i>${icon[l]} ${esc(levelName(l))}</span>`).join("")}</div>
    <div class="heatmap">${Object.keys(C.sections).map(sec => `<div class="heat-row"><span class="heat-label" title="${esc(C.sections[sec])}">${sec}</span>
      ${Object.keys(C.objectives).filter(o => o.split(".")[0] === sec).map(o => {
        const m = P.objectives[o];
        const level = m.level === "new" ? levelName(m.level) : t("{level}, estimated {pct}%", { level: levelName(m.level), pct: Math.round(m.estimate * 100) });
        const tip = `<b>${o} ${esc(C.objectives[o])}</b><br>${esc(level)}<br>${esc(t("Select to practise"))}`;
        return `<button class="heat-cell lvl-${m.level}" data-cell-objective="${o}" data-tip="${esc(tip)}" aria-label="${esc(t("Objective {id}: {level}. Practise it.", { id: o, level: levelName(m.level) }))}">${o.split(".")[1]}<i aria-hidden="true">${icon[m.level]}</i></button>`;
      }).join("")}</div>`).join("")}</div>`;
}

function calendarHtml(days) {
  const max = Math.max(1, ...days.map(d => d.actions));
  const step = n => n === 0 ? 0 : Math.min(4, Math.ceil((n / max) * 4));
  const first = new Date(days[0].date + "T12:00:00").getDay();
  const pad = (first + 6) % 7;  // weeks start on Monday
  const cells = Array(pad).fill(`<span class="cal-cell pad"></span>`).concat(days.map(d =>
    `<span class="cal-cell q${step(d.actions)}" data-tip="${esc(`<b>${esc(formatDate(d.date + "T12:00:00", { weekday: "short", month: "short", day: "numeric" }))}</b><br>${plural(d.actions, "study action")}`)}"></span>`));
  return `<div class="calendar" role="img" aria-label="${esc(t("Study actions per day over the last 12 weeks"))}">${cells.join("")}</div>
    <div class="legend-row"><span>${esc(t("Less"))}</span>${[0, 1, 2, 3, 4].map(q => `<i class="swatch cal-cell q${q}"></i>`).join("")}<span>${esc(t("More"))}</span></div>`;
}

function badgesHtml(list) {
  return `<div class="badges">${list.map(b => `<div class="badge ${b.earned ? "earned" : ""}">
      <strong>${b.earned ? "✓ " : ""}${esc(b.title)}</strong>
      <span>${esc(b.description)}</span>
      ${b.earned ? `<small>${esc(t("Earned"))}</small>` : meter(b.progress[0], b.progress[1], b.title, true)}
    </div>`).join("")}</div>`;
}

export function readyChecklist() {
  const ready = P.ready;
  return `<div class="ready ${ready.done ? "done" : ""}">
    <h2>${esc(ready.done ? t("Ready to book the exam") : t("Ready to book the exam?"))}</h2>
    <ul>${ready.items.map(i => `<li class="${i.done ? "done" : ""}"><span aria-hidden="true">${i.done ? "✓" : ""}</span>
      ${esc(i.label)}<small>${i.done ? esc(t("Done.")) + " " : ""}${esc(i.detail)}</small></li>`).join("")}</ul>
  </div>`;
}

export function statTiles() {
  const r = P.readiness, a = P.activity, sure = P.calibration.sure;
  return `<div class="stats">
    ${statTile(r.status === "ok" ? `${Math.round(r.pass_probability * 100)}%` : "–", esc(t("chance to pass")),
      esc(r.status === "ok" ? t("Expected score {low} to {high}%", { low: r.low_pct, high: r.high_pct }) : t("Not enough data yet")))}
    ${statTile(a.streak, esc(tn(a.streak, "day in a row", "days in a row")), esc(tn(a.active_days, "{n} study day in total", "{n} study days in total")))}
    ${statTile(a.hours, esc(t("hours studied")), esc(t("Estimated from your activity")))}
    ${statTile(sure.answers ? `${Math.round(100 * sure.correct / sure.answers)}%` : "–", esc(t("right when Sure")),
      esc(sure.answers ? tn(sure.answers, "{n} answer, goal 90%", "{n} answers, goal 90%") : t("Rate your confidence when answering")))}
  </div>`;
}

export const trendHtml = () => `<div class="chart-card">${trendChart(P.mocks)}</div>`;
export const objectiveMapHtml = () => `<div class="chart-card">${heatmapHtml()}</div>`;
export const activityHtml = () => `<div class="chart-card">${calendarHtml(P.activity.days)}</div>`;
export const badgeListHtml = () => badgesHtml(P.badges);

export function readinessHtml(r) {
  if (r.status !== "ok") {
    return `<p>${esc(t("Not enough data yet: readiness needs first answers to about {needed} questions you have never seen (you have {evidence}). A mock exam is the fastest way to get there.", { needed: r.needed, evidence: r.evidence }))}</p>`;
  }
  const gaps = [];
  if (r.untested.length) gaps.push(tn(r.untested.length, "{n} objective has too little evidence for a mastery level (fewer than about 2 answers)", "{n} objectives have too little evidence for a mastery level (fewer than about 2 answers)"));
  if (r.weak.length) gaps.push(tn(r.weak.length, "{n} is weak ({ids})", "{n} are weak ({ids})", { ids: r.weak.join(", ") }));
  return `<div class="readiness">
      <b>${Math.round(r.pass_probability * 100)}%</b>
      <span>${esc(t("estimated chance to pass. Expected score {expected}%, most likely between {low}% and {high}% (passing: {passing}%).", { expected: r.expected_pct, low: r.low_pct, high: r.high_pct, passing: r.passing_pct }))}</span>
    </div>
    <p class="small muted prose">${esc(t("Based only on the first answer you ever gave to each question, so practising the same questions again cannot inflate it. Mock answers count fully, practice answers 60%, and older answers fade."))}${gaps.length ? " " + esc(t("Also: {gaps}.", { gaps: gaps.join(t(", and ")) })) : ""}</p>`;
}
