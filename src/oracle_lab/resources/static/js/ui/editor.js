/* SQL editor: CodeMirror when the CDN loaded (SQL highlighting for the current exam's database engine, bracket matching,
   autocomplete with Ctrl+Space or after a dot); otherwise the plain text area. */

import { esc } from "../core/dom.js";
import { C } from "../core/state.js";
import { api } from "../core/api.js";

let schemaCache = null;

export async function getSchema() {
  if (!schemaCache) {
    const res = await api("/api/schema");
    if (!res.ok) return res;
    schemaCache = res;
  }
  return schemaCache;
}

export function setSchema(res) { schemaCache = res?.ok ? res : null; }
export function invalidateSchema() { schemaCache = null; }

function schemaTables() {
  const tables = {};
  for (const t of schemaCache?.tables || []) tables[t.name.toLowerCase()] = t.columns.map(c => c.name.toLowerCase());
  return tables;
}

export async function schemaHtml() {
  try {
    const schema = await getSchema();
    if (!schema.ok) return `<p class="small muted">Schema unavailable: ${esc(schema.error)}</p>`;
    return schema.tables.map(t => `<details><summary>${esc(t.name)}</summary><ul>
      ${t.columns.map(c => `<li class="${c.nullable ? "" : "nn"}"><b>${esc(c.name.toLowerCase())}</b><span>${esc(c.type)}</span></li>`).join("")}
    </ul><button class="link-btn" data-insert="${esc(t.name.toLowerCase())}">Insert a SELECT</button></details>`).join("")
      + `<p class="xsmall muted">* NOT NULL</p>`;
  } catch {
    return `<p class="small muted">Schema unavailable.</p>`;
  }
}

function plainKeys(textarea, onRun) {
  textarea.addEventListener("keydown", e => {
    if ((e.ctrlKey || e.metaKey) && e.key === "Enter") { e.preventDefault(); onRun(); }
    else if (e.key === "Tab" && !e.shiftKey) {
      e.preventDefault();
      const { selectionStart: s, selectionEnd: t, value } = textarea;
      textarea.value = value.slice(0, s) + "  " + value.slice(t);
      textarea.selectionStart = textarea.selectionEnd = s + 2;
    }
  });
}

export function makeEditor(textarea, { onRun, onChange }) {
  if (!window.CodeMirror) {
    plainKeys(textarea, onRun);
    if (onChange) textarea.addEventListener("input", () => onChange(textarea.value));
    return {
      get: () => textarea.value,
      set: v => { textarea.value = v; onChange?.(v); },
      selection: () => textarea.value.slice(textarea.selectionStart, textarea.selectionEnd),
      onSelection: () => {},
      focus: () => textarea.focus(),
    };
  }
  const { CodeMirror } = window;
  const hint = cm => cm.showHint({ hint: CodeMirror.hint.sql, tables: schemaTables(), completeSingle: false });
  const cm = CodeMirror.fromTextArea(textarea, {
    mode: C.engine?.editor_mode || "text/x-sql", lineNumbers: true, matchBrackets: true, autoCloseBrackets: true,
    indentUnit: 2, tabSize: 2, lineWrapping: true, viewportMargin: Infinity,
    // Escape leaves the editor, so keyboard users are never trapped by Tab indenting.
    extraKeys: {
      "Ctrl-Enter": () => onRun(), "Cmd-Enter": () => onRun(), "Ctrl-Space": hint,
      Tab: c => c.replaceSelection("  "), Esc: c => c.getInputField().blur(),
    },
  });
  cm.getInputField().setAttribute("aria-label", textarea.getAttribute("aria-label") || "SQL editor");
  cm.on("inputRead", (c, change) => { if (change.text[0] === ".") hint(c); });
  if (onChange) cm.on("change", () => onChange(cm.getValue()));
  return {
    cm,
    get: () => cm.getValue(),
    set: v => cm.setValue(v),
    selection: () => cm.getSelection(),
    onSelection: fn => cm.on("cursorActivity", () => fn(!!cm.getSelection())),
    focus: () => cm.focus(),
  };
}
