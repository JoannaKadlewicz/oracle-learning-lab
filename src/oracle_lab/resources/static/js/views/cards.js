/* Flashcards with spaced repetition: pick a deck, flip, rate. */

import { $, $$, esc, inlineCode, plural, shuffle } from "../core/dom.js";
import { api } from "../core/api.js";
import { C, P, apply, dueCards, cardLearned, topicLabel } from "../core/state.js";
import { main, go } from "../core/router.js";
import { toast, toastError } from "../ui/feedback.js";
import { meter, pageHead, section } from "../ui/widgets.js";

let deck = null;

export function resetDeck() { deck = null; }

/** Start studying these cards; keepOrder for decks already in a meaningful order. */
export function openDeck(cards, keepOrder) {
  const ids = cards.map(c => c.id);
  deck = { queue: keepOrder ? ids : shuffle(ids), done: 0, again: 0, flipped: false, total: cards.length };
  go("/cards");
}

function render() {
  if (!deck) return renderSetup();
  renderCard();
}

function renderSetup() {
  const due = dueCards();
  main.innerHTML = `
    ${pageHead("Flashcards", "Flip a card, then rate how well you knew it. Good brings it back after 1 day, then 3, then longer; Easy stretches the gaps faster; Again repeats it in this session. A card counts as learned once its gap reaches a week.")}
    <div class="row">
      <button class="btn large" id="study-due" ${due.length ? "" : "disabled"}>${due.length ? `Study ${plural(due.length, "due card")}` : "No cards due today"}</button>
      <button class="btn secondary large" id="study-weak" title="Cards from the three topics where your mastery is lowest, due and new cards first">Study my weakest topics</button>
      <button class="btn ghost large" id="study-all">All ${C.flashcards.length} cards</button>
    </div>
    ${section("Decks by topic", `<div class="table-wrap"><table class="data">
      <thead><tr><th>Topic</th><th>Learned</th><th class="num">Due</th><th><span class="sr-only">Actions</span></th></tr></thead>
      <tbody>${Object.keys(C.topics).map(t => {
        const cards = C.flashcards.filter(c => c.topic === t);
        const d = dueCards(t).length;
        const learned = cards.filter(c => cardLearned(c.id)).length;
        return `<tr><td>${esc(topicLabel(t))}</td><td>${meter(learned, cards.length, "Learned")}</td>
          <td class="num ${d ? "" : "muted"}">${d}</td>
          <td class="actions"><button class="btn secondary small" data-deck="${t}">Study</button></td></tr>`;
      }).join("")}</tbody>
    </table></div>`)}`;
  $("#study-due").addEventListener("click", () => openDeck(due));
  $("#study-all").addEventListener("click", () => openDeck(C.flashcards));
  $("#study-weak").addEventListener("click", () => {
    const rank = t => ({ new: 1, weak: 0, learning: 2, strong: 3 }[P.topics[t]?.level] ?? 1) + (P.topics[t]?.estimate || 0);
    const weakest = Object.keys(C.topics).sort((a, b) => rank(a) - rank(b)).slice(0, 3);
    const dueSet = new Set(dueCards());
    const cards = C.flashcards.filter(c => weakest.includes(c.topic)).sort((a, b) => dueSet.has(b) - dueSet.has(a));
    toast("Weakest topics: " + weakest.map(topicLabel).join(", "));
    openDeck(cards.slice(0, 30), true);
  });
  $$("[data-deck]", main).forEach(b => b.addEventListener("click", () => openDeck(C.flashcards.filter(c => c.topic === b.dataset.deck))));
}

