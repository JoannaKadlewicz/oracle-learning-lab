/* The exam drop-down in the rail: a select-only combobox (WAI-ARIA APG pattern) whose listbox
   groups the exams by database product. Focus stays on the button; aria-activedescendant names
   the active option. The open list is position: fixed so the scrolling rail cannot clip it. */

import { esc, icon } from "../core/dom.js";
import { logoBadge } from "./workspace-tiles.js";
import { t } from "../core/i18n.js";

const TYPEAHEAD_MS = 500;

/** Renders the picker into `host`, replacing its content. Safe to call again on every change. */
export function examPicker(host, { exams, current, onPick, locked = () => false }) {
  host._examPicker?.destroy();
  const id = host.id || "exam-picker";
  const hadFocus = host.contains(document.activeElement);
  const cur = exams.find(x => x.code === current) || exams[0];
  host.classList.add("exam-picker");
  host.innerHTML = buttonHtml(id, cur) + listHtml(id, exams, cur.code, locked);

  const button = host.querySelector(".exam-picker-button");
  const list = host.querySelector(".exam-picker-list");
  const options = [...list.querySelectorAll("[role=option]")];
  let active = -1;
  let typed = "";
  let typedAt = 0;

  const isOpen = () => !list.hidden;

  function setActive(i) {
    active = Math.max(0, Math.min(options.length - 1, i));
    options.forEach((o, n) => o.classList.toggle("active", n === active));
    button.setAttribute("aria-activedescendant", options[active].id);
    options[active].scrollIntoView({ block: "nearest" });
  }

  function open() {
    if (isOpen()) return;
    list.hidden = false;
    button.setAttribute("aria-expanded", "true");
    place();
    setActive(options.findIndex(o => o.dataset.exam === cur.code));
    // Shown first, then faded in, so the opacity transition has a start value.
    requestAnimationFrame(() => list.classList.add("shown"));
    document.addEventListener("pointerdown", onOutside, true);
    // Capture: scroll does not bubble, and the rail (not the window) is what usually scrolls.
    document.addEventListener("scroll", onScroll, true);
    window.addEventListener("resize", onResize);
  }

  function close({ focus = true } = {}) {
    if (!isOpen()) return;
    list.hidden = true;
    list.classList.remove("shown");
    button.setAttribute("aria-expanded", "false");
    button.removeAttribute("aria-activedescendant");
    document.removeEventListener("pointerdown", onOutside, true);
    document.removeEventListener("scroll", onScroll, true);
    window.removeEventListener("resize", onResize);
    if (focus) button.focus();
  }

  function pick(i) {
    if (options[i].getAttribute("aria-disabled") === "true") return;  // needs a subscription: stays open, stays put
    const code = options[i].dataset.exam;
    close();
    if (code !== cur.code) onPick(code);
  }

  /** Under the button, or above it when the viewport has no room below. */
  function place() {
    const r = button.getBoundingClientRect();
    const gap = 6;
    list.style.left = `${r.left}px`;
    list.style.minWidth = `${r.width}px`;
    list.style.maxWidth = `${Math.max(r.width, window.innerWidth - r.left - 8)}px`;
    list.style.top = "0px";
    list.style.bottom = "auto";
    const h = list.offsetHeight;
    const below = window.innerHeight - r.bottom - gap;
    if (h > below && r.top - gap > below) {
      list.style.top = "auto";
      list.style.bottom = `${window.innerHeight - r.top + gap}px`;
      list.style.maxHeight = `${r.top - 2 * gap}px`;
    } else {
      list.style.top = `${r.bottom + gap}px`;
      list.style.maxHeight = `${below - gap}px`;
    }
  }

  function onOutside(e) {
    if (!host.contains(e.target)) close({ focus: false });
  }

  function onScroll(e) {
    if (e.target !== list) close({ focus: false });
  }

  function onResize() {
    close({ focus: false });
  }

  /** Moves to the next option whose code or name starts with what was typed in the last 500 ms. */
  function typeahead(ch) {
    const now = Date.now();
    typed = now - typedAt > TYPEAHEAD_MS ? ch : typed + ch;
    typedAt = now;
    const prefix = typed.toLowerCase();
    // A repeated single letter cycles; a longer prefix may stay on the active option.
    const start = typed.length === 1 ? active + 1 : active;
    for (let n = 0; n < options.length; n++) {
      const o = options[(start + n) % options.length];
      const x = exams.find(y => y.code === o.dataset.exam);
      if (x.code.toLowerCase().startsWith(prefix) || x.name.toLowerCase().startsWith(prefix)) {
        setActive(options.indexOf(o));
        return;
      }
    }
  }

  function onKey(e) {
    if (!isOpen()) {
      if (["ArrowDown", "ArrowUp", "Enter", " "].includes(e.key)) {
        e.preventDefault();
        open();
      }
      return;
    }
    switch (e.key) {
      case "ArrowDown": setActive(active + 1); break;
      case "ArrowUp": setActive(active - 1); break;
      case "Home": setActive(0); break;
      case "End": setActive(options.length - 1); break;
      case "Enter": case " ": pick(active); break;
      // Stopped here so the drawer's own Escape handler does not close the drawer too.
      case "Escape": e.stopPropagation(); close(); break;
      case "Tab": close({ focus: false }); return;
      default:
        if (e.key.length === 1 && !e.ctrlKey && !e.metaKey && !e.altKey) typeahead(e.key);
        else return;
    }
    e.preventDefault();
  }

  button.addEventListener("keydown", onKey);
  // Space activates a button on keyup; the keydown already handled it.
  button.addEventListener("keyup", e => { if (e.key === " ") e.preventDefault(); });
  button.addEventListener("click", () => (isOpen() ? close() : open()));
  // Keeps focus on the button while the pointer is on the list.
  list.addEventListener("pointerdown", e => e.preventDefault());
  list.addEventListener("click", e => {
    const o = e.target.closest("[role=option]");
    if (o) pick(options.indexOf(o));
  });
  list.addEventListener("pointermove", e => {
    const o = e.target.closest("[role=option]");
    if (o && options.indexOf(o) !== active) setActive(options.indexOf(o));
  });

  host._examPicker = { destroy: () => close({ focus: false }) };
  if (hadFocus) button.focus();
}

