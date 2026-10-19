# Cheat sheet: the rules the exam tests most

Read it in the evenings before the exam. Every result in the tables was executed on Oracle 19.3
and on Oracle 23ai (23.26) on 2026-10-18; where they differ, both are given. The other rules
are covered by database-verified questions in the app or come from Oracle's documentation.

## Order of evaluation

`FROM/JOIN → WHERE → GROUP BY → HAVING → SELECT → DISTINCT → ORDER BY → OFFSET/FETCH`

- Column aliases exist from SELECT on: usable in ORDER BY, not in WHERE or HAVING (19c), and
  in GROUP BY only on 23ai.
- `ORDER BY` can use an alias, a position (`ORDER BY 2`), or an expression not in the select
  list (except after DISTINCT or in a compound query).
- `NULLS LAST` is the default for ascending sorts, `NULLS FIRST` for descending.
- `FETCH FIRST 3 ROWS WITH TIES` needs ORDER BY to find ties; `OFFSET 5 ROWS` alone skips rows.

## NULL

| Expression | Result |
|---|---|
| `NULL = NULL`, `NULL <> 1` | unknown: the row is not returned |
| `x NOT IN (1, NULL)` | never true: 0 rows |
| `NULL IN (1, NULL)` | unknown: 0 rows |
| `5 + NULL`, `'a' \|\| NULL` | NULL, but `'a' \|\| NULL` = `'a'` |
| `LENGTH('')` | NULL (the empty string is NULL) |
| `DECODE(NULL, NULL, 'equal', 'not')` | `equal` (DECODE treats two NULLs as equal) |
| `CASE WHEN NULL = NULL THEN 'eq' ELSE 'ne' END` | `ne` |
| `COUNT(*)` vs `COUNT(col)` | all rows vs non-NULL values |
| `AVG(col)` | ignores NULLs: use `AVG(NVL(col, 0))` to count them as 0 |
| Set operators, `DISTINCT`, `GROUP BY` | treat NULLs as equal to each other |

`NVL(a, b)` (same type), `NVL2(a, if_not_null, if_null)`, `NULLIF(a, b)` (NULL when equal),
`COALESCE(a, b, c, ...)` (first non-NULL, short-circuits).

## Functions you must compute by heart

| Expression | Result |
|---|---|
| `ROUND(15.193, -1)` / `TRUNC(15.79, -1)` | 20 / 10 |
| `MOD(-7, 3)` / `REMAINDER(7, 4)` | -1 (sign of the dividend) / -1 (rounds the quotient) |
| `INSTR('banana', 'a', -1)` | 6 (searches backwards, position counted from the left) |
| `SUBSTR('database', -4, 2)` | `ba` |
| `LPAD('7', 3, '0')` / `TRIM(LEADING '0' FROM '0070')` | `007` / `70` |
| `ROUND(DATE '2024-07-16', 'MONTH')` | 2024-08-01 (day 16 or later rounds up) |
| `ROUND(DATE '2024-07-01', 'YEAR')` | 2025-01-01 (July or later rounds up) |
| `ADD_MONTHS(DATE '2024-01-31', 1)` | 2024-02-29 (month end stays month end) |
| `MONTHS_BETWEEN(DATE '2024-03-31', DATE '2024-02-29')` | 1 (both are month ends) |
| `TO_CHAR(DATE '2024-01-05', 'fmDay, Month DD')` | `Friday, January 5` (fm removes padding) |
| `RR` with `49` / `50` (in this century) | 2049 / 1950 |
| `date - date` / `date + 1` / `date + 1/24` | days (NUMBER) / next day / one hour later |

## Group functions

- Every non-aggregated column in SELECT must be in GROUP BY (ORA-00979), but a GROUP BY column
  need not be selected.
- WHERE filters rows before grouping and cannot contain a group function (ORA-00934); HAVING filters groups.
- Group functions nest two levels deep at most, and only with GROUP BY:
  `MAX(AVG(salary))` works, `COUNT(MAX(AVG(salary)))` raises ORA-00935.