function renderCard() {
  if (!deck.queue.length) {
    main.innerHTML = `
      ${pageHead("Deck finished", `${plural(deck.done, "card")} done${deck.again ? `, ${deck.again} sent back for another pass` : ""}. The next reviews are scheduled.`)}
      <div class="row"><button class="btn" id="deck-back">Choose another deck</button><a class="btn secondary" href="/">Back to Today</a></div>`;
    $("#deck-back").addEventListener("click", () => { deck = null; render(); });
    return;
  }
  const card = C.flashcards.find(c => c.id === deck.queue[0]);
  const info = P.cards[card.id];
  const status = !info ? "New card" : info.interval >= 1 ? `Every ${plural(info.interval, "day")}` : "Relearning";
  const progress = deck.total ? (deck.done / deck.total) * 100 : 0;
  main.innerHTML = `
    <h1 class="sr-only">Flashcards</h1>
    <div class="deck">
      <div class="deck-top">
        <div class="deck-stats" aria-live="polite">
          <span><b>${deck.queue.length}</b> left</span><span><b>${deck.done}</b> done</span><span><b>${deck.again}</b> again</span>
        </div>
        <span class="spacer"></span>
        <button class="link-btn quiet small" id="deck-quit">Stop studying</button>
      </div>
      <div class="deck-progress"><i style="width:${progress}%"></i></div>
      <div class="card-stage">
        <button class="index-card ${deck.flipped ? "flipped" : ""}" id="card" aria-label="${deck.flipped ? "Answer side. Press to show the question." : "Question side. Press to show the answer."}">
          <div class="card-face card-front" aria-hidden="${deck.flipped}">
            <span class="card-box">${status}</span>
            <p class="card-topic">${esc(topicLabel(card.topic))}</p>
            <div class="card-text">${inlineCode(card.front)}</div>
            <p class="card-hint">Space or click to flip</p>
          </div>
          <div class="card-face card-back" aria-hidden="${!deck.flipped}">
            <div class="card-text">${inlineCode(card.back)}</div>
            <p class="card-hint">1 again, 2 good, 3 easy</p>
          </div>
        </button>
      </div>
      <div class="ratings" role="group" aria-label="How well did you know it?">
        <button class="btn secondary" data-rating="again" ${deck.flipped ? "" : "disabled"}>Again <small>Show it again soon (1)</small></button>
        <button class="btn" data-rating="good" ${deck.flipped ? "" : "disabled"}>Good <small>I knew it (2)</small></button>
        <button class="btn secondary" data-rating="easy" ${deck.flipped ? "" : "disabled"}>Easy <small>Too easy (3)</small></button>
      </div>
    </div>`;
  $("#card").addEventListener("click", flipCard);
  $$("[data-rating]", main).forEach(b => b.addEventListener("click", () => rateCard(b.dataset.rating)));
  $("#deck-quit").addEventListener("click", () => { deck = null; render(); });
}

function flipCard() {
  deck.flipped = !deck.flipped;
  const el = $("#card");
  el.classList.toggle("flipped", deck.flipped);
  el.setAttribute("aria-label", deck.flipped ? "Answer side. Press to show the question." : "Question side. Press to show the answer.");
  $$(".card-face", el).forEach((f, n) => f.setAttribute("aria-hidden", n === 0 ? deck.flipped : !deck.flipped));
  $$("[data-rating]", main).forEach(b => { b.disabled = !deck.flipped; });
}

async function rateCard(rating) {
  if (!deck.flipped) return;
  const id = deck.queue.shift();
  if (rating === "again") { deck.again++; deck.queue.splice(Math.min(deck.queue.length, 3), 0, id); }
  else deck.done++;
  deck.flipped = false;
  try { apply(await api("/api/card", { id, rating })); } catch { toastError("Could not save the card result."); }
  renderCard();
  $("#card")?.focus({ preventScroll: true });
}

function onKey(e) {
  if (!deck || !deck.queue.length) return;
  if (e.key === " " || (e.key === "Enter" && e.target.id !== "card")) { e.preventDefault(); flipCard(); }
  else if (e.key === "1") rateCard("again");
  else if (e.key === "2") rateCard("good");
  else if (e.key === "3") rateCard("easy");
}

export const cardsView = { title: "Flashcards", render, onKey };
