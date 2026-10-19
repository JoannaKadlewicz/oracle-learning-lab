# Topic 8: Set Operators

Environment: Oracle Database 19c, schema ORASTUDY. Every result below was **executed**
against the sample data.

## Concept

Set operators combine the results of two or more SELECTs ("branches") into one compound query.

| Operator | Returns | Duplicates | Commutative |
|---|---|---|---|
| `UNION` | rows from either branch | removed | yes |
| `UNION ALL` | all rows from both branches | kept | yes (as a multiset) |
| `INTERSECT` | rows returned by both branches | removed | yes |
| `MINUS` | rows of the first branch not in the second | removed | **no** |

Oracle 19c has only these four. `EXCEPT`, `MINUS ALL`, `INTERSECT ALL` arrived in 21c.

## 9.1 Matching the SELECT statements

- Same **number of columns** in every branch, else **ORA-01789: query block has incorrect
  number of result columns**.
- Corresponding columns must be in the same **data type group** (numeric, character, date).
  `employee_id UNION last_name` → **ORA-01790: expression must have same datatype as
  corresponding expression**. No implicit NUMBER → VARCHAR2 conversion; use `TO_CHAR`.
- Names, lengths and precisions need not match: `department_id NUMBER(4)` with
  `salary NUMBER(8,2)`, `VARCHAR2(30)` with `VARCHAR2(25)` are fine.
- `NULL` fits any column, so it is the usual placeholder:

```sql
SELECT e.last_name, e.salary FROM employees e
UNION ALL
SELECT c.customer_name, NULL FROM customers c;      -- 14 rows
```

- **Headings come from the first SELECT.** For
  `SELECT e.last_name AS name, e.salary ... UNION SELECT c.customer_name AS customer, c.credit_limit AS amount ...`
  the columns are `NAME, SALARY`.
- **Precedence**: all set operators are equal and run left to right (standard SQL gives
  INTERSECT priority). Use parentheses to be explicit.
- **NULLs are equal to each other** when set operators compare rows (unlike `=`).

## 9.2 UNION and UNION ALL

```sql
SELECT e.department_id FROM employees e
UNION
SELECT d.department_id FROM departments d;   -- 5 rows: 10, 20, 30, 40, NULL
```

The same query with `UNION ALL` returns 13 rows (9 + 4).

- UNION removes duplicates **within** a branch too: `job_title UNION <empty>` → 5 rows, not 9.
- `country_code UNION ...` over US, GB, US, PL, NULL → 4 rows (one NULL kept).
- `A UNION B` ≡ `SELECT DISTINCT * FROM (A UNION ALL B)` ≡ `B UNION A`.
- UNION ALL is cheaper (no duplicate elimination). Neither guarantees an order without ORDER BY.

## 9.3 INTERSECT

```sql
SELECT o.sales_rep_id FROM orders o
INTERSECT
SELECT e.employee_id FROM employees e WHERE e.department_id = 20;   -- 105, 106
```

- Distinct rows only: the 5 orders taken by these two reps collapse to 2 values.
- NULL matches NULL: `department_id INTERSECT department_id of commissioned staff` → 20 and NULL.
  A join or `IN` would return only 20.
- `A INTERSECT B` ≡ `A WHERE key IN (B)` when key is unique and not NULL; a plain join repeats rows.

Precedence example:

```sql
SELECT d.department_id FROM departments d
UNION
SELECT e.department_id FROM employees e
INTERSECT
SELECT e.department_id FROM employees e WHERE e.salary > 10000;
```

Oracle: `(departments UNION employees) INTERSECT {10, 20, 30}` → **3 rows**.
Standard SQL would compute the INTERSECT first and return 4 rows.

## 9.4 MINUS

```sql
SELECT d.department_id FROM departments d MINUS SELECT e.department_id FROM employees e;  -- 40
SELECT e.department_id FROM employees e MINUS SELECT d.department_id FROM departments d;  -- NULL
```

- Direction matters. The second query returns the NULL of employee 108 because departments has no NULL.
- A NULL in the second branch does **not** wipe out the result as it does with `NOT IN`.
  The first query above is equivalent to NOT EXISTS, to NULL-filtered NOT IN, and to a
  LEFT JOIN ... WHERE e.employee_id IS NULL; a plain NOT IN returns 0 rows.
