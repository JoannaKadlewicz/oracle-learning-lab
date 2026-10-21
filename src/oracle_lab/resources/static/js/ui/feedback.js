/* Toasts and modal dialogs. Dialogs use <dialog> for focus trapping, Escape and the backdrop,
   and replace window.confirm/prompt so the app keeps one look and one voice. */

import { $, esc } from "../core/dom.js";

let toastTimer;
let toastTag = null;

/** `tag` names a toast so clearToast(tag) can take it down without touching any other message. */
export function toast(message, { error = false, tag = null } = {}) {
  const el = $("#toast");
  toastTag = tag;
  el.textContent = message;
  el.classList.toggle("error", error);
  el.classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.remove("show"), error ? 5000 : 2800);
}

/** Hides the toast; with a tag, only when the toast showing is that one. */
export function clearToast(tag) {
  if (tag !== undefined && tag !== toastTag) return;
  clearTimeout(toastTimer);
  $("#toast").classList.remove("show");
}

export const toastError = message => toast(message, { error: true });

/** A modal with `inner` inside a method="dialog" form; resolves the returnValue of the button that closed it. */
export function openDialog(inner, onOpen) {
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

/** Closes every open dialog as if cancelled (its promise resolves "cancel"), for example when a
    mock exam's time runs out while a question is open. */
export function closeDialogs() {
  document.querySelectorAll("dialog.modal[open]").forEach(d => d.close("cancel"));
}

/** Resolves true when the person confirms. `focus: "cancel"` starts on the cancel button, so a
    stray Enter keeps things as they are. */
export async function confirmDialog({ title, body = "", confirm = "Continue", cancel = "Cancel", danger = false, focus = "confirm" }) {
  const value = await openDialog(`
    <h2>${esc(title)}</h2>
    ${body ? `<p>${esc(body)}</p>` : ""}
    <div class="row">
      <button type="button" class="btn secondary" data-close ${focus === "cancel" ? "autofocus" : ""}>${esc(cancel)}</button>
      <button class="btn ${danger ? "danger solid" : ""}" value="ok" ${focus === "cancel" ? "" : "autofocus"}>${esc(confirm)}</button>
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
export async function passwordDialog({ title, body = "", label = "Password", confirm = "Continue", danger = false, autocomplete = "current-password" }) {
  let input;
  const result = await openDialog(`
    <h2>${esc(title)}</h2>
    ${body ? `<p>${esc(body)}</p>` : ""}
    <label class="field"><span>${esc(label)}</span><input type="password" name="value" autocomplete="${esc(autocomplete)}" required></label>
    <div class="row">
      <button type="button" class="btn secondary" data-close>Cancel</button>
      <button class="btn ${danger ? "danger solid" : ""}" value="ok">${esc(confirm)}</button>
    </div>`, dialog => { input = dialog.querySelector("input"); input.focus(); });
  return result === "ok" ? input.value : null;
}
