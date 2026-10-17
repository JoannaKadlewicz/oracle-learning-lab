# Topic 1: Relational Concepts and the Basic SELECT

Environment: Oracle Database 19c, schema ORASTUDY. Every result shown below was
**executed** against the sample data (rolled back, nothing changed). SQL*Plus formatting
(column widths, blank for NULL) is client display, not stored data.

## 1.1 Relational database concepts

| Logical model (ERD) | Relational / SQL | Physical storage |
|---|---|---|
| Entity | Table | Segment in a tablespace |
| Attribute | Column (one data type) | Bytes in data blocks |
| Instance | Row (no guaranteed order) | Row piece with a ROWID |
| Unique identifier | Primary key (UNIQUE + NOT NULL, one per table) | Usually a unique index |
| Relationship | Foreign key (matches a parent key or is NULL) | — |

- Relationships are stored as **values**, not pointers: `employees.department_id = departments.department_id`.
- A foreign key may be NULL (employee 108 Grant has no department). A value with no parent fails:

```sql
INSERT INTO employees (employee_id, last_name, hire_date, department_id)
VALUES (900, 'Novak', DATE '2024-01-10', 99);
-- ORA-02291: integrity constraint (ORASTUDY.EMPLOYEES_DEPARTMENT_FK) violated - parent key not found
```

- Data files and tablespaces are physical; SQL never names them in a query.

## 1.2 SELECT clauses and the ERD

- **Projection** (choose attributes) = the SELECT list. **Selection** (choose rows) = WHERE.
  **Join** (follow a relationship) = FROM with several tables and a join condition.
- 1:M: the foreign key goes on the *many* side (employees holds department_id).
- M:N: an intersection table. `order_items` links orders and products; its primary key
  `ORDER_ITEMS_PK` is `(order_id, line_no)`, with foreign keys to both parents.
- Optional relationship ("may") = nullable FK; mandatory ("must") = NOT NULL FK.

## 1.3 The database and SQL

| Category | Statements |
|---|---|
| DML | SELECT, INSERT, UPDATE, DELETE, MERGE |
| DDL | CREATE, ALTER, DROP, RENAME, TRUNCATE, COMMENT (auto-commit) |
| DCL | GRANT, REVOKE |
| Transaction control | COMMIT, ROLLBACK, SAVEPOINT |

- SQL is declarative: the optimizer decides how to access the data.
- Keywords and unquoted identifiers are case-insensitive (stored in UPPERCASE); data is not.
  `select E.Last_Name FROM Employees e where e.last_name = 'KING'` runs and returns **0 rows**.
- The `;` is a client terminator (SQL*Plus, SQL Developer), not part of the statement.

## 2.1 The SELECT statement

```sql
SELECT *            FROM departments;        -- all columns, table order
SELECT e.*, e.salary FROM employees e;       -- * mixed with other items must be qualified
```

- `SELECT *, salary FROM employees` → **ORA-00923**: FROM keyword not found where expected.
- `FROM employees AS e` → **ORA-00933**: SQL command not properly ended (AS is only for column aliases).
- Logical processing order: FROM → WHERE → GROUP BY → HAVING → SELECT → ORDER BY.
- `DUAL` is a one-row table for expressions; 19c needs `FROM dual` (23ai makes FROM optional).
- `DESCRIBE employees` is a SQL*Plus command: Name, Null?, Type. It shows no other constraints.

## 2.2 Column aliases

```sql
SELECT e.salary * 12 AS annual, e.salary "Monthly Pay" FROM employees e ORDER BY annual;
```

- AS is optional. Double quotes keep case, spaces and reserved words.
- An alias works in ORDER BY, but not in WHERE / GROUP BY / HAVING of the same query
  (`WHERE annual > 100000` → **ORA-00904**).
- `SELECT e.last_name "Name" ... ORDER BY name` → **ORA-00904**: the alias is `Name`, not `NAME`.
- `SELECT e.salary 'pay'` → **ORA-00923**: single quotes make a string, not an alias.

## 2.3 Concatenation and literals

| Expression | Result |
|---|---|
| `'It''s done'` | `It's done` |
| `q'[It's done]'`, `q'{O'Neil}'`, `q'!O'Neil!'` | text with the quote |
| `e.last_name \|\| NULL \|\| '!'` (King) | `King!` |
| `e.last_name \|\| ' earns ' \|\| e.salary` (Ernst) | `Ernst earns 6000` |
| `CONCAT(e.last_name, ', ', e.first_name)` | **ORA-00909** in 19c (2 arguments only) |

- `||` treats NULL as an empty string; numbers and dates are converted implicitly.
- q-quote delimiters: `[]`, `{}`, `()`, `<>` close with their partner; any other character is repeated.

## 2.4 DISTINCT

- Applies to the **whole row**: `SELECT DISTINCT department_id, job_title` → 6 rows.
- NULLs are one group: `SELECT DISTINCT commission_pct` → 4 rows (.3, .2, .15, NULL).
- `UNIQUE` is an Oracle synonym. DISTINCT must come right after SELECT
  (`SELECT department_id, DISTINCT job_title` → **ORA-00936**).

## 2.5 Arithmetic and NULL

| Expression (employee 104, salary 6000) | Result |
|---|---|
| `e.salary + 100 * 12` | `7200` |
| `(e.salary + 100) * 12` | `73200` |
| `24000 * 12 + 24000 * 12 * NULL` (King) | NULL |
| `100 / NULL` | NULL |
| `e.salary / NVL(e.commission_pct, 0)` | **ORA-01476**: divisor is equal to zero |

- `*` `/` before `+` `-`, left to right otherwise. NULL is not 0 and not a space.
- In Oracle `''` **is** NULL.

## Common traps

1. Using a column alias in WHERE (ORA-00904), or quoting it with single quotes (ORA-00923).
2. Quoted alias in mixed case, referenced unquoted in ORDER BY.
3. `AS` before a table alias (ORA-00933).
4. Thinking DISTINCT applies to the first column only, or that it drops NULLs.
5. Expecting `NULL + x` to be `x` (it is NULL), but `NULL || 'x'` to be NULL (it is `x`).
6. Forgetting precedence: `salary + 100 * 12`.
7. Backslash escapes (`'It\'s'`) — Oracle has none; double the quote or use `q'[...]'`.
8. Assuming rows come back in insertion order without ORDER BY.

> **Oracle vs. standard SQL / other databases**
>
> - `FROM` is mandatory in 19c (`FROM dual`); PostgreSQL, SQL Server, MySQL and Oracle 23ai allow `SELECT 1`.
> - `''` is NULL in Oracle; in PostgreSQL, SQL Server and MySQL it is an empty string.
> - `||` ignores NULL in Oracle; in standard SQL and PostgreSQL `'a' || NULL` is NULL.
>   SQL Server concatenates with `+`, MySQL with `CONCAT()` (`||` is OR by default).
> - `q'[...]'` alternative quoting and the `UNIQUE` synonym for DISTINCT are Oracle-only.
> - `AS` for table aliases is accepted by most other databases, not by Oracle.
> - Unquoted identifiers fold to UPPERCASE in Oracle (standard), to lowercase in PostgreSQL.
