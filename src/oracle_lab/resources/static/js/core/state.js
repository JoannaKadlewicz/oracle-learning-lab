/* Application state. Exported `let` bindings are live: importers always read the current value,
   and only the setters below change them.

   C  content of the chosen exam track: topics, questions, flashcards, labs
   S  saved progress from the server: attempts, cards, labs, settings
   P  computed by app/engine.py: mastery, mistakes, due items, daily plan; plus
      P.sql_available, the snapshot's top-level flag (false: this user cannot run SQL here)
   DB the connected database: version, major */

import { api } from "./api.js";
import { t } from "./i18n.js";

export let C = null;
export let S = null;
export let P = null;
export let DB = null;
export let A = null;  // the user's access in the current workspace: { workspace, level, usable, limits, used }
export const Q = {};
export const L = {};
export const CARD = {};

export function apply(snapshot) {
  S = snapshot.state;
  P = snapshot.progress;
  if (P) P.sql_available = snapshot.sql_available !== false;
  if (snapshot.access) A = snapshot.access;  // mock exam answers come without it: the last one stays
}

/* The account's plan (guest, user, pro, admin) and what it may use; the server enforces the same table
   (access/plans.py). */
const FEATURES = {
  sql_lab: ["pro", "admin", "learner"],
  mock: ["user", "pro", "admin", "learner"],
  exercises: ["user", "pro", "admin", "learner"],
  many_workspaces: ["pro", "admin", "learner"],
};
export const plan = () => A?.plan ?? "admin";
export const can = feature => FEATURES[feature].includes(plan());
export const isGuest = () => plan() === "guest";

/** The one line shown where a graded exercise would run, when it cannot. */
export const noSql = () => isGuest()
  ? t("Create a free account to solve SQL exercises: 10 a day are included.")
  : t("SQL practice isn't enabled on this server yet.");
/** The one line shown where free SQL (the lab, a card's Try it, Run without checking) would run, when it cannot. */
export const noLab = () => isGuest() ? t("Free SQL runs are part of the Pro plan. Start with a free account.")
  : !can("sql_lab") ? t("The SQL lab is part of the Pro plan.") : noSql();
export const sqlOff = () => P?.sql_available === false;
/** Free SQL (lab, Try it, Run without checking) is off: no practice, or not the Pro plan. */
export const labOff = () => sqlOff() || !can("sql_lab");
/** What is left today of a daily `kind` ("questions", "cards" or "exercises"); Infinity without a limit. */
export const leftToday = kind => {
  const limit = A?.limits?.[kind];
  return limit == null ? Infinity : Math.max(0, limit - (A.used?.[kind] ?? 0));
};

/** What is left of today's plan after the questions: flashcard ids not reviewed yet, and the
    exercise when it is planned, not passed, and SQL is available. */
export function todayLeft() {
  const plan = P.plan;
  return {
    cards: plan.cards.filter(id => !plan.done.cards.includes(id) && CARD[id]),
    lab: plan.lab && !plan.done.lab && !sqlOff() && L[plan.lab] ? plan.lab : null,
  };
}

export function setDatabase(db) { DB = db; }

export async function loadProgress() {
  apply(await api("/api/progress"));
}

/** The content of the chosen exam; reloaded when the track changes. */
export async function loadContent() {
  C = await api("/api/content");
  C.questions.forEach(q => { Q[q.id] = q; });
  C.labs.forEach(l => { L[l.id] = l; });
  C.flashcards.forEach(c => { CARD[c.id] = c; });
}

export const topicName = id => C.topics[id] || id;
export const topicNo = id => Number(id.slice(1));
export const topicLabel = id => `${topicNo(id)}. ${topicName(id)}`;

/** Items whose SQL needs a newer database than the connected one (the server marks them with `needs`). */
export const needsNewerDb = item => !!(item.needs && DB && DB.major < item.needs.major);

export function lastAttempt(qid) {
  const list = S.attempts[qid];
  return list && list.length ? list[list.length - 1] : null;
}

export const mistakes = () => P.mistakes;
/** Flashcards to study now: due reviews first, then new cards within today's allowance (`P.card_queue`).
    A topic's new cards come from the same allowance, as many as `P.card_topic_counts` gives it. */
export function dueCards(topic) {
  const queue = P.card_queue;
  if (!topic) return [...queue.due, ...queue.new].map(id => CARD[id]).filter(Boolean);
  const due = queue.due.map(id => CARD[id]).filter(c => c && c.topic === topic);
  const fresh = C.flashcards.filter(c => c.topic === topic && !P.cards[c.id]).slice(0, P.card_topic_counts[topic]?.new || 0);
  return [...due, ...fresh];
}
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
