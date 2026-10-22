/* Account roles are plans: guest (no account), user (free account), pro (paid; an admin grants it for now), admin.
   What each may use is in core/state.js (can); the server enforces the same table. */

import { t } from "./i18n.js";

/** What an admin can assign, least to most rights. Guests come only from "Try it without an account". */
export const ROLES = ["user", "pro", "admin"];

export const roleLabel = role => ({ guest: t("Guest"), user: t("User"), pro: t("Pro"), admin: t("Administrator") }[role] ?? role);

/** One line on what the role allows, for the role pickers. */
export const roleSummary = role => ({
  user: t("Unlimited quizzes, flashcards and lessons, 10 graded SQL exercises a day, one workspace."),
  pro: t("Everything a user has, plus the SQL lab, unlimited exercises and any number of workspaces."),
  admin: t("Everything, including accounts, plans and sign-up settings."),
}[role] ?? "");

/** The pages a plan may see locked. */
export const SQL_VIEWS = ["exercises", "lab"];
