# Topic 11: Views, Sequences, Indexes and Synonyms

Environment: Oracle Database 19.3, schema ORASTUDY. Every result and error code below was
**executed** on 2026-10-17 against copies of the sample tables (`LAB_` objects, dropped afterwards).
Exam objectives: 11.1 indexes, 11.2 synonyms, 11.3 sequences, 13.1 views.

## Views (13.1)

A view is a stored query. It holds no rows, so dropping it never touches data.

```sql
CREATE [OR REPLACE] [FORCE | NOFORCE] VIEW name [(col, ...)] AS
SELECT ...
[WITH CHECK OPTION | WITH READ ONLY];
```

| Rule | Detail |
|---|---|
| Expressions need names | `SELECT salary * 12 FROM ...` in a view: **ORA-00998** (use an alias or a column list) |
| `ORDER BY` | Allowed in the defining query |
| `OR REPLACE` | Changes the query and keeps grants on the view; on a table name: **ORA-00955** |
| `ALTER VIEW` | Only `COMPILE` and view constraints. `ALTER VIEW v AS SELECT ...`: **ORA-00922** |
| `FORCE` | Creates the view even if a base table is missing; status `INVALID` |
| `NOFORCE` (default) | Missing table: **ORA-00942**, nothing created |
| `DROP VIEW v` | Dependent views stay but become `INVALID` (**ORA-04063** when queried); `DROP VIEW v CASCADE`: **ORA-00905** |

A FORCE view recompiles itself on first use once the table exists:

| Step | `USER_OBJECTS.STATUS` of the view |
|---|---|
| `CREATE FORCE VIEW lab_v AS SELECT * FROM lab_missing` | INVALID |
| `SELECT * FROM lab_v` | **ORA-04063**: view has errors |
| `CREATE TABLE lab_missing (id NUMBER)`, then `SELECT * FROM lab_v` | VALID, 0 rows |

### DML through views

A view row must map to exactly one base-table row. These make a view non-updatable
(**ORA-01732**: data manipulation operation not legal on this view):
`DISTINCT`, `GROUP BY` / group functions, `ROWNUM`, set operators.
Still updatable: `WHERE`, column aliases, `ORDER BY`.

| Through the view... | Result |
|---|---|
| UPDATE a column defined as `salary * 12` | **ORA-01733**: virtual column not allowed here |
| DELETE from that same view | Works (the row still maps to one table row) |
| Change a column of the non key-preserved table in a join | **ORA-01779** |
| INSERT a row outside a `WITH CHECK OPTION` filter | **ORA-01402** |
| Any DML on a `WITH READ ONLY` view | **ORA-42399** |

In a join `employees e JOIN departments d`, employees is *key-preserved* (each employee appears
at most once), so `SET salary = ...` works but `SET department_name = ...` fails with ORA-01779 on 19c.
(Oracle 21c relaxed this: it allows the update when each target row changes only once, and raises
ORA-30926 otherwise. The exam targets 19c.)

`WITH CHECK OPTION` also works on a subquery used as a DML target:

```sql
INSERT INTO (SELECT employee_id, last_name, hire_date, department_id
             FROM employees WHERE department_id = 30 WITH CHECK OPTION)
VALUES (900, 'Test', DATE '2024-01-01', 20);     -- ORA-01402
DELETE FROM (SELECT employee_id FROM employees WITH READ ONLY)
WHERE employee_id = 108;                          -- ORA-42399
```

The options are recorded as view constraints in `USER_CONSTRAINTS`: type `V` for CHECK OPTION,
type `O` for READ ONLY.

## Sequences (11.3)

`CREATE SEQUENCE s;` gives START WITH 1, INCREMENT BY 1, MINVALUE 1, MAXVALUE 28 nines,
NOCYCLE, CACHE 20 (`USER_SEQUENCES`: `CACHE_SIZE` 20, `CYCLE_FLAG` N).

| Statement | Result |
|---|---|
| `SELECT s.CURRVAL` before any `NEXTVAL` in the session | **ORA-08002** |
| `SELECT s.NEXTVAL a, s.CURRVAL b, s.NEXTVAL c FROM dual` (new sequence) | `1, 1, 1`: one increment per row |
| NOCYCLE sequence past MAXVALUE | **ORA-08004** |
| `START WITH 5 INCREMENT BY 5 MINVALUE 1 MAXVALUE 15 CYCLE NOCACHE` | 5, 10, 15, **1**: cycles to MINVALUE |
| `CREATE SEQUENCE s MAXVALUE 3 CYCLE` (default CACHE 20) | **ORA-04013**: CACHE must be less than one cycle |
| `ALTER SEQUENCE s START WITH 100` | **ORA-02283** |
| `ALTER SEQUENCE s MAXVALUE 20` when 50 was issued | **ORA-04009** |
| `ALTER SEQUENCE s INCREMENT BY 10 / CYCLE / CACHE 50` | Allowed, affects future values |
| `ALTER SEQUENCE s RESTART START WITH 1` | Allowed in 18c and later |

