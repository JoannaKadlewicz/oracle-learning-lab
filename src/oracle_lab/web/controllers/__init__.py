"""HTTP controllers: each one maps a group of endpoints onto a service and registers its own routes."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from oracle_lab.i18n import message_of
from oracle_lab.services import NotFoundError
from oracle_lab.web.http import HttpError, Response


def respond(action: Callable[[], Any], invalid: tuple[type[Exception], ...] = (ValueError, TypeError)) -> Response:
    """Run a service call: its result as JSON, NotFoundError as 404, invalid input as 400."""
    try:
        return Response.json(action())
    except NotFoundError as exc:
        raise HttpError(404, message_of(exc)) from exc
    except invalid as exc:
        raise HttpError(400, message_of(exc)) from exc
