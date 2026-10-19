# Topic 4 Exercises

Schema: ORASTUDY (`setup/01_create_tables.sql`, `setup/02_seed_data.sql`).
Run with `setup/run_sql.sh <file.sql>`. Do not look at `solutions.sql` until you have attempted them
(it will be created after you submit).

## Exercise 1 (Basic): NULL-safe display

**Objective:** NVL / NVL2 and type rules.

For every employee, return:
- `employee_id`
- `commission_display`: the commission as a percentage string such as `30%`, or `No commission` if NULL
- `has_manager`: `Y` if `manager_id` is not NULL, else `N`

Order by `employee_id`. Expected: 9 rows; employee 101 shows `30%`, employee 100 shows `No commission` and `N`.

## Exercise 2 (Intermediate): Salary bands and formatting

**Objective:** CASE, TO_CHAR number masks, and date formatting.

For employees in departments 20 and 30, return:
- `last_name`
- `salary_fmt`: salary formatted like `$14,000.00` with no leading space
- `band`: `HIGH` if salary >= 10000, `MID` if salary >= 5000, else `LOW`
- `hired`: hire date formatted like `March 2019` (no padding)

Order by salary descending, then `last_name` ascending. Expected: 7 rows.

## Exercise 3 (Advanced): Predict, then explain

Without running them first, predict the result of each query and explain why. Then run them.

```sql
-- a)
SELECT DECODE(NULL, NULL, 'match', 'no match') AS r FROM dual;

-- b)
SELECT CASE NULL WHEN NULL THEN 'match' ELSE 'no match' END AS r FROM dual;

-- c)
SELECT COUNT(*) AS cnt
FROM   orders o
WHERE  TRUNC(o.order_date) = DATE '2024-03-31';

-- d)
SELECT NVL2(NULLIF('A', 'A'), 'x', 'y') AS r FROM dual;

-- e)
SELECT COALESCE(NULL, 1, 'two') AS r FROM dual;
```
