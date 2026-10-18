# Topic 10: Use DDL to Manage Tables and Their Relationships

Environment: Oracle Database 19c, schema ORASTUDY. The results and error codes below were
executed with temporary `LAB_` tables that were dropped afterwards (DDL commits, so the
sample tables were never altered). The recycle bin / FLASHBACK lines are documented behavior. Objectives 12.1–12.4 and 12.6–12.8 (12.5 TRUNCATE is in
topic 9). External tables (12.7) cannot be created by ORASTUDY (no directory privileges), so
that section is documented behavior only.

## 12.1 Describing and working with tables

- Unquoted names: start with a letter; letters, digits, `_`, `$`, `#`; up to 128 bytes (19c);
  not a reserved word; stored in **uppercase**. `lab_t10_x$h` works; `lab_t10-x` → ORA-00922,
  `order` → ORA-00903, a name starting with a digit → error.
- Quoted names keep their case: after `CREATE TABLE "Staff"`, `SELECT * FROM staff` → **ORA-00942**;
  and so does `"STAFF"`; only `"Staff"` works.
- `DESCRIBE t` (SQL*Plus) / `USER_TAB_COLUMNS` show columns, types and nullability.
- `ALTER TABLE t READ ONLY`: SELECT and DROP work; INSERT, DELETE, TRUNCATE → **ORA-12081**.
- `DROP TABLE t` moves t to the recycle bin (`FLASHBACK TABLE t TO BEFORE DROP`);
  `DROP TABLE t PURGE` does not. A table referenced by a foreign key → **ORA-02449**,
  unless `CASCADE CONSTRAINTS` (drops the foreign key constraints, not the child rows).

## 12.2 Columns and data types

| Type | Notes |
|---|---|
| `VARCHAR2(n)` | size required (else ORA-00906); max 4000 bytes (32767 with MAX_STRING_SIZE=EXTENDED) |
| `CHAR(n)` | fixed, blank-padded; default size 1; max 2000 bytes |
| `NUMBER(p,s)` | p digits in total, s after the point; plain `NUMBER` = any value |
| `DATE` | date + time to the second; `TIMESTAMP(n)` adds fractional seconds |
| `CLOB`, `BLOB` | LOBs: no ORDER BY / GROUP BY / comparison (ORA-00932) |
| `LONG` | legacy; one per table (ORA-01754) |

| Expression | Result |
|---|---|
| `CAST(12.345 AS NUMBER(5,2))` | `12.35` (rounded) |
| `CAST(1250.5 AS NUMBER(5,-2))` | `1300` (negative scale rounds to hundreds) |
| `commission_pct NUMBER(3,2)` set to 10 | **ORA-01438** (max 9.99) |
| `country_code CHAR(2)` set to `'USA'` | **ORA-12899** value too large (never truncated) |

`ALTER TABLE ... MODIFY`: widening always works; narrowing works only if all values fit
(**ORA-01441**); changing the type needs an empty column (**ORA-01439**, even for `'123'`).

## 12.3 Creating tables

```sql
CREATE TABLE lab_projects (
    project_id     NUMBER(6)    CONSTRAINT lab_projects_pk PRIMARY KEY,           -- column level
    project_name   VARCHAR2(40) NOT NULL,
    status         VARCHAR2(10) DEFAULT 'NEW',
    department_id  NUMBER(4)    REFERENCES departments (department_id),
    CONSTRAINT lab_projects_uk UNIQUE (project_name, department_id)                -- table level
);
```

- A multi-column key must be out of line; two inline `PRIMARY KEY` clauses → **ORA-02260**.
- `DEFAULT` applies only when the column is omitted: an explicit NULL is stored as NULL
  (use `DEFAULT ON NULL`, 12c+). `MODIFY (status DEFAULT 'OPEN')` changes future inserts only.
  A default cannot reference another column (**ORA-00904**).
- **CTAS** copies columns, data and explicit NOT NULL constraints only (no PK, UNIQUE, CHECK,
  FK, indexes). `WHERE 1 = 2` copies just the structure. Expressions need an alias:
  `SELECT e.salary * 12 FROM ...` → **ORA-00998**.

## 12.4 Dropping columns and SET UNUSED

```sql
ALTER TABLE t DROP COLUMN notes;             -- one column
ALTER TABLE t DROP (notes, fax);             -- several: parentheses, no COLUMN keyword
ALTER TABLE t SET UNUSED (notes);            -- fast, irreversible, hidden from USER_TAB_COLUMNS
ALTER TABLE t DROP UNUSED COLUMNS;           -- reclaim space later
```

- `DROP COLUMN a, b` → ORA-00933; `DROP COLUMNS (a, b)` → ORA-02000. The last column cannot be dropped (**ORA-12983**).
- A referenced key column needs `CASCADE CONSTRAINTS` (**ORA-12992** otherwise).
- Unused columns are counted in `USER_UNUSED_COL_TABS`; their names can be reused.