## Joins

- `NATURAL JOIN` and `USING` columns must not be qualified with a table alias (ORA-25155 for NATURAL, ORA-25154 for USING).
- An outer join followed by `WHERE inner_table.col = ...` turns back into an inner join; put the
  condition in `ON` to keep unmatched rows.
- `(+)` goes on the side that may be missing; it cannot express a full outer join.
- A self-join needs two aliases; a non-equijoin uses `BETWEEN` or `>`/`<` in the condition.
- A missing join condition gives a Cartesian product: rows(A) × rows(B).

## Subqueries

- `=` with a subquery that returns more than one row: ORA-01427 at run time.
- `> ALL (...)` means greater than the maximum; `< ANY (...)` means less than the maximum.
- `NOT IN (subquery)` returns no rows if the subquery returns any NULL; `NOT EXISTS` does not have this problem.
- A scalar subquery that returns no row gives NULL.

## Set operators

- Same number of columns (ORA-01789) and type groups by position (ORA-01790; no implicit NUMBER to text).
- Column names come from the first SELECT; ORDER BY only once, at the end.
- `UNION`, `INTERSECT`, `MINUS` remove duplicates; `UNION ALL` keeps them and does not sort.
- All set operators have equal precedence and run top to bottom unless parenthesized.

## DML, transactions, DDL

- DDL (CREATE, ALTER, DROP, TRUNCATE, GRANT) commits the open transaction, even if it fails
  after parsing.
- `ROLLBACK TO SAVEPOINT s` keeps the work before `s` and the transaction stays open.
- `TRUNCATE` is DDL: no WHERE, no rollback, fires no DELETE triggers, keeps the table structure.
- `MERGE`: one target row updated by two source rows raises ORA-30926.
- `INSERT ALL` evaluates every WHEN clause; `INSERT FIRST` stops at the first true WHEN.
- Constraints: NOT NULL only as a column constraint; a FOREIGN KEY may reference a PRIMARY KEY or
  a UNIQUE key; `ON DELETE CASCADE` / `ON DELETE SET NULL`; UNIQUE allows several NULLs.
- `CREATE TABLE ... AS SELECT` copies NOT NULL constraints only.
- `SET UNUSED` is instant and cannot be undone; `DROP UNUSED COLUMNS` removes the data later.

## Views, sequences, indexes, synonyms

- DML through a view is not possible when the view uses group functions, GROUP BY, DISTINCT,
  ROWNUM or (for INSERT) leaves out NOT NULL columns without defaults.
- `WITH CHECK OPTION` rejects changes that would make the row disappear from the view.
- `CURRVAL` before the first `NEXTVAL` in the session: ORA-08002. A rolled-back NEXTVAL is not returned again: gaps are normal.
- PRIMARY KEY and UNIQUE constraints create an index automatically; foreign keys do not.
- A private synonym is resolved before a public one with the same name.

## Privileges

- `WITH ADMIN OPTION` (system privileges, roles): revoking does not cascade.
- `WITH GRANT OPTION` (object privileges): revoking cascades to the users the grantee granted to.
- You need a privilege directly (not through a role) to create a view or procedure on another user's table.

## Time zones

- `SYSDATE`/`SYSTIMESTAMP`: database server time. `CURRENT_DATE`/`CURRENT_TIMESTAMP`/`LOCALTIMESTAMP`: session time zone.
- `LOCALTIMESTAMP` has no time zone; `CURRENT_TIMESTAMP` does.
- `TIMESTAMP WITH LOCAL TIME ZONE` stores normalized to the database time zone and shows values in the session time zone.
- `INTERVAL YEAR TO MONTH` for months and years, `INTERVAL DAY TO SECOND` for days to fractions.
- Adding `INTERVAL '1' MONTH` to January 31 raises ORA-01839; `ADD_MONTHS` does not.
