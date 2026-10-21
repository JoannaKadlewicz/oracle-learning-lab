# Writing study content

Content lives in one module per topic (`t01_basic_select.py` …), each with three lists:
`QUESTIONS`, `FLASHCARDS` and `LABS`. Every item has a `topic` (`t01`…`t14`) and an
`objective` from `objectives.py` (official 1Z0-071 numbering, for example `"7.4"`).

After every change run, from the repository root:

    .venv/bin/oracle-lab validate --coverage
    .venv/bin/python -m pytest -q

Both must pass. The validator runs your SQL against the ORASTUDY schema and rolls back.
`--topic t08` limits the database checks to one topic (much faster while authoring).

## Exam tracks (1Z0-071 and 1Z0-171)

The app prepares for two exams: **1Z0-071** (Oracle Database SQL, 19c behavior) and **1Z0-171**
(Oracle AI Database SQL Associate, 23ai behavior). Sections 1-16 belong to both; section 17
(topic `t15`, "SQL features new in 23ai") belongs to 1Z0-171 only.

- An item belongs to both exams unless it has `"exams": ["1Z0-071"]` (or `["1Z0-171"]`).
  Topic t15 items default to 1Z0-171.
- Mark an item `"exams": ["1Z0-071"]` when its answer is only true before 23ai (for example
  "GROUP BY on a column alias raises ORA-00904", which works in 23ai).
- If only the error code differs, keep it on both exams and add
  `"try_error_since": {"23": "ORA-03048"}`, and mention the 23ai code in the explanation.
- The validator checks 1Z0-171 items when connected to Oracle 23ai or later and 1Z0-071 items
  on older versions. Check against both databases:

      .venv/bin/oracle-lab validate --topic t15                                    # 19c
      STUDY_DSN=localhost:1522/FREEPDB1 STUDY_PASSWORD_FILE=~/.orastudy23_pwd \
          .venv/bin/oracle-lab validate --topic t15                                # 23ai

### Validating as a learner

Learners run in private schemas with only direct CREATE privileges and no roles (see
`LEARNER_GRANTS` in `provisioning/schemas.py`), so content must not depend on ORASTUDY's extra
privileges (for example the 23ai `DB_DEVELOPER_ROLE`). Validate once as a learner-equivalent user
too. As a privileged account create it (local dev databases only; keep the password in a file):

    CREATE USER oll_validate IDENTIFIED BY "<password>" QUOTA UNLIMITED ON USERS;
    GRANT CREATE SESSION, CREATE TABLE, CREATE VIEW, CREATE SEQUENCE, CREATE SYNONYM TO oll_validate;
    -- 23ai only, in addition:
    GRANT CREATE DOMAIN, CREATE PROCEDURE TO oll_validate;

Then, once to load the sample tables into that user and on later runs without `--reset`:

    STUDY_DSN=localhost:1522/FREEPDB1 STUDY_USER=oll_validate STUDY_PASSWORD_FILE=<file> \
        .venv/bin/oracle-lab validate --reset

## Adding an exam

An exam is one entry in the registry plus content and a database. Nothing outside the registry and
the content packs names an exam, so a new one needs no change outside these steps.

1. **Registry entry.** Add an `Exam` to `EXAMS` in `src/oracle_lab/exams.py`: `code`, `name`,
   `product` (the group in the exam drop-down), `engine` (a key of `ENGINES`), `database` (the
   database key, see 3), `database_label`, `fallback` (the database key of another exam of the same
   engine, or `None`; if the exam's own database is not configured it runs on the fallback key's
   database, so 1Z0-171 uses the default database until `STUDY_DSN_23AI` is set), `versions`
   (engine major versions the exam covers, minimum inclusive and maximum exclusive, `None` for no
   maximum), `pack`, `questions`, `minutes`, `passing_pct` and `about`. `DEFAULT_EXAM` is the exam
   shown when nothing is chosen. `exams.problems()` reports registry mistakes (a missing default, an
   unknown engine, a database key shared by two engines, a bad fallback), and a test runs it.
2. **Content pack.** Add a `Pack` to `PACKS` in `content/__init__.py` with its topics, sections,
   objectives, `notes` globs, `home_notes` (the notes the home page links to) and the items, then
   set the exam's `pack` to its id. Topic, section, objective, question, flashcard and lab ids must
   be unique across all packs, since the app looks them up across packs: prefix a new pack's ids,
   for example topics `pg01`, `pg02`. `oracle-lab validate --static` reports an id two packs share.
   Built-in notes are found in the notes directory under `docs/*.md` and `topics/*/*.md` or
   `topics/*/*.sql`; a pack's `notes` globs, relative to the notes directory, narrow that to the
   pack's own notes. To reuse a pack, leave it alone and tag items with `"exams": [...]`. Use
   `topic_exams` and `section_exams` for topics and sections that belong to some of the pack's exams
   only, and `topic_needs` for a topic whose items need a database version
   (`{"major": 23, "label": "Oracle 23ai"}`). An item belongs to every exam of its pack unless its
   own `exams` list or its topic's `topic_exams` narrows it.
