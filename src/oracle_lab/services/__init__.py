"""Use cases of the app. They combine the study domain, the state store and the databases, and know
nothing about HTTP: the web controllers translate requests into calls to these services."""

from collections.abc import Callable

Clock = Callable[[], float]


class NotFoundError(LookupError):
    """The request names a question, exercise or mock exam that does not exist."""
