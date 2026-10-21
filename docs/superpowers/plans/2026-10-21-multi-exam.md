# Multi-exam Platform Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the two-button exam switch with a grouped exam drop-down, make exams data (a registry), group content in packs, and put all learner-facing SQL behind a database-engine boundary with Oracle as the only engine, with no behaviour change for Oracle learners.

**Architecture:**
- **Exam registry.** `src/oracle_lab/exams.py` is a dependency-free registry of `Exam` records. Config, content, routing, the validator and the front-end payload all read it.
- **Engine boundary.** `src/oracle_lab/engines/` defines an `Engine` protocol. `engines/oracle.py` implements it as thin adapters over today's modules (`database/`, `grading/`, `analysis/`, `provisioning/`).
- **Content packs.** Content is grouped into packs (`content.PACKS`, one pack `oracle-sql`).
- **Front end.** It gets every exam-specific word from the server payload, and the sidebar gets an accessible listbox picker in `js/ui/exam-picker.js`.

**Tech Stack:**
- **Server:** Python 3.12 standard library, python-oracledb thin mode, pytest, ruff.
- **Front end:** a vanilla-JS ES-module SPA with a strict CSP.
- **Browser checks:** Playwright, from the session's scratch `pwlib`.

**Spec:** `docs/superpowers/specs/2026-10-21-multi-exam-design.md`

## Global Constraints

- **Stack:** Python 3.12 stdlib server and a vanilla-JS ES-module SPA, with no new dependencies.
  - The CSP stays strict: no inline handlers or styles-by-script, and inline `<script>` only through the existing hash mechanism (`web/static.py inline_script_hashes`).
- **Stored data stays readable without a migration:**
  - `settings.exam` keeps exam codes ("1Z0-071", "1Z0-171");
  - mocks keep their `exam` code;
  - practice-schema records keep the database keys "default" and "23ai".
- **Environment variable names do not change.**
  - These are read exactly as today: `STUDY_DSN`, `STUDY_USER`, `STUDY_PASSWORD`, `STUDY_DSN_23AI`, `STUDY_USER_23AI`, `STUDY_PASSWORD_23AI`.
  - So are `STUDY_PROVISIONER_USER`, `STUDY_PROVISIONER_PASSWORD`, `STUDY_GATEWAY_USER`, `STUDY_GATEWAY_PASSWORD`, `STUDY_PRACTICE_TABLESPACE` and `STUDY_PRACTICE_QUOTA_MB`, each with and without the `_23AI` suffix.
  - The key "default" has no suffix; any other key's suffix is `"_" + key.upper()`.
- **Default exam:** "1Z0-071". An unknown or missing saved exam means 1Z0-071.
- **Oracle learners see no change** other than the picker:
  - the same questions, cards and exercises per exam;
  - the same SQL results;
  - the same error explanations.
- **Fallback:** a missing database falls back only to the exam's registry `fallback` key, which must be the same engine.
  - 1Z0-171 has fallback "default"; 1Z0-071 has none.
  - A cross-engine fallback makes startup fail with `ConfigurationError`.
- **Validation by connected database:** `oracle-lab validate` checks every exam whose engine and version range match the connected database. 1Z0-071 is checked on Oracle majors [19, 23) and 1Z0-171 on [23, ∞). The optional `--exam CODE` restricts the run to one exam.
- **App storage is out of scope:** `accounts/oracle_store.py`, `database/app_store.py` and the SQLite/memory stores.
- **Copy:** plain sentence-case English, no exclamation marks, in the app's existing voice.
- **Exam literals:** the application code may name "1Z0-071", "1Z0-171", "19c" or "23ai" only in these places:
  - `exams.py`, `engines/oracle.py`, the `content/` package and `analysis/error_hints.py` (Oracle engine data);
  - `tools/validate_content.py` (the Oracle content validator);
  - `config.py` (its docstring);
  - static HTML fallback copy.
- **Tests** run with `.venv/bin/python -m pytest -q`, and lint with `.venv/bin/python -m ruff check src tests`. Both must pass after every task.

## Review Focus

1. **A saved exam code that no longer exists** (or garbage in `settings.exam`) gets 1Z0-071 everywhere: the content, the routing and the picker's current item. No 500. Test owner: Task 1.
2. **Existing practice-schema records keyed "23ai"** are still found and used for 1Z0-171, and a 1Z0-171 learner on a server without a 23ai target still gets their "default" schema. Test owner: Task 4.
3. **Single-key study shortcuts** ("1"–"4", letters) do not fire while focus is on the picker or its open list. Test owner: Task 7 (browser check).
4. **Escape inside the mobile drawer** closes only the open picker list, and focus returns to the picker button. Test owner: Task 7 (browser check).
5. **Switching exams while a mock exam runs** still asks first. After switching back, the mock resumes with its answers intact. Test owner: Task 7 (browser check).

---

### Task 1: Exam registry

**Files:**
- Create: `src/oracle_lab/exams.py`
- Modify: `src/oracle_lab/content/objectives.py:21-28` (remove `EXAMS`, `DEFAULT_EXAM`, `EXAM`); `src/oracle_lab/content/__init__.py:43` (re-export them from the registry)
- Test: `tests/test_exams.py` (new)

