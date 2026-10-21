import { $ } from "/js/core/dom.js";
import { postForm, getConfig, waitText, showError, setBusy, wirePasswordToggles, focusFirstMissing, carryNext } from "/js/auth/form.js";

const params = new URLSearchParams(location.search);
const next = params.get("next") || "";
const form = $("#login-form");

wirePasswordToggles();
carryNext(next);
if (params.get("error") === "google") showError("Sign-in with Google did not complete. Please try again.", { focus: false });

getConfig().then(config => { $("#google").hidden = !config.google; });

form.addEventListener("submit", async event => {
  event.preventDefault();
  showError("");
  if (focusFirstMissing(form)) return showError("Enter your email and password.", { focus: false });
  setBusy(form, true);
  const result = await postForm("/api/auth/login", { email: $("#email").value.trim(), password: $("#password").value, next });
  if (result.ok) return location.assign(result.next || "/");
  setBusy(form, false);
  showError([result.error, result.status === 429 ? waitText(result.retryAfter) : ""].filter(Boolean).join(" "));
});
