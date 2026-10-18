/* Application state. Exported `let` bindings are live: importers always read the current value,
   and only the setters below change them.

   C  content of the chosen exam track: topics, questions, flashcards, labs
   S  saved progress from the server: attempts, cards, labs, settings
   P  computed by app/engine.py: mastery, mistakes, due items, daily plan
   DB the connected database: version, major */

import { api } from "./api.js";

export let C = null;
export let S = null;
export let P = null;
export let DB = null;
export const Q = {};
export const L = {};
export const CARD = {};

export function apply(snapshot) {
  S = snapshot.state;
  P = snapshot.progress;
}

export function setDatabase(db) { DB = db; }

export async function loadProgress() {
  apply(await api("/api/progress"));
}

/** The content of the chosen exam track (1Z0-071 or 1Z0-171); reloaded when the track changes. */
export async function loadContent() {
  C = await api("/api/content");
  C.questions.forEach(q => { Q[q.id] = q; });
  C.labs.forEach(l => { L[l.id] = l; });
  C.flashcards.forEach(c => { CARD[c.id] = c; });
}

export const topicName = id => C.topics[id] || id;
export const topicNo = id => Number(id.slice(1));
export const topicLabel = id => `${topicNo(id)}. ${topicName(id)}`;
export const dbLabel = code => code === "1Z0-171" ? "Oracle 23ai" : "Oracle 19c";

/** Items whose SQL only runs on Oracle 23ai, when the connected database is older. */
export const blockedOn23ai = item => item.topic === "t15" && DB && DB.major < 23;

export function lastAttempt(qid) {
  const list = S.attempts[qid];
  return list && list.length ? list[list.length - 1] : null;
}

export const mistakes = () => P.mistakes;
export const dueCards = topic => P.due_cards.map(id => CARD[id]).filter(c => !topic || c.topic === topic);
export const cardLearned = id => (P.cards[id]?.interval || 0) >= 7;

export function topicStats(topic) {
  const qs = C.questions.filter(q => q.topic === topic);
  let answered = 0, correct = 0;
  for (const q of qs) {
    const a = lastAttempt(q.id);
    if (a) { answered++; if (a.correct) correct++; }
  }
  const cards = C.flashcards.filter(c => c.topic === topic);
  const labs = C.labs.filter(l => l.topic === topic);
  return {
    total: qs.length, answered, correct,
    cards: cards.length, learned: cards.filter(c => cardLearned(c.id)).length,
    labs: labs.length, passed: labs.filter(l => S.labs[l.id]?.passed).length,
  };
}
