/* Flashcards with spaced repetition: pick a deck, flip, rate. Beside the card, a SQL editor
   holds the card's sample (try_sql), so the rule on the card can be tried once it is answered.
   The sample stays hidden until the flip: its leading comment usually states the answer. */

import { $, $$, esc, shuffle } from "../core/dom.js";
import { api } from "../core/api.js";
import { t, tn, lang, LANGUAGES } from "../core/i18n.js";
import { store } from "../core/store.js";
import { C, P, CARD, DB, A, apply, dueCards, cardLearned, topicLabel, topicNo, needsNewerDb, labOff, noLab, todayLeft, leftToday, isGuest } from "../core/state.js";
import { main, go } from "../core/router.js";
import { toast, toastError } from "../ui/feedback.js";
import { meter, pageHead, section, loading, limitPanel } from "../ui/widgets.js";
import { makeEditor } from "../ui/editor.js";
import { resultsHtml, errorBox } from "../ui/sql.js";
import { formatSample } from "../ui/sample.js";
import { cardText } from "../ui/cardtext.js";
import { labDraft } from "./lab.js";

let deck = null;

/* The language of the card text. The switch above the card shows the same card in the other language (to check
   something unclear in your own) without changing the app's language or reloading; it stays until switched back.
   Each language's cards are fetched once per exam track. */
const LANGUAGE_NAMES = { en: ["EN", "English"], pl: ["PL", "Polski"] };
let cardLanguage = null;  // null: the app's language
const translations = {};  // "exam:language" -> { cards: {id: card}, topics }

const shownLanguage = () => cardLanguage ?? lang();

async function cardsIn(code) {
  if (code === lang()) return { cards: CARD, topics: C.topics };
  const key = `${C.exam.code}:${code}`;
  if (!translations[key]) {
    const content = await api("/api/content", undefined, { language: code });
    translations[key] = { cards: Object.fromEntries(content.flashcards.map(c => [c.id, c])), topics: content.topics };
  }
  return translations[key];
}

/** The card's texts in the shown language (the app's when that language is not loaded). */
function shownCard(card) {
  const source = cardLanguage && translations[`${C.exam.code}:${cardLanguage}`];
  const other = source?.cards[card.id];
  if (!other) return { front: card.front, back: card.back, topic: topicLabel(card.topic), language: lang() };
  return { front: other.front, back: other.back, topic: `${topicNo(card.topic)}. ${source.topics[card.topic] ?? ""}`, language: cardLanguage };
}

const languageSwitch = () => `<div class="seg card-lang" role="group" aria-label="${esc(t("Card language"))}" title="${esc(t("Show this card in another language. Press L to switch."))}">
  ${LANGUAGES.map(code => `<button type="button" data-card-lang="${code}" lang="${code}" aria-label="${esc(LANGUAGE_NAMES[code][1])}" aria-pressed="${code === shownLanguage()}">${LANGUAGE_NAMES[code][0]}</button>`).join("")}
</div>`;

/** Shows the current card in `code`, in place: the side, the rating buttons and the Try-it editor stay as they are. */
async function showCardIn(code) {
  if (!deck?.queue.length || code === shownLanguage()) return;
  const id = deck.queue[0];
  try { await cardsIn(code); } catch (err) { toastError(err.message); return; }
  if (!deck || deck.queue[0] !== id || !$("#card")) return;  // the card changed meanwhile
  cardLanguage = code === lang() ? null : code;
  const shown = shownCard(currentCard());
  const el = $("#card");
  el.lang = shown.language;
  $(".card-topic", el).textContent = shown.topic;
  $(".card-front .card-text", el).innerHTML = cardText(shown.front);
  $(".card-question", el).innerHTML = cardText(shown.front);
  $(".card-back .card-text", el).innerHTML = cardText(shown.back);
  $$("[data-card-lang]", main).forEach(b => b.setAttribute("aria-pressed", String(b.dataset.cardLang === shownLanguage())));
}

