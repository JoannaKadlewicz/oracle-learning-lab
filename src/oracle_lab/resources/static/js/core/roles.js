/* Account roles. What a user may do inside a workspace is their access there (free or subscribed, see
   core/state.js), not their role. The server enforces both; the page only follows. */

import { t } from "./i18n.js";

/** Least to most rights: the order of the role pickers. */
export const ROLES = ["user", "admin"];

export const roleLabel = role => ({ user: t("User"), admin: t("Administrator") }[role] ?? role);

/** One line on what the role allows, for the role pickers. */
export const roleSummary = role => ({
  user: t("Studies in the workspaces an admin gives them, or their one free workspace."),
  admin: t("Everything, including accounts and sign-up settings."),
}[role] ?? "");

/** The pages a free workspace shows locked. */
export const SQL_VIEWS = ["exercises", "lab"];
