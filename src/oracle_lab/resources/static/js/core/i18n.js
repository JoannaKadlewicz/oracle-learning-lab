/* The interface language: "en" (the source text) or "pl" (the catalog /i18n/pl.json).
   t("Text {name}", { name }) looks a string up; tn(n, "{n} item", "{n} items") picks a plural form.
   Also loaded by the sign-in pages, so it imports nothing private. */

export const LANGUAGES = ["en", "pl"];
export const DEFAULT_LANGUAGE = "en";

const LANG_KEY = "study:lang";
const EXPLICIT_KEY = "study:lang-explicit";
// The catalog's three plural forms, by Intl plural category.
const FORM_INDEX = { one: 0, few: 1, many: 2, other: 2 };

let current = DEFAULT_LANGUAGE;
let catalog = {};
let rules = null;

const supported = code => LANGUAGES.includes(code) ? code : null;

function stored(key) {
  try { return localStorage.getItem(key); } catch { return null; }
}

function format(text, params) {
  return String(text).replace(/\{(\w+)\}/g, (whole, name) => (name in params ? String(params[name]) : whole));
}

/** Loads the catalog of `code` (English needs none) and sets <html lang>. A catalog that cannot be loaded
    leaves the page in English. */
export async function initI18n(code) {
  const wanted = supported(code) || DEFAULT_LANGUAGE;
  catalog = {};
  if (wanted !== DEFAULT_LANGUAGE) {
    try {
      const res = await fetch(`/i18n/${wanted}.json`, { headers: { "X-Language": wanted } });
      if (!res.ok) throw new Error(`/i18n/${wanted}.json: HTTP ${res.status}`);
      catalog = await res.json();
    } catch (err) {
      console.error(err);
      catalog = {};
      current = DEFAULT_LANGUAGE;
      document.documentElement.lang = current;
      return current;
    }
  }
  current = wanted;
  rules = new Intl.PluralRules(current);
  document.documentElement.lang = current;
  return current;
}

export const lang = () => current;

/** The catalog's text for `msgid` (or `msgid` itself) with {name} placeholders filled from `params`. */
export function t(msgid, params = {}) {
  const text = catalog[msgid];
  return format(typeof text === "string" ? text : msgid, params);
}

/** `one` or `many` for n in English; in another language, the catalog's form list under `many`, chosen
    by the language's plural rules. {n} is replaced with n. */
export function tn(n, one, many, params = {}) {
  const values = { n, ...params };
  const forms = catalog[many];
  if (Array.isArray(forms) && forms.length === 3) {
    const category = (rules ??= new Intl.PluralRules(current)).select(n);
    return format(forms[FORM_INDEX[category] ?? 2], values);
  }
  return format(n === 1 ? one : many, values);
}

/** The account's setting (when signed in), else the language remembered in this browser, else the first
    supported one in the browser's languages, else English. */
export function preferredLanguage(account) {
  const chosen = supported(account) || supported(stored(LANG_KEY));
  if (chosen) return chosen;
  for (const tag of navigator.languages || [navigator.language || ""]) {
    const base = supported(String(tag).toLowerCase().split("-")[0]);
    if (base) return base;
  }
  return DEFAULT_LANGUAGE;
}

/** True when the learner picked the language on a sign-in page during an earlier or this visit. */
export const explicitLanguage = () => stored(EXPLICIT_KEY) === "true";

/** Remembers `code` in this browser; `explicit` marks it as the learner's own click. */
export function rememberLanguage(code, { explicit = false } = {}) {
  if (!supported(code)) return;
  try {
    localStorage.setItem(LANG_KEY, code);
    if (explicit) localStorage.setItem(EXPLICIT_KEY, "true");
  } catch { /* private window: the choice lasts for this page only */ }
}

/** The language remembered in this browser, if any (not the detected one). */
export const rememberedLanguage = () => supported(stored(LANG_KEY));

export function formatDate(date, options = {}) {
  return new Intl.DateTimeFormat(current, options).format(date instanceof Date ? date : new Date(date));
}

export function formatNumber(n, options = {}) {
  return new Intl.NumberFormat(current, options).format(n);
}

/** Forgets that the learner clicked a language (it has been saved to the account). */
export function clearExplicitLanguage() {
  try { localStorage.removeItem(EXPLICIT_KEY); } catch { /* nothing to forget */ }
}

/** Fills the static texts of `root`: data-i18n="Text" replaces the element's text, and
    data-i18n-aria-label="Text" its aria-label. English is the text already in the HTML. */
export function translatePage(root = document) {
  for (const el of root.querySelectorAll("[data-i18n]")) el.textContent = t(el.dataset.i18n);
  for (const el of root.querySelectorAll("[data-i18n-aria-label]")) el.setAttribute("aria-label", t(el.dataset.i18nAriaLabel));
}

let saveToAccount = null;

/** The app registers how a signed-in learner's language is saved (this module is public, so it cannot
    reach the account itself): an async function of the language code. */
export function setAccountSaver(save) { saveToAccount = save; }

/** Switches the interface to `code`: remembered in this browser as the learner's own choice, saved to the
    account when signed in, then the page reloads to render in it. */
export async function changeLanguage(code) {
  if (!supported(code)) return;
  rememberLanguage(code, { explicit: true });
  if (saveToAccount) {
    try {
      await saveToAccount(code);
      clearExplicitLanguage();
    } catch (err) { console.error(err); }  // still reload: this browser keeps the choice
  }
  location.reload();
}

/** Wires the buttons `[data-lang="en"|"pl"]` inside `root`: the current language is pressed, a click switches. */
export function wireLanguageSwitch(root = document) {
  for (const button of root.querySelectorAll("[data-lang]")) {
    const code = button.dataset.lang;
    button.setAttribute("aria-pressed", String(code === current));
    button.addEventListener("click", () => { if (code !== current) changeLanguage(code); });
  }
}