const otherLanguage = () => LANGUAGES.find(code => code !== shownLanguage());

// Below this width the Try-it panel sits under the card, so it stays behind a button even after the flip.
const narrow = matchMedia("(max-width: 1179.98px)");
narrow.addEventListener("change", () => { if (deck?.queue.length && $("#card-try")) updateTry(currentCard()); });

/** The four ratings in key order: [rating sent to the server, label, what it means]. */
const ratings = () => [
  ["again", t("Again"), t("Didn't know it")],
  ["hard", t("Hard"), t("Took some effort")],
  ["good", t("Medium"), t("Knew it")],
  ["easy", t("Easy"), t("Knew it at once")],
];
const RATING_KEYS_SEEN = "seen-rating-keys";

const currentCard = () => C.flashcards.find(c => c.id === deck.queue[0]);

export function resetDeck() { deck = null; }

/** Start studying these cards; keepOrder for decks already in a meaningful order, fromToday for
    today's session (its end then leads on to today's exercise). */
export function openDeck(cards, keepOrder, { fromToday = false } = {}) {
  const ids = cards.map(c => c.id);
  deck = { queue: keepOrder ? ids : shuffle(ids), done: 0, again: 0, flipped: false, revealed: false, tryOpen: false, busy: false,
    total: cards.length, fromToday };
  go("/cards");
}

function render() {
  if (deck && !leftToday("cards")) { deck = null; main.innerHTML = limitPanel("cards", A.limits.cards, isGuest()); return; }
  if (!deck) return renderSetup();
  renderCard();
}

function renderSetup() {
  const due = dueCards();
  const queue = P.card_queue;
  const counts = id => P.card_topic_counts[id] || { due: 0, new: 0 };
  main.innerHTML = `
    ${pageHead(esc(t("Flashcards")), esc(t("Flip a card, then rate how well you knew it: Again repeats it in this session, Hard brings it back soon, Medium a little later, Easy later still. A card counts as learned once its gap reaches a week. You get up to {n} new cards a day; change it in {settings}.", { n: P.settings.new_cards_per_day ?? 15 })).replace("{settings}", `<a href="/settings">${esc(t("Settings"))}</a>`))}
    <div class="row">
      <button class="btn large" id="study-due" ${due.length ? "" : "disabled"}>${esc(due.length ? t("Study {due} due · {fresh} new", { due: queue.due.length, fresh: queue.new.length }) : t("No cards due today"))}</button>
      <button class="btn secondary large" id="study-weak" title="${esc(t("Cards from the three topics where your mastery is lowest, due and new cards first"))}">${esc(t("Study my weakest topics"))}</button>
      <button class="btn ghost large" id="study-all">${esc(t("All {n} cards", { n: C.flashcards.length }))}</button>
    </div>
    ${section(esc(t("Decks by topic")), `<div class="table-wrap"><table class="data">
      <thead><tr><th>${esc(t("Topic"))}</th><th>${esc(t("Learned"))}</th><th class="num">${esc(t("Due"))}</th><th class="num">${esc(t("New"))}</th><th><span class="sr-only">${esc(t("Actions"))}</span></th></tr></thead>
      <tbody>${Object.keys(C.topics).map(id => {
        const cards = C.flashcards.filter(c => c.topic === id);
        const { due: d, new: n } = counts(id);
        const learned = cards.filter(c => cardLearned(c.id)).length;
        return `<tr><td>${esc(topicLabel(id))}</td><td>${meter(learned, cards.length, t("Learned"))}</td>
          <td class="num ${d ? "" : "muted"}">${d}</td><td class="num ${n ? "" : "muted"}">${n}</td>
          <td class="actions"><button class="btn secondary small" data-deck="${id}" ${d + n ? "" : `title="${esc(t("Nothing due: go through every card of this topic"))}"`}>${esc(d + n ? t("Study") : t("Review all"))}</button></td></tr>`;
      }).join("")}</tbody>
    </table></div>`, { aside: `<span class="${queue.new_left ? "" : "new-left-none"}">${esc(t("{n} new left today", { n: queue.new_left }))}</span>` })}`;
  $("#study-due").addEventListener("click", () => openDeck(due));
  $("#study-all").addEventListener("click", () => openDeck(C.flashcards));
  $("#study-weak").addEventListener("click", () => {
    const rank = id => ({ new: 1, weak: 0, learning: 2, strong: 3 }[P.topics[id]?.level] ?? 1) + (P.topics[id]?.estimate || 0);
    const weakest = Object.keys(C.topics).sort((a, b) => rank(a) - rank(b)).slice(0, 3);
    // Due reviews first, then new cards within what is left of today's allowance, then cards already seen.
    const inWeak = c => weakest.includes(c.topic);
    const dueNow = P.card_queue.due.map(id => CARD[id]).filter(c => c && inWeak(c));
    const dueIds = new Set(dueNow.map(c => c.id));
    const fresh = C.flashcards.filter(c => inWeak(c) && !P.cards[c.id]).slice(0, P.card_queue.new_left);
    const seen = C.flashcards.filter(c => inWeak(c) && P.cards[c.id] && !dueIds.has(c.id));
    toast(t("Weakest topics: {topics}", { topics: weakest.map(topicLabel).join(", ") }));
    openDeck([...dueNow, ...fresh, ...seen].slice(0, 30), true);
  });
  // A topic deck studies its due reviews, then its share of today's new cards; with nothing left, every card.
  $$("[data-deck]", main).forEach(b => b.addEventListener("click", () => {
    const topic = b.dataset.deck;
    const queued = dueCards(topic);
    if (queued.length) openDeck(queued, true);
    else openDeck(C.flashcards.filter(c => c.topic === topic));
  }));
}

