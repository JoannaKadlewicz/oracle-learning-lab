"""Printable readiness report: one self-contained HTML page (print it to PDF from the browser).

Built from the same progress summary the dashboard uses (engine.progress), so the numbers match.
"""

import datetime
from html import escape

LEVELS = {"strong": ("Strong", "✓"), "learning": ("Learning", "~"), "weak": ("Weak", "!"), "new": ("Not started", "·")}


def _pct(part, whole):
    return f"{round(100 * part / whole)}%" if whole else "–"


def _trend_svg(mocks, passing_pct):
    if not mocks:
        return "<p class='muted'>No mock exams yet.</p>"
    W, H, L, R, T, B = 560, 180, 36, 150, 10, 26
    n = len(mocks)

    def x(i):
        return L + (W - L - R) / 2 if n == 1 else L + i * (W - L - R) / (n - 1)

    def y(v):
        return T + (100 - v) * (H - T - B) / 100

    parts = [f"<svg viewBox='0 0 {W} {H}' class='trend' role='img' aria-label='Mock exam scores over time'>"]
    for v in (0, 25, 50, 75, 100):
        parts.append(f"<line class='grid' x1='{L}' x2='{W - R}' y1='{y(v)}' y2='{y(v)}'/>"
                     f"<text class='axis' x='{L - 5}' y='{y(v) + 4}' text-anchor='end'>{v}%</text>")
    parts.append(f"<line class='pass' x1='{L}' x2='{W - R}' y1='{y(passing_pct)}' y2='{y(passing_pct)}'/>"
                 f"<text class='axis' x='{W - R + 5}' y='{y(passing_pct) + 4}'>pass {passing_pct}%</text>")
    series = [("s1", "Overall", lambda m: m["pct"]),
              ("s2", "New questions", lambda m: round(100 * m["fresh"][0] / m["fresh"][1]) if m["fresh"][1] else None)]
    ends = []
    for cls, label, value in series:
        pts = [(x(i), value(m)) for i, m in enumerate(mocks) if value(m) is not None]
        if not pts:
            continue
        parts.append(f"<polyline class='line {cls}' points='{' '.join(f'{px},{y(v)}' for px, v in pts)}'/>")
        parts += [f"<circle class='dot {cls}' cx='{px}' cy='{y(v)}' r='4'/>" for px, v in pts]
        ends.append((pts[-1], cls, label))
    # Direct labels with values, stacked at least 14px apart so close values never collide.
    label_y = None
    for (lx, lv), cls, label in sorted(ends, key=lambda e: -e[0][1]):
        label_y = y(lv) + 4 if label_y is None else max(y(lv) + 4, label_y + 14)
        parts.append(f"<text class='direct' x='{lx + 8}' y='{label_y}'><tspan class='{cls}-mark'>■</tspan> {label} {lv}%</text>")
    for i, m in enumerate(mocks):
        if n <= 8 or i % -(-n // 8) == 0:
            day = datetime.date.fromtimestamp(m["started"]).strftime("%d %b")
            parts.append(f"<text class='axis' x='{x(i)}' y='{H - 6}' text-anchor='middle'>{day}</text>")
    parts.append("</svg>")
    return "".join(parts)


def _mock_kind(m):
    return "Full mock" if m["full"] else f"Timed set ({m['score'][1]} questions)"


def render(content, state, progress, now):
    p = progress
    r = p["readiness"]
    today = datetime.date.fromtimestamp(now).strftime("%d %B %Y")
    sure = p["calibration"]["sure"]
    labs_by_kind = {}
    for lab in content.LABS:
        labs_by_kind.setdefault(lab.get("kind", "query"), [0, 0])[1] += 1
        if state.get("labs", {}).get(lab["id"], {}).get("passed"):
            labs_by_kind[lab.get("kind", "query")][0] += 1

    if r["status"] == "ok":
        headline = (f"<b class='hero'>{round(r['pass_probability'] * 100)}%</b><span>estimated chance to pass. "
                    f"Expected score {r['expected_pct']}%, most likely {r['low_pct']}–{r['high_pct']}% "
                    f"(passing score {r['passing_pct']}%).</span>")
    else:
        headline = (f"<b class='hero'>–</b><span>Not enough evidence yet for a readiness estimate "
                    f"({r['evidence']} of about {r['needed']} first answers).</span>")

    checklist = "".join(
        f"<li class='{'done' if i['done'] else ''}'><span>{'✓' if i['done'] else '○'}</span> {escape(i['label'])} "
        f"<small>{escape(i['detail'])}</small></li>" for i in p["ready"]["items"])

    rows = []
    for sec, title in content.SECTIONS.items():
        cells = []
        for o in [o for o in content.OBJECTIVES if o.split(".")[0] == sec]:
            m = p["objectives"][o]
            label, icon = LEVELS[m["level"]]
            cells.append(f"<span class='cell lvl-{m['level']}' title='{escape(content.OBJECTIVES[o])}: {label}'>{o} {icon}</span>")
        rows.append(f"<tr><td>{sec}. {escape(title)}</td><td>{''.join(cells)}</td></tr>")

    mock_rows = "".join(
        f"<tr><td>{datetime.date.fromtimestamp(m['started']).isoformat()}</td>"
        f"<td>{_mock_kind(m)}</td>"
        f"<td class='num'>{m['pct']}%</td><td class='num'>{_pct(*m['fresh'])} of {m['fresh'][1]}</td>"
        f"<td>{'Pass' if m['passed'] else 'Below pass'}</td></tr>"
        for m in reversed(p["mocks"])) or "<tr><td colspan='5' class='muted'>No mock exams yet.</td></tr>"

    earned = [b for b in p["badges"] if b["earned"]]
    a = p["activity"]
    lab_line = ", ".join(f"{labs_by_kind[k][0]} of {labs_by_kind[k][1]} {name}"
                         for k, name in (("query", "query"), ("dml", "DML"), ("ddl", "DDL")) if k in labs_by_kind)

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{content.EXAM['code']} readiness report</title>
<style>
  :root {{ --ink:#172338; --muted:#56667E; --rule:#C9D5E5; --paper:#fff; --s1:#2a78d6; --s2:#eb6834;
          --good:#0ca30c; --warn:#fab219; --bad:#d03b3b; color-scheme: light; }}
  @media (prefers-color-scheme: dark) {{ :root:not([data-theme="light"]) {{ --ink:#E5ECF6; --muted:#9AAAC2; --rule:#2C3B55; --paper:#0F1724;
          --s1:#3987e5; --s2:#d95926; color-scheme: dark; }} }}
  :root[data-theme="dark"] {{ --ink:#E5ECF6; --muted:#9AAAC2; --rule:#2C3B55; --paper:#0F1724; --s1:#3987e5; --s2:#d95926; color-scheme: dark; }}
  body {{ background: var(--paper); color: var(--ink); font: 14px/1.5 system-ui, sans-serif; margin: 0 auto; padding: 28px 16px; max-width: 800px; }}
  h1 {{ font-size: 24px; margin: 0; }} h2 {{ font-size: 16px; margin: 22px 0 8px; }}
  .muted, small {{ color: var(--muted); }}
  .summary {{ display: flex; gap: 14px; align-items: baseline; flex-wrap: wrap; margin: 14px 0; }}
  .hero {{ font-size: 44px; line-height: 1; font-variant-numeric: tabular-nums; }}
  table {{ border-collapse: collapse; width: 100%; }} td, th {{ text-align: left; padding: 5px 8px; border-bottom: 1px solid var(--rule); vertical-align: top; }}
  th {{ font-size: 12px; color: var(--muted); }} .num {{ text-align: right; font-variant-numeric: tabular-nums; }}
  ul.check {{ list-style: none; padding: 0; margin: 0; }} ul.check li span {{ display: inline-block; width: 1.2em; }} ul.check li.done span {{ color: var(--good); font-weight: 700; }}
  .cell {{ display: inline-block; margin: 1px 2px; padding: 0 5px; border-radius: 3px; font-size: 11px; font-weight: 700; color: #0b0b0b; }}
  .lvl-strong {{ background: var(--good); }} .lvl-learning {{ background: var(--warn); }} .lvl-weak {{ background: var(--bad); }}
  .lvl-new {{ background: transparent; color: var(--muted); box-shadow: inset 0 0 0 1px var(--rule); }}
  .grid3 {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 10px; }}
  .grid3 div {{ border: 1px solid var(--rule); border-radius: 6px; padding: 8px 10px; }} .grid3 b {{ font-size: 20px; display: block; }}
  svg.trend {{ width: 100%; height: auto; }} svg .grid {{ stroke: var(--rule); }} svg .pass {{ stroke: var(--muted); stroke-dasharray: 5 4; }}
  svg .axis {{ fill: var(--muted); font-size: 10px; }} svg .line {{ fill: none; stroke-width: 2; }} svg .line.s1 {{ stroke: var(--s1); }} svg .line.s2 {{ stroke: var(--s2); }}
  svg .dot {{ stroke: var(--paper); stroke-width: 2; }} svg .dot.s1 {{ fill: var(--s1); }} svg .dot.s2 {{ fill: var(--s2); }} svg .direct {{ fill: var(--ink); font-size: 11px; font-weight: 700; }}
  .legend {{ font-size: 12px; color: var(--muted); }} .legend i {{ display: inline-block; width: 10px; height: 10px; border-radius: 2px; margin: 0 4px 0 10px; }}
  svg .s1-mark {{ fill: var(--s1); }} svg .s2-mark {{ fill: var(--s2); }}
  footer {{ margin-top: 24px; font-size: 12px; color: var(--muted); }}
  @media print {{ :root, :root[data-theme="dark"] {{ --ink:#172338 !important; --muted:#56667E !important; --rule:#C9D5E5 !important;
          --paper:#fff !important; --s1:#2a78d6 !important; --s2:#eb6834 !important; color-scheme: light; }}
    body {{ padding: 0; max-width: none; }} @page {{ margin: 14mm; }} h2 {{ break-after: avoid; }} table, svg {{ break-inside: avoid; }} }}
</style></head>
<body>
<h1>{escape(content.EXAM['name'])} ({content.EXAM['code']}): readiness report</h1>
<p class="muted">{today} · {len(content.QUESTIONS)} practice questions, {len(content.LABS)} graded SQL exercises, {content.EXAM['database']}</p>
<div class="summary">{headline}</div>

<h2>Ready to book the exam?</h2>
<ul class="check">{checklist}</ul>

<h2>Study evidence</h2>
<div class="grid3">
  <div><b>{a['active_days']}</b>study days</div>
  <div><b>{a['hours']}</b>hours studied (estimated)</div>
  <div><b>{_pct(sure['correct'], sure['answers'])}</b>right when sure ({sure['answers']} answers)</div>
  <div><b>{len(earned)} of {len(p['badges'])}</b>badges earned</div>
</div>
<p class="muted">Exercises passed: {lab_line}.</p>

<h2>Mock exams</h2>
<p class="legend"><i style="background:var(--s1)"></i>Overall score<i style="background:var(--s2)"></i>Score on questions new to the learner</p>
{_trend_svg(p["mocks"], content.EXAM["passing_pct"])}
<table><thead><tr><th>Date</th><th>Kind</th><th class="num">Score</th><th class="num">New questions</th><th>Result</th></tr></thead>
<tbody>{mock_rows}</tbody></table>

<h2>Mastery per official objective</h2>
<p class="legend">✓ Strong · ~ Learning · ! Weak · · Not started</p>
<table><tbody>{''.join(rows)}</tbody></table>

<h2>Badges earned</h2>
<p>{escape(", ".join(b["title"] for b in earned)) or "None yet."}</p>

<footer>Generated by Oracle Learning Lab. Questions are original practice material, not exam items.
The pass estimate uses only the first answer ever given to each question (mock answers count fully,
practice answers 60%, older answers fade), so repeating questions cannot inflate it. Mastery levels
combine quiz answers weighted by stated confidence, flashcards and graded SQL exercises.</footer>
</body></html>
"""
