/* Mistakes: wrong answers and lucky guesses, open until proven on different days. */

import { $, $$, esc, inlineCode, plural } from "../core/dom.js";
import { P, Q, mistakes, topicLabel } from "../core/state.js";
import { main, go } from "../core/router.js";
import { pageHead, empty } from "../ui/widgets.js";
import { startQuiz } from "./quiz.js";

const REASONS = { confident: "Wrong while sure", wrong: "Wrong", guess: "Lucky guess" };

function render() {
  const list = mistakes();
  const lede = `A mistake is cleared after confident correct answers (Sure or Think so) on ${P.proof_days} different days, because one correct answer is not proof. Mistakes you were sure about come first: they are misconceptions.`;
  if (!list.length) {
    main.innerHTML = `${pageHead("Mistakes", lede)}
      ${empty("No open mistakes", "Wrong answers and lucky guesses collect here until you prove them.", `<button class="btn" id="to-quiz">Start a practice quiz</button>`)}`;
    $("#to-quiz").addEventListener("click", () => go("#/quiz"));
    return;
  }
  const batch = Math.min(list.length, 20);
  main.innerHTML = `
    ${pageHead(`${plural(list.length, "open mistake")}`, lede,
      `<button class="btn large" id="retry-all">Retry ${list.length > 20 ? `the ${batch} most important` : batch === 1 ? "it" : `all ${batch}`}</button>`)}
    <div class="table-wrap"><table class="data">
      <thead><tr><th>Question</th><th class="hide-s">Why it is here</th><th class="num" title="Days with a confident correct answer since the last miss">Proof</th><th><span class="sr-only">Actions</span></th></tr></thead>
      <tbody>${list.map(m => {
        const q = Q[m.id];
        return `<tr>
          <td><span class="xsmall muted">${esc(topicLabel(q.topic))}</span><br>${inlineCode(q.prompt)}</td>
          <td class="hide-s"><span class="reason reason-${m.reason}">${REASONS[m.reason]}</span></td>
          <td class="num muted" aria-label="${m.proof} of ${P.proof_days} days proven">${m.proof}/${P.proof_days}</td>
          <td class="actions"><button class="btn secondary small" data-retry="${m.id}">Retry</button></td></tr>`;
      }).join("")}</tbody>
    </table></div>`;
  $("#retry-all").addEventListener("click", () => startQuiz({ mode: "practice", ids: list.slice(0, 20).map(m => m.id), keepOrder: true }));
  $$("[data-retry]", main).forEach(b => b.addEventListener("click", () => startQuiz({ mode: "practice", ids: [b.dataset.retry] })));
}

export const reviewView = { title: "Mistakes", render };