Where `NEXTVAL` / `CURRVAL` may appear: the select list of a top-level SELECT, `INSERT ... VALUES`,
the select list of `INSERT ... SELECT`, `UPDATE ... SET`, and a column `DEFAULT` (12c).
Not allowed (**ORA-02287**): `WHERE`, `DISTINCT`, `GROUP BY`, `ORDER BY`, set operators,
subqueries, view definitions.

Sequences are not transactional: a ROLLBACK does not give values back, so gaps are normal.

## Indexes (11.1)

| Kind | Syntax | Dictionary |
|---|---|---|
| B-tree (default) | `CREATE INDEX i ON t (col)` | `UNIQUENESS` NONUNIQUE |
| Unique | `CREATE UNIQUE INDEX i ON t (col)` | `UNIQUENESS` UNIQUE |
| Composite | `CREATE INDEX i ON t (department_id, salary)` | `USER_IND_COLUMNS.COLUMN_POSITION` 1, 2 |
| Function-based | `CREATE INDEX i ON t (UPPER(last_name))` | `INDEX_TYPE` FUNCTION-BASED NORMAL, expression in `USER_IND_EXPRESSIONS` |
| Invisible | `... INVISIBLE` or `ALTER INDEX i INVISIBLE` | `VISIBILITY` INVISIBLE; still maintained by DML |

- PRIMARY KEY and UNIQUE constraints create an index with the constraint's name. Foreign keys do not:
  `employees` has only `EMPLOYEES_PK` and `EMPLOYEES_EMAIL_UK`.
- A unique single-column index allows any number of NULLs (employee 108 and a new row may both have NULL email).
- Same columns in the same order again: **ORA-01408**. A different order is a different index.
- `DROP INDEX` on an index enforcing a PK/UK: **ORA-02429**. Drop the constraint instead.
- `DROP TABLE` drops its indexes and constraints; views and synonyms on it remain (INVALID).

## Synonyms (11.2)

```sql
CREATE [OR REPLACE] [PUBLIC] SYNONYM name FOR [schema.]object;
DROP [PUBLIC] SYNONYM name;
```

- Private synonyms need `CREATE SYNONYM`; public ones need `CREATE PUBLIC SYNONYM` (ORASTUDY: **ORA-01031**).
- A synonym is only an alias: it grants nothing.
- Targets: tables, views, sequences (`SELECT syn.NEXTVAL FROM dual` works), procedures, other synonyms.
  Not indexes, constraints or columns.
- The target is not checked at creation: `CREATE SYNONYM lab_g FOR lab_ghost` succeeds, using it
  raises **ORA-00980**: synonym translation is no longer valid.
- Synonyms share the namespace with tables, views and sequences: same name as your table: **ORA-00955**.
- Resolution of an unqualified name: your own schema first (including private synonyms), then public synonyms.

## Common traps

1. `ALTER VIEW` cannot change the query; use `CREATE OR REPLACE VIEW` (keeps grants).
2. Dropping a view or a synonym never affects data or the base table.
3. A view with an unaliased expression is an error, not an auto-named column.
4. `WITH CHECK OPTION` errors are ORA-01402; `WITH READ ONLY` errors are ORA-42399 in 19c.
5. CYCLE restarts at MINVALUE, not at START WITH.
6. `CURRVAL` is per session and needs a `NEXTVAL` first; two `NEXTVAL`s in one row return the same value.
7. START WITH cannot be altered; MAXVALUE cannot drop below the current value.
8. Foreign keys get no automatic index; UNIQUE does not mean NOT NULL.
9. An invisible index is still maintained by DML and can be made VISIBLE again; it is not dropped.
10. `CREATE SYNONYM` does not grant privileges and does not check the target.

> **Oracle vs. standard SQL / other databases**
>
> - Views, `WITH CHECK OPTION` and `CREATE VIEW` are standard SQL. `WITH READ ONLY`, `FORCE` and
>   `CREATE OR REPLACE VIEW` are Oracle extensions (PostgreSQL and MySQL also have `OR REPLACE`).
> - `CREATE SEQUENCE` is standard (SQL:2003), but the standard and PostgreSQL / SQL Server use
>   `NEXT VALUE FOR s` or `nextval('s')`; Oracle uses `s.NEXTVAL` and `s.CURRVAL`. MySQL has no
>   sequences (AUTO_INCREMENT). Oracle 12c also offers identity columns.
> - `CREATE INDEX` is not part of the SQL standard at all; every product has its own syntax.
>   Function-based indexes are called expression indexes in PostgreSQL.
> - Synonyms are Oracle (and SQL Server) specific; PostgreSQL uses `search_path` or views instead.

