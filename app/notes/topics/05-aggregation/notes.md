# Topic 5: Reporting Aggregated Data Using Group Functions

Environment: Oracle Database 19c, schema ORASTUDY. Every result below was **executed** on
2026-10-17 against the sample data (in a rolled-back session). Objectives 6.1–6.3.

## Concept

A group function takes many rows and returns one value. Without `GROUP BY` the whole result
of `FROM`/`WHERE` is one group; with `GROUP BY` there is one output row per group.
Logical processing order:

    FROM → WHERE → GROUP BY → HAVING → SELECT → ORDER BY

Almost every rule in this topic follows from that order.

## 6.1 Using group functions

| Function | Input types | NULLs | Over zero rows |
|---|---|---|---|
| `COUNT(*)` | rows | counted | 0 |
| `COUNT(expr)`, `COUNT(DISTINCT expr)` | any | ignored | 0 |
| `SUM`, `AVG`, `STDDEV`, `VARIANCE` | numeric only | ignored | NULL |
| `MIN`, `MAX` | number, character, date | ignored | NULL |
| `LISTAGG(expr, delim) WITHIN GROUP (ORDER BY ...)` | any | ignored | NULL |

```sql
SELECT COUNT(*), COUNT(e.commission_pct), COUNT(DISTINCT e.commission_pct)
FROM   employees e;                                   -- 9, 4, 3
SELECT AVG(e.commission_pct), AVG(NVL(e.commission_pct, 0))
FROM   employees e;                                   -- .2, .0888...
SELECT SUM(e.salary), SUM(DISTINCT e.salary)
FROM   employees e;                                   -- 84100, 73300
SELECT MIN(e.last_name), MAX(e.commission_pct)
FROM   employees e;                                   -- De Haan, .3
```

- `DISTINCT` works inside any group function (`SUM(DISTINCT ...)`, `AVG(DISTINCT ...)`).
- `SUM(e.last_name)` → **ORA-01722: invalid number** (implicit conversion of 'King').
- `LISTAGG(e.last_name, ', ') WITHIN GROUP (ORDER BY e.last_name)` for department 20 →
  `Kochhar, Partners, Russell`. 19c also accepts `LISTAGG(DISTINCT ...)`.

**Empty table** (`promotions` has no rows):

| Query | Result |
|---|---|
| `SELECT COUNT(*), COUNT(promo_id), SUM(discount_pct), MAX(promo_name) FROM promotions` | one row: `0, 0, NULL, NULL` |
| `SELECT promo_name, COUNT(*) FROM promotions GROUP BY promo_name` | **no rows** |
| `SELECT COUNT(*) FROM promotions HAVING COUNT(*) = 0` | one row: `0` |

**Nesting** (maximum two levels, `GROUP BY` required, single-row result):

```sql
SELECT MAX(AVG(e.salary)) FROM employees e GROUP BY e.department_id;   -- 24000
SELECT MAX(AVG(e.salary)) FROM employees e;                             -- ORA-00978
SELECT e.department_id, MAX(AVG(e.salary)) FROM employees e
GROUP  BY e.department_id;                                              -- ORA-00937
SELECT SUM(MAX(MIN(e.salary))) FROM employees e
GROUP  BY e.department_id;                                              -- ORA-00935
```

## 6.2 Creating groups of data

```sql
SELECT e.department_id, COUNT(*) FROM employees e GROUP BY e.department_id;
-- 4 rows: 10 → 1, 20 → 3, 30 → 4, NULL → 1   (all NULLs form one group)
SELECT e.department_id, e.job_title, COUNT(*) FROM employees e
GROUP  BY e.department_id, e.job_title;   -- 6 rows, one per existing combination
```

Rules:

- Every non-aggregated SELECT expression must appear in `GROUP BY`, otherwise
  **ORA-00979: not a GROUP BY expression**. The reverse is not required: a `GROUP BY`
  column need not be selected.
- Constants and functions of grouped columns are fine: `SELECT UPPER(e.job_title) ... GROUP BY e.job_title`.
  But `SELECT e.job_title ... GROUP BY UPPER(e.job_title)` → ORA-00979.
- `GROUP BY` cannot use a SELECT alias in 19c (**ORA-00904**) and is not positional:
  `GROUP BY 1` groups by the constant 1.
- `ORDER BY` in a grouped query may use GROUP BY expressions, group functions (even ones
  not selected), aliases and positions. `ORDER BY e.salary` → ORA-00979;
  `ORDER BY 3` with two selected columns → ORA-01785.
- Grouping does not sort. Only `ORDER BY` guarantees order.
- `COUNT(c.country_code)` for the NULL group of customers is `0`, while `COUNT(*)` is `1`.

## 6.3 Restricting group results

| | `WHERE` | `HAVING` |
|---|---|---|
| Filters | rows, before grouping | groups, after grouping |
| Group functions | not allowed (**ORA-00934**) | allowed, selected or not |
| Columns | any column | GROUP BY expressions only (else ORA-00979) |
| SELECT aliases | no | no (ORA-00904) |

```sql
SELECT e.department_id, COUNT(*)
FROM   employees e
WHERE  e.department_id IS NOT NULL      -- row filter
GROUP  BY e.department_id
HAVING COUNT(*) > 1;                    -- group filter: 20 → 3, 30 → 4
```

- `HAVING` without `GROUP BY` is legal: `SELECT COUNT(*) FROM employees HAVING COUNT(*) > 5`
  returns one row (`9`).
- A condition on a GROUP BY column gives the same result in `WHERE` or in `HAVING`;
  `WHERE` is the natural place (it removes rows before the work of grouping).
- `GROUP BY AVG(e.salary)` → ORA-00934: group functions belong only in SELECT, HAVING, ORDER BY.

## Common traps

1. `COUNT(col)` and `AVG(col)` silently skip NULLs: `AVG(commission_pct)` is .2, not .0889.
2. `SUM` over no rows is NULL, not 0. Wrap in `NVL(SUM(x), 0)` when you need a number.
3. An aggregate without GROUP BY always returns one row, even from an empty table;
   with GROUP BY an empty input returns no rows.
4. `COUNT(DISTINCT col)` does not count NULL; `GROUP BY col` does make a NULL group.
5. Selecting a column next to a nested group function (ORA-00937), or nesting without
   GROUP BY (ORA-00978), or three levels deep (ORA-00935).
6. Aliases: usable in ORDER BY only, never in WHERE, GROUP BY or HAVING (19c).
7. `GROUP BY 1` is not "the first column".
8. A filter on a group function in WHERE (ORA-00934), a plain column in HAVING (ORA-00979).

> **Oracle vs. standard SQL / other databases**
>
> - MySQL (without `ONLY_FULL_GROUP_BY`) lets you select non-grouped columns and returns an
>   arbitrary value; Oracle always raises ORA-00979.
> - PostgreSQL, MySQL and SQL Server-style `GROUP BY 1` / `GROUP BY alias` are not valid
>   in Oracle 19c. Oracle 23ai adds GROUP BY aliases and positions (positions need
>   `group_by_position_enabled`).
> - Nested aggregates such as `MAX(AVG(x))` are an Oracle extension; the standard (and
>   PostgreSQL) require a subquery.
> - `LISTAGG` is Oracle's (and SQL:2016's) string aggregation; PostgreSQL uses `STRING_AGG`,
>   MySQL `GROUP_CONCAT`.
> - Oracle treats `''` as NULL, so empty strings are ignored by `COUNT(col)` as well.
