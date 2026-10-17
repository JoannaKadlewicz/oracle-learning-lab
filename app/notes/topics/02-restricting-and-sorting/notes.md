# Topic 2: Restricting and Sorting Data

Environment: Oracle Database 19c, schema ORASTUDY. Every SQL result shown below was
**executed** against the sample data (rolled back, nothing changed). Substitution variables,
DEFINE and VERIFY are SQL*Plus (and SQLcl / SQL Developer script) features: they cannot run
through the app, so that section describes documented SQL*Plus behavior.

## 3.1 Operator precedence

| Order | Operators |
|---|---|
| 1 | Arithmetic `*` `/`, then `+` `-`, and `\|\|` |
| 2 | Comparison: `=` `<>` `<` `>` `<=` `>=`, `IS [NOT] NULL`, `LIKE`, `[NOT] BETWEEN`, `[NOT] IN` |
| 3 | `NOT` |
| 4 | `AND` |
| 5 | `OR` |

```sql
WHERE e.job_title = 'Sales Rep' OR e.job_title = 'Programmer' AND e.salary > 5000
-- = Sales Rep OR (Programmer AND salary > 5000)  -> 5 rows: 103, 104, 105, 106, 108
```

`WHERE NOT e.department_id = 30 AND e.salary > 5000` returned **3 rows** (100, 101, 105):
NOT applies only to the first comparison, and Grant (NULL department) is UNKNOWN either way.

## 3.2 Limiting rows

- `BETWEEN a AND b` is inclusive (`>= a AND <= b`); `BETWEEN 10 AND 5` matches nothing.
- `IN (list)` is a chain of `=` with OR. `NOT IN (10, 20, NULL)` returned **0 rows**;
  `IN (10, 20, NULL)` returned the 5 employees of departments 10 and 20.
- `LIKE`: `%` = any sequence, `_` = exactly one character, case-sensitive.
  `LIKE '_o%'` → Kochhar, Lorentz. Literal wildcard: `LIKE '%\_%' ESCAPE '\'`.
- NULL: only `IS NULL` / `IS NOT NULL` work. `commission_pct = NULL` returns 0 rows, no error.
- Dates hold a time: `order_date BETWEEN DATE '2024-03-01' AND DATE '2024-03-31'` returned
  2 orders (1004, 1005) and missed 1006 at 23:30. Use `>= DATE '2024-03-01' AND < DATE '2024-04-01'` (3 orders).

Row limiting clause (12c+), applied after ORDER BY:

```sql
ORDER BY e.employee_id OFFSET 2 ROWS FETCH NEXT 2 ROWS ONLY;   -- 102, 103
ORDER BY e.salary FETCH FIRST 2 ROWS WITH TIES;                -- 108, 106, 107 (3 rows)
ORDER BY e.salary DESC FETCH FIRST 25 PERCENT ROWS ONLY;      -- 3 rows (2.25 rounded up)
```

- `FIRST`/`NEXT` and `ROW`/`ROWS` are interchangeable. `OFFSET` alone returns the rest.
- `WITH TIES` needs ORDER BY to be meaningful and compares all ORDER BY keys.
- `ROWNUM` is assigned before ORDER BY; `WHERE ROWNUM > 1` returned **0 rows**.

## 3.3 Substitution variables (SQL*Plus)

| Syntax | Behavior |
|---|---|
| `&name` | Prompts if `name` is undefined; the value is used once and not kept |
| `&&name` | Prompts if undefined, then **defines** it; later `&name`/`&&name` do not prompt |
| `'&name'` | Quotes stay in the statement, so the user types `King`, not `'King'` |

- Substitution is plain **text replacement on the client** before the statement is sent:
  it can replace a value, a column, a table name, or a whole condition (`ORDER BY &col`).
- `WHERE last_name = &name` with input `King` becomes `= King` → ORA-00904 "KING": invalid identifier.
- `&` inside a string (`'R&D'`) is still a substitution prefix. `SET DEFINE OFF` disables
  substitution; `SET DEFINE ON` restores it (`SET DEFINE ^` changes the prefix character).

## 3.4 DEFINE, UNDEFINE and VERIFY

```text
SQL> DEFINE dept_id = 20
SQL> DEFINE dept_id
DEFINE DEPT_ID         = "20" (CHAR)
SQL> SELECT last_name FROM employees WHERE department_id = &dept_id;
old   1: SELECT last_name FROM employees WHERE department_id = &dept_id
new   1: SELECT last_name FROM employees WHERE department_id = 20
SQL> UNDEFINE dept_id
```

- `DEFINE` alone lists all variables (including predefined `_DATE`, `_USER`, ...).
- DEFINE always creates a **CHAR** variable; it lasts until UNDEFINE or the end of the session.
- `SET VERIFY ON` (default) prints the `old`/`new` lines; `SET VERIFY OFF` hides them but
  substitution still happens.

## 3.5 Sorting

- `ASC` is the default; ASC/DESC applies to one item only (`ORDER BY a DESC, b` sorts b ascending).
- NULLs sort as the highest value: last in ASC, first in DESC. Override with `NULLS FIRST/LAST`.
- ORDER BY can use a column not selected, an expression, an alias, or a position:
  `SELECT last_name, department_id ... ORDER BY 2 DESC, 1` puts **Grant** (NULL department) first.
- With DISTINCT, ORDER BY must use selected items: `SELECT DISTINCT job_title ... ORDER BY salary`
  → **ORA-01791**: not a SELECTed expression. A position beyond the list → **ORA-01785**.
- Without ORDER BY, row order is not guaranteed.

## Common traps

1. `OR` mixed with `AND` without parentheses.
2. `= NULL`, `IN (NULL)`, `NOT IN (..., NULL)` — all quietly return nothing.
3. BETWEEN with reversed bounds, or with date-only upper bounds on DATE columns.
4. LIKE is case-sensitive; `_` is a wildcard, not an underscore, without ESCAPE.
5. `ROWNUM > 1` or ROWNUM with ORDER BY in the same query block.
6. Forgetting that DESC puts NULLs first.
7. Unquoted `&name` for text; thinking `SET VERIFY OFF` stops prompting (it does not; `SET DEFINE OFF` does).
8. Thinking `&` keeps its value: only `&&`, DEFINE and ACCEPT define a variable.

> **Oracle vs. standard SQL / other databases**
>
> - `OFFSET ... FETCH` is ISO SQL:2008 and works in Oracle 12c+, PostgreSQL, SQL Server 2012+.
>   MySQL and PostgreSQL also have `LIMIT`; SQL Server has `TOP`. Oracle has neither in 19c.
> - NULL ordering: Oracle and PostgreSQL treat NULL as highest; SQL Server and MySQL as lowest.
>   `NULLS FIRST/LAST` exists in Oracle and PostgreSQL, not in SQL Server or MySQL.
> - `LIKE` is case-sensitive in Oracle and PostgreSQL; with default collations it is
>   case-insensitive in SQL Server and MySQL. SQL Server's `[_]` bracket escape is not Oracle syntax.
> - `ROWNUM` is Oracle-only.
> - Substitution variables are a client feature (SQL*Plus, SQLcl, SQL Developer), not SQL;
>   other clients use bind variables (`:name`) or their own variable syntax.
