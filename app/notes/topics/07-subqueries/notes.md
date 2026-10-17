# Topic 7: Subqueries

Environment: Oracle Database 19c, schema ORASTUDY. Every result below was **executed**
against the sample data (DML examples were rolled back).

## Concept

A subquery is a SELECT nested inside another statement. What you may do with it depends on
how many rows it returns and whether it refers to the outer statement.

| Kind | Returns | Use with | Wrong row count |
|---|---|---|---|
| Single-row / scalar | at most 1 row, 1 column | `=  <>  <  >  <=  >=`, SELECT list, ORDER BY, SET | 2+ rows → ORA-01427; 0 rows → NULL |
| Multiple-row | any number of rows | `IN`, `NOT IN`, `op ANY`, `op ALL`, `EXISTS` | never an error |
| Multiple-column | several columns | `(a, b) IN (SELECT x, y ...)`, `SET (a, b) = (SELECT x, y ...)` | |
| Correlated | depends on the outer row | anywhere; logically run once per outer row | |
| Inline view | a row source | FROM clause; may have its own ORDER BY | |

## 8.1 Single-row subqueries

```sql
SELECT e.last_name, e.salary
FROM   employees e
WHERE  e.salary > (SELECT AVG(e2.salary) FROM employees e2)    -- 9344.44
ORDER  BY e.salary DESC;
```

Result: King 24000, Kochhar 14000, De Haan 12000.

- `= (SELECT e2.salary FROM employees e2 WHERE e2.department_id = 20)` raises
  **ORA-01427: single-row subquery returns more than one row** (department 20 has three people).
  The check happens at run time, so the same query can work on other data.
- A subquery that finds **no rows** gives NULL: `WHERE e.salary <> (... employee_id = 999)`
  returns 0 rows and no error.
- In the SELECT list: `(SELECT MAX(e.salary) ... )` is NULL for Research, but
  `(SELECT COUNT(*) ...)` is **0**: an aggregate without GROUP BY always returns one row.
- `MAX(AVG(salary)) ... GROUP BY department_id` collapses groups into one row (24000 → King).
- HAVING may compare with a subquery:
  `HAVING AVG(e.salary) > (SELECT AVG(e2.salary) FROM employees e2)` → only department 10.
- **No ORDER BY inside a WHERE subquery**: ORA-00907 missing right parenthesis.
  ORDER BY *is* allowed in an inline view (`FROM (SELECT ... ORDER BY ...)`).
- Scalar subqueries are allowed in SELECT, WHERE, HAVING, ORDER BY, CASE, UPDATE SET and
  INSERT VALUES; **not** in GROUP BY (ORA-22818), CHECK constraints or DEFAULT expressions.