**Interfaces:**
- Produces, in `oracle_lab.exams` (it imports nothing from `oracle_lab` except stdlib):
  - `DEFAULT_DATABASE = "default"`
  - `@dataclass(frozen=True) class Exam`:
    - `code: str`, `name: str`, `product: str`, `engine: str`;
    - `database: str` (a database key), `database_label: str`, `fallback: str | None`;
    - `versions: tuple[int, int | None]` (engine major versions, min inclusive, max exclusive);
    - `pack: str`, `questions: int`, `minutes: int`, `passing_pct: int`, `about: str`.
    - Property `database_env -> str`: `"STUDY_DSN"` for "default", else `"STUDY_DSN_" + key.upper()`.
    - Method `public() -> dict`. Keys: code, name, product, database (= `database_label`), database_env, versions (a list), questions, minutes, passing_pct, about.
  - `EXAMS: dict[str, Exam]` in display order. The two entries, verbatim:
    - **1Z0-071:** name "Oracle Database SQL", product "Oracle", engine "oracle", database "default", database_label "Oracle Database 19c", fallback None, versions (19, 23), pack "oracle-sql", 63 questions, 120 minutes, 63% pass. About: "Tests Oracle Database 19c behavior. Questions whose answer changed in 23ai are shown on this exam only."
    - **1Z0-171:** name "Oracle AI Database SQL Associate", product "Oracle", engine "oracle", database "23ai", database_label "Oracle AI Database 23ai", fallback "default", versions (23, None), pack "oracle-sql", 60 questions, 120 minutes, 65% pass. About: "Tests the same SQL on Oracle 23ai and adds topic 15, the SQL features new in 23ai."
  - `DEFAULT_EXAM = "1Z0-071"`
  - `get(code: str | None) -> Exam`: unknown or None gives `EXAMS[DEFAULT_EXAM]`.
  - `database_keys() -> list[str]`: unique keys over `database` and `fallback`, "default" first, then registry order.
  - `engine_of_key(key: str) -> str`
  - `env_suffix(key: str) -> str`: `""` for "default", else `"_" + key.upper()`.
  - `matching(engine: str, major: int) -> list[Exam]`: exams with that engine whose `versions` range contains `major`.
  - `problems(exams: Mapping[str, Exam], engine_names: Collection[str]) -> list[str]`. It reports, one message each:
    - a default exam that is missing;
    - an unknown engine;
    - a database key used by two engines;
    - a fallback whose key is not used by any exam of the same engine, or that is the exam's own key;
    - a fallback of another engine.
