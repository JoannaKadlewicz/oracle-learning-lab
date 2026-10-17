# Topic 9: Managing Tables using DML Statements (and Transactions)

Environment: Oracle Database 19c, schema ORASTUDY. The results below were executed: DML on the
sample tables in rolled-back sessions, DDL experiments on temporary `LAB_` tables that were
dropped afterwards. Trigger, high-water-mark, locking and privilege remarks are documented
behavior (ORASTUDY cannot create triggers, and locking needs two sessions). Objectives 10.1–10.5 and 12.5.

## 10.1 INSERT, UPDATE and DELETE

| Statement | Result |
|---|---|
| `INSERT INTO departments VALUES (50, 'Legal', NULL)` | 1 row (no column list: every column, table order) |
| `INSERT INTO departments VALUES (60, 'Legal')` | **ORA-00947**: not enough values |
| `INSERT INTO departments (department_name, department_id) VALUES ('Audit', 70)` | 1 row (any column order) |
| `INSERT INTO employees (employee_id, last_name, email) VALUES (200, 'Novak', 'ANOVAK')` | **ORA-01400** (hire_date is NOT NULL, no default) |
| `UPDATE employees SET salary = 0 WHERE employee_id = 108` | **ORA-02290** check constraint violated |
| `UPDATE employees SET email = 'SKING' WHERE employee_id = 101` | **ORA-00001** unique constraint violated |
| `UPDATE employees SET department_id = 99 WHERE employee_id = 108` | **ORA-02291** parent key not found |
| `UPDATE employees SET salary = NULL WHERE employee_id = 108` | 1 row: a CHECK passes when it is UNKNOWN |
| `DELETE FROM customers WHERE customer_id = 1` | **ORA-02292** child record found |
| `DELETE FROM orders WHERE customer_id = 1` | 3 orders, and their 3 items via ON DELETE CASCADE (6 items left) |

- Omitted columns get their `DEFAULT`, else NULL. `INSERT ... SELECT` has no `VALUES` keyword.
- `SET col = (subquery)`: zero rows → NULL; more than one row → **ORA-01427**.
- Subqueries see the data as of the start of the statement (statement-level read consistency),
  so a correlated UPDATE does not see its own earlier row changes.

```sql
UPDATE employees e
SET    e.salary = e.salary * 1.05
WHERE  e.salary < (SELECT AVG(i.salary) FROM employees i WHERE i.department_id = e.department_id);
-- 4 rows: 105, 106 (dept 20) and 104, 107 (dept 30). Grant (no department) is not updated.
```

`DELETE FROM departments d WHERE d.department_id NOT IN (SELECT e.department_id FROM employees e)`
deletes **0** rows: the subquery contains a NULL, so NOT IN is never TRUE.

## 10.2 Multitable inserts

| Form | Behavior |
|---|---|
| `INSERT ALL INTO a ... INTO b ... SELECT` | unconditional: every INTO for every row |
| `INSERT ALL WHEN c1 THEN INTO ... WHEN c2 THEN INTO ... [ELSE INTO ...]` | every true WHEN |
| `INSERT FIRST WHEN ... [ELSE ...]` | only the first true WHEN; always conditional |

```sql
INSERT ALL
  INTO promotions (promo_id, promo_name, discount_pct) VALUES (department_id, department_name, 10)
  INTO promotions (promo_id, promo_name, discount_pct) VALUES (department_id + 100, department_name, 20)
SELECT department_id, department_name FROM departments;     -- 8 rows (4 x 2)
```

With tiers `salary >= 10000` / `salary >= 5000` / `ELSE`, INSERT FIRST put 3 rows in each tier;
INSERT ALL would have put the three top earners into the middle tier as well.
Restrictions: a view as target → ORA-01702; `NEXTVAL` in the subquery → ORA-02287 (in VALUES it
worked); `INSERT FIRST` without WHEN → ORA-00905. Remote tables are not allowed either (documented).

## 10.3 MERGE

```sql
MERGE INTO customers c
USING (SELECT 3 AS id, 'Initech' AS name, 4000 AS lim FROM dual
       UNION ALL SELECT 4, 'Umbrella', 1500 FROM dual
       UNION ALL SELECT 6, 'Stark', 2500 FROM dual) s
ON (c.customer_id = s.id)
WHEN MATCHED THEN UPDATE SET c.credit_limit = s.lim
                  DELETE WHERE c.credit_limit < 2000
WHEN NOT MATCHED THEN INSERT (customer_id, customer_name, credit_limit) VALUES (s.id, s.name, s.lim);
```

