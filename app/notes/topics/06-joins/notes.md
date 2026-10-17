# Topic 6: Displaying Data from Multiple Tables (Joins)

Environment: Oracle Database 19c, schema ORASTUDY. Every result below was **executed** on
2026-10-17 against the sample data (in a rolled-back session). Objectives 7.1–7.5.

Data facts used below: 9 employees, 4 departments. Employee 108 (Grant) has no department,
department 40 (Research) has no employees, employee 100 (King) has no manager.

## 7.1 Types of joins

| Syntax | Join condition | Join column in the result |
|---|---|---|
| `JOIN ... ON cond` | any condition | both copies, qualify if ambiguous (ORA-00918) |
| `JOIN ... USING (col, ...)` | equality on the listed same-name columns | one copy, must **not** be qualified (ORA-25154) |
| `NATURAL JOIN` | equality on **all** same-name columns | one copy, must not be qualified (ORA-25155) |
| `FROM a, b WHERE cond` | Oracle/old syntax, condition in WHERE | both copies |
| `CROSS JOIN` | none | – |

`INNER` and `OUTER` are optional keywords. These four return the same 8 rows:

```sql
SELECT e.last_name, d.department_name FROM employees e JOIN departments d ON e.department_id = d.department_id;
SELECT e.last_name, d.department_name FROM employees e JOIN departments d USING (department_id);
SELECT last_name, department_name     FROM employees NATURAL JOIN departments;
SELECT e.last_name, d.department_name FROM employees e, departments d WHERE e.department_id = d.department_id;
```

- `NATURAL JOIN ... ON` and `USING (d.department_id)` are errors (USING takes simple names: ORA-01748).
- `JOIN` with no ON/USING → ORA-00905: missing keyword.
- For inner joins a filter in ON or in WHERE gives the same result.
- Multi-table joins are evaluated left to right; four tables need three join conditions.
  `customers → orders → order_items → products` filtered to Hardware returns 6 rows.
- NATURAL JOIN trap: `employees e1 NATURAL JOIN employees e2` compares all 10 columns and
  returns only **3** rows, because a NULL in any column never equals NULL.

## 7.2 Self-joins

The same table twice, with two aliases. The condition decides the roles:

```sql
SELECT e.last_name, m.last_name AS manager
FROM   employees e
JOIN   employees m ON e.manager_id = m.employee_id;   -- 8 rows: King has no manager
```

- `LEFT JOIN employees m ...` keeps King with a NULL manager (9 rows).
- Reversed (`e.employee_id = m.manager_id`), m becomes the subordinate: for Kochhar
  it returns Grant, Partners, Russell.
- Grouped by manager it returns 3 rows: King 2, Kochhar 3, De Haan 3.

## 7.3 Non-equijoins

A join on anything other than `=`, typically a range:

```sql
SELECT e.last_name, e.salary, g.grade
FROM   employees e
JOIN   salary_grades g ON e.salary BETWEEN g.min_salary AND g.max_salary;  -- 9 rows
```

Grades: A 3 (Partners, Lorentz, Grant), B 3, C 2, D 1. `BETWEEN` is inclusive and equals
`>= AND <=`; `BETWEEN g.max_salary AND g.min_salary` returns nothing. With only a lower bound
(`ON e.salary >= g.min_salary`) each employee matches several grades: **19** rows.
Non-equijoins need ON or WHERE; USING and NATURAL JOIN only produce equality.

## 7.4 Outer joins

| Query | Rows |
|---|---|
| `employees e JOIN departments d ON ...` | 8 |
| `employees e LEFT JOIN departments d ON ...` | 9 (adds Grant) |
| `employees e RIGHT JOIN departments d ON ...` | 9 (adds Research) |
| `employees e FULL JOIN departments d ON ...` | 10 |

Oracle syntax: `(+)` goes on the side that **may be missing**:

```sql
WHERE e.department_id = d.department_id(+)    -- = employees LEFT JOIN departments
```

- `(+)` on both sides → **ORA-01468**; FULL OUTER JOIN has no `(+)` form.
- `(+)` in the WHERE clause of a query that also uses ANSI joins → **ORA-25156**.
  (19c accepts `(+)` inside an ANSI `ON` clause and makes the join outer, but don't mix the styles.)
- In the old syntax every condition on the optional table needs `(+)`:
  `AND e.salary(+) > 10000` keeps Research; without the `(+)` it disappears.

**ON vs WHERE** for the optional table:

```sql
SELECT d.department_name, COUNT(e.employee_id)
FROM   departments d
LEFT JOIN employees e ON e.department_id = d.department_id AND e.salary > 10000
GROUP  BY d.department_name;     -- 4 rows, Research 0
-- same filter in WHERE: 3 rows, Research is gone (NULL > 10000 is not true)
```

- Anti-join: `departments d LEFT JOIN employees e ON ... WHERE e.employee_id IS NULL` →
  `Research`.
- `COUNT(*)` counts the NULL-extended row (Research → 1); `COUNT(e.employee_id)` → 0.

## 7.5 Cartesian products

Every row paired with every row: rows(A) × rows(B).

- `departments CROSS JOIN salary_grades` → 16. `CROSS JOIN ... ON` → ORA-00933.
- `FROM employees e, departments d WHERE e.salary > 10000` → 3 × 4 = **12** (no join condition).
- `JOIN ... ON 1 = 1` → 16.
- `employees NATURAL JOIN orders` → **63**: no common column names, so no condition at all.

## Common traps

1. Qualifying a USING/NATURAL column (ORA-25154 / ORA-25155) vs. not qualifying an ON
   column that exists in both tables (ORA-00918).
2. NATURAL JOIN joins on *every* same-name column, or on none (Cartesian product).
3. Filtering the optional table in WHERE turns an outer join into an inner join.
4. `COUNT(*)` after an outer join counts unmatched rows as 1.
5. `(+)` marks the deficient side, which is the opposite of the side named by LEFT/RIGHT.
6. A self-join's direction is set by the condition, not by alias names.
7. Range joins duplicate rows when ranges overlap and drop rows when there are gaps.
8. N tables need at least N − 1 join conditions.

> **Oracle vs. standard SQL / other databases**
>
> - `(+)` is Oracle-only; ANSI `LEFT/RIGHT/FULL OUTER JOIN` (supported since Oracle 9i) is
>   portable and is what other databases use. Oracle recommends the ANSI form.
> - MySQL has no `FULL OUTER JOIN`; Oracle and PostgreSQL do.
> - In MySQL `JOIN` without ON is allowed (it acts as CROSS JOIN); Oracle raises ORA-00905.
> - SQL Server has no `NATURAL JOIN` or `USING`; Oracle, PostgreSQL and MySQL do.
> - Oracle also supports `CROSS APPLY` / `OUTER APPLY` and `LATERAL` (12c+), which are not
>   on the 1Z0-071 objectives.
