"""Behaviour every AppStores implementation must have; each check takes a fresh AppStores."""

from __future__ import annotations

import pytest

from oracle_lab.accounts.repositories import AppStores
from oracle_lab.auth.models import (
    AuditEvent,
    EmailTaken,
    Identity,
    LoginFlow,
    ResetToken,
    SessionRecord,
    User,
)


def make_user(n: int = 1, email: str | None = None) -> User:
    return User(f"u{n}", email or f"user{n}@example.com", f"User {n}", "learner", "active", 100.0, None, None)


def password_identity(user: User) -> Identity:
    return Identity("password", user.email, user.id, "hash")


def make_session(token_hash: str, user_id: str, expires_at: float = 1000.0) -> SessionRecord:
    return SessionRecord(token_hash, user_id, "csrf", 1.0, 1.0, expires_at, "127.0.0.1", "agent")


def user_round_trip(stores: AppStores) -> None:
    user = make_user()
    stores.users.add(user, password_identity(user))
    assert stores.users.get(user.id) == user
    assert stores.users.by_email(user.email) == user
    assert stores.users.by_identity("password", user.email) == user
    assert stores.users.identities(user.id) == [password_identity(user)]
    assert stores.users.count() == 1
    assert stores.users.all() == [user]
    assert stores.users.get("nobody") is None


def duplicate_email_raises_email_taken(stores: AppStores) -> None:
    first = make_user(1, "same@example.com")
    stores.users.add(first, password_identity(first))
    second = make_user(2, "same@example.com")
    with pytest.raises(EmailTaken):
        stores.users.add(second, Identity("google", "g-2", second.id))
    assert stores.users.get(second.id) is None
    assert stores.users.count() == 1


def duplicate_identity_raises_email_taken(stores: AppStores) -> None:
    first = make_user(1)
    stores.users.add(first, Identity("google", "g-1", first.id))
    second = make_user(2)
    with pytest.raises(EmailTaken):
        stores.users.add(second, Identity("google", "g-1", second.id))
    assert stores.users.get(second.id) is None


def delete_removes_identities(stores: AppStores) -> None:
    user = make_user()
    stores.users.add(user, password_identity(user))
    stores.users.add_identity(Identity("google", "g-1", user.id))
    stores.users.delete(user.id)
    assert stores.users.get(user.id) is None
    assert stores.users.by_identity("google", "g-1") is None
    assert stores.users.identities(user.id) == []


def flow_take_is_single_use(stores: AppStores) -> None:
    flow = LoginFlow("f1", "state", "nonce", "verifier", "login", None, "/", 500.0)
    stores.flows.add(flow)
    assert stores.flows.take("f1") == flow
    assert stores.flows.take("f1") is None


def reset_take_rejects_used_and_expired(stores: AppStores) -> None:
    stores.resets.add(ResetToken("ok", "u1", "admin", 100.0))
    stores.resets.add(ResetToken("old", "u1", "admin", 50.0))
    assert stores.resets.take("old", 50.0) is None
    taken = stores.resets.take("ok", 10.0)
    assert taken is not None and taken.used_at == 10.0
    assert stores.resets.take("ok", 11.0) is None
    assert stores.resets.take("unknown", 11.0) is None


def sessions_delete_for_user_keeps_one(stores: AppStores) -> None:
    for h in ("a", "b", "c"):
        stores.sessions.add(make_session(h, "u1"))
    stores.sessions.add(make_session("other", "u2"))
    stores.sessions.delete_for_user("u1", keep="b")
    assert [s.token_hash for s in stores.sessions.for_user("u1")] == ["b"]
    assert stores.sessions.get("other") is not None
    stores.sessions.delete_for_user("u1")
    assert stores.sessions.for_user("u1") == []


def purge_drops_expired_sessions_and_flows(stores: AppStores) -> None:
    stores.sessions.add(make_session("old", "u1", expires_at=10.0))
    stores.sessions.add(make_session("new", "u1", expires_at=100.0))
    stores.flows.add(LoginFlow("old", "s", "n", "v", "login", None, "/", 10.0))
    stores.flows.add(LoginFlow("new", "s", "n", "v", "login", None, "/", 100.0))
    stores.sessions.purge(50.0)
    stores.flows.purge(50.0)
    assert stores.sessions.get("old") is None and stores.sessions.get("new") is not None
    assert stores.flows.take("old") is None and stores.flows.take("new") is not None


