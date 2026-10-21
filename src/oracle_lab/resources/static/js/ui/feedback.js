/* Toasts and modal dialogs. Dialogs use <dialog> for focus trapping, Escape and the backdrop,
   and replace window.confirm/prompt so the app keeps one look and one voice. */

import { $, esc } from "../core/dom.js";

let toastTimer;

export function toast(message, { error = false } = {}) {
  const el = $("#toast");
  el.textContent = message;
  el.classList.toggle("error", error);
  el.classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.remove("show"), error ? 5000 : 2800);
}

export const toastError = message => toast(message, { error: true });

function openDialog(inner, onOpen) {
  return new Promise(resolve => {
    const dialog = document.createElement("dialog");
    dialog.className = "modal";
    dialog.innerHTML = `<form method="dialog">${inner}</form>`;
    document.body.append(dialog);
    dialog.addEventListener("close", () => {
      resolve(dialog.returnValue);
      dialog.remove();
    });
    // Cancel is type="button": Enter in a field then submits with the confirming button.
    dialog.querySelector("[data-close]")?.addEventListener("click", () => dialog.close("cancel"));
    dialog.showModal();
    onOpen?.(dialog);
  });
}

/** Resolves true when the person confirms. */
export async function confirmDialog({ title, body = "", confirm = "Continue", cancel = "Cancel", danger = false }) {
  const value = await openDialog(`
    <h2>${esc(title)}</h2>
    ${body ? `<p>${esc(body)}</p>` : ""}
    <div class="row">
      <button type="button" class="btn secondary" data-close>${esc(cancel)}</button>
      <button class="btn ${danger ? "danger solid" : ""}" value="ok" autofocus>${esc(confirm)}</button>
    </div>`);
  return value === "ok";
}

/** Resolves the entered text, or null when cancelled. */
export async function promptDialog({ title, body = "", label, value = "", confirm = "Save" }) {
  let input;
  const result = await openDialog(`
    <h2>${esc(title)}</h2>
    ${body ? `<p>${esc(body)}</p>` : ""}
    <label class="field"><span>${esc(label)}</span><input type="text" name="value" value="${esc(value)}" autocomplete="off"></label>
    <div class="row">
      <button type="button" class="btn secondary" data-close>Cancel</button>
      <button class="btn" value="ok">${esc(confirm)}</button>
    </div>`, dialog => { input = dialog.querySelector("input"); input.select(); });
  return result === "ok" ? input.value : null;
}

/** Asks for a password before a dangerous step. Resolves the entered text, or null when cancelled. */
export async function passwordDialog({ title, body = "", label = "Password", confirm = "Continue", danger = false }) {
  let input;
  const result = await openDialog(`
    <h2>${esc(title)}</h2>
    ${body ? `<p>${esc(body)}</p>` : ""}
    <label class="field"><span>${esc(label)}</span><input type="password" name="value" autocomplete="current-password" required></label>
    <div class="row">
      <button type="button" class="btn secondary" data-close>Cancel</button>
      <button class="btn ${danger ? "danger solid" : ""}" value="ok">${esc(confirm)}</button>
    </div>`, dialog => { input = dialog.querySelector("input"); input.focus(); });
  return result === "ok" ? input.value : null;
}