function renderCard() {
  if (!deck.queue.length) {
    const lab = deck.fromToday ? todayLeft().lab : null;
    main.innerHTML = `
      ${pageHead(esc(t("Deck finished")), esc(deck.again
        ? tn(deck.done, "{n} card done, {again} sent back for another pass. The next reviews are scheduled.", "{n} cards done, {again} sent back for another pass. The next reviews are scheduled.", { again: deck.again })
        : tn(deck.done, "{n} card done. The next reviews are scheduled.", "{n} cards done. The next reviews are scheduled.")))}
      <div class="row">${lab ? `<a class="btn" href="/exercises/${esc(lab)}">${esc(t("Continue: today's exercise"))}</a>` : ""}
        <button class="btn ${lab ? "secondary" : ""}" id="deck-back">${esc(t("Choose another deck"))}</button><a class="btn secondary" href="/">${esc(t("Back to Today"))}</a></div>`;
    $("#deck-back").addEventListener("click", () => { deck = null; render(); });
    return;
  }
  const card = currentCard();
  const shown = shownCard(card);
  const info = P.cards[card.id];
  const status = !info ? t("New card") : info.interval >= 1 ? tn(info.interval, "Every {n} day", "Every {n} days") : t("Relearning");
  const progress = deck.total ? (deck.done / deck.total) * 100 : 0;
  main.innerHTML = `
    <h1 class="sr-only">${esc(t("Flashcards"))}</h1>
    <div class="deck-split">
    <div class="deck">
      <div class="deck-top">
        <div class="deck-stats" aria-live="polite">
          <span><b>${deck.queue.length}</b> ${esc(t("left"))}</span><span><b>${deck.done}</b> ${esc(t("done"))}</span><span><b>${deck.again}</b> ${esc(t("again"))}</span>
        </div>
        <span class="spacer"></span>
        ${languageSwitch()}
        <button class="link-btn quiet small" id="deck-quit">${esc(t("Stop studying"))}</button>
      </div>
      <div class="deck-progress"><i style="width:${progress}%"></i></div>
      <div class="card-stage">
        <button class="index-card ${deck.flipped ? "flipped" : ""}" id="card" lang="${esc(shown.language)}" aria-label="${esc(cardSideLabel())}">
          <div class="card-face card-front" aria-hidden="${deck.flipped}">
            <span class="card-box">${esc(status)}</span>
            <p class="card-topic">${esc(shown.topic)}</p>
            <div class="card-text">${cardText(shown.front)}</div>
            <p class="card-hint">${esc(t("Space or click to flip"))}</p>
          </div>
          <div class="card-face card-back" aria-hidden="${!deck.flipped}">
            <p class="card-question">${cardText(shown.front)}</p>
            <div class="card-text">${cardText(shown.back)}</div>
            <p class="card-hint">${esc(t("1 again, 2 hard, 3 medium, 4 easy"))}</p>
          </div>
        </button>
      </div>
      <div class="ratings" role="group" aria-label="${esc(t("How well did you know it?"))}">
        ${ratings().map(([rating, label, hint], n) => `<button class="rate rate-${rating}" data-rating="${rating}" aria-keyshortcuts="${n + 1}" ${deck.flipped ? "" : "disabled"}>
          <kbd aria-hidden="true">${n + 1}</kbd><span class="rate-label">${esc(label)}</span><span class="rate-hint">${esc(hint)}</span></button>`).join("")}
      </div>
    </div>
    <section class="card-try panel" id="card-try" aria-label="${esc(t("Try it in SQL"))}"></section>
    </div>`;
  $("#card").addEventListener("click", flipCard);
  $$("[data-rating]", main).forEach(b => b.addEventListener("click", () => rateCard(b.dataset.rating)));
  $("#deck-quit").addEventListener("click", () => { deck = null; render(); });
  $$("[data-card-lang]", main).forEach(b => b.addEventListener("click", () => showCardIn(b.dataset.cardLang)));
  updateTry(card);
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
    box.innerHTML = `<p class="card-try-later">${esc(t("Try it in SQL after you answer"))}</p>`;
    return null;
  }
  const sample = formatSample(card.try_sql);
  const off = labOff();
  const note = esc(off ? noLab()
    : needsNewerDb(card)
    ? t("This sample needs {needs}, and your database is {product} {version}.", { needs: card.needs.label, product: DB.product, version: DB.version })
    : !sample ? t("No sample for this card. Write your own query; changes are rolled back.")
    : card.cleanup ? t("A sample for this card. Predict the result, then run it. Its LAB_ objects are dropped before and after each run.")
      : t("A sample for this card. Predict the result, then run it. Changes are rolled back."));
  if (state === "closed") {
    box.innerHTML = `<div class="card-try-bar"><p>${note}</p>
      <button class="btn secondary" id="card-try-open" aria-expanded="false" aria-controls="card-try">${esc(t("Try it"))}</button></div>`;
    $("#card-try-open").addEventListener("click", () => {
      deck.tryOpen = true;
      updateTry(card)?.focus();
    });
    return null;
  }
  deck.tryOpen = true;  // once open it stays open, so a resize never throws the SQL away
  box.innerHTML = `
    <div class="card-try-head"><h2>${esc(t("Try it"))}</h2><p>${note}</p></div>
    <div class="editor-wrap">
      <textarea class="editor" id="card-sql" aria-label="${esc(t("SQL for this card"))}" spellcheck="false" autocapitalize="off" autocomplete="off">${esc(sample)}</textarea>
      <div class="editor-bar">
        <button class="btn" id="card-run" ${off ? "disabled" : ""}><span>${esc(t("Run"))}</span> <span class="kbd">Ctrl+Enter</span></button>
        ${sample ? `<button class="link-btn quiet" id="card-restore">${esc(t("Restore the sample"))}</button>` : ""}
        <span class="links"><button class="link-btn" id="card-lab" ${off ? "disabled" : ""}>${esc(t("Open in SQL lab"))}</button></span>
      </div>
    </div>
    <div class="results" id="card-results" aria-live="polite"></div>`;
  return bindTry(card, sample);
}

