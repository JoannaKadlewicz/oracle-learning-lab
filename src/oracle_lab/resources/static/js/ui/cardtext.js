/* A flashcard's question or answer as HTML, with the SQL inside the prose set as code:
   error codes, literals, quoted names, function calls and runs of upper-case SQL words. */

import { esc } from "../core/dom.js";

const WORD = /[\p{L}\p{N}_$#]/u;
const ERROR_CODE = /^(?:ORA|PLS|SP2)-\d{5}/;
const CALL = /^[A-Z][A-Z0-9_$#]*(?:\.[A-Z][A-Z0-9_$#]*)*(?=\()/;
const NAME = String.raw`[A-Z][A-Z0-9_$#]+(?:\.[A-Z0-9_$#*]+)*`;
const CAPS = new RegExp(String.raw`^${NAME}(?:[ ]+${NAME})*(?![\p{L}\p{N}_])`, "u");
// Upper-case words that are prose, not SQL.
const PROSE = new Set(["SQL", "ANSI", "ISO", "OK", "PL", "II", "III", "IV", "VI", "DDL", "DML", "DCL", "TCL", "CTAS", "FK", "PK", "UTC", "US"]);
// A statement written out in the text, from the start of a sentence...
const STATEMENT = /^(?:SELECT|INSERT|UPDATE|DELETE|MERGE)\s/;
// ...ends where the prose starts again: a sentence or clause mark, or a Polish word.
const PROSE_START = /^(?:[.;:?!](?=\s|$)|,(?=\s+(?:a|i|albo|lub|ale|bo|gdy|czyli|więc)\s)|\s+—\s|\s+\((?=\p{Ll}+\s|\p{Ll}*[ąćęłńóśźż]))/u;
// A keyword followed by one of these is the word in a sentence ("SELECT i uprawnienia"), not a statement.
const NOT_STATEMENT = /^\S+\s+(?:i|a|oraz|lub|albo|to|jest|z|w|na|daje|zwraca|\p{L}*[ąćęłńóśźż]\p{L}*)(?![\p{L}\p{N}_])/u;
const POLISH_WORD = /^\s+(?:\p{L}*[ąćęłńóśźżĄĆĘŁŃÓŚŹŻ]\p{L}*|z|w|to|co|czy|nie|jest|daje|zwraca|gdy|oraz|albo|po|na|do|jak|ale|np|dla|bo|tylko|zadziała|działa)(?![\p{L}\p{N}_])/u;
const MAX = 80;

/** End index of a literal ('...', q'[...]', N'...') starting at i, or -1. */
function literalEnd(text, i) {
  let j = i;
  if (/[nN]/.test(text[j]) && text[j + 1] === "'") j++;
  if (/[qQ]/.test(text[j]) && text[j + 1] === "'") {
    const open = text[j + 2];
    const close = { "[": "]", "{": "}", "(": ")", "<": ">" }[open] || open;
    if (!open || /\s/.test(open)) return -1;
    const end = text.indexOf(close + "'", j + 3);
    return end < 0 || end - i > MAX ? -1 : end + 2;
  }
  if (text[j] !== "'") return -1;
  for (let k = j + 1; k < text.length && k - i <= MAX; k++) {
    if (text[k] === "\n") return -1;
    if (text[k] === "'") {
      if (text[k + 1] === "'") { k++; continue; }
      return k + 1;
    }
  }
  return -1;
}

/** End index of a statement written out at i: up to where the prose starts again, or -1. */
function statementEnd(text, i) {
  if (!STATEMENT.test(text.slice(i)) || NOT_STATEMENT.test(text.slice(i))) return -1;
  for (let k = i; k < text.length; k++) {
    if (text[k] === "'" && !WORD.test(text[k - 1] || "")) {
      const end = literalEnd(text, k);
      if (end > 0) { k = end - 1; continue; }
    }
    const rest = text.slice(k);
    if (text[k - 1] !== "." && PROSE_START.test(rest)) return k + (text[k] === ";" ? 1 : 0);
    if (POLISH_WORD.test(rest)) return k;
  }
  return text.length;
}

/** End index of the bracket that closes the one at i, skipping literals, or -1. */
function callEnd(text, i) {
  let depth = 0;
  for (let k = i; k < text.length && k - i <= MAX; k++) {
    if (text[k] === "'") {
      const end = literalEnd(text, k);
      if (end < 0) return -1;
      k = end - 1;
    } else if (text[k] === "(") depth++;
    else if (text[k] === ")" && --depth === 0) return k + 1;
  }
  return -1;
}

export function cardText(text) {
  const raw = String(text ?? "");
  let out = "", plain = "";
  const code = s => { out += esc(plain) + `<code>${esc(s)}</code>`; plain = ""; };
  for (let i = 0; i < raw.length;) {
    const rest = raw.slice(i);
    if (!WORD.test(raw[i - 1] || "") && raw[i - 1] !== "'") {
      const sentence = /(?:^|[.;:?!]\s+)$/.test(raw.slice(0, i));
      let end = sentence ? statementEnd(raw, i) : -1;
      let m;
      if (end < 0) end = literalEnd(raw, i);
      if (end < 0 && (m = rest.match(ERROR_CODE))) end = i + m[0].length;
      if (end < 0 && rest[0] === '"') {
        const close = raw.indexOf('"', i + 1);
        if (close > i + 1 && close - i <= 40 && !raw.slice(i, close).includes("\n")) end = close + 1;
      }
      if (end < 0 && (m = rest.match(CALL))) end = callEnd(raw, i + m[0].length);
      if (end < 0 && (m = rest.match(CAPS)) && !PROSE.has(m[0])) end = i + m[0].length;
      if (end > i) { code(raw.slice(i, end)); i = end; continue; }
    }
    plain += raw[i++];
  }
  return out + esc(plain);
}
