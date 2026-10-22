"""The admin API. Every route needs an admin principal (others get 404) and, for POSTs, the CSRF token."""

from __future__ import annotations

from collections.abc import Callable

from oracle_lab.access.service import UnknownUserError, WorkspaceService
from oracle_lab.auth.models import Principal
from oracle_lab.i18n import Msg, message_of
from oracle_lab.services.admin import AdminService
from oracle_lab.web.http import HttpError, Request, Response
from oracle_lab.web.middleware import require_admin
from oracle_lab.web.routing import Router

OK = {"ok": True}


def _string(data: dict, name: str) -> str:
    value = data.get(name)
    if not isinstance(value, str) or not value:
        raise HttpError(400, Msg.of("{name} must be a non-empty string", name=name))
    return value


def _optional(data: dict, name: str, kind: type) -> object:
    value = data.get(name)
    if value is not None and (not isinstance(value, kind) or (kind is int and isinstance(value, bool))):
        raise HttpError(400, Msg.of("{name} has the wrong type", name=name))
    return value


def _meta(request: Request) -> dict:
    """The client of a request, for the audit record of an admin action."""
    return {"ip": request.client, "user_agent": request.header("User-Agent")}


class AdminController:
    def __init__(self, admin: AdminService, workspaces: WorkspaceService):
        self.admin = admin
        self.workspaces = workspaces

    def register(self, router: Router) -> None:
        routes = {
            ("GET", "/api/admin/users"): self.users,
            ("GET", "/api/admin/events"): self.events,
            ("GET", "/api/admin/settings"): self.settings,
            ("POST", "/api/admin/reset-link"): self.reset_link,
            ("POST", "/api/admin/lock"): self.lock,
            ("POST", "/api/admin/unlock"): self.unlock,
            ("POST", "/api/admin/role"): self.role,
            ("POST", "/api/admin/delete"): self.delete,
            ("POST", "/api/admin/recreate-schema"): self.recreate_schema,
            ("POST", "/api/admin/delete-inactive"): self.delete_inactive,
            ("POST", "/api/admin/settings"): self.update_settings,
            ("POST", "/api/admin/membership"): self.membership,
            ("POST", "/api/admin/limits"): self.limits,
        }
        for (method, path), handler in routes.items():
            router.add(method, path, self._guarded(handler))

    def _guarded(self, handler: Callable[[Request], Response]) -> Callable[[Request], Response]:
        """Checks the role first (a refusal is audited as admin_denied); a refused action (ValueError: own
        account, bad value) is a 400."""
        def run(request: Request) -> Response:
            try:
                require_admin(request)
            except HttpError:
                principal = request.principal if isinstance(request.principal, Principal) else None
                self.admin.denied(principal, request.path, **_meta(request))
                raise
            try:
                return handler(request)
            except ValueError as exc:
                raise HttpError(400, message_of(exc)) from exc
        return run

    def users(self, request: Request) -> Response:
        return Response.json({"users": self.admin.users(include_guests=request.query("guests") == "1")})

    def limits(self, request: Request) -> Response:
        data = request.json()
        saved = self.admin.set_limits(require_admin(request), _string(data, "user_id"), data.get("limits"),
                                      **_meta(request))
        return Response.json({"ok": True, "limits": saved})

    def events(self, request: Request) -> Response:
        try:
            limit = int(request.query("limit", "200"))
        except ValueError as exc:
            raise HttpError(400, "limit must be a number") from exc
        return Response.json({"events": self.admin.events(limit, request.query("event") or None,
                                                          request.query("user_id") or None)})

    def settings(self, _: Request) -> Response:
        return Response.json(self.admin.settings())

    def reset_link(self, request: Request) -> Response:
        return Response.json({"link": self.admin.reset_link(require_admin(request), _string(request.json(), "user_id"),
                                                            **_meta(request))})

    def lock(self, request: Request) -> Response:
        self.admin.lock(require_admin(request), _string(request.json(), "user_id"), **_meta(request))
        return Response.json(OK)

    def unlock(self, request: Request) -> Response:
        self.admin.unlock(require_admin(request), _string(request.json(), "user_id"), **_meta(request))
        return Response.json(OK)

    def role(self, request: Request) -> Response:
        data = request.json()
        self.admin.set_role(require_admin(request), _string(data, "user_id"), _string(data, "role"), **_meta(request))
        return Response.json(OK)

    def delete(self, request: Request) -> Response:
        self.admin.delete(require_admin(request), _string(request.json(), "user_id"), **_meta(request))
        return Response.json(OK)

    def recreate_schema(self, request: Request) -> Response:
        data = request.json()
        schema = self.admin.recreate_schema(require_admin(request), _string(data, "user_id"), _string(data, "key"),
                                            **_meta(request))
        return Response.json({"ok": True, "schema": schema})

    def delete_inactive(self, request: Request) -> Response:
        days = _optional(request.json(), "days", int)
        if days is None:
            raise HttpError(400, "days is required")
        return Response.json({"deleted": self.admin.delete_inactive(require_admin(request), days, **_meta(request))})

    def update_settings(self, request: Request) -> Response:
        data = request.json()
        return Response.json(self.admin.update_settings(require_admin(request), _optional(data, "open", bool),
                                                        _optional(data, "max_users", int),
                                                        _optional(data, "plan_defaults", dict), **_meta(request)))

    def membership(self, request: Request) -> Response:
        data = request.json()
        try:
            self.workspaces.set_membership(require_admin(request), _string(data, "user_id"), data.get("workspace"),
                                           data.get("member"), **_meta(request))
        except UnknownUserError as exc:
            raise HttpError(404, "Not found") from exc
        return Response.json(OK)