## More facts checked (2026-10-18, 19c and 23ai)

| Statement | Result |
|---|---|
| `CREATE SYNONYM s FOR employees` when `s` exists | **ORA-00955**; `CREATE OR REPLACE SYNONYM` retargets it |
| `ALTER SYNONYM s FOR departments` | **ORA-00922** (ALTER SYNONYM cannot change the target) |
| `DROP SYNONYM dict` (DICT is only public) | **ORA-01434**: private synonym to be dropped does not exist |
| `CREATE SYNONYM s FOR employees.last_name`, then use it | Created (read as schema EMPLOYEES, object LAST_NAME); use: **ORA-00980** |
| Table dropped, then re-created with the same name | Synonym INVALID meanwhile, works and becomes VALID again afterwards |
| `GENERATED ALWAYS AS IDENTITY`: explicit value (even NULL) / UPDATE | **ORA-32795** / **ORA-32796** |
| `GENERATED BY DEFAULT AS IDENTITY`: explicit NULL | **ORA-01400**; `BY DEFAULT ON NULL` fills it |
| Second identity column | **ORA-30669** |
| Identity column in the dictionary | `IDENTITY_COLUMN` YES, `NULLABLE` N, sequence `ISEQ$$_nnnnn` dropped with the table |
| `DEFAULT seq.NEXTVAL` after `DROP SEQUENCE seq` | Inserts fail with **ORA-02289** |
| `NEXTVAL` with `ORDER BY`, in an inline view, with `DISTINCT`, in `WHERE` | **ORA-02287** |
| `ADD CONSTRAINT ... UNIQUE (email)` when a non-unique index on email exists | Reuses that index (`INDEX_NAME`), no new index; `DROP INDEX` then **ORA-02429** |
| Second index on `(email)`, unique or not | **ORA-01408**; allowed if `INVISIBLE` (only one visible per column list) |
| `DROP PRIMARY KEY` / `DROP PRIMARY KEY KEEP INDEX` | Drops / keeps the index Oracle created for the key |
| `INSERT INTO (SELECT employee_id, last_name FROM employees)` | **ORA-01400** on hire_date |
| `WITH CHECK OPTION` view that does not show department_id, insert | **ORA-01402** (the column becomes NULL) |
| `DELETE` through `employees JOIN departments` | Deletes from employees (key-preserved) only |
| `CREATE OR REPLACE VIEW` without the CHECK OPTION | The view's type V constraint disappears |
| `CREATE VIEW v (a, b) AS SELECT one_column ...` | **ORA-01730** |
| `WHERE ROWNUM <= 3 ORDER BY salary` | ROWNUM first, then sort: wrong top-N; sort in an inline view |

## Oracle 23ai differences (1Z0-171)

Checked on Oracle 23ai Free (23.26), same ORASTUDY schema, `LAB_N11_` objects dropped afterwards.

- **`IF NOT EXISTS` / `IF EXISTS`**: `CREATE VIEW | SEQUENCE | INDEX | SYNONYM | TABLE IF NOT EXISTS`
  and `DROP ... IF EXISTS` work. In 19c they are syntax errors (ORA-00905, ORA-00933, ORA-00969).
- `IF NOT EXISTS` does nothing when the name exists, **even if the definition differs**:
  `CREATE INDEX IF NOT EXISTS i ON t (name)` after `i ON t (id)` keeps the old index;
  `CREATE SEQUENCE IF NOT EXISTS s START WITH 50` keeps the existing `s` (LAST_NUMBER 1).
- `CREATE OR REPLACE VIEW IF NOT EXISTS ...`: **ORA-11541** (REPLACE and IF NOT EXISTS cannot coexist).
- `SELECT s.NEXTVAL;` works without `FROM dual` (19c: ORA-00923).
- Updating a column of the non key-preserved table in a join view: **ORA-30926** when a row would be
  changed twice (19c: ORA-01779 always).
- Reworded messages, same codes: ORA-04013 "The CACHE value may not exceed the CYCLE value.",
  ORA-08002 "Sequence ... is not yet defined in this session."
- Annotations: `name VARCHAR2(20) ANNOTATIONS (display 'Name')` is listed in `USER_ANNOTATIONS_USAGE`
  (ANNOTATION_NAME `DISPLAY`, COLUMN_NAME `NAME`). Domains: `CREATE DOMAIN` appears in `USER_DOMAINS`,
  and `USER_TAB_COLUMNS` has a `DOMAIN_NAME` column. None of these exist in 19c (ORA-00942 / ORA-00904).
- Unchanged: synonym rules, identity columns, ORA-01408, ORA-02429, KEEP INDEX, CHECK OPTION and READ ONLY errors.