function bindTry(card, sampleSql) {
  const results = $("#card-results");
  const editor = makeEditor($("#card-sql"), { onRun: () => run() });
  editor.onSelection(has => { $("#card-run span").textContent = has ? t("Run selection") : t("Run"); });
  const run = async () => {
    if (labOff()) return;
    const sql = editor.selection() || editor.get();
    if (!sql.trim()) return toast(t("Type some SQL first."));
    const btn = $("#card-run");
    btn.disabled = true;
    results.innerHTML = loading(t("Running"));
    try { results.innerHTML = resultsHtml(await api("/api/run", { sql, keep: false, card: card.id }), { expectError: card.try_error }); }
    catch (err) { results.innerHTML = errorBox(err.message); }
    btn.disabled = false;
  };
  $("#card-run").addEventListener("click", run);
  $("#card-restore")?.addEventListener("click", () => { editor.set(sampleSql); results.innerHTML = ""; editor.focus(); });
  $("#card-lab").addEventListener("click", () => { labDraft(editor.get()); go("/lab"); });
  return editor;
}

const cardSideLabel = () => deck.flipped ? t("Answer side. Press to show the question.") : t("Question side. Press to show the answer.");

function flipCard() {
  if (deck.busy) return;
  deck.flipped = !deck.flipped;
  const el = $("#card");
  el.classList.toggle("flipped", deck.flipped);
  el.setAttribute("aria-label", cardSideLabel());
  $$(".card-face", el).forEach((f, n) => f.setAttribute("aria-hidden", n === 0 ? deck.flipped : !deck.flipped));
  $$("[data-rating]", main).forEach(b => { b.disabled = !deck.flipped; });
  if (deck.flipped && !deck.revealed) {
    deck.revealed = true;
    // Once per learner: the rating keys changed from three ratings to four.
    if (!store(RATING_KEYS_SEEN)) {
      store(RATING_KEYS_SEEN, true);
      toast(t("Rating keys: 1 Again · 2 Hard · 3 Medium · 4 Easy"));
    }
    updateTry(currentCard());
  }
}

