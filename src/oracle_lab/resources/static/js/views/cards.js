/* Flashcards with spaced repetition: pick a deck, flip, rate. Beside the card, a SQL editor
   holds the card's sample (try_sql), so the rule on the card can be tried once it is answered.
   The sample stays hidden until the flip: its leading comment usually states the answer. */

import { $, $$, esc, inlineCode, plural, shuffle } from "../core/dom.js";
import { api } from "../core/api.js";
import { C, P, DB, apply, dueCards, cardLearned, topicLabel, blockedOn23ai } from "../core/state.js";
import { main, go } from "../core/router.js";
import { toast, toastError } from "../ui/feedback.js";
import { meter, pageHead, section, loading } from "../ui/widgets.js";
import { makeEditor } from "../ui/editor.js";
import { resultsHtml, errorBox } from "../ui/sql.js";
import { labDraft } from "./lab.js";

let deck = null;

// Below this width the Try-it panel sits under the card, so it stays behind a button even after the flip.
const narrow = matchMedia("(max-width: 1179.98px)");
narrow.addEventListener("change", () => { if (deck?.queue.length && $("#card-try")) updateTry(currentCard()); });

const RATINGS = [["again", "Again", "secondary"], ["hard", "Hard", "secondary"], ["good", "Good", ""], ["easy", "Easy", "secondary"]];
const AGAIN_LABEL = "Again in this session";

/** The leading `--` comment block of a sample (what it shows) and the SQL after it. */
export function splitSample(sql) {
  const lines = String(sql || "").split("\n");
  const notes = [];
  let i = 0;
  for (; i < lines.length; i++) {
    const line = lines[i].trim();
    if (line.startsWith("--")) notes.push(line.replace(/^--\s?/, ""));
    else if (line) break;
  }
  return { notes: notes.filter(Boolean), sql: lines.slice(i).join("\n").trim() };
}

const currentCard = () => C.flashcards.find(c => c.id === deck.queue[0]);

export function resetDeck() { deck = null; }

/** Start studying these cards; keepOrder for decks already in a meaningful order. */
export function openDeck(cards, keepOrder) {
  const ids = cards.map(c => c.id);
  deck = { queue: keepOrder ? ids : shuffle(ids), done: 0, again: 0, flipped: false, revealed: false, tryOpen: false, total: cards.length };
  go("/cards");
}

function render() {
  if (!deck) return renderSetup();
  renderCard();
}

function renderSetup() {
  const due = dueCards();
  const queue = P.card_queue;
  const counts = t => P.card_topic_counts[t] || { due: 0, new: 0 };
  main.innerHTML = `
    ${pageHead("Flashcards", `Flip a card, then rate how well you knew it. Good brings it back after 1 day, then 3, then longer; Hard grows the gap slowly, Easy stretches it faster; Again repeats it in this session. A card counts as learned once its gap reaches a week. You get up to ${esc(P.settings.new_cards_per_day ?? 15)} new cards a day; change it in <a href="/settings">Settings</a>.`)}
    <div class="row">
      <button class="btn large" id="study-due" ${due.length ? "" : "disabled"}>${due.length ? `Study ${queue.due.length} due · ${queue.new.length} new` : "No cards due today"}</button>
      <button class="btn secondary large" id="study-weak" title="Cards from the three topics where your mastery is lowest, due and new cards first">Study my weakest topics</button>
      <button class="btn ghost large" id="study-all">All ${C.flashcards.length} cards</button>
    </div>
    ${section("Decks by topic", `<div class="table-wrap"><table class="data">
      <thead><tr><th>Topic</th><th>Learned</th><th class="num">Due</th><th class="num">New</th><th><span class="sr-only">Actions</span></th></tr></thead>
      <tbody>${Object.keys(C.topics).map(t => {
        const cards = C.flashcards.filter(c => c.topic === t);
        const { due: d, new: n } = counts(t);
        const learned = cards.filter(c => cardLearned(c.id)).length;
        return `<tr><td>${esc(topicLabel(t))}</td><td>${meter(learned, cards.length, "Learned")}</td>
          <td class="num ${d ? "" : "muted"}">${d}</td><td class="num ${n ? "" : "muted"}">${n}</td>
          <td class="actions"><button class="btn secondary small" data-deck="${t}" ${d + n ? "" : `title="Nothing due: go through every card of this topic"`}>${d + n ? "Study" : "Review all"}</button></td></tr>`;
      }).join("")}</tbody>
    </table></div>`, { aside: `<span class="${queue.new_left ? "" : "new-left-none"}">${queue.new_left} new left today</span>` })}`;
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
  // A topic deck studies its due reviews, then its share of today's new cards; with nothing left, every card.
  $$("[data-deck]", main).forEach(b => b.addEventListener("click", () => {
    const t = b.dataset.deck;
    const queued = dueCards(t);
    if (queued.length) openDeck(queued, true);
    else openDeck(C.flashcards.filter(c => c.topic === t));
  }));
}

