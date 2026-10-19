/* Progress: readiness, mock exams, calibration and mastery per official objective. */

import { $$, esc, shuffle } from "../core/dom.js";
import { C, P } from "../core/state.js";
import { main } from "../core/router.js";
import { levelBadge, meter, pageHead, section, empty } from "../ui/widgets.js";
import { bindTips, hideTip, readyChecklist, statTiles, trendHtml, objectiveMapHtml, activityHtml, badgeListHtml, readinessHtml } from "../ui/charts.js";
import { startQuiz, startMock } from "./quiz.js";

function practiseObjective(objective) {
  const ids = C.questions.filter(q => q.objective === objective).map(q => q.id);
  startQuiz({ mode: "practice", ids: shuffle(ids).slice(0, 10) });
}

function render() {
  const cal = P.calibration;
  const rated = Object.values(cal).reduce((n, c) => n + c.answers, 0);
  const pct = c => c.answers ? Math.round((c.correct / c.answers) * 100) : null;
  const earned = P.badges.filter(b => b.earned).length;

  const mocks = P.mocks.length ? `<div class="table-wrap"><table class="data">
      <thead><tr><th>Date</th><th>Kind</th><th>Score</th><th class="hide-s">On new questions</th><th><span class="sr-only">Report</span></th></tr></thead>
      <tbody>${[...P.mocks].reverse().map(m => `<tr>
        <td class="nowrap">${new Date(m.started * 1000).toLocaleDateString()}</td>
        <td>${m.full ? "Full mock" : `Timed set, ${m.score[1]} questions`}</td>
        <td><span class="level ${m.passed ? "level-strong" : "level-weak"}">${m.pct}%</span></td>
        <td class="hide-s">${m.fresh[1] ? `${Math.round((m.fresh[0] / m.fresh[1]) * 100)}% of ${m.fresh[1]}` : `<span class="muted small">All seen before</span>`}</td>
        <td class="actions"><a class="btn secondary small" href="/mock/${esc(m.id)}">Report</a></td></tr>`).join("")}
      </tbody></table></div>`
    : empty("No mock exams yet", `A full mock has ${C.exam.questions} questions in ${C.exam.minutes} minutes and covers every objective.`, `<button class="btn" id="first-mock">Take a mock exam</button>`);

  const calibration = rated ? `<div class="table-wrap"><table class="data">
      <thead><tr><th>When you said</th><th class="num">Answers</th><th>Correct</th><th class="hide-s">Goal</th></tr></thead>
      <tbody>${[["sure", "Sure", "90% or more"], ["think", "Think so", "60 to 90%"], ["guess", "Guessing", "Below 60%"]].map(([k, label, goal]) => `<tr>
        <td>${label}</td><td class="num">${cal[k].answers}</td>
        <td>${cal[k].answers ? meter(cal[k].correct, cal[k].answers, "Correct", k !== "sure") : `<span class="muted small">None</span>`}</td>
        <td class="hide-s muted small">${goal}</td></tr>`).join("")}
      </tbody></table></div>`
    : empty("No rated answers yet", "Rate your confidence when you answer practice questions, and your calibration shows up here.");
  const calNote = !rated ? "" : pct(cal.sure) !== null && pct(cal.sure) < 90 && cal.sure.answers >= 10
    ? `You are right ${pct(cal.sure)}% of the time when you are sure. On the exam that means overconfident answers you will not double-check; review your confident mistakes first.`
    : "Well calibrated means: when you are sure, you are almost always right. Rate honestly; guesses stay on your mistakes list until you prove them.";

  const objectives = Object.keys(C.sections).map(sec => {
    const objs = Object.keys(C.objectives).filter(o => o.split(".")[0] === sec);
    return `<div class="obj-section"><h3>${sec}. ${esc(C.sections[sec])}</h3>
      <div class="table-wrap"><table class="data objectives"><colgroup><col class="c-no"><col><col class="c-level"><col class="c-meter hide-s"><col class="c-link"></colgroup><tbody>${objs.map(o => {
        const m = P.objectives[o];
        const n = C.questions.filter(q => q.objective === o).length;
        return `<tr><td class="num muted small">${o}</td><td>${esc(C.objectives[o])}</td>
          <td>${levelBadge(m)}</td>
          <td class="hide-s">${m.level === "new" ? `<span class="muted small">No data</span>` : meter(Math.round(m.estimate * 100), 100, "Estimated accuracy")}</td>
          <td class="actions">${n ? `<button class="btn secondary small" data-objective="${o}">Practise ${n}</button>` : `<span class="muted small">No questions</span>`}</td></tr>`;
      }).join("")}</tbody></table></div></div>`;
  }).join("");

  main.innerHTML = `
    ${pageHead("Progress", "Your readiness for the exam, your mock exams, how well your confidence matches your answers, and mastery per official exam objective.",
      `<a class="btn secondary" href="/report" target="_blank" rel="noopener">Printable readiness report</a>`)}
    ${readyChecklist()}
    <div class="section" style="margin-top:14px">${statTiles()}</div>
    ${section("Readiness", readinessHtml(P.readiness))}
    ${section("Mock exams", `${P.mocks.length > 1 ? trendHtml() + `<div style="height:14px"></div>` : ""}${mocks}`)}
    ${section("Objective map", objectiveMapHtml(), { aside: "Select an objective to practise it." })}
    ${section("Calibration", calibration, { note: calNote })}
    ${section("Activity", activityHtml(), { aside: "Last 12 weeks" })}
    ${section("Badges", badgeListHtml(), { aside: `${earned} of ${P.badges.length} earned, only with evidence the app can check` })}
    ${section("Mastery by objective", objectives, { aside: "Recent answers count more, a confident wrong answer counts extra, a correct guess counts as half wrong." })}`;

  $$("#first-mock", main).forEach(b => b.addEventListener("click", () => startMock()));
  bindTips(main);
  $$("[data-cell-objective]", main).forEach(c => c.addEventListener("click", () => practiseObjective(c.dataset.cellObjective)));
  $$("[data-objective]", main).forEach(b => b.addEventListener("click", () => practiseObjective(b.dataset.objective)));
}

export const progressView = { title: "Progress", render, leave: hideTip };
