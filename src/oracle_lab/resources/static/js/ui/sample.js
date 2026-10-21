/* Layout of a flashcard's sample for the editor: one step per statement with its `--` comment,
   a blank line between steps, and a long one-line statement broken before its main clauses.
   Only whitespace outside quotes changes, so the SQL runs exactly as written. */

const CLAUSE = /^(?:SELECT|(?:LEFT|RIGHT|FULL|CROSS|NATURAL|INNER)(?:\s+OUTER)?\s+JOIN|JOIN|FROM|WHERE|GROUP\s+BY|HAVING|ORDER\s+BY|UNION(?:\s+ALL)?|INTERSECT|MINUS|OFFSET|FETCH|SET)\b/i;
const SET_OPERATOR = /^(?:UNION|INTERSECT|MINUS)/i;
const LONG = 60;

/** For each character of one line: true when it is SQL at bracket depth 0 (not in a literal,
    a quoted name, a comment or brackets); `end` is where a trailing `--` comment starts. */
function topLevel(text) {
  const top = new Array(text.length).fill(false);
  let depth = 0;
  for (let i = 0; i < text.length;) {
    const c = text[i];
    if (c === "-" && text[i + 1] === "-") return { top, end: i };
    if (c === "/" && text[i + 1] === "*") {
      const end = text.indexOf("*/", i + 2);
      i = end < 0 ? text.length : end + 2;
    } else if ((c === "q" || c === "Q") && text[i + 1] === "'" && !/[\w$#]/.test(text[i - 1] || "")) {
      const open = text[i + 2];
      const close = { "[": "]", "{": "}", "(": ")", "<": ">" }[open] || open;
      const end = text.indexOf(close + "'", i + 3);
      i = end < 0 ? text.length : end + 2;
    } else if (c === "'") {
      let j = i + 1;
      while (j < text.length && !(text[j] === "'" && text[j + 1] !== "'")) j += text[j] === "'" ? 2 : 1;
      i = j + 1;
    } else if (c === '"') {
      const end = text.indexOf('"', i + 1);
      i = end < 0 ? text.length : end + 1;
    } else {
      if (c === "(") depth++;
      else if (c === ")") depth = Math.max(0, depth - 1);
      else if (depth === 0) top[i] = true;
      i++;
    }
  }
  return { top, end: text.length };
}

const semicolons = (text, top) => [...text].filter((c, i) => c === ";" && top[i]).length;

/** Whether the line ends a statement (a top-level `;` before any trailing comment). */
function endsStatement(line) {
  const { top, end } = topLevel(line);
  const code = line.slice(0, end).trimEnd();
  return code.endsWith(";") && top[code.length - 1];
}

/** A long one-line statement, broken before FROM, WHERE, joins, set operators and so on. */
export function breakClauses(line) {
  const { top, end } = topLevel(line);
  if (end < line.length || line.length <= LONG || semicolons(line, top) !== 1) return [line];
  const update = /^\s*UPDATE\b/i.test(line);
  const cuts = [];
  for (let i = 1; i < line.length; i++) {
    if (!top[i] || !/\s/.test(line[i - 1]) || /[\w$#]/.test(line[i - 1])) continue;
    const m = line.slice(i).match(CLAUSE);
    if (!m) continue;
    const word = m[0].toUpperCase();
    const before = line.slice(0, i).trimEnd().split(/\s+/).at(-1).toUpperCase();
    if ((word === "SET" && !update) || (word === "FROM" && before === "DELETE")) continue;
    // SELECT starts a line only as the query of CREATE ... AS SELECT or INSERT ... SELECT.
    if (word === "SELECT" && !(/^\s*INSERT\b/i.test(line) || before === "AS" && /^\s*CREATE\b/i.test(line))) continue;
    cuts.push(i);
    if (SET_OPERATOR.test(word)) {
      const after = i + m[0].length;
      const next = line.slice(after).search(/\S/);
      if (next > 0) cuts.push(after + next);
    }
    i += m[0].length - 1;
  }
  const parts = [];
  let from = 0;
  for (const at of cuts) { parts.push(line.slice(from, at).trimEnd()); from = at; }
  parts.push(line.slice(from));
  return parts.filter(p => p.trim());
}

/** The sample as the editor shows it. */
export function formatSample(sql) {
  const out = [];
  let inStatement = false;   // a statement has started and not yet ended
  let lastCode = false;      // the previous non-blank line was SQL
  const gap = () => { if (out.length && out.at(-1) !== "") out.push(""); };
  for (const raw of String(sql || "").split("\n")) {
    const line = raw.trimEnd();
    const t = line.trim();
    if (!t) { gap(); continue; }
    if (t.startsWith("--") && !inStatement) {
      if (lastCode) gap();
      out.push(line);
      lastCode = false;
      continue;
    }
    if (!inStatement && lastCode) gap();
    out.push(...(inStatement ? [line] : breakClauses(line)));
    inStatement = !endsStatement(line);
    lastCode = true;
  }
  while (out.at(-1) === "") out.pop();
  return out.join("\n");
}

/** The `--` comment lines a statement starts with, as one line of text ("" if none). */
export function stepCaption(sql) {
  const notes = [];
  for (const raw of String(sql).split("\n")) {
    const t = raw.trim();
    if (t.startsWith("--")) notes.push(t.replace(/^--\s?/, ""));
    else if (t) break;
  }
  return notes.filter(Boolean).join(" ");
}
