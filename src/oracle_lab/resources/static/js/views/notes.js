/* Notes: the Markdown notes and SQL files of the repository, plus notes saved from the lab. */

import { $, $$, esc } from "../core/dom.js";
import { api } from "../core/api.js";
import { main, go } from "../core/router.js";
import { pageHead, loading, empty } from "../ui/widgets.js";

let currentNote = null;

/** Show a note; other views link to notes through this. */
export function openNote(path, navigate = true) {
  currentNote = path;
  if (navigate) go("/notes");
}

// "topics/06-joins/notes.md" -> group "Topics", label "6. Joins"
function describe(note) {
  const [root, folder, file] = note.path.split("/");
  if (root === "docs") return { group: "Guides", label: note.title };
  if (root === "personal") return { group: "My notes", label: note.title.replace(/^My notes \/ /, "") };
  const m = folder.match(/^(\d+)-(.*)$/);
  const topic = m ? `${Number(m[1])}. ${m[2].replace(/-/g, " ").replace(/^./, c => c.toUpperCase())}` : folder;
  const stem = file.replace(/\.md$/, "");
  return { group: "Topics", label: stem === "notes" ? topic : `${topic}: ${stem}` };
}

async function render() {
  main.innerHTML = `${pageHead("Notes", "Lesson notes for every topic, and your saved SQL notes.")}${loading("Loading notes")}`;
  const list = await api("/api/notes");
  if (!list.some(n => n.path === currentNote)) currentNote = (list.find(n => n.path.includes("notes.md")) || list[0])?.path;
  const groups = {};
  for (const n of list) {
    const d = describe(n);
    (groups[d.group] ||= []).push({ ...n, label: d.label });
  }
  const options = Object.entries(groups).map(([g, items]) => `<optgroup label="${esc(g)}">${items.map(n =>
    `<option value="${esc(n.path)}" ${n.path === currentNote ? "selected" : ""}>${esc(n.label)}</option>`).join("")}</optgroup>`).join("");

  main.innerHTML = `
    ${pageHead("Notes", "Lesson notes for every topic, and your saved SQL notes.")}
    <label class="list-picker field"><span>Note</span><select id="note-picker">${options}</select></label>
    <div class="split">
      <nav class="split-list" aria-label="Notes">
        <div class="split-scroll">
          ${Object.entries(groups).map(([g, items]) => `<p class="item-group">${esc(g)}</p><ul class="item-list">${items.map(n =>
            `<li><button data-note="${esc(n.path)}" aria-current="${n.path === currentNote}"><span></span><span>${esc(n.label)}</span></button></li>`).join("")}</ul>`).join("")}
        </div>
      </nav>
      <article class="note-body" id="note">${loading("Loading")}</article>
    </div>`;
  const show = path => { currentNote = path; render(); };
  $$("[data-note]", main).forEach(b => b.addEventListener("click", () => show(b.dataset.note)));
  $("#note-picker").addEventListener("change", e => show(e.target.value));
  $("[aria-current='true']", main)?.scrollIntoView({ block: "nearest" });

  if (!currentNote) { $("#note").innerHTML = empty("No notes yet"); return; }
  const note = await api("/api/note?path=" + encodeURIComponent(currentNote));
  const isSql = currentNote.endsWith(".sql");
  if (isSql || !window.marked) {
    $("#note").innerHTML = `<pre class="code"><code>${esc(note.text)}</code></pre>`
      + (isSql ? `<button class="btn secondary" id="open-lab">Open in the SQL lab</button>` : "");
  } else {
    $("#note").innerHTML = window.marked.parse(note.text);
  }
  $("#open-lab")?.addEventListener("click", async () => {
    const { labDraft } = await import("./lab.js");
    labDraft(note.text);
    go("/lab");
  });
}

export const notesView = { title: "Notes", render };