3. **Database.** Every exam names a database key. `default` is the primary database and uses
   `STUDY_DSN`, `STUDY_USER` and `STUDY_PASSWORD[_FILE]`. Any other key adds its upper-case form as
   a suffix: key `23ai` reads `STUDY_DSN_23AI`, `STUDY_USER_23AI` and `STUDY_PASSWORD_23AI[_FILE]`.
   `STUDY_USER_<KEY>` and `STUDY_PASSWORD_<KEY>` default to the primary database's user and
   password. The key is used only when its `STUDY_DSN` is set. Otherwise the exam runs on its
   fallback key's database, and an exam with neither shows the database as not set up. Private
   practice schemas take the same suffix on `STUDY_PROVISIONER_USER`,
   `STUDY_PROVISIONER_PASSWORD[_FILE]`, `STUDY_GATEWAY_USER`, `STUDY_GATEWAY_PASSWORD[_FILE]`,
   `STUDY_PRACTICE_TABLESPACE` and `STUDY_PRACTICE_QUOTA_MB`.
4. **New engine.** An exam for another database product needs an engine. Implement `engines.Engine`
   (and its `Provisioner`) in `engines/<name>.py`, register an instance in `ENGINES` in
   `engines/__init__.py`, and provide the product's sample tables and error explanations.
   `engines/oracle.py` is the reference. The database checks of `oracle-lab validate` are
   Oracle-only today, so a new engine must also add validator support. A second engine will also
   meet these places that still assume Oracle: `provisioning/practice.py` names practice schemas
   with Oracle's `schema_name()`; the `Database` protocol and `session()` in
   `database/connection.py` are typed to `oracledb.Connection`; and the SQL lab's help line tells
   learners to end PL/SQL blocks with a line holding only `/`. An exam for a product that already
   has an engine needs none of this.
