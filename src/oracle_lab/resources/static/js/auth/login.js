import { $ } from "/js/core/dom.js";
import { postForm, getConfig, fillAbout, waitText, showError, setBusy, wirePasswordToggles, focusFirstMissing, carryNext } from "/js/auth/form.js";

const params = new URLSearchParams(location.search);
const next = params.get("next") || "";
const form = $("#login-form");

wirePasswordToggles();
carryNext(next);
// Why Google sign-in failed (error=google_<code> from /auth/google/*): fixed texts only, never the raw parameter.
const GOOGLE_ERRORS = {
  google_exists: "An account with this email already exists. Sign in with your password, then connect Google in Settings.",
  google_closed: "Registration is closed.",
  google_throttled: "Too many attempts. Try again in a few minutes.",
};
const GOOGLE_FAILED = "Sign-in with Google did not complete. Please try again.";
if (params.has("error")) showError(GOOGLE_ERRORS[params.get("error")] || GOOGLE_FAILED, { focus: false });

getConfig().then(config => { $("#google").hidden = !config.google; fillAbout(config); });

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
