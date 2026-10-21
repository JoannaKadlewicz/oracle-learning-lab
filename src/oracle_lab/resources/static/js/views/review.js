/* Mistakes: wrong answers and lucky guesses, open until proven on different days. */

import { $, $$, esc, inlineCode, plural } from "../core/dom.js";
import { P, Q, mistakes, topicLabel } from "../core/state.js";
import { main, go } from "../core/router.js";
import { t, tn } from "../core/i18n.js";
import { pageHead, empty } from "../ui/widgets.js";
import { startQuiz } from "./quiz.js";

const reasonName = reason => ({ confident: t("Wrong while sure"), wrong: t("Wrong"), guess: t("Lucky guess") }[reason] ?? reason);

function render() {
  const list = mistakes();
  const lede = esc(t("A mistake is cleared after confident correct answers (Sure or Think so) on {days} different days, because one correct answer is not proof. Mistakes you were sure about come first: they are misconceptions.", { days: P.proof_days }));
  if (!list.length) {
    main.innerHTML = `${pageHead(esc(t("Mistakes")), lede)}
      ${empty(esc(t("No open mistakes")), esc(t("Wrong answers and lucky guesses collect here until you prove them.")), `<button class="btn" id="to-quiz">${esc(t("Start a practice quiz"))}</button>`)}`;
    $("#to-quiz").addEventListener("click", () => go("/quiz"));
    return;
  }
  const batch = Math.min(list.length, 20);
  main.innerHTML = `
    ${pageHead(esc(plural(list.length, "open mistake")), lede,
      `<button class="btn large" id="retry-all">${esc(list.length > 20 ? t("Retry the {n} most important", { n: batch }) : batch === 1 ? t("Retry it") : t("Retry all {n}", { n: batch }))}</button>`)}
    <div class="table-wrap"><table class="data">
      <thead><tr><th>${esc(t("Question"))}</th><th class="hide-s">${esc(t("Why it is here"))}</th><th class="num" title="${esc(t("Days with a confident correct answer since the last miss"))}">${esc(t("Proof"))}</th><th><span class="sr-only">${esc(t("Actions"))}</span></th></tr></thead>
      <tbody>${list.map(m => {
        const q = Q[m.id];
        return `<tr>
          <td><span class="xsmall muted">${esc(topicLabel(q.topic))}</span><br>${inlineCode(q.prompt)}</td>
          <td class="hide-s"><span class="reason reason-${m.reason}">${esc(reasonName(m.reason))}</span></td>
          <td class="num muted" aria-label="${esc(tn(P.proof_days, "{proof} of {n} day proven", "{proof} of {n} days proven", { proof: m.proof }))}">${m.proof}/${P.proof_days}</td>
          <td class="actions"><button class="btn secondary small" data-retry="${m.id}">${esc(t("Retry"))}</button></td></tr>`;
      }).join("")}</tbody>
    </table></div>`;
  $("#retry-all").addEventListener("click", () => startQuiz({ mode: "practice", ids: list.slice(0, 20).map(m => m.id), keepOrder: true }));
  $$("[data-retry]", main).forEach(b => b.addEventListener("click", () => startQuiz({ mode: "practice", ids: [b.dataset.retry] })));
}

export const reviewView = { get title() { return t("Mistakes"); }, render };
