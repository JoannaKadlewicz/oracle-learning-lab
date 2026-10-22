/* The account roles and what each may do here. The server enforces them; the page only follows. */

import { t } from "./i18n.js";

/** Least to most rights: the order of the role pickers. */
export const ROLES = ["free", "learner", "admin"];

export const roleLabel = role => ({ free: t("Free"), learner: t("Learner"), admin: t("Administrator") }[role] ?? role);

/** One line on what the role allows, for the role pickers. */
export const roleSummary = role => ({
  free: t("Flashcards, quizzes, progress and notes. No SQL."),
  learner: t("Everything except the admin page, SQL included."),
  admin: t("Everything, including accounts and sign-up settings."),
}[role] ?? "");

/** Free accounts get neither the SQL lab nor the exercises. */
export const canRunSql = user => user?.role !== "free";
export const SQL_VIEWS = ["exercises", "lab"];
