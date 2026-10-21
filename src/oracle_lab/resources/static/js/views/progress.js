/* Progress: readiness, mock exams, calibration and mastery per official objective. */

import { $$, esc, shuffle } from "../core/dom.js";
import { C, P } from "../core/state.js";
import { main } from "../core/router.js";
import { t, tn, formatDate, lang } from "../core/i18n.js";
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
      <thead><tr><th>${esc(t("Date"))}</th><th>${esc(t("Kind"))}</th><th>${esc(t("Score"))}</th><th class="hide-s">${esc(t("On new questions"))}</th><th><span class="sr-only">${esc(t("Report"))}</span></th></tr></thead>
      <tbody>${[...P.mocks].reverse().map(m => `<tr>
        <td class="nowrap">${esc(formatDate(m.started * 1000))}</td>
        <td>${esc(m.full ? t("Full mock") : tn(m.score[1], "Timed set, {n} question", "Timed set, {n} questions"))}</td>
        <td><span class="level ${m.passed ? "level-strong" : "level-weak"}">${m.pct}%</span></td>
        <td class="hide-s">${m.fresh[1] ? esc(t("{pct}% of {n}", { pct: Math.round((m.fresh[0] / m.fresh[1]) * 100), n: m.fresh[1] })) : `<span class="muted small">${esc(t("All seen before"))}</span>`}</td>
        <td class="actions"><a class="btn secondary small" href="/mock/${esc(m.id)}">${esc(t("Report"))}</a></td></tr>`).join("")}
      </tbody></table></div>`
    : empty(esc(t("No mock exams yet")), esc(t("A full mock has {questions} questions in {minutes} minutes and covers every objective.", { questions: C.exam.questions, minutes: C.exam.minutes })),
      `<button class="btn" id="first-mock">${esc(t("Take a mock exam"))}</button>`);

  const calibration = rated ? `<div class="table-wrap"><table class="data">
      <thead><tr><th>${esc(t("When you said"))}</th><th class="num">${esc(t("Answers"))}</th><th>${esc(t("Correct"))}</th><th class="hide-s">${esc(t("Goal"))}</th></tr></thead>
      <tbody>${[["sure", t("Sure"), t("90% or more")], ["think", t("Think so"), t("60 to 90%")], ["guess", t("Guessing"), t("Below 60%")]].map(([k, label, goal]) => `<tr>
        <td>${esc(label)}</td><td class="num">${cal[k].answers}</td>
        <td>${cal[k].answers ? meter(cal[k].correct, cal[k].answers, t("Correct"), k !== "sure") : `<span class="muted small">${esc(t("None"))}</span>`}</td>
        <td class="hide-s muted small">${esc(goal)}</td></tr>`).join("")}
      </tbody></table></div>`
    : empty(esc(t("No rated answers yet")), esc(t("Rate your confidence when you answer practice questions, and your calibration shows up here.")));
  const calNote = esc(!rated ? "" : pct(cal.sure) !== null && pct(cal.sure) < 90 && cal.sure.answers >= 10
    ? t("You are right {pct}% of the time when you are sure. On the exam that means overconfident answers you will not double-check; review your confident mistakes first.", { pct: pct(cal.sure) })
    : t("Well calibrated means: when you are sure, you are almost always right. Rate honestly; guesses stay on your mistakes list until you prove them."));

  const objectives = Object.keys(C.sections).map(sec => {
    const objs = Object.keys(C.objectives).filter(o => o.split(".")[0] === sec);
    return `<div class="obj-section"><h3>${sec}. ${esc(C.sections[sec])}</h3>
      <div class="table-wrap"><table class="data objectives"><colgroup><col class="c-no"><col><col class="c-level"><col class="c-meter hide-s"><col class="c-link"></colgroup><tbody>${objs.map(o => {
        const m = P.objectives[o];
        const n = C.questions.filter(q => q.objective === o).length;
        return `<tr><td class="num muted small">${o}</td><td>${esc(C.objectives[o])}</td>
          <td>${levelBadge(m)}</td>
          <td class="hide-s">${m.level === "new" ? `<span class="muted small">${esc(t("No data"))}</span>` : meter(Math.round(m.estimate * 100), 100, t("Estimated accuracy"))}</td>
          <td class="actions">${n ? `<button class="btn secondary small" data-objective="${o}">${esc(t("Practise {n}", { n }))}</button>` : `<span class="muted small">${esc(t("No questions"))}</span>`}</td></tr>`;
      }).join("")}</tbody></table></div></div>`;
  }).join("");

  main.innerHTML = `
    ${pageHead(esc(t("Progress")), esc(t("Your readiness for the exam, your mock exams, how well your confidence matches your answers, and mastery per official exam objective.")),
      `<a class="btn secondary" href="/report?lang=${lang()}" target="_blank" rel="noopener">${esc(t("Printable readiness report"))}</a>`)}
    ${readyChecklist()}
    <div class="section" style="margin-top:14px">${statTiles()}</div>
    ${section(esc(t("Readiness")), readinessHtml(P.readiness))}
    ${section(esc(t("Mock exams")), `${P.mocks.length > 1 ? trendHtml() + `<div style="height:14px"></div>` : ""}${mocks}`)}
    ${section(esc(t("Objective map")), objectiveMapHtml(), { aside: esc(t("Select an objective to practise it.")) })}
    ${section(esc(t("Calibration")), calibration, { note: calNote })}
    ${section(esc(t("Activity")), activityHtml(), { aside: esc(t("Last 12 weeks")) })}
    ${section(esc(t("Badges")), badgeListHtml(), { aside: esc(t("{earned} of {total} earned, only with evidence the app can check", { earned, total: P.badges.length })) })}
    ${section(esc(t("Mastery by objective")), objectives, { aside: esc(t("Recent answers count more, a confident wrong answer counts extra, a correct guess counts as half wrong.")) })}`;

  $$("#first-mock", main).forEach(b => b.addEventListener("click", () => startMock()));
  bindTips(main);
  $$("[data-cell-objective]", main).forEach(c => c.addEventListener("click", () => practiseObjective(c.dataset.cellObjective)));
  $$("[data-objective]", main).forEach(b => b.addEventListener("click", () => practiseObjective(b.dataset.objective)));
}

export const progressView = { get title() { return t("Progress"); }, render, leave: hideTip };