- Rows, not entities, are compared: `job_title MINUS job_title of department 20` → President,
  IT Manager, Programmer (Grant's Sales Rep title disappears even though he is not in 20).

## 9.5 ORDER BY in set operations

- Only **one** ORDER BY, after the **last** SELECT; it sorts the whole result.
  `SELECT ... ORDER BY e.last_name UNION SELECT ...` → **ORA-00933: SQL command not properly ended**.
- Allowed: positions (`ORDER BY 2 DESC`), first-query column names or aliases (`ORDER BY name`, `salary`).
- Not allowed: a second-branch alias (`ORDER BY cust` → **ORA-00904**), a table-qualified
  column (`ORDER BY e.last_name` → **ORA-00904**), a position beyond the column count
  (`ORDER BY 3` → **ORA-01785**).
- DESC puts NULLs **first** by default:

```sql
SELECT e.last_name AS name, e.salary AS amount FROM employees e WHERE e.department_id = 20
UNION ALL
SELECT c.customer_name, c.credit_limit FROM customers c
ORDER  BY 2 DESC, 1;
```

| NAME | AMOUNT |
|---|---|
| Initech | NULL |
| Kochhar | 14000 |
| Russell | 6000 |
| Acme Corp | 5000 |
| ... | ... |

Add `NULLS LAST` to move Initech to the end.

## Common traps

1. Assuming headings or ORDER BY names come from the last SELECT. They come from the first.
2. ORDER BY in a middle branch (ORA-00933) or with a table alias / second-branch alias (ORA-00904).
3. Expecting implicit NUMBER/VARCHAR2 conversion between branches (ORA-01790).
4. Thinking NULLs never match in set operators. They do, unlike in joins and IN.
5. Treating MINUS as commutative, or expecting it to keep duplicates.
6. Reading `A UNION B INTERSECT C` with standard SQL precedence.
7. Thinking UNION output is sorted. Only ORDER BY guarantees order.
8. Counting UNION results without collapsing duplicates inside a single branch.

> **Oracle vs. standard SQL / other databases**
> - Oracle uses `MINUS`; the standard (and PostgreSQL, SQL Server, Oracle 21c+) uses `EXCEPT`.
> - Standard SQL, PostgreSQL and SQL Server give `INTERSECT` higher precedence than `UNION`/`EXCEPT`;
>   Oracle evaluates all set operators left to right.
> - `INTERSECT ALL` / `EXCEPT ALL` exist in the standard and PostgreSQL, and in Oracle only from 21c.
> - Oracle sorts NULLs as the highest value (first with DESC); SQL Server sorts them as the lowest.

## Oracle 23ai differences (1Z0-171)

Checked on Oracle AI Database 23ai (FREEPDB1) with the same sample data.

- **EXCEPT, EXCEPT ALL, MINUS ALL and INTERSECT ALL** work (available since 21c). In 19c,
  `EXCEPT` raises ORA-00933 and `MINUS ALL` / `INTERSECT ALL` raise ORA-00928 missing SELECT keyword.
  - `EXCEPT` is a synonym of `MINUS`: `orders.customer_id EXCEPT GB customers` → 1, 3, 5.
  - `MINUS ALL` subtracts occurrences: order customer ids 1, 1, 1, 2, 2, 3, 5 `MINUS ALL`
    customers (each id once) → **1, 1, 2** (3 rows; plain MINUS → 0 rows).
  - `INTERSECT ALL` keeps the smaller number of occurrences: order customer ids
    `INTERSECT ALL` customers → 1, 2, 3, 5 (4 rows).
- **Precedence is unchanged**: `departments UNION employees INTERSECT high earners` still
  returns 3 rows on 23ai (left to right), not the 4 rows of standard SQL precedence.
- **ORDER BY in a middle branch** raises **ORA-03048** (SQL reserved word 'UNION' is not
  syntactically valid following ...) instead of ORA-00933. ORA-00907 (ORDER BY inside a
  parenthesized branch), ORA-00904 (second-branch alias or `e.` column in ORDER BY),
  ORA-01785 (ORDER BY expression or position beyond the column count), ORA-01789 and
  ORA-01790 are the same as in 19c.
- **UNION output order differs.** On 19c the sample UNION queries happened to come back sorted
  (10, 20, 30, 40, NULL); on 23ai the same query returned 10, 20, 30, NULL, 40. Neither version
  guarantees any order without ORDER BY.
