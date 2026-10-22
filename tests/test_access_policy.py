"""Who may use which workspace, the free plan's limits, and today's usage."""

from __future__ import annotations

from oracle_lab import exams
from oracle_lab.access import limits, policy
from oracle_lab.access.models import WorkspaceAccess
from oracle_lab.study import engine

NOW = 1_800_000_000.0


def row(workspace, level, user="u1"):
    return WorkspaceAccess(user, workspace, level, user, 1.0)


def test_admin_is_a_member_everywhere_without_rows():
    assert all(policy.level_in("admin", [], code) == "member" for code in exams.EXAMS)
    assert policy.usable("admin", []) == list(exams.EXAMS)


def test_levels_follow_the_rows():
    rows = [row("1Z0-071", "member")]
    assert policy.level_in("user", rows, "1Z0-071") == "member"
    assert policy.level_in("user", rows, "1Z0-171") == "none"
    assert policy.usable("user", rows) == ["1Z0-071"]


def test_current_workspace_falls_back_to_a_usable_one():
    assert policy.current_workspace("user", [row("1Z0-071", "member")], "1Z0-171") == "1Z0-071"
    assert policy.current_workspace("user", [row("1Z0-171", "member")], "1Z0-171") == "1Z0-171"
    assert policy.current_workspace("user", [], "1Z0-071") is None
    assert policy.current_workspace("admin", [], None) == exams.DEFAULT_EXAM


def test_used_today_counts_only_today():
    today = engine.day_start(NOW)
    state = {
        "attempts": {"q1": [{"t": today - 60}, {"t": today + 60}], "q2": [{"t": today + 120}]},
        "cards": {"c1": {"reviews": [[today - 60, "good"], [today + 10, "good"]]}, "c2": {"reviews": [[today + 20, "easy"]]}},
    }
    assert limits.used_today(state, NOW) == {"questions": 2, "cards": 2, "exercises": 0, "checks": 0}
    assert limits.used_today({}, NOW) == {"questions": 0, "cards": 0, "exercises": 0, "checks": 0}


def test_note_allowed_for_free_users():
    assert limits.note_allowed("topics/02-restricting-and-sorting/notes.md", 2)
    assert not limits.note_allowed("topics/03-single-row-functions/notes.md", 2)
    assert limits.note_allowed("docs/exam-guide-2026.md", 2)
    assert not limits.note_allowed("docs/cheat-sheet.md", 2)
    assert limits.note_allowed("docs/cheat-sheet.md", None)


def test_workspaces_have_titles_and_tiles():
    for exam in exams.EXAMS.values():
        assert exam.title.startswith("Oracle SQL · ") and exam.tile
        assert exam.public()["title"] == exam.title and exam.public()["tile"] == exam.tile