function renderCard() {
  if (!deck.queue.length) {
    main.innerHTML = `
      ${pageHead("Deck finished", `${plural(deck.done, "card")} done${deck.again ? `, ${deck.again} sent back for another pass` : ""}. The next reviews are scheduled.`)}
      <div class="row"><button class="btn" id="deck-back">Choose another deck</button><a class="btn secondary" href="/">Back to Today</a></div>`;
    $("#deck-back").addEventListener("click", () => { deck = null; render(); });
    return;
  }
  const card = currentCard();
  const info = P.cards[card.id];
  const sample = splitSample(card.try_sql);
  const status = !info ? "New card" : info.interval >= 1 ? `Every ${plural(info.interval, "day")}` : "Relearning";
  const progress = deck.total ? (deck.done / deck.total) * 100 : 0;
  main.innerHTML = `
    <h1 class="sr-only">Flashcards</h1>
    <div class="deck-split">
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
            <p class="card-question">${inlineCode(card.front)}</p>
            <div class="card-text">${inlineCode(card.back)}</div>
            ${sample.sql && sample.notes.length ? `<p class="card-sample"><b>What the sample shows:</b> ${sample.notes.map(esc).join("<br>")}</p>` : ""}
            <p class="card-hint">1 again, 2 hard, 3 good, 4 easy</p>
          </div>
        </button>
      </div>
      <div class="ratings" role="group" aria-label="How well did you know it?">
        ${RATINGS.map(([rating, label, kind], n) => `<button class="btn ${kind}" data-rating="${rating}" aria-keyshortcuts="${n + 1}" ${deck.flipped ? "" : "disabled"}>
          ${label} <small data-when="${rating}">${rating === "again" ? AGAIN_LABEL : ""}</small></button>`).join("")}
      </div>
    </div>
    <section class="card-try panel" id="card-try" aria-label="Try it in SQL"></section>
    </div>`;
  $("#card").addEventListener("click", flipCard);
  $$("[data-rating]", main).forEach(b => b.addEventListener("click", () => rateCard(b.dataset.rating)));
  $("#deck-quit").addEventListener("click", () => { deck = null; render(); });
  updateTry(card);
  if (deck.revealed) loadPreviews(card.id);
}

/** The next interval each rating would give, from the engine; the buttons stay plain if it fails. */
async function loadPreviews(id) {
  let days;
  try { days = await api(`/api/card/preview?id=${encodeURIComponent(id)}`); } catch { return; }
  if (!deck || deck.queue[0] !== id || !deck.revealed) return;
  for (const [rating] of RATINGS.slice(1)) {
    const el = $(`[data-when="${rating}"]`, main);
    if (el && Number.isFinite(days[rating])) el.textContent = `${Math.max(1, Math.round(days[rating]))} d`;
  }
}

/* ---------------------------------------------------------------- try it */

/* Before the flip the panel is one quiet line; after it, the editor (on narrow screens behind a button).
   Returns the editor when this call created it. */
function tryState() {
  if (!deck.revealed) return "later";
  return narrow.matches && !deck.tryOpen ? "closed" : "open";
}

