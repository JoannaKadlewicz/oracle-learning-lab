# Grading SQL Against a Real Database

> I built a study app for the Oracle 1Z0-071 SQL exam that grades every exercise by running it on a real Oracle 19c database instead of comparing text. Then I pointed the same machinery at my own question bank, and it found answers I had written with confidence that Oracle disagreed with. This is how the grader works and what it caught.

## Why not compare text?

Comparing your SQL to a stored answer string does not work: two correct queries can look nothing alike (a join or a subquery, `NVL` or `COALESCE`). The only fair judge is the database.

So my 1Z0-071 app runs on a local Oracle 19c instance, in a learning schema with nine small tables. It has 116 graded exercises (labs): 79 query labs, 14 DML labs and 23 DDL labs. Each kind needs a different idea of "correct".

## Query labs: compare rows, not text

For a query lab, the server runs your SELECT and the reference solution on the same connection, then compares the two results. Before comparing, every value is turned into text, with NULL mapped to a marker that no real string can collide with:

```python
def normalize_rows(rows):
    return [tuple("\x00NULL" if v is None else str(v) for v in r) for r in rows]
```

A NULL never equals the string `'NULL'`, and the rows can be sorted, so they compare as a multiset: duplicates count, order does not. Order is checked only when the task asks for it, and the first failure decides the feedback:

```python
elif sorted(got) != sorted(want):
    passed = False
    ...
elif lab.get("ordered", True) and got != want:
    passed = False
    feedback.append("The right rows, but in the wrong order. Check ORDER BY and tie-breakers.")
```

Column count comes first, then row count, then the values as a multiset, then the order. Column names are deliberately not graded: if the values are right but your aliases differ, you pass with a note.

A failed lab also gets a row diff marking each row as correct, extra, missing, in the wrong position, or changed. A wrong row is paired with a missing one when at least half of their cells match, and only the differing cells are highlighted.

## DML labs: change the data, then look

An exercise like "give every Programmer a 10% raise" cannot be graded on the UPDATE statement itself. It is graded on what the data looks like afterwards. Each DML lab has a `check` query, and grading works like this:

1. Run your statements.
2. Run the check query and keep its rows.
3. Roll back.
4. Do the same with the reference solution, then compare the two check results like a query lab.

That only keeps the sample data intact if nothing commits, so DML labs accept INSERT, UPDATE, DELETE, MERGE, SAVEPOINT, ROLLBACK, SELECT and WITH, and refuse anything else before it runs.

## DDL labs: grade the data dictionary

DDL commits, so a rollback does not help. For "create a projects table with a primary key and a foreign key to departments", the check query reads the data dictionary instead: `USER_TAB_COLUMNS` for names, types and nullability, `USER_CONSTRAINTS` and `USER_CONS_COLUMNS` for the keys. The checks avoid constraint names, so whether you name a constraint or let Oracle call it `SYS_C...` does not matter.

Every object a lab creates must start with `LAB_`, and each DDL lab has a cleanup script that the validator only allows to drop `LAB_` objects. Cleanup runs before and after grading, so a half-finished attempt cannot break the next one.

## Making the checks trustworthy

A check query can be wrong in two quiet ways, and the content validator (`app/validate_content.py`) tests for both on every run.

First, it must be deterministic. The validator runs the reference solution twice and requires identical results. That catches checks that depend on sequence values, SYSDATE or system-generated names.

Second, doing nothing must not pass. The validator runs the cleanup, then the bare check query, and fails if the result already matches:

```python
before = query_or_error(conn, lab["check"])
if before == (columns, rows):
    errors.append(f"{label}: the check query gives the same result without the solution, so doing nothing passes")
```

## Letting the database check the questions too

The other half of the content is 453 multiple-choice questions, and whoever writes a question bank can be wrong. So questions have optional fields that make the database the judge:

