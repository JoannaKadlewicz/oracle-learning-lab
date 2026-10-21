import { $ } from "/js/core/dom.js";
import { postForm, getConfig, fillAbout, showError, showProblems, setBusy, disableForm, wirePasswordToggles, focusFirstMissing } from "/js/auth/form.js";

const token = new URLSearchParams(location.search).get("token") || "";
const form = $("#reset-form");

wirePasswordToggles();
getConfig().then(fillAbout);
if (!token) {
  showError("This reset link is invalid or has expired. Ask your administrator for a new one.", { focus: false });
  disableForm(form);
}

form.addEventListener("submit", async event => {
  event.preventDefault();
  showError("");
  showProblems([]);
  if (focusFirstMissing(form)) return showError("Enter a new password.", { focus: false });
  setBusy(form, true);
  const result = await postForm("/api/auth/reset", { token, password: $("#password").value });
  if (!result.ok) {
    setBusy(form, false);
    showProblems(result.problems);
    showError(result.error, { focus: !result.problems.length });
    if (result.problems.length) $("#password").focus();
    return;
  }
  form.hidden = true;
  $("#done").hidden = false;
  $("#done a").focus();
});