## 12.6 Temporary tables

| | Global temporary table | Private temporary table (18c+) |
|---|---|---|
| Definition | permanent, shared | session only, in memory |
| Name | any | prefix `ORA$PTT_` (parameter PRIVATE_TEMP_TABLE_PREFIX) |
| Default | `ON COMMIT DELETE ROWS` (DURATION `SYS$TRANSACTION`) | `ON COMMIT DROP DEFINITION` |
| Option | `ON COMMIT PRESERVE ROWS` (`SYS$SESSION`) | `ON COMMIT PRESERVE DEFINITION` |
| Dictionary | `USER_TABLES.TEMPORARY = 'Y'` | `USER_PRIVATE_TEMP_TABLES` |

After inserting 3 rows into each GTT and committing: DELETE ROWS table 0 rows, PRESERVE ROWS
table 3 rows. Data is always private to the session; indexes on a GTT are allowed.

## 12.7 External tables (documented behavior, not executed)

```sql
CREATE TABLE ext_sales (id NUMBER, amount NUMBER)
ORGANIZATION EXTERNAL (
  TYPE ORACLE_LOADER               -- or ORACLE_DATAPUMP
  DEFAULT DIRECTORY data_dir       -- a DIRECTORY object (needs CREATE ANY DIRECTORY to create)
  ACCESS PARAMETERS (FIELDS TERMINATED BY ',')
  LOCATION ('sales.csv'))
REJECT LIMIT UNLIMITED;
```

Read-only: no DML, no indexes, no enforced keys. The file is read at query time; copy the data in
with CTAS or INSERT ... SELECT.

## 12.8 Managing constraints

| Constraint | Allows NULL? | Notes |
|---|---|---|
| `NOT NULL` | no | column level only; add later with `MODIFY (c NOT NULL)` |
| `UNIQUE` | yes, many NULLs | creates/uses a unique index |
| `PRIMARY KEY` | no | one per table; UNIQUE + NOT NULL |
| `FOREIGN KEY` | yes | references a PK or UNIQUE key; `ON DELETE CASCADE / SET NULL` |
| `CHECK` | passes when UNKNOWN | no SYSDATE, USER, sequences or subqueries |

- `ALTER TABLE t ADD CONSTRAINT n NOT NULL (c)` → ORA-00904; `ADD (c NOT NULL)` → ORA-02263; use
  `MODIFY (c NOT NULL)` or `MODIFY c CONSTRAINT n NOT NULL`.
- Existing duplicates: `ADD PRIMARY KEY` → **ORA-02437**.
- `ENABLE NOVALIDATE` checks only new DML: `CHECK (id > 5) ENABLE NOVALIDATE` was accepted on
  rows with id 1, and then `INSERT ... VALUES (2)` failed with ORA-02290. `ENABLE` alone means VALIDATE:
  re-enabling it after a DISABLE failed with ORA-02293.
- Disabling a referenced PK: **ORA-02297**; `DISABLE PRIMARY KEY CASCADE` also disabled the FK.
- `CHECK (d > SYSDATE)` → **ORA-02436**. `DROP TABLE parent` → **ORA-02449**; with `CASCADE CONSTRAINTS`
  the child table stayed, only its FK constraint was dropped.
- Errors: ORA-00001 unique, ORA-01400 NULL into NOT NULL, ORA-02290 check, ORA-02291 parent
  missing, ORA-02292 children exist.

## Common traps

1. Defining NOT NULL out of line, or adding it with `ADD CONSTRAINT`.
2. Expecting CTAS to copy the primary key, CHECKs or indexes.
3. Forgetting the alias for an expression in CTAS (ORA-00998).
4. `DROP COLUMN a, b` instead of `DROP (a, b)`.
5. Believing an explicit NULL takes the DEFAULT value.
6. Expecting Oracle to truncate a too-long string or cap a too-large number.
7. Changing a column's type while it holds data (ORA-01439), even if the values would convert.
8. Thinking ON COMMIT PRESERVE ROWS makes GTT rows visible to other sessions.
9. Mixing up ORA-02291 (child without parent) and ORA-02292 (parent with children).

> **Oracle vs. standard SQL / other databases**
> - Oracle `VARCHAR2` and `''` = NULL are Oracle-specific; standard SQL uses `VARCHAR`.
> - Oracle uses `ALTER TABLE ... MODIFY`; PostgreSQL uses `ALTER COLUMN ... TYPE / SET NOT NULL`,
>   and SQL Server uses `ALTER COLUMN`.
> - DDL commits in Oracle, so `CREATE`/`ALTER`/`DROP` cannot be rolled back (PostgreSQL can).
> - Global temporary tables follow the SQL standard; private temporary tables, `SET UNUSED`,
>   `READ ONLY` tables and the recycle bin are Oracle-specific.
> - Oracle has no `ON UPDATE CASCADE` for foreign keys (MySQL and PostgreSQL do).

