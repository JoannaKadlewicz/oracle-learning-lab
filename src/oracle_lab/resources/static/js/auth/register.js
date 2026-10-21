import { $ } from "/js/core/dom.js";
import { t } from "/js/core/i18n.js";
import { initAuthPage, carryLanguage, postForm, getConfig, fillAbout, waitText, showError, showProblems, setBusy, disableForm, wirePasswordToggles, focusFirstMissing, carryNext } from "/js/auth/form.js";

await initAuthPage();

const next = new URLSearchParams(location.search).get("next") || "";
const form = $("#register-form");

wirePasswordToggles();
carryNext(next);

getConfig().then(config => {
  fillAbout(config);
  $("#google").hidden = !(config.google && config.registration_open);
  if (!config.registration_open) {
    $("#closed").hidden = false;
    disableForm(form);
  }
});

form.addEventListener("submit", async event => {
  event.preventDefault();
  showError("");
  showProblems([]);
  if (focusFirstMissing(form)) return showError(t("Enter an email and a password."), { focus: false });
  setBusy(form, true);
  const result = await postForm("/api/auth/register", { email: $("#email").value.trim(), password: $("#password").value, next });
  if (result.ok) {
    await carryLanguage();
    return location.assign(result.next || "/");
  }
  setBusy(form, false);
  showProblems(result.problems);
  showError([result.error, result.status === 429 ? waitText(result.retryAfter) : ""].filter(Boolean).join(" "), { focus: !result.problems.length });
  if (result.problems.length) $("#password").focus();
});