Result: 3 updated to 4000, 4 updated to 1500 and then **deleted** (DELETE WHERE tests the new
value), 6 inserted. Customer 5 (limit 1000) is untouched: it is not in the source.

- Either WHEN clause is optional; each may have its own `WHERE`.
- Updating an ON-clause column → **ORA-38104**.
- A target row matched by several source rows → **ORA-30926** (unable to get a stable set of rows).
  Aggregate the source first.

## 10.4 Transactions

- A transaction starts with the first DML statement and ends with COMMIT, ROLLBACK, or any
  DDL/DCL statement (implicit commit), or when the session ends.
- DDL commits **before** it runs, so even a failing `CREATE TABLE` (ORA-00955, name in use)
  committed the pending INSERT in our test, and so did `COMMENT ON TABLE`. A DDL with a syntax
  error (ORA-00907) did **not** commit. `ALTER SESSION`, `LOCK TABLE` and `SAVEPOINT` did not either.
- **Statement-level rollback:** a failing statement is undone completely; earlier work stays
  pending and the transaction stays open.

```sql
UPDATE employees SET salary = salary + 1000 WHERE employee_id = 100;   -- OK, pending
UPDATE employees SET salary = salary - 5000 WHERE department_id = 30;  -- ORA-02290 (107 would be -200)
-- King: 25000; department 30: 12000, 9000, 6000, 4800 (unchanged)
```

- Readers never wait and never see other sessions' uncommitted data; writers lock rows, and
  only a second writer of the **same row** waits.

## 10.5 Controlling transactions

```sql
UPDATE departments SET location = 'A' WHERE department_id = 10;
SAVEPOINT sp;
UPDATE departments SET location = 'B' WHERE department_id = 20;
SAVEPOINT sp;                         -- same name: the savepoint moves here
UPDATE departments SET location = 'C' WHERE department_id = 30;
ROLLBACK TO sp;                       -- 10 = A, 20 = B, 30 = Warsaw
```

- `ROLLBACK TO s1` keeps s1 and the transaction, but erases later savepoints:
  a following `ROLLBACK TO s2` raises **ORA-01086**.
- `ROLLBACK` (no TO) undoes everything and erases all savepoints. There is no partial COMMIT.

## 12.5 Truncating tables

| | DELETE | TRUNCATE |
|---|---|---|
| Kind | DML | DDL (implicit commit) |
| WHERE | yes | no |
| Rollback | yes, until COMMIT | no |
| DML triggers | fire | do not fire |
| Space | high-water mark stays | high-water mark reset |

- Parent table whose rows are referenced by child rows through an **enabled** foreign key:
  `TRUNCATE` → **ORA-02266**. (On our 19c database the same TRUNCATE succeeded once the child
  table was empty.)
- `TRUNCATE TABLE parent CASCADE` (12c+) truncated both tables when the FK was ON DELETE CASCADE;
  with a plain FK and child rows it failed with **ORA-14705**.
- Structure, constraints, indexes and grants remain. Another user's table needs DROP ANY TABLE.

## Common traps

1. `NOT IN` with a NULL in the subquery: the DELETE/UPDATE touches 0 rows.
2. Expecting a CHECK constraint to reject NULL (it does not; add NOT NULL).
3. INSERT FIRST vs INSERT ALL counts when WHEN conditions overlap.
4. Believing MERGE `DELETE WHERE` can remove rows that were not matched and updated.
5. Updating a column used in the MERGE ON clause (ORA-38104).
6. Thinking a failed statement rolls back the whole transaction (only the statement).
7. Any DDL in the middle of a transaction commits it and erases all savepoints, so a later
   `ROLLBACK TO` fails with ORA-01086.
8. TRUNCATE on a parent table with child rows fails (ORA-02266); DELETE would report ORA-02292.

> **Oracle vs. standard SQL / other databases**
> - Oracle has no autocommit in the database: a client (SQL Developer, SQL*Plus with
>   `SET AUTOCOMMIT ON`) may commit for you. PostgreSQL's psql and SQL Server default to autocommit.
> - DDL is transactional in PostgreSQL (can be rolled back); in Oracle it always commits.
> - `INSERT ALL` / `INSERT FIRST` are Oracle extensions. `MERGE` is SQL:2003; the
>   `DELETE WHERE` branch inside WHEN MATCHED is Oracle-specific.
> - Oracle treats `''` as NULL: inserting `''` into department_name raised ORA-01400.
> - `TRUNCATE ... CASCADE` exists in PostgreSQL too, but there it truncates referencing
>   tables regardless of ON DELETE rules.