Correlated example (employees above their own department's average):

```sql
SELECT e.last_name, e.department_id, e.salary
FROM   employees e
WHERE  e.salary > (SELECT AVG(e2.salary)
                   FROM   employees e2
                   WHERE  e2.department_id = e.department_id);
```

Result: Kochhar (20), De Haan (30), Hunold (30). Grant has no department, so his average is
NULL and the comparison is UNKNOWN.

## 8.2 Multiple-row subqueries

| Operator | Meaning | Same as | Empty subquery |
|---|---|---|---|
| `IN` / `= ANY` | equals one of them | | FALSE |
| `NOT IN` / `<> ALL` | differs from all | | TRUE |
| `> ANY` | above at least one | `> MIN` | FALSE |
| `> ALL` | above every one | `> MAX` | TRUE |
| `< ANY` | below at least one | `< MAX` | FALSE |
| `< ALL` | below every one | `< MIN` | TRUE |

Department 30 earns 12000, 9000, 6000, 4800:
`salary > ALL (...)` → 2 rows (King, Kochhar); `salary > ANY (...)` → 6;
`salary < ANY (...)` → 6; against department 40 (empty) `> ALL` → all 9, `> ANY` → 0.

**The NOT IN trap.** Employee 108 has a NULL department, so

```sql
SELECT d.department_name FROM departments d
WHERE  d.department_id NOT IN (SELECT e.department_id FROM employees e);   -- 0 rows
```

`x NOT IN (10, 20, 30, NULL)` = `x<>10 AND x<>20 AND x<>30 AND x<>NULL`, and the last part is
always UNKNOWN. Fixes that return **Research**:

```sql
... NOT IN (SELECT e.department_id FROM employees e WHERE e.department_id IS NOT NULL)
... WHERE NOT EXISTS (SELECT 1 FROM employees e WHERE e.department_id = d.department_id)
```

A NULL in an `IN` list is harmless: the IN query with `10, 20, 30, 40, NULL` still returns 8 employees.

**EXISTS** only checks whether a row comes back; the select list is irrelevant
(`SELECT NULL`, `SELECT 1`, `SELECT *` are the same). Employees who manage someone:
`WHERE EXISTS (SELECT NULL FROM employees r WHERE r.manager_id = e.employee_id)` → King,
Kochhar, De Haan.

**Pairwise comparison**: `WHERE (e.department_id, e.salary) IN (SELECT department_id, MAX(salary) ... GROUP BY department_id)`.

**IN vs EXISTS vs JOIN**: customers with orders. IN, `= ANY` and EXISTS return 4 customers
once each; a plain JOIN returns 7 rows (Acme Corp three times) unless you add DISTINCT.

## 8.3 Correlated UPDATE and DELETE

```sql
UPDATE order_items i
SET    i.unit_price = (SELECT p.list_price FROM products p WHERE p.product_id = i.product_id)
WHERE  i.unit_price < (SELECT p.list_price FROM products p WHERE p.product_id = i.product_id);
-- 4 rows updated; the Consulting Hour line (list_price NULL) is untouched

DELETE FROM orders o
WHERE  NOT EXISTS (SELECT 1 FROM order_items i WHERE i.order_id = o.order_id);
-- 1 row deleted: order 1007
```

Rules:
- **No WHERE clause = every row is updated.** Rows with no match get NULL:
  `SET c.credit_limit = (SELECT SUM(...) ... WHERE o.customer_id = c.customer_id)` sets
  Umbrella (no orders) to NULL. COUNT would give 0. Repeat the correlation in
  `WHERE EXISTS (...)` to touch only matching rows.
- **Statement-level read consistency**: every subquery evaluation sees the data as of the
  start of the statement. `SET salary = (SELECT AVG(...) same department)` gives everyone in
  department 30 exactly 7950, no matter which row is updated first. Likewise, deleting
  lines below their order's average quantity removes exactly 2 lines (1001/1, 1004/2).
- If the SET subquery returns 2+ rows for any row: **ORA-01427** and the whole statement is
  rolled back (no partial update).
- Several columns at once: `SET (i.unit_price, i.quantity) = (SELECT p.list_price, 1 FROM ...)`.
  Without parentheses: ORA-00927; too few subquery columns: ORA-00947.
- A NULL produced by the subquery passes a `CHECK (salary > 0)` constraint (UNKNOWN is not a violation).

## Common traps

1. `NOT IN` with a NULL anywhere in the subquery → no rows. `NOT EXISTS` is NULL-safe.
2. `=` with a subquery that can return several rows → ORA-01427 (at run time, data-dependent).
3. `> ANY` is `> MIN`, not `> MAX`; `< ALL` is `< MIN`.
4. `ALL` over an empty set is TRUE (all rows), `ANY` over an empty set is FALSE (no rows).
5. Empty scalar subquery → NULL, but `COUNT(*)` scalar subquery → 0.
6. ORDER BY inside a WHERE subquery → ORA-00907.
7. Correlated UPDATE without WHERE nulls out the unmatched rows.
8. Expecting a correlated UPDATE/DELETE to see its own earlier row changes. It does not.
9. A JOIN instead of IN/EXISTS duplicates outer rows when the inner table has several matches.

> **Oracle vs. standard SQL / other databases**
> - `ANY`, `SOME` and `ALL`, `EXISTS`, row-value `(a, b) IN (SELECT ...)` and scalar subqueries are standard SQL;
>   SQL Server does not support row-value IN.
> - `SET (a, b) = (SELECT ...)` is supported by Oracle and PostgreSQL; SQL Server uses `UPDATE ... FROM` instead,
>   and MySQL cannot select from the table being updated in a subquery (error 1093), which Oracle allows.
> - `MAX(AVG(x))` (nested aggregates) is Oracle-only; elsewhere use an inline view.
> - Oracle does not report "no data found" for an empty scalar subquery; that is a PL/SQL `SELECT INTO` error.