- **`answer_sql`**: for "how many rows does this return?" questions. A query whose single value must equal the text of the correct option exactly.
- **`equivalent_sql`**: for "which two queries return the same result?" questions. The validator runs every option and checks that exactly the marked options return the same rows, as a multiset, as the reference query.
- **`try_sql` with `try_error`**: for "what error is raised?" questions. The statement must fail with exactly that ORA- code, and a `try_sql` without `try_error` must succeed. These run in a rolled-back transaction, and the validator rejects DDL and COMMIT in them.

Today 254 of the 453 questions are checked this way on every validator run: 141 with `answer_sql`, 43 with `equivalent_sql` and 70 with `try_error`.

## What execution caught

This is the part that convinced me the design was worth it. When the content was executed against Oracle 19c, these claims turned out to be wrong. All of them were fixed.

- **(+) inside an ANSI ON clause.** The question said `JOIN departments d ON e.department_id = d.department_id(+)` raises ORA-25156. On 19c it runs and acts as a left outer join. ORA-25156 comes from `(+)` in the WHERE clause of a query that also uses ANSI joins. The corrected question now ships with the statement that proves it:

  ```sql
  SELECT e.last_name, d.department_name FROM employees e JOIN departments d ON e.department_id = d.department_id(+);
  ```

- **UPDATE on USER_TABLES.** Running it gave ORA-02030 (can only select from fixed tables/views). The item now states that code and verifies it with `try_error`.
- **TRUNCATE of a parent table** succeeded in our 19c test once the child table was empty. It fails with ORA-02266 only while child rows reference it.
- **A failed DDL statement does not always commit.** A DDL that fails while executing (for example ORA-00955, name already used) still commits the pending transaction. One rejected for a syntax error commits nothing.
- **Several wrong ORA- codes** in the tables-and-constraints topic.
- **A question asked for the row count of a `COUNT(*)` query.** That is always one row, which was not what the question meant to test.
- **USER_ views can have an OWNER column**, and **DROP VIEW has a CASCADE CONSTRAINTS option**. The content had stated otherwise.

Each of these would have taught something false.

## The time zone problem: DPY-3022

The app uses python-oracledb in thin mode, so no Oracle client is needed. But thin mode cannot fetch a `TIMESTAMP WITH TIME ZONE` value that uses a region name such as `Europe/Warsaw`, and fails with DPY-3022. It also drops the offset of other time zone values, and does not convert `TIMESTAMP WITH LOCAL TIME ZONE` to the session time zone.

The fix lets the database do the formatting. The server parses each query and, if any column has a time zone type, wraps it so those columns come back as text:

```python
TEXT_FETCH_FORMATS = {
    oracledb.DB_TYPE_TIMESTAMP_TZ: "YYYY-MM-DD HH24:MI:SSXFF TZR",
    oracledb.DB_TYPE_TIMESTAMP_LTZ: "YYYY-MM-DD HH24:MI:SSXFF",
}
```

The wrapper is `SELECT TO_CHAR("COL", '<format>') AS "COL", ... FROM (<your query>)`. If wrapping fails, for example because of `FOR UPDATE` inside the inline view, the server falls back to the plain query. The grader compares exactly the text you see.

## What I would do next

- **Make privileges executable.** The privileges topic is mostly conceptual, because ORASTUDY cannot create users or roles. A second schema would let revoke cascading, roles and CREATE SESSION be verified the same way as everything else.
- **Review notes 1 to 8 by execution.** Notes for topics 9 to 14 were checked by running their examples. The first eight still need that pass.
- **Grow the question bank with the generator.** The app can now draft questions with Claude and run
  them through the same validator; only drafts whose answer Oracle confirms reach a review queue, and
  nothing enters the bank without a human accepting it. The next step is using it to fill thin objectives.

Since writing the first version of this, the validator also runs in CI against Oracle XE 21c in
Docker. That surfaced two genuine 19c/21c differences (21c raises ORA-30926 where 19c raises
ORA-01427 or ORA-01779), which the content now records per version instead of hiding.