function buttonHtml(id, cur) {
  return `<button type="button" class="exam-picker-button" id="${id}-button" role="combobox"
      aria-haspopup="listbox" aria-expanded="false" aria-controls="${id}-list"
      aria-labelledby="exam-switch-label ${id}-button">
    ${logoBadge(cur.logo, "tiny")}
    <span class="exam-picker-value">
      <span class="exam-picker-code">${esc(cur.code)}</span>
      <span class="exam-picker-db">${esc(cur.database)}</span>
    </span>
    <svg class="exam-picker-chevron" aria-hidden="true"><use href="#i-down"/></svg>
  </button>`;
}

/** One group per product, in registry order (the order of `exams`). */
function listHtml(id, exams, current, locked) {
  const products = [...new Set(exams.map(x => x.product))];
  const groups = products.map((p, g) => `
    <li role="group" aria-labelledby="${id}-g${g}">
      <div class="exam-picker-heading" id="${id}-g${g}">${esc(p)}</div>
      <ul role="none">${exams.filter(x => x.product === p).map(x => optionHtml(id, x, current, locked(x.code))).join("")}</ul>
    </li>`).join("");
  return `<ul class="exam-picker-list" id="${id}-list" role="listbox" aria-labelledby="exam-switch-label" hidden>${groups}</ul>`;
}

/** A workspace the user may not open is listed (and announced) but not selectable: "Requires a subscription". */
function optionHtml(id, x, current, locked) {
  const selected = x.code === current;
  return `<li role="option" id="${id}-${esc(x.code)}" data-exam="${esc(x.code)}" aria-selected="${selected}"${locked ? ` aria-disabled="true" class="locked"` : ""}>
    <span class="exam-picker-option-title">${logoBadge(x.logo, "tiny")}<span class="exam-picker-code">${esc(x.code)}</span> ${esc(x.name)}</span>
    <span class="exam-picker-option-meta">${locked ? `${icon("lock")} ${esc(t("Pro plan"))}`
      : esc(t("{database}, {questions} questions, {minutes} min", { database: x.database, questions: x.questions, minutes: x.minutes }))}</span>
    <svg class="exam-picker-tick" aria-hidden="true"><use href="#i-check"/></svg>
  </li>`;
}
