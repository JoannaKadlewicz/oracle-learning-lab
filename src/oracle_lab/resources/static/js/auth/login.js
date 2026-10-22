import { $ } from "/js/core/dom.js";
import { t } from "/js/core/i18n.js";
import { initAuthPage, postForm, getConfig, fillAbout, waitText, showError, setBusy, wirePasswordToggles, focusFirstMissing, carryNext } from "/js/auth/form.js";

await initAuthPage();

const params = new URLSearchParams(location.search);
const next = params.get("next") || "";
const form = $("#login-form");

wirePasswordToggles();
carryNext(next);
// Why Google sign-in failed (error=google_<code> from /auth/google/*): fixed texts only, never the raw parameter.
function googleError(code) {
  switch (code) {
    case "google_exists": return t("An account with this email already exists. Sign in with your password, then connect Google in Settings.");
    case "google_closed": return t("Registration is closed.");
    case "google_throttled": return t("Too many attempts. Try again in a few minutes.");
    default: return t("Sign-in with Google did not complete. Please try again.");
  }
}
if (params.has("error")) showError(googleError(params.get("error")), { focus: false });

getConfig().then(config => { $("#google").hidden = !config.google; fillAbout(config); });

form.addEventListener("submit", async event => {
  event.preventDefault();
  showError("");
  if (focusFirstMissing(form)) return showError(t("Enter your email and password."), { focus: false });
  setBusy(form, true);
  const result = await postForm("/api/auth/login", { email: $("#email").value.trim(), password: $("#password").value, next });
  if (result.ok) return location.assign(result.next || "/");
  setBusy(form, false);
  showError([result.error, result.status === 429 ? waitText(result.retryAfter) : ""].filter(Boolean).join(" "));
});

// "Try it without an account": a guest session, then the app (which asks for a workspace first).
$("#try-guest").addEventListener("click", async () => {
  const result = await postForm("/api/auth/guest", {});
  if (result.ok) location.assign("/");
  else showError(result.retryAfter ? waitText(result.retryAfter) : result.error);
});
