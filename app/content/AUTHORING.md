# Writing study content

Content lives in one module per topic (`t01_basic_select.py` …), each with three lists:
`QUESTIONS`, `FLASHCARDS` and `LABS`. Every item has a `topic` (`t01`…`t14`) and an
`objective` from `objectives.py` (official 1Z0-071 numbering, for example `"7.4"`).

After every change run, from the repository root:

    .venv/bin/python app/validate_content.py --coverage
    .venv/bin/python -m pytest -q app/tests

Both must pass. The validator runs your SQL against the ORASTUDY schema and rolls back.

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

IDs are `c` plus three digits and never change once published (progress is stored by ID).
Use only the ID range you were given.

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
  (search `app/content` before choosing one). Cleanup may only drop `LAB_` objects.
- The check must not depend on system-generated names (`SYS_C…`), sequence values, or
  SYSDATE: the validator runs the solution twice and requires identical results.
- The check must give a different result without the solution, so doing nothing cannot pass.
- See `lab-programmer-raise` (t09) and `lab-create-projects` (t10) for complete examples.

## The sample schema

Tables: departments, employees, customers, products, orders, order_items, salary_grades,
events (time zones and intervals) and promotions (always empty). The edge cases built into the
data are listed at the top of `app/sql/02_seed_data.sql`. Never change the sample data or the
scripts in `app/sql/`: existing answers depend on them.

Database safety while authoring:
- Experiment with `server.run_script(sql)` (rolled back) or a connection you roll back.
- Never COMMIT changes to the sample tables, never run DDL on them, never reset the schema.
- Drop any `LAB_` objects you create while experimenting.