- Consumed later as `content.EXAMS` (code → `public()` dict), `content.DEFAULT_EXAM` and `content.EXAM` (the default's public dict), so `study/tracks.py`, `study/recording.py`, `services/study.py` and `tools/validate_content.py` keep working unchanged in this task.

- [ ] **Step 1: Write the failing tests** in `tests/test_exams.py`:

```python
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
    for saved in (None, "", "1Z0-999", 42):
        state = {"settings": {"exam": saved}}
        assert exam_code(state) == "1Z0-071" and track(state).CODE == "1Z0-071"
```

- [ ] **Step 2: Run** `.venv/bin/python -m pytest tests/test_exams.py -q`. Expected: it fails, because the module `oracle_lab.exams` doesn't exist yet.
- [ ] **Step 3: Implement `oracle_lab/exams.py`** with the interfaces above. Then make `content.EXAMS` equal `{code: e.public() for code, e in exams.EXAMS.items()}`, `content.DEFAULT_EXAM = exams.DEFAULT_EXAM` and `content.EXAM = content.EXAMS[DEFAULT_EXAM]`, and delete those three names from `objectives.py` (keep its docstring accurate). Make `study/tracks.exam_code` tolerate non-string values (`42` must not raise).
- [ ] **Step 4: Run** `.venv/bin/python -m pytest -q`. Expected: everything passes. `tests/test_content.py` still sees 63/60 question counts.
- [ ] **Step 5: Commit:** `git add src/oracle_lab/exams.py src/oracle_lab/content tests/test_exams.py src/oracle_lab/study/tracks.py && git commit -m "feat(exams): exam registry as the one source of exam facts"`

---

### Task 2: Content packs

**Files:**
- Modify: `src/oracle_lab/content/__init__.py` (Pack, PACKS, item_exams, for_exam); `src/oracle_lab/study/notes.py:61-90` (pack-scoped listing); `src/oracle_lab/web/controllers/notes.py` and the services that build `NotesLibrary` (pass the current exam's pack); `src/oracle_lab/tools/validate_content.py` (unique IDs across all packs; `exams` values checked against the item's pack)
- Test: `tests/test_content.py`, `tests/test_notes*.py` or `tests/test_web.py` (whichever covers `/api/notes` today)

**Interfaces:**
- Consumes: `exams.EXAMS`, `exams.get`, `Exam.pack` (Task 1).
- Produces, in `oracle_lab.content`:
  - `@dataclass(frozen=True) class Pack`:
    - `id: str`, `topics: dict[str, str]`, `sections: dict[str, str]`, `objectives: dict[str, str]`;
    - `topic_exams: dict[str, list[str]]`, `section_exams: dict[str, list[str]]`;
    - `topic_needs: dict[str, dict]` (topic → `{"major": int, "label": str}`);
    - `notes: tuple[str, ...]` (glob patterns relative to `NOTES_DIR`);
    - `home_notes: tuple[dict, ...]` (each `{"path", "title", "blurb"}`);
    - `questions: list[dict]`, `flashcards: list[dict]`, `labs: list[dict]`.
  - `PACKS: dict[str, Pack]` with exactly one pack, `"oracle-sql"`. It holds today's TOPICS, SECTIONS, OBJECTIVES, `TOPIC_EXAMS={"t15": ["1Z0-171"]}`, `SECTION_EXAMS={"17": ["1Z0-171"]}`, all modules plus `generated.json`, and these:
    - `topic_needs={"t15": {"major": 23, "label": "Oracle 23ai"}}`;
    - `notes=("docs/*.md", "topics/*/*.md", "topics/*/*.sql")`;
    - `home_notes`, verbatim:
      - path "docs/exam-guide-2026.md", title "Exam guide 2026", blurb "1Z0-071 and 1Z0-171 compared, with every 19c and 23ai difference.";
      - path "docs/cheat-sheet.md", title "Cheat sheet", blurb "The rules and traps of every topic on one page.".
  - `pack_of(code: str | None) -> Pack`, the pack of `exams.get(code)`.
  - `item_exams(item: dict, pack: Pack | None = None) -> list[str]`. It returns the item's `exams`, else its topic's in the pack, else **the codes of the exams whose `pack` is this pack's id**. `pack` defaults to the pack that holds the item.
  - `for_exam(code)` returns the same `SimpleNamespace` attributes as today (CODE, EXAM, TOPICS, SECTIONS, OBJECTIVES, QUESTIONS, FLASHCARDS, LABS) plus `PACK` and `HOME_NOTES`.
    - Items are filtered from the exam's pack only.
    - Every item of a topic in `topic_needs` is returned as a **copy** with `"needs": {"major", "label"}` added. The stored dicts are never mutated.
  - Module-level `TOPICS`, `SECTIONS`, `OBJECTIVES`, `QUESTIONS`, `FLASHCARDS`, `LABS` stay. They are the union over packs (equal to today with one pack), so `recording`, `error_hints` and the validator keep working.
  - `NotesLibrary.list(globs: tuple[str, ...] | None = None)` and `NotesLibrary.read(path, globs=None)`: when `globs` is given, built-in notes are limited to those patterns. Personal notes are always included.

- [ ] **Step 1: Write the failing tests** (add to `tests/test_content.py`):

```python
from oracle_lab import content, exams

def test_one_pack_holds_everything():
    pack = content.PACKS["oracle-sql"]
    assert set(content.PACKS) == {"oracle-sql"}
    assert len(pack.questions) == len(content.QUESTIONS) and len(pack.flashcards) == len(content.FLASHCARDS)

def test_untagged_items_belong_only_to_their_packs_exams(monkeypatch):
    fake = exams.Exam(code="PG-1", name="PG", product="PostgreSQL", engine="oracle", database="default",
                      database_label="x", fallback=None, versions=(1, None), pack="other", questions=1,
                      minutes=1, passing_pct=1, about="")
    monkeypatch.setitem(exams.EXAMS, "PG-1", fake)
    monkeypatch.setitem(content.PACKS, "other", content.Pack(
        id="other", topics={}, sections={}, objectives={}, topic_exams={}, section_exams={}, topic_needs={},
        notes=(), home_notes=(), questions=[], flashcards=[], labs=[]))
    untagged = next(q for q in content.QUESTIONS if "exams" not in q and q["topic"] != "t15")
    assert content.item_exams(untagged) == ["1Z0-071", "1Z0-171"]
    assert content.for_exam("PG-1").QUESTIONS == []

def test_needs_marks_t15_items_without_mutating_content():
    view = content.for_exam("1Z0-171")
    t15 = [c for c in view.FLASHCARDS if c["topic"] == "t15"]
    assert t15 and all(c["needs"] == {"major": 23, "label": "Oracle 23ai"} for c in t15)
    assert all("needs" not in c for c in content.FLASHCARDS)
    assert all("needs" not in q for q in content.for_exam("1Z0-071").QUESTIONS)

def test_for_exam_unchanged_for_oracle():  # same filtering as before the packs
    for code in ("1Z0-071", "1Z0-171"):
        view = content.for_exam(code)
        assert [q["id"] for q in view.QUESTIONS] == [q["id"] for q in content.QUESTIONS
                                                      if code in content.item_exams(q)]
    assert [h["title"] for h in content.for_exam("1Z0-071").HOME_NOTES] == ["Exam guide 2026", "Cheat sheet"]
```

Also add a notes test: with `globs=("docs/*.md",)` the list has no `topics/` path and `read("topics/01-…/notes.md", globs=…)` returns None. Without globs the list is unchanged.

- [ ] **Step 2: Run** `.venv/bin/python -m pytest tests/test_content.py -q`. Expected: it fails, because `PACKS` isn't defined.
- [ ] **Step 3: Implement** the interfaces above. The notes controller (or the service behind it) passes `content.pack_of(exam_code(state)).notes` for the signed-in user. Validator structure checks: IDs unique across all packs, and `exams` values must be codes of exams using the item's pack.
- [ ] **Step 4: Run** `.venv/bin/python -m pytest -q` and `.venv/bin/python -m oracle_lab.cli validate --static` (or `.venv/bin/oracle-lab validate --static`). Expected: the tests pass, and the static validation reports 0 problems.
- [ ] **Step 5: Commit:** `git commit -am "feat(content): content packs; untagged items stay within their pack"` (plus any new test file).

---

### Task 3: Config by database key

**Files:**
- Modify: `src/oracle_lab/config.py` (remove `EXAM_23AI` and `Settings.database_23ai`; add `Settings.databases`; derive practice targets from registry keys); every importer of `EXAM_23AI` or `database_23ai` (`bootstrap.py`, `cli.py`, `provisioning/practice.py`). In `bootstrap.build_catalog` and `practice.py` only the minimal change that keeps today's behaviour: Task 4 replaces both.
- Test: `tests/test_config.py`

**Interfaces:**
- Consumes: `exams.database_keys()`, `exams.env_suffix()` (Task 1).
- Produces:
  - `Settings.databases: dict[str, DatabaseTarget]`. It always contains "default" (= `Settings.database`, which stays). It holds every other registry key whose `STUDY_DSN{suffix}` is set: user `STUDY_USER{suffix}` or the default user, and password `STUDY_PASSWORD{suffix}` or the default password, exactly as `database_23ai` was built.
  - `Settings.practice: dict[str, PracticeTarget]`: one entry per registry key whose provisioner and gateway users are set, read with that key's suffix and DSN. Keys and env names are identical to today's for "default" and "23ai".
  - `Settings.from_env` raises `ConfigurationError` when `exams.problems(exams.EXAMS, engines-known)` is non-empty. In this task the known engine set is `{"oracle"}`; Task 4 switches it to `engines.ENGINES`.

- [ ] **Step 1: Update and add tests** in `tests/test_config.py`.
  - Replace the `database_23ai` assertions with `settings.databases["23ai"]` ones, same values.
  - Add:

```python
def test_databases_by_registry_key():
    s = Settings.from_env({"STUDY_DSN": "h:1/A", "STUDY_DSN_23AI": "h:2/B", "STUDY_USER_23AI": "u23"})
    assert set(s.databases) == {"default", "23ai"}
    assert s.databases["default"] is s.database or s.databases["default"] == s.database
    assert (s.databases["23ai"].dsn, s.databases["23ai"].user) == ("h:2/B", "u23")
    assert set(Settings.from_env({"STUDY_DSN": "h:1/A"}).databases) == {"default"}

def test_practice_targets_keep_their_env_names(): # identical to today's key set and suffixes
    env = {"STUDY_DSN": "h:1/A", "STUDY_DSN_23AI": "h:2/B",
           "STUDY_PROVISIONER_USER": "p", "STUDY_GATEWAY_USER": "g",
           "STUDY_PROVISIONER_USER_23AI": "p2", "STUDY_GATEWAY_USER_23AI": "g2"}
    s = Settings.from_env(env)
    assert set(s.practice) == {"default", "23ai"}
    assert s.practice["23ai"].provisioner.user == "p2" and s.practice["23ai"].gateway.dsn == "h:2/B"
```

- [ ] **Step 2: Run** `.venv/bin/python -m pytest tests/test_config.py -q`. Expected: it fails, because `databases` doesn't exist yet.
- [ ] **Step 3: Implement.** In `practice.py`, replace the `EXAM_23AI` comparison with the registry: `key = exams.get(code).database`, falling back to the exam's `fallback` (Task 4 completes it). Change `cli._serve`'s log line to list `settings.databases` generically: "databases: default=…, 23ai=…".
- [ ] **Step 4: Run** `.venv/bin/python -m pytest -q`. Expected: everything passes, including `tests/test_practice.py`. Its `EXAM_23AI` import becomes the literal `"1Z0-171"` or `exams.get("1Z0-171").code`.
- [ ] **Step 5: Commit:** `git commit -am "refactor(config): databases and practice targets keyed by the exam registry"`

---

### Task 4: Engine boundary, Oracle engine, and routing

**Files:**
- Create: `src/oracle_lab/engines/__init__.py`, `src/oracle_lab/engines/oracle.py`
- Modify:
  - `src/oracle_lab/database/connection.py` (`DatabaseCatalog` by database key);
  - `src/oracle_lab/provisioning/practice.py` (`for_exam` via the registry, the engine's `proxy_database`);
  - `src/oracle_lab/bootstrap.py` (build the catalog and provisioners through the engines; `problems` check against `engines.ENGINES`);
  - `src/oracle_lab/services/sql_lab.py` (all SQL through the current exam's engine);
  - `src/oracle_lab/cli.py` (`init-db` and `_ensure_profiles` through the engines; one provisioner builder, no duplicated wiring);
  - `src/oracle_lab/config.py` (known engines now `engines.ENGINES`).
- Test: `tests/test_engines.py` (new), `tests/test_practice.py`, `tests/test_web.py` (as needed for the catalog constructor change)

**Interfaces:**
- Consumes: `exams.get`, `exams.engine_of_key`, `exams.DEFAULT_DATABASE` (Task 1); `Settings.databases`, `Settings.practice` (Task 3).
- Produces, in `oracle_lab.engines`:

```python
class Provisioner(Protocol):
    def ensure_profile(self) -> None: ...
    def create(self, name: str) -> None: ...
    def drop(self, name: str) -> None: ...
    def size_mb(self, name: str) -> float | None: ...

class Engine(Protocol):
    name: str          # registry engine id, "oracle"
    label: str         # shown to learners, "Oracle"
    editor_mode: str   # CodeMirror mode, "text/x-plsql" for Oracle
    def database(self, target: DatabaseTarget, call_timeout_ms: int) -> Database: ...
    def proxy_database(self, gateway: DatabaseTarget, schema: str, call_timeout_ms: int) -> Database: ...
    def provisioner(self, target: PracticeTarget, call_timeout_ms: int) -> Provisioner: ...
    def run_script(self, database: Database, script: str, *, keep_changes: bool = False,
                   inspect: bool = False) -> dict[str, Any]: ...
    def run_cleanup(self, database: Database, item: dict) -> None: ...
    def grade(self, database: Database, lab: dict, sql: str) -> dict[str, Any]: ...
    def visualize(self, database: Database, sql: str) -> dict[str, Any]: ...
    def describe(self, database: Database) -> dict[str, Any]: ...
    def reset_sample(self, database: Database) -> dict[str, Any]: ...
    def ensure_sample(self, database: Database, timeout: float) -> bool: ...

ENGINES: dict[str, Engine]          # {"oracle": OracleEngine()}
def engine(name: str) -> Engine     # KeyError for an unknown name
def engine_for_exam(code: str | None) -> Engine
def engine_for_key(key: str) -> Engine
```

- `OracleEngine` (in `engines/oracle.py`) delegates to today's code with the same arguments: `OracleDatabase`, `ProxyDatabase`, `SchemaProvisioner` (with `PROVISIONER_CALL_TIMEOUT_MS` from bootstrap moved here, and `sample_loader` and `proxy_factory` as bootstrap builds them today), `ScriptRunner(...).run`, `labs.run_cleanup` inside `session()`, `labs.grade`, `visualizer.visualize(conn, sql, query_rows)` inside `session()`, `describe_schema`, `SampleSchema(db).reset()` and `ensure_sample_schema`. `describe()` adds `"product": "Oracle"` into the returned `database` dict when the result is ok.
- `DatabaseCatalog(by_key: Mapping[str, Database])`:
  - `.default` is `by_key["default"]`;
  - `for_exam(code) -> Database | None` returns the database of the exam's `database` key, else of its `fallback` key, else None;
  - `has_track_databases` is `len(by_key) > 1`;
  - `all()` lists the distinct databases.
- `PracticeDatabases.for_exam(code)`:
  - `key` is the first of (`exam.database`, `exam.fallback`) present in `self.provisioners`.
  - With no key, an admin gets `self.shared.for_exam(code)` if not None. Everyone else, and an admin with None, gets `PracticeUnavailable(NOT_SET_UP)`.
  - A ready schema is returned as `engines.engine_for_key(key).proxy_database(...)`.
  - `provisioning_hook` keeps pre-provisioning `exams.DEFAULT_DATABASE`.
- `_TrackDatabase` gains `current_engine() -> Engine`, the engine of the user's current exam. `SqlLabService.run`, `visualize`, `schema` and `reset_sample_data` and `ExerciseService.grade` call the engine, never `ScriptRunner`, `labs`, `visualizer`, `describe_schema` or `SampleSchema` directly.

- [ ] **Step 1: Write the failing tests** in `tests/test_engines.py`:

```python
from oracle_lab import engines, exams
from oracle_lab.database.connection import DatabaseCatalog

def test_oracle_engine_registered():
    e = engines.engine("oracle")
    assert (e.name, e.label, e.editor_mode) == ("oracle", "Oracle", "text/x-plsql")
    assert engines.engine_for_exam("1Z0-171") is e and engines.engine_for_key("23ai") is e

def test_catalog_routes_by_key_with_same_engine_fallback():
    a, b = object(), object()
    assert DatabaseCatalog({"default": a, "23ai": b}).for_exam("1Z0-171") is b
    assert DatabaseCatalog({"default": a}).for_exam("1Z0-171") is a        # registry fallback
    assert DatabaseCatalog({"default": a}).for_exam("1Z0-071") is a

def test_fake_engine_exam_without_database_is_not_set_up(monkeypatch):
    fake = exams.Exam(code="PG-1", name="PG", product="PostgreSQL", engine="fake", database="pg16",
                      database_label="PostgreSQL 16", fallback=None, versions=(16, None), pack="oracle-sql",
                      questions=1, minutes=1, passing_pct=1, about="")
    monkeypatch.setitem(exams.EXAMS, "PG-1", fake)
    monkeypatch.setitem(engines.ENGINES, "fake", engines.ENGINES["oracle"])
    assert DatabaseCatalog({"default": object()}).for_exam("PG-1") is None
```

In `tests/test_practice.py` add (Review Focus 2) a learner case and an admin case:
- **Learner:** a learner with an existing repo record `PracticeSchema(user, "23ai", …, status="ready")` and both provisioners gets a proxy database built on the "23ai" gateway for `for_exam("1Z0-171")`. With only the "default" provisioner, the same learner gets the "default" schema.
- **Admin:** a fake exam whose database key is unconfigured and has no fallback raises `PracticeUnavailable(NOT_SET_UP)` for a learner, and for an admin when the shared catalog has no database for it.

- [ ] **Step 2: Run** `.venv/bin/python -m pytest tests/test_engines.py tests/test_practice.py -q`. Expected: it fails, because the module `oracle_lab.engines` doesn't exist yet.
- [ ] **Step 3: Implement** the interfaces. `engines/oracle.py` imports `config` (DatabaseTarget, PracticeTarget), so `config.Settings.from_env` must import `engines` inside the function, not at module level, to avoid an import cycle. In bootstrap, build the catalog as `DatabaseCatalog({key: engines.engine_for_key(key).database(t, settings.call_timeout_ms) for key, t in settings.databases.items()})` and the provisioners as `engines.engine_for_key(key).provisioner(t, …)`.
- [ ] **Step 4: Run** `.venv/bin/python -m pytest -q` and `.venv/bin/python -m ruff check src tests`. Expected: both pass, with no change to any test of SQL results, grading or provisioning behaviour.
- [ ] **Step 5: Commit:** `git add -A src/oracle_lab tests && git commit -m "feat(engines): database-engine boundary with Oracle as the engine; routing by the exam registry"`

---

### Task 5: Validator picks exams through the registry

**Files:**
- Modify: `src/oracle_lab/tools/validate_content.py:380-438` (remove `track_of`; registry matching; `--exam`); `src/oracle_lab/cli.py` (the `validate` parser gets `--exam`; `_validate` uses the default database built through its engine)
- Test: `tests/test_content.py` or a new `tests/test_validate.py` (with a fake connection object exposing `.version`)

**Interfaces:**
- Consumes: `exams.matching`, `exams.get`, `exams.EXAMS` (Task 1); `engines.engine_for_key("default")` (Task 4).
- Produces:
  - `validate_content.exams_to_check(version: str, only: str | None = None) -> list[str]`. It returns the codes of `exams.matching("oracle", major)`, or `[only]` when `only` is given (an unknown `only` is a `SystemExit` with the message "unknown exam: X").
  - `db_errors(database, topic=None, only=None)` checks items with `any(code in content.item_exams(item) for code in codes)`, and prints "Database: Oracle {version}, checking the {codes joined by ' and '} items…".
  - `run(args, database)` reads `getattr(args, "exam", None)`.

- [ ] **Step 1: Write the failing tests:**

```python
from oracle_lab.tools import validate_content as v

def test_exams_to_check_by_version():
    assert v.exams_to_check("19.3.0.0.0") == ["1Z0-071"]
    assert v.exams_to_check("21.3.0.0.0") == ["1Z0-071"]
    assert v.exams_to_check("23.5.0.24.7") == ["1Z0-171"]
    assert v.exams_to_check("19.3.0.0.0", only="1Z0-171") == ["1Z0-171"]
```

- [ ] **Step 2: Run** the test file. Expected: it fails, because `exams_to_check` isn't defined.
- [ ] **Step 3: Implement**, and add `validate.add_argument("--exam", help="check one exam's items only, for example 1Z0-171")`.
- [ ] **Step 4: Run** `.venv/bin/python -m pytest -q`, then, if the local 19c database is reachable, `STUDY_DSN=localhost:1525/ORAPDB1 .venv/bin/oracle-lab validate --topic t01`. Expected: the tests pass. The run prints "checking the 1Z0-071 items", with the same problem count as on `main` (compare by running the same command on `main` first, if the database is reachable).
- [ ] **Step 5: Commit:** `git commit -am "feat(validate): choose exams by the connected database through the registry; --exam"`

---

### Task 6: Server payload for the front end

**Files:**
- Modify:
  - `src/oracle_lab/services/study.py` (`track_content`);
  - `src/oracle_lab/web/controllers/auth.py` (`/api/auth/config`);
  - `src/oracle_lab/web/controllers/sql_lab.py` (no change if `describe` already carries product);
  - `src/oracle_lab/cli.py` (parser description: "Oracle Learning Lab: SQL certification exam practice").
- Test: `tests/test_web.py`, `tests/test_auth_web.py`

**Interfaces:**
- Consumes: `exams.EXAMS`, `Exam.public()` (Task 1); `content.for_exam(...).HOME_NOTES` (Task 2); `engines.engine_for_exam` (Task 4).
- Produces:
  - `GET /api/content` adds:
    - `"engine": {"name", "label", "editor_mode"}` of the current exam;
    - `"home_notes": [...]` from the pack;
    - each item of a `topic_needs` topic carries `"needs"`.
    - `"exams"` stays a dict code → public dict, in registry order. `"exam"` is the current one's public dict.
  - `GET /api/auth/config` adds `"exams": [{"code", "database"}]` in registry order (public, no auth).
  - `GET /api/schema`, when ok, has `database.product` (from Task 4's `describe`).

- [ ] **Step 1: Write the failing tests:**

```python
def test_content_payload_has_engine_and_exam_facts(serve):
    http = serve().sign_in()
    body = json.loads(http("/api/content")[2])
    assert body["engine"] == {"name": "oracle", "label": "Oracle", "editor_mode": "text/x-plsql"}
    assert list(body["exams"]) == ["1Z0-071", "1Z0-171"]
    assert body["exam"]["code"] == "1Z0-071" and body["exam"]["product"] == "Oracle"
    assert [n["path"] for n in body["home_notes"]] == ["docs/exam-guide-2026.md", "docs/cheat-sheet.md"]

def test_auth_config_lists_exams(serve):
    body = json.loads(serve()("/api/auth/config")[2])
    assert body["exams"][0] == {"code": "1Z0-071", "database": "Oracle Database 19c"}
```

(Adapt `serve`, `sign_in` and `http` to the fixtures these test files already use.)

- [ ] **Step 2: Run** the two tests. Expected: they fail with a KeyError on 'engine' and 'exams'.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** `.venv/bin/python -m pytest -q`. Expected: everything passes.
- [ ] **Step 5: Commit:** `git commit -am "feat(api): exam, engine and home-note facts in the content and sign-in payloads"`

---

### Task 7: The exam picker

**Files:**
- Create: `src/oracle_lab/resources/static/js/ui/exam-picker.js`
- Modify:
  - `src/oracle_lab/resources/static/index.html:65-68` (replace the `.seg` group with `<div id="exam-picker"></div>` under the "Preparing for" label, keeping the label element's id);
  - `src/oracle_lab/resources/static/js/shell.js:36-58` (`renderExamSwitch` renders the picker; `switchExam` unchanged in behaviour);
  - `src/oracle_lab/resources/static/js/main.js:35-42` (global shortcuts skip events inside `.exam-picker`);
  - `src/oracle_lab/resources/static/css/shell.css:70-74` (picker styles; remove the old `.exam-switch .seg` rules);
  - `src/oracle_lab/resources/static/js/core/state.js:57` (remove `dbLabel`).

**Interfaces:**
- Consumes: `C.exams` (code → public dict with code, name, product, database, questions, minutes), `C.exam.code` (Task 6).
- Produces: `export function examPicker(host: HTMLElement, { exams: object[], current: string, onPick: (code) => void }): void`. It renders and wires the picker into `host`, replacing its content, and is idempotent across calls.

**Behaviour (the spec's builder call, as decided):**
- **Button:** `button.exam-picker-button` with `role="combobox"`, `aria-haspopup="listbox"`, `aria-expanded`, `aria-controls` and `aria-labelledby` (the "Preparing for" label id plus itself). It shows the current code (mono, 600) and, under it, its `database` label (small, muted), with a chevron.
- **List:** `ul[role=listbox]`, holding one `role="group"` per `product` (in registry order) labelled by a visible group heading. Each item is `li[role=option]` with `aria-selected` on the current one and a tick. An item shows the code and name, and a second line "{database}, {questions} questions, {minutes} min".
- **Open list placement:** the list is `position: fixed`, placed under the button from `getBoundingClientRect()`, or above it when there is no room below. It closes on outside pointerdown, on window resize, and on scroll of the rail. It must not be clipped by the scrolling rail.
- **Keyboard:**
  - Closed: Down, Up, Alt+Down, Enter and Space open it, with the active option = current.
  - Open: Up and Down move; Home and End jump; typing a character moves to the next option whose code or name starts with the typed prefix (500 ms buffer).
  - Enter or Space picks the active option. Escape closes it, with `stopPropagation` so the mobile drawer stays open. Tab closes it without picking. Focus returns to the button after a pick or close.
- **Picking:** picking the current exam only closes. Picking another calls `onPick(code)`, which is today's `switchExam` (the mock confirmation, the content reload and the toast all stay as they are).
- **Look:** in both themes it uses only existing tokens: `--paper`, `--paper-2`, `--rule`, `--ink`, `--muted`, `--link`, `--focus`, `--r-s`, `--r-m` and `--shadow-pop`. The keyboard focus ring is visible, and there's no animation beyond a 120 ms opacity fade, which is skipped with reduced motion.

- [ ] **Step 1: Implement** `exam-picker.js`, the shell, main and CSS changes above.
- [ ] **Step 2: Browser check** with a throwaway server and Playwright (see "Browser checks" below). Assert:
  - the picker shows "1Z0-071 / Oracle Database 19c" for a new user;
  - opening it shows one group "Oracle" with 2 options;
  - ArrowDown then Enter switches to 1Z0-171 (the toast "Now preparing for 1Z0-171." appears, Today's meta line shows 1Z0-171, and the mobile `#topbar-exam` text is 1Z0-171);
  - pressing "1" while the picker has focus on the Flashcards deck view does not rate a card (Review Focus 3);
  - at 390 px width, inside the opened drawer, Escape closes the list but not the drawer, and focus is on the picker button (Review Focus 4);
  - starting a mock exam, then picking the other exam, shows the "Switch to …?" dialog, and after switching back the mock resumes with its answered count unchanged (Review Focus 5);
  - there are no page errors and no CSP violations.
  - Take screenshots at 390, 1366 and 2560 px wide, in dark and light, with the list open, and review them.
- [ ] **Step 3: Run** `.venv/bin/python -m pytest -q`. Expected: everything passes (the CSP hash tests included).
- [ ] **Step 4: Commit:** `git add -A src/oracle_lab/resources/static && git commit -m "feat(ui): exam drop-down grouped by database product"`

---

### Task 8: Exam-specific words come from the payload

**Files:**
- Modify, in `src/oracle_lab/resources/static/`:
  - `js/core/state.js:59-60` (replace `blockedOn23ai` with `needsNewerDb`);
  - `js/views/cards.js:164-165`, `js/views/exercises.js:108`, `js/views/quiz.js:354,570-571`;
  - `js/views/home.js:13-18,140-143`, `js/views/settings.js:18,43,~48`;
  - `js/shell.js:72-80` (database status);
  - `js/views/lab.js:26`, `js/ui/sql.js:67`, `js/ui/editor.js:1,64-68`;
  - `js/auth/login.js`, `js/auth/register.js`, `js/auth/reset.js` (fill `.auth-about` from `/api/auth/config`).
- Test: `tests/test_exam_literals.py` (new)

**Interfaces:**
- Consumes: `C.engine`, `C.exam` (`database`, `database_env`, `versions`, `about`), `C.exams`, `C.home_notes`, `item.needs`, `DB.product` (Task 6); `/api/auth/config` `exams` (Task 6).
- Produces: `export const needsNewerDb = item => !!(item.needs && DB && DB.major < item.needs.major)` in `state.js`.

**Copy, verbatim** (`{…}` is interpolated and escaped with `esc`):
- **cards.js note:** "This sample needs {item.needs.label}, and your database is {DB.product} {DB.version}."
- **exercises.js callout:**
  - Shared start: "This exercise needs {needs.label}, and your database is {DB.product} {DB.version}."
  - Admin ending: " Set <code>{C.exam.database_env}</code> to give {C.exam.code} its own database (see the README)."
  - Others' ending: " {C.exam.code}'s SQL features need {needs.label}, which this server does not provide."
- **quiz.js badge:** "Runs on {needs.label} only". Its title: "{C.exam.code}'s SQL features need {needs.label}, which this server does not provide."
- **quiz.js:354:** "Every answer was checked against {C.engine.label}."
- **home.js warning:** it shows only when `DB && C.exam.versions[0] > DB.major`.
  - Shared start: "You are preparing for {code}, but the SQL lab is connected to {DB.product} {DB.version}. Quizzes and flashcards work as usual; SQL that needs {C.exam.database} won't run."
  - Admin ending: " Set <code>{C.exam.database_env}</code> to give {code} its own database (see the README)."
  - Others' ending: " This server does not provide {C.exam.database}."
- **home.js links:** they are rendered from `C.home_notes`: icon "doc" for the first and "notes" for the rest, `data-note=path`, `<strong>title</strong><span>blurb</span>`.
- **settings.js header:** "You are preparing for <b>{code}</b>, {name}. Switch exams at the top of the menu; progress is kept for each exam."
- **settings.js about section:** titled "About the exams". It has one paragraph per exam of `C.exams`: "<b>{code}</b> ({name}): {about}". The reset copy says "of every exam" instead of "of both exams".
- **Database status:** "{product} {major.minor} connected". Its title: "{dsn}, {product} {version}".
- **lab.js:26:** `{DB.product} {DB.version}`, falling back to "your database".
- **sql.js:67:** "Cannot connect to the database.\n{error}\n\nCheck that the database server is running."
- **editor.js:** the mode is `C.engine?.editor_mode || "text/x-sql"`, and the header comment becomes "SQL highlighting for the current exam's database engine".
- **Sign-in pages:** the `.auth-about` text becomes "Practice questions, flashcards and an SQL lab on your own database, for the {list} exams." Here {list} joins "{code} ({database})" with ", " and " and " before the last item. The static HTML text stays as the fallback when the fetch fails.

- [ ] **Step 1: Write the failing test** `tests/test_exam_literals.py`. It walks `src/oracle_lab` (`.py`, `.js` and `.css`; not `.html`, not `.md`, not `.sql`) and fails on any file outside the allowed set that contains "1Z0-071", "1Z0-171", "19c" or "23ai".
  - The allowed set is exactly: `exams.py`, `engines/oracle.py`, everything under `content/`, `analysis/error_hints.py`, `tools/validate_content.py` and `config.py`.
  - The failure message lists `file:line` for each hit.
- [ ] **Step 2: Run** `.venv/bin/python -m pytest tests/test_exam_literals.py -q`. Expected: it fails, listing state.js, home.js, settings.js, exercises.js, quiz.js, cards.js, provisioning/practice.py's docstring and any other leftovers.
- [ ] **Step 3: Implement** the copy above. Remove the remaining literals by rewording docstrings and comments generically (for example "the exam's own database").
- [ ] **Step 4: Run** `.venv/bin/python -m pytest -q`, then do a browser check (see below). In both exams, the Today guide links, the settings "About the exams", the database status text, the flashcard and exercise 23ai notes (on 1Z0-171 with a 19c database) and the sign-in about line all read as specified. There are no page errors.
- [ ] **Step 5: Commit:** `git commit -am "refactor(ui): exam and engine words from the server; no exam literals outside the registry"`

---

### Task 9: Docs — adding an exam

**Files:**
- Modify: `src/oracle_lab/content/AUTHORING.md` (a new section "Adding an exam"); `README.md` (one short paragraph pointing to it, and the drop-down replacing "switch" in any UI wording); `docs/docker.md` (mention that each exam's database key maps to `STUDY_DSN{_KEY}`, with 23ai as the example)

**Content of "Adding an exam"** (prose, about 25 lines):
1. **Registry entry:** add an `Exam` in `src/oracle_lab/exams.py`, with its fields explained.
2. **Content pack:** add a pack in `content/` (topics, sections, objectives, notes globs, home notes, items), or reuse a pack and tag items with `exams`.
3. **Database:** give the exam a database key. Its settings are `STUDY_DSN_<KEY>` and friends, and optionally the practice provisioner and gateway with the same suffix.
4. **New engine:** for a new database product, implement `engines.Engine` in `engines/<name>.py`, register it in `ENGINES`, and provide its sample tables and error explanations. Oracle's `engines/oracle.py` is the reference.
5. **Validate** with `oracle-lab validate` against that database, and `--exam CODE` for one exam.

- [ ] **Step 1: Write the docs.**
- [ ] **Step 2: Run** `.venv/bin/python -m pytest -q`. Expected: everything passes (no doc tests, a sanity check only).
- [ ] **Step 3: Commit:** `git commit -am "docs: how to add an exam or a database engine"`

---

## Browser checks (Tasks 7 and 8)

- **Throwaway server.** Start one on port 8098 with fresh data. Never use 8080 or 8071, which belong to the owner:

```bash
S=/tmp/claude-1000/-home-phubertstasiuk-PycharmProjects-oracle-learning-lab/4a5750f6-08dd-4084-b286-06e0edb91613/scratchpad
rm -rf $S/mx && mkdir $S/mx
(env STUDY_PORT=8098 STUDY_PUBLIC_URL=http://127.0.0.1:8098 STUDY_DATA_DIR=$S/mx .venv/bin/oracle-lab serve > $S/mx.log 2>&1 &)
```

- **Database.** It has no database, so the status reads "Database offline", and that's fine for the picker checks. For Task 8's database-status and 23ai-note checks, add `STUDY_DSN=localhost:1525/ORAPDB1 STUDY_PASSWORD_FILE=secrets/study_db_password` (the local 19c, read-only use; the first registered user is admin).
- **Playwright.** Use `PYTHONPATH=$S/pwlib` and `chromium.launch(executable_path="/usr/bin/google-chrome")`.
- **Accounts.** Registration is limited to 3 per IP per hour, so restart the server with fresh data when you need more accounts.
- **Stopping the server.** Find the pid with `ss -ltnpH "sport = :8098"` and kill it. Never use `pkill -f`.