async function rateCard(rating) {
  // While a rating is saving, keys and clicks wait, so the next card cannot open already flipped.
  if (!deck.flipped || deck.busy) return;
  deck.busy = true;
  const current = deck;
  const id = deck.queue.shift();
  if (rating === "again") { deck.again++; deck.queue.splice(Math.min(deck.queue.length, 3), 0, id); }
  else deck.done++;
  deck.flipped = false;
  deck.revealed = false;
  deck.tryOpen = false;
  try { apply(await api("/api/card", { id, rating })); } catch (err) {
    if (err.limit) { deck = null; main.innerHTML = limitPanel("cards", A?.limits?.cards, isGuest()); current.busy = false; return; }
    toastError(t("Could not save the card result."));
  }
  current.busy = false;
  if (deck !== current) return;  // the deck was closed meanwhile
  renderCard();
  $("#card")?.focus({ preventScroll: true });
}

function onKey(e) {
  if (e.repeat || !deck || !deck.queue.length) return;
  // Space and Enter flip only from the card or the page itself; on Run, Try it or Stop studying they
  // press that button. Enter on the card is its own click, so only Space is handled there.
  const onPage = e.target === document.body || e.target === main;
  if ((e.key === " " && (onPage || e.target.id === "card")) || (e.key === "Enter" && onPage)) { e.preventDefault(); flipCard(); }
  else if (e.key === "1") rateCard("again");
  else if (e.key === "2") rateCard("hard");
  else if (e.key === "3") rateCard("good");
  else if (e.key === "4") rateCard("easy");
  else if (e.key === "l" || e.key === "L") showCardIn(otherLanguage());
}

export const cardsView = { get title() { return t("Flashcards"); }, render, onKey };
