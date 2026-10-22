"""Admins and plans: roles, per-account limits, plan defaults, and guests hidden from the accounts table."""

from __future__ import annotations

import json

import pytest

from conftest import Client
from oracle_lab.accounts.memory import memory_stores


@pytest.fixture
def lab(serve):
    stores = memory_stores()
    server = serve(stores=stores)
    admin = server.sign_in("admin@x.org")
    user = Client(server.port).sign_in("user@x.org")
    return stores, admin, user, stores.users.by_email("user@x.org").id


def body(response):
    return json.loads(response[2])


def test_role_picker_accepts_pro_and_refuses_guest(lab):
    stores, admin, _, uid = lab
    assert admin("/api/admin/role", {"user_id": uid, "role": "pro"})[0] == 200
    assert stores.users.get(uid).role == "pro"
    assert admin("/api/admin/role", {"user_id": uid, "role": "guest"})[0] == 400
    stores.users.set_role(uid, "guest")
    assert admin("/api/admin/role", {"user_id": uid, "role": "pro"})[0] == 400  # a guest has no account to upgrade


def test_admin_sets_and_clears_account_limits(lab):
    stores, admin, _, uid = lab
    assert admin("/api/admin/limits", {"user_id": uid, "limits": {"exercises": 25, "questions": None}})[0] == 200
    row = next(u for u in body(admin("/api/admin/users"))["users"] if u["id"] == uid)
    assert row["limits"] == {"exercises": 25} and row["effective_limits"]["exercises"] == 25
    assert admin("/api/admin/limits", {"user_id": uid, "limits": {"exercises": -2}})[0] == 400
    assert admin("/api/admin/limits", {"user_id": uid, "limits": None})[0] == 200
    row = next(u for u in body(admin("/api/admin/users"))["users"] if u["id"] == uid)
    assert row["limits"] == {} and row["effective_limits"]["exercises"] == 10
    assert any(e.event == "account_limits_changed" for e in stores.audit.recent(20))


def test_guests_hidden_unless_asked(lab):
    stores, admin, _, uid = lab
    stores.users.set_role(uid, "guest")
    assert uid not in [u["id"] for u in body(admin("/api/admin/users"))["users"]]
    assert uid in [u["id"] for u in body(admin("/api/admin/users?guests=1"))["users"]]


def test_plan_defaults_round_trip(lab):
    _, admin, _, _ = lab
    defaults = body(admin("/api/admin/settings"))["plan_defaults"]
    assert defaults == {"guest_questions": 20, "guest_cards": 20, "guest_topics": 2, "user_exercises": 10}
    changed = body(admin("/api/admin/settings", {"plan_defaults": {"user_exercises": 5}}))
    assert changed["plan_defaults"]["user_exercises"] == 5 and changed["plan_defaults"]["guest_questions"] == 20
    assert admin("/api/admin/settings", {"plan_defaults": {"guest_topics": 99}})[0] == 400