## More verified results (19c and 23ai)

- Private temporary tables: no constraints (even NOT NULL), no DEFAULT, no index → **ORA-14451**;
  CTAS works; a name without `ORA$PTT_` → ORA-00903; a GTT named `ora$ptt_...` → ORA-32463;
  `ON COMMIT DELETE ROWS` → ORA-00901. Creating one did **not** commit a pending INSERT, and the
  following ROLLBACK also dropped the table (DROP DEFINITION).
- Global temporary tables: a foreign key → **ORA-14455** (PK and CHECK are fine). While sessions have
  rows: `ALTER TABLE ... ADD` → ORA-14450, `DROP` → ORA-14452. `TRUNCATE` removes only your rows.
- External tables: a missing DIRECTORY object fails at CREATE (**ORA-06564**); a PRIMARY KEY → ORA-30657.
- `DROP COLUMN` / `SET UNUSED` of a column in a multi-column PK or CHECK → **ORA-12991**;
  `CASCADE CONSTRAINTS` drops the whole constraint. A parent key column → ORA-12992. A READ ONLY
  table → ORA-12081. Dropping a column drops its single-column index.
- After `SET UNUSED (note)`: `ADD (note DATE)` works, `DROP COLUMN note` → ORA-00904, USER_TAB_COLS
  shows a hidden `SYS_C00002_...$` column. A later `DROP COLUMN` of any column also removed the
  unused columns (USER_UNUSED_COL_TABS was empty afterwards).
- `PRIMARY KEY DEFERRABLE INITIALLY DEFERRED`: two equal keys inserted fine, `COMMIT` → **ORA-02091**
  and the table was empty; `SET CONSTRAINT ... IMMEDIATE` → ORA-00001 but the rows stayed. The
  key's index is NONUNIQUE. `SET CONSTRAINT` on a non-deferrable constraint → ORA-02447;
  `MODIFY CONSTRAINT ... DEFERRABLE` is a syntax error (deferrability is fixed at creation).
- `pid NOT NULL REFERENCES parent ON DELETE SET NULL`: deleting a parent with children → ORA-01407.
- FK to a column without a PK/UNIQUE → ORA-02270; to a column of another type → ORA-02267.
  `ON UPDATE CASCADE` / `ON DELETE RESTRICT` do not exist (syntax error). LOB in PK/UNIQUE → ORA-02329.
- Identity: `GENERATED ALWAYS` → ORA-32795 on INSERT, ORA-32796 on UPDATE; `BY DEFAULT` with an
  explicit NULL → ORA-01400; `BY DEFAULT ON NULL` fills it; a second identity column → ORA-30669.
- CTAS: `(id PRIMARY KEY, name) AS SELECT ...` works; data types in the list → ORA-01773; wrong number
  of names → ORA-01730. Defaults and identity are not copied; NOT NULL (also implied by DEFAULT ON NULL
  or identity) is.

## Oracle 23ai differences (1Z0-171)

Verified on Oracle 23ai Free (23.26) with temporary `LAB_N10_` tables; everything else in this topic
(temporary tables, deferrable constraints, ORA-12991, identity columns, CTAS rules) behaved as on 19c.

| 23ai | 19c |
|---|---|
| `CREATE TABLE IF NOT EXISTS t (...)` when t exists: no error, the **old definition is kept** (the new column list is ignored); the statement still commits | ORA-00922 |
| `DROP TABLE IF EXISTS t PURGE` when t is missing: no error | ORA-00933 |
| `flag BOOLEAN DEFAULT FALSE`; inserting `'yes'` stored TRUE | ORA-00904 at CREATE |
| `b NUMBER DEFAULT ON NULL FOR INSERT AND UPDATE 7`: an UPDATE to NULL stores 7 (USER_TAB_COLUMNS.DEFAULT_ON_NULL_UPD) | ORA-00936; DEFAULT ON NULL covers INSERT only |
| USER_TAB_COLUMNS.DATA_DEFAULT_VC: the default as VARCHAR2 (DATA_DEFAULT is a LONG) | column does not exist |

- Up to 4096 columns per table only with the initialization parameter `MAX_COLUMNS = EXTENDED`.
  Our 23ai database has the default `STANDARD`, and a 1001-column table failed with ORA-01792 exactly
  as on 19c.
- Not in this release: `ALTER TABLE t ADD IF NOT EXISTS (...)` (ORA-02000), `DROP COLUMN IF EXISTS`
  (ORA-03048) and `CREATE OR REPLACE TABLE` (ORA-00922).
- New codes for some syntax errors: `ON UPDATE CASCADE` → ORA-02000 (19c ORA-00905);
  `MODIFY CONSTRAINT ... DEFERRABLE` → ORA-03049 (19c ORA-00933). Messages for ORA-00001 and ORA-00942
  now name the table (and columns).
