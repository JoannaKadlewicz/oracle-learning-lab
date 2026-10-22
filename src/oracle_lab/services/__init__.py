"""Use cases of the app. They combine the study domain, the state store and the databases, and know
nothing about HTTP: the web controllers translate requests into calls to these services."""

from collections.abc import Callable

Clock = Callable[[], float]


class NotFoundError(LookupError):
    """The request names a question, exercise or mock exam that does not exist."""


class AccessError(Exception):
    """A workspace refusal. The web layer answers `status` with {"error": message, **extra}."""

    status = 403
    extra: dict = {}


class WorkspaceRequired(AccessError):  # noqa: N818 - names fixed by the design
    """The user has no workspace yet: they must pick one first."""

    status = 409
    extra = {"workspace": "required"}


class AccessDenied(AccessError):  # noqa: N818
    """The user's level in the workspace does not include this."""


class LimitReached(AccessError):  # noqa: N818
    """A free plan's daily allowance of `kind` ("questions" or "cards") is used up."""

    def __init__(self, message, kind: str):
        super().__init__(message)
        self.extra = {"limit": kind}


NEEDS_SUBSCRIPTION = "This needs a subscription to the workspace."
WORKSPACE_REQUIRED = "Choose a workspace first."