5. **Validate.** Run `oracle-lab validate` against the exam's database. It picks the exams to check
   from the connected database: those whose engine and `versions` match its version. `--exam CODE`
   checks one exam's items only, on that exam's own database (else its fallback's), and warns when
   the database's version is outside the exam's `versions`. Run it once per database, as in the
   1Z0-071 and 1Z0-171 example above.

## Ground rules

- **Original material only.** Never copy or paraphrase real exam questions or dumps.
- **Oracle Database 19c behavior.** If 23ai differs, say so in the explanation.
- **Verify everything you can by running it.** Use the database, not memory, for every result,
  row count, error code and output format. If a claim cannot be run (privileges across users,
  external tables, recycle bin settings) state only behavior you are certain of, as documented
  by Oracle.
- **Explanations teach.** Say why the right answer is right *and* why each tempting
  distractor is wrong. Two to four sentences. Mention the ORA- code when an error is involved.
- **Distractors are plausible.** Each wrong option should match a real misconception
  (another database's behavior, a confused rule, an off-by-one count).
- Match the style of the existing items: `e.` aliases, uppercase keywords, `DATE '2024-01-31'` literals.

## Questions

    {
        "id": "q06-short-name",          # q<topic number>-<kebab name>, unique
        "topic": "t06",
        "objective": "7.4",
        "prompt": "How many rows does this query return?",
        "code": "SELECT ...\nFROM ...;",  # optional, shown as a code block
        "options": ["3", "4", "5", "9"],  # 2 to 8 options; shuffled when shown
        "answer": [1],                    # indexes of correct options
        "explanation": "...",
        "try_sql": "SELECT ...;",         # optional: runnable demo for the SQL lab
        "try_error": "ORA-00979",         # only if try_sql is meant to fail
        "answer_sql": "SELECT COUNT(*) FROM (...)",   # optional, see below
        "equivalent_sql": "SELECT ...",               # optional, see below
    }

- Multi-answer questions must say how many: "Which two statements are true?" with two answers.
  The exam uses many "choose two/three" items; aim for about 40% multi-answer.
- `try_sql` may only use SELECT, WITH, INSERT, UPDATE, DELETE, MERGE, SAVEPOINT and ROLLBACK
  (no DDL, no COMMIT). It runs in a transaction that is rolled back.
- **`answer_sql`** makes the answer database-verified: a query returning one row with one column
  whose text must equal the correct option exactly. Use it for every "how many rows / what is
  returned" question where the option is a single value. For example, options
  `["2", "3", "4", "5"]` with `"answer_sql": "SELECT COUNT(*) FROM (<the query>)"`.
- **`equivalent_sql`** makes "which queries return the same result" questions database-verified:
  options are queries, and the validator checks that exactly the `answer` options return the
  same rows (as a multiset) as `equivalent_sql`. Options that fail count as not equivalent.
- Question types to mix: predict the output, which error is raised, which statements are true,
  which queries are equivalent, which statement fixes the error, which clause is evaluated first.

## Flashcards

    {"id": "c123", "topic": "t06", "objective": "7.4", "front": "Question?", "back": "Answer."}

    {"id": "c124", ..., "try_sql": "SELECT ROUND(1234.5, -2) FROM dual;"}   # optional

IDs are `c` plus three or four digits and never change once published (progress is stored by ID).

`try_sql` (optional) is the sample loaded into the SQL editor beside the card, so the rule on
the card can be tried at once. Same rules as a question's `try_sql`: SELECT, WITH, DML,
SAVEPOINT and ROLLBACK only, rolled back after the run, and `try_error` (plus
`try_error_since`) when the sample is meant to fail. Add it whenever the card states something
a statement can show (a function, a clause, NULL handling, an error); keep the sample short,
on the sample tables or `dual`, with a `--` comment saying what to look at. Leave it out for
cards about theory (the editor then starts empty).
The app shows each statement's `--` comment as the heading of its step in the results, and an
error matching `try_error` (or a code named in that comment) as expected, so put a comment
before each statement that shows something different. Long one-line statements are broken
before FROM, WHERE and the other main clauses in the editor; write them on one line or format
them yourself.

For a card about DDL, the sample may create and change its own objects, named after the card
(`lab_c055_emp` for card c055), when the card also has a `cleanup` that drops all of them:

    {"id": "c055", ...,
     "try_sql": "CREATE TABLE lab_c055_emp AS SELECT * FROM employees;\nSELECT ... FROM user_constraints ...;",
     "cleanup": "DROP TABLE lab_c055_emp PURGE;"}

The app runs the cleanup before and after every run of the sample, so it can be run again.
DDL commits, including any DML before it, so DML in such a sample may only change the card's
own tables. The validator runs the sample between two cleanups and fails it if anything else
in the schema or the sample data changed, or one of its objects is left behind.
Use only the ID range you were given. New cards of topic tNN use `c(1000 + NN * 50)` to
`c(1049 + NN * 50)`: t01 c1050-c1099, t02 c1100-c1149, ... t15 c1750-c1799.

## Labs (graded exercises)

Every lab needs `hint`, and should have `hint2`: a stronger hint shown before the solution.
The task must fully specify the result: columns, filters, and row order.

**`query`** (default): one SELECT, graded on its rows.

    {"id": "lab-short-name", "topic": "t06", "objective": "7.4", "title": "...", "task": "...",
     "columns": "department_name, headcount",   # must match the solution's column names
     "ordered": True,                           # True: row order is graded (solution needs ORDER BY)
     "solution": "SELECT ...", "hint": "...", "hint2": "..."}

**`dml`**: DML statements, graded on the result of `check` afterwards, then rolled back.
Only INSERT, UPDATE, DELETE, MERGE, SAVEPOINT, ROLLBACK, SELECT and WITH are allowed.
Use it for DML, MERGE, multi-table inserts, correlated UPDATE/DELETE and savepoints.

    {"id": "lab-...", ..., "kind": "dml",
     "solution": "UPDATE ...;\nDELETE ...;",
     "check": "SELECT ... FROM employees e ORDER BY e.employee_id"}   # needs ORDER BY

**`ddl`**: any statements, graded on `check` (usually over USER_TAB_COLUMNS, USER_CONSTRAINTS,
USER_INDEXES, USER_SEQUENCES, USER_VIEWS, USER_TAB_PRIVS_MADE …). DDL commits, so `cleanup`
drops the lab's objects before and after grading.

    {"id": "lab-...", ..., "kind": "ddl",
     "solution": "CREATE TABLE lab_projects (...);",
     "check": "SELECT ... FROM user_tab_columns WHERE table_name = 'LAB_PROJECTS' ORDER BY ...",
     "cleanup": "DROP TABLE lab_projects PURGE;"}

- Object names created by labs must start with `LAB_` and be unique across all content
  (search `src/oracle_lab/content` before choosing one). Cleanup may only drop `LAB_` objects.
- The check must not depend on system-generated names (`SYS_C…`), sequence values, or
  SYSDATE: the validator runs the solution twice and requires identical results.
- The check must give a different result without the solution, so doing nothing cannot pass.
- See `lab-programmer-raise` (t09) and `lab-create-projects` (t10) for complete examples.

**"Fix the bug" exercises** (`query` and `dml` labs): add `"starter"`, a broken or almost-right
statement that the editor opens with. The task describes the intended result; the learner finds
and fixes the mistake (a classic exam trap: NOT IN with NULLs, a missing join condition, WHERE
instead of HAVING, a wrong format model...). The validator checks that the starter does not
already pass. Start the title with "Fix:".

## The sample schema

Tables: departments, employees, customers, products, orders, order_items, salary_grades,
events (time zones and intervals) and promotions (always empty). The edge cases built into the
data are listed at the top of `src/oracle_lab/resources/sql/02_seed_data.sql`. Never change the sample data or the
scripts in `src/oracle_lab/resources/sql/`: existing answers depend on them.

Database safety while authoring:
- Experiment with `server.run_script(sql)` (rolled back) or a connection you roll back.
- Never COMMIT changes to the sample tables, never run DDL on them, never reset the schema.
- Drop any `LAB_` objects you create while experimenting.