def session_touch_and_reauth(stores: AppStores) -> None:
    stores.sessions.add(make_session("a", "u1"))
    stores.sessions.touch("a", 5.0)
    stores.sessions.set_reauth("a", 9.0)
    rec = stores.sessions.get("a")
    assert rec is not None and rec.last_seen_at == 5.0 and rec.reauth_until == 9.0


def throttle_counts_window(stores: AppStores) -> None:
    for t in (1.0, 5.0, 9.0):
        stores.throttle.record("k", t)
    stores.throttle.record("other", 9.0)
    assert stores.throttle.count_since("k", 5.0) == 2
    assert stores.throttle.count_since("k", 10.0) == 0
    assert stores.throttle.last("k") == 9.0
    assert stores.throttle.last("none") is None
    stores.throttle.purge(5.0)
    assert stores.throttle.count_since("k", 0.0) == 2
    stores.throttle.clear("k")
    assert stores.throttle.count_since("k", 0.0) == 0
    assert stores.throttle.count_since("other", 0.0) == 1


def audit_recent_newest_first_and_filters(stores: AppStores) -> None:
    def ev(t: float, event: str, user_id: str | None) -> AuditEvent:
        return AuditEvent(t, event, "ok", user_id, "ip", "ua", {})

    stores.audit.add(ev(1.0, "login", "u1"))
    stores.audit.add(ev(3.0, "logout", "u2"))
    stores.audit.add(ev(2.0, "login", "u2"))
    assert [e.t for e in stores.audit.recent()] == [3.0, 2.0, 1.0]
    assert [e.t for e in stores.audit.recent(limit=2)] == [3.0, 2.0]
    assert [e.t for e in stores.audit.recent(event="login")] == [2.0, 1.0]
    assert [e.t for e in stores.audit.recent(user_id="u2")] == [3.0, 2.0]
    stores.audit.purge(2.0)
    assert [e.t for e in stores.audit.recent()] == [3.0, 2.0]


def settings_round_trip(stores: AppStores) -> None:
    assert stores.settings.get("k") is None
    stores.settings.set("k", "v")
    stores.settings.set("k", "w")
    assert stores.settings.get("k") == "w"


def practice_schemas_round_trip(stores: AppStores) -> None:
    from oracle_lab.auth.models import PracticeSchema

    rec = PracticeSchema("u1", "19c", "LAB_U1", "ready", 1.0)
    stores.schemas.put(rec)
    assert stores.schemas.get("u1", "19c") == rec
    assert stores.schemas.for_user("u1") == [rec]
    assert stores.schemas.all() == [rec]
    stores.schemas.delete_for_user("u1")
    assert stores.schemas.get("u1", "19c") is None


def state_store_is_per_user(stores: AppStores) -> None:
    with stores.states.for_user("a").transaction() as state:
        state["settings"]["x"] = 1
    assert stores.states.for_user("a").load()["settings"] == {"x": 1}
    assert stores.states.for_user("b").load()["settings"] == {}
    stores.states.delete("a")
    assert stores.states.for_user("a").load()["settings"] == {}


def notes_are_per_user(stores: AppStores) -> None:
    a = stores.notes.for_user("a")
    assert a.add("note", "First", "# First\n") == "note.md"
    assert a.add("note", "Second", "# Second\n") == "note-2.md"
    assert a.add("note", "Third", "# Third\n") == "note-3.md"
    assert a.read("note-2.md") == "# Second\n"
    assert a.read("missing.md") is None
    assert [n for n, _ in a.entries()] == ["note.md", "note-3.md", "note-2.md"]
    assert dict(a.entries())["note.md"] == "First"
    assert stores.notes.for_user("b").entries() == []
    stores.notes.delete("a")
    assert stores.notes.for_user("a").entries() == []


CONTRACT = [
    user_round_trip,
    duplicate_email_raises_email_taken,
    duplicate_identity_raises_email_taken,
    delete_removes_identities,
    flow_take_is_single_use,
    reset_take_rejects_used_and_expired,
    sessions_delete_for_user_keeps_one,
    purge_drops_expired_sessions_and_flows,
    session_touch_and_reauth,
    throttle_counts_window,
    audit_recent_newest_first_and_filters,
    settings_round_trip,
    practice_schemas_round_trip,
    state_store_is_per_user,
    notes_are_per_user,
]