function updateTry(card) {
  const box = $("#card-try");
  const state = tryState();
  if (!box || box.dataset.state === state) return null;
  box.dataset.state = state;
  if (state === "later") {
    box.innerHTML = `<p class="card-try-later">Try it in SQL after you answer</p>`;
    return null;
  }
  const sample = splitSample(card.try_sql);
  const note = blockedOn23ai(card)
    ? `This sample uses Oracle 23ai syntax, and your database is Oracle ${esc(DB.version)}.`
    : !sample.sql ? "No sample for this card. Write your own query; changes are rolled back."
    : card.cleanup ? "A sample for this card. Predict the result, then run it. Its LAB_ objects are dropped before and after each run."
      : "A sample for this card. Predict the result, then run it. Changes are rolled back.";
  if (state === "closed") {
    box.innerHTML = `<div class="card-try-bar"><p>${note}</p>
      <button class="btn secondary" id="card-try-open" aria-expanded="false" aria-controls="card-try">Try it</button></div>`;
    $("#card-try-open").addEventListener("click", () => {
      deck.tryOpen = true;
      updateTry(card)?.focus();
    });
    return null;
  }
  deck.tryOpen = true;  // once open it stays open, so a resize never throws the SQL away
  box.innerHTML = `
    <div class="card-try-head"><h2>Try it</h2><p>${note}</p></div>
    <div class="editor-wrap">
      <textarea class="editor" id="card-sql" aria-label="SQL for this card" spellcheck="false" autocapitalize="off" autocomplete="off">${esc(sample.sql)}</textarea>
      <div class="editor-bar">
        <button class="btn" id="card-run"><span>Run</span> <span class="kbd">Ctrl+Enter</span></button>
        ${sample.sql ? `<button class="link-btn quiet" id="card-restore">Restore the sample</button>` : ""}
        <span class="links"><button class="link-btn" id="card-lab">Open in SQL lab</button></span>
      </div>
    </div>
    <div class="results" id="card-results" aria-live="polite"></div>`;
  return bindTry(card, sample.sql);
}

function bindTry(card, sampleSql) {
  const results = $("#card-results");
  const editor = makeEditor($("#card-sql"), { onRun: () => run() });
  editor.onSelection(has => { $("#card-run span").textContent = has ? "Run selection" : "Run"; });
  const run = async () => {
    const sql = editor.selection() || editor.get();
    if (!sql.trim()) return toast("Type some SQL first.");
    const btn = $("#card-run");
    btn.disabled = true;
    results.innerHTML = loading("Running");
    try { results.innerHTML = resultsHtml(await api("/api/run", { sql, keep: false, card: card.id })); }
    catch (err) { results.innerHTML = errorBox(err.message); }
    btn.disabled = false;
  };
  $("#card-run").addEventListener("click", run);
  $("#card-restore")?.addEventListener("click", () => { editor.set(sampleSql); results.innerHTML = ""; editor.focus(); });
  $("#card-lab").addEventListener("click", () => { labDraft(editor.get()); go("/lab"); });
  return editor;
}

function flipCard() {
  deck.flipped = !deck.flipped;
  const el = $("#card");
  el.classList.toggle("flipped", deck.flipped);
  el.setAttribute("aria-label", deck.flipped ? "Answer side. Press to show the question." : "Question side. Press to show the answer.");
  $$(".card-face", el).forEach((f, n) => f.setAttribute("aria-hidden", n === 0 ? deck.flipped : !deck.flipped));
  $$("[data-rating]", main).forEach(b => { b.disabled = !deck.flipped; });
  if (deck.flipped && !deck.revealed) {
    deck.revealed = true;
    updateTry(currentCard());
    loadPreviews(deck.queue[0]);
  }
}

async function rateCard(rating) {
  if (!deck.flipped) return;
  const id = deck.queue.shift();
  if (rating === "again") { deck.again++; deck.queue.splice(Math.min(deck.queue.length, 3), 0, id); }
  else deck.done++;
  deck.flipped = false;
  deck.revealed = false;
  deck.tryOpen = false;
  try { apply(await api("/api/card", { id, rating })); } catch { toastError("Could not save the card result."); }
  renderCard();
  $("#card")?.focus({ preventScroll: true });
}

function onKey(e) {
  if (!deck || !deck.queue.length) return;
  if (e.key === " " || (e.key === "Enter" && e.target.id !== "card")) { e.preventDefault(); flipCard(); }
  else if (e.key === "1") rateCard("again");
  else if (e.key === "2") rateCard("hard");
  else if (e.key === "3") rateCard("good");
  else if (e.key === "4") rateCard("easy");
}

export const cardsView = { title: "Flashcards", render, onKey };
