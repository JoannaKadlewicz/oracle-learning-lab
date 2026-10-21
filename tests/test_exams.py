from oracle_lab import content, exams


def test_default_is_1z0_071_and_unknown_codes_fall_back():
    assert exams.DEFAULT_EXAM == "1Z0-071"
    assert exams.get(None).code == "1Z0-071"
    assert exams.get("NOPE").code == "1Z0-071"
    assert exams.get("1Z0-171").database == "23ai"

def test_database_keys_and_env_names():
    assert exams.database_keys() == ["default", "23ai"]
    assert exams.env_suffix("default") == "" and exams.env_suffix("23ai") == "_23AI"
    assert exams.get("1Z0-171").database_env == "STUDY_DSN_23AI"
    assert exams.get("1Z0-071").database_env == "STUDY_DSN"

def test_matching_by_engine_version():
    assert [e.code for e in exams.matching("oracle", 19)] == ["1Z0-071"]
    assert [e.code for e in exams.matching("oracle", 21)] == ["1Z0-071"]
    assert [e.code for e in exams.matching("oracle", 23)] == ["1Z0-171"]
    assert exams.matching("postgres", 16) == []

def test_real_registry_has_no_problems():
    assert exams.problems(exams.EXAMS, {"oracle"}) == []

def test_cross_engine_fallback_is_a_problem():
    fake = exams.Exam(code="PG-1", name="PG", product="PostgreSQL", engine="postgres", database="pg16",
                      database_label="PostgreSQL 16", fallback="default", versions=(16, None), pack="pg",
                      questions=10, minutes=30, passing_pct=60, about="")
    found = exams.problems({**exams.EXAMS, "PG-1": fake}, {"oracle", "postgres"})
    assert any("PG-1" in p and "fallback" in p for p in found)

def test_content_reexports_registry():
    assert content.DEFAULT_EXAM == "1Z0-071"
    assert content.EXAMS["1Z0-171"]["database"] == "Oracle AI Database 23ai"
    assert content.EXAMS["1Z0-071"]["product"] == "Oracle"
    assert content.EXAM["code"] == "1Z0-071"

def test_garbage_saved_exam_means_default():  # Review Focus 1
    from oracle_lab.study.tracks import exam_code, track
    for saved in (None, "", "1Z0-999", 42, ["x"]):
        state = {"settings": {"exam": saved}}
        assert exam_code(state) == "1Z0-071" and track(state).CODE == "1Z0-071"
