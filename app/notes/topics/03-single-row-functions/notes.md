# Topic 3: Single-Row Functions

Environment: Oracle Database 19c, schema ORASTUDY, session `NLS_DATE_FORMAT = 'YYYY-MM-DD HH24:MI:SS'`,
`NLS_DATE_LANGUAGE = AMERICAN`. Every result below was executed against the sample data.
Brackets `[...]` in a result show leading or trailing blanks.

Single-row functions return one value per row. They can appear in SELECT, WHERE, ORDER BY,
HAVING and SET clauses, and they never change stored data.

## 4.1 Character functions

| Expression | Result | Rule |
|---|---|---|
| `UPPER('King')`, `LOWER('King')`, `INITCAP('o''neil mc-DONALD')` | `KING`, `king`, `O'Neil Mc-Donald` | INITCAP starts a new word after any non-alphanumeric character |
| `CONCAT('a', 'b')` | `ab` | Exactly two arguments; three raise **ORA-00909** |
| `LENGTH('De Haan')`, `LENGTH('')` | `7`, NULL | `''` is NULL in Oracle |
| `SUBSTR('ORACLE SQL', -3, 2)` | `SQ` | Negative start counts from the end; length still goes right |
| `SUBSTR('ORACLE', 0, 3)` | `ORA` | Position 0 is treated as 1 |
| `SUBSTR('De Haan', 4, -4)` | NULL | Length < 1 gives NULL |
| `INSTR('BANANA', 'AN', 1, 2)` | `4` | (string, search, start, occurrence); 0 if not found |
| `INSTR('BANANA', 'A', -1, 2)` | `4` | Negative start searches backwards from the end |
| `LPAD('42', 5, '*')`, `RPAD('42', 5, '*')` | `***42`, `42***` | Length is the *total* length |
| `LPAD('ORACLE', 3)` | `ORA` | Shorter target length truncates (keeps the left part) |
| `LPAD('ab', 5)` | `[   ab]` | Default pad character is a blank |
| `REPLACE('banana', 'an')` | `ba` | Missing/NULL replacement removes every match |
| `TRIM('x' FROM 'xxaxx')` | `a` | `TRIM([LEADING\|TRAILING\|BOTH] char FROM s)` |
| `TRIM('xy' FROM 'xyaxy')` | **ORA-30001** | TRIM takes one character only |
| `RTRIM('ORACLE', 'CLE')`, `LTRIM('ORACLE', 'CLE')` | `ORA`, `ORACLE` | LTRIM/RTRIM remove any characters *in the set* |

Case-insensitive search: convert the column, not just the literal.

```sql
SELECT e.employee_id FROM employees e WHERE UPPER(e.last_name) = 'KING';   -- 100
SELECT e.employee_id FROM employees e WHERE e.last_name = 'KING';          -- no rows
```

## 4.2 Arithmetic with dates

A DATE always holds a time (to the second). Numbers added to a DATE are **days**.

| Expression | Result type | Example |
|---|---|---|
| `DATE + n`, `DATE - n` | DATE | `DATE '2024-03-01' - 0.5` = `2024-02-29 12:00:00` |
| `DATE - DATE` | NUMBER (days) | `DATE '2024-03-10' - DATE '2024-03-01'` = `9` |
| `DATE + DATE` | error | **ORA-00975: date + date not allowed** |
| `DATE + n/24`, `DATE + n/1440` | DATE | hours, minutes: order 1006 `+ 90/1440` = `2024-04-01 01:00:00` |

```sql
SELECT o.order_date - DATE '2024-03-01'          AS diff,   -- 30.9791666...
       TRUNC(o.order_date - DATE '2024-03-01')   AS t       -- 30 (numeric TRUNC)
FROM   orders o WHERE o.order_id = 1006;
```

Hours between two DATEs: `(d2 - d1) * 24`; 09:30 to 18:00 gives `8.5`.

## 4.3 ROUND, TRUNC and MOD

| Expression | Result | Note |
|---|---|---|
| `ROUND(1234.567, -2)`, `TRUNC(1234.567, 1)` | `1200`, `1234.5` | Negative precision works left of the point |
| `ROUND(45.926, 1)`, `TRUNC(45.96, 1)`, `ROUND(45.96, 1)` | `45.9`, `45.9`, `46` | |
| `ROUND(-2.5)`, `ROUND(2.5)` | `-3`, `3` | Halves round away from zero (NUMBER) |
| `TRUNC(-2.7)`, `FLOOR(-2.7)` | `-2`, `-3` | TRUNC goes toward zero |
| `MOD(-7, 3)` | `-1` | Sign of the dividend |
| `MOD(10, 0)` | `10` | No division-by-zero error |

`WHERE MOD(e.salary, 1000) = 0` keeps 6 of the 9 employees; `MOD(e.employee_id, 2) = 0` finds even ids.

## 4.4 Date functions

| Expression | Result |
|---|---|
| `ADD_MONTHS(DATE '2024-01-31', 1)` | `2024-02-29` (last-day rule) |
| `ADD_MONTHS(DATE '2023-02-28', 1)` | `2023-03-31` (28 Feb 2023 *is* a month end) |
| `ADD_MONTHS(DATE '2024-02-28', 1)` | `2024-03-28` |
| `MONTHS_BETWEEN(DATE '2024-03-31', DATE '2024-02-29')` | `1` (both month ends) |
| `MONTHS_BETWEEN(DATE '2024-03-16', DATE '2024-02-15')` | `1.0322...` (1 + 1/31) |
| `MONTHS_BETWEEN(DATE '2024-01-01', DATE '2024-03-01')` | `-2` (first earlier → negative) |
| `NEXT_DAY(DATE '2024-03-05', 'TUESDAY')` (a Tuesday) | `2024-03-12` (strictly later) |
| `LAST_DAY(order 1006)` | `2024-03-31 23:30:00` (keeps the time) |
| `ROUND(DATE '2024-07-16', 'MM')`, `ROUND(DATE '2024-07-15', 'MM')` | `2024-08-01`, `2024-07-01` |
| `ROUND(DATE '2024-07-01', 'YYYY')`, `ROUND(DATE '2024-06-30', 'YYYY')` | `2025-01-01`, `2024-01-01` |
| `TRUNC(order 1006)`, `TRUNC(order 1006, 'MM')` | `2024-03-31 00:00:00`, `2024-03-01 00:00:00` |

Day names in NEXT_DAY depend on `NLS_DATE_LANGUAGE`. `TRUNC(d, 'DAY')` depends on `NLS_TERRITORY`
(the first day of the week).

Selecting a whole month when DATEs hold times:

```sql
WHERE o.order_date >= DATE '2024-03-01' AND o.order_date < DATE '2024-04-01'  -- 1004, 1005, 1006
WHERE TRUNC(o.order_date, 'MM') = DATE '2024-03-01'                           -- same rows
WHERE o.order_date BETWEEN DATE '2024-03-01' AND DATE '2024-03-31'            -- misses 1006 (23:30)
```

## Common traps

1. `CONCAT` with three arguments: ORA-00909. Use `||`.
2. `TRIM` with a multi-character set: ORA-30001. Use `LTRIM`/`RTRIM`.
3. `LTRIM`/`RTRIM` remove a *set* of characters, not a prefix: `LTRIM('De Haan', 'De')` = `' Haan'`.
4. `SUBSTR(s, -3, 2)` reads to the right from the third-last character.
5. `INSTR` returns 0 (not NULL) when not found.
6. `LENGTH('')` is NULL, not 0.
7. `ROUND(2.5)` = 3 (not banker's rounding); `TRUNC(-2.7)` = -2.
8. `MOD(10, 0)` = 10; `MOD(-7, 3)` = -1.
9. `DATE + DATE` is an error; `DATE - DATE` is a NUMBER, not an INTERVAL.
10. `NEXT_DAY` never returns the same day; `LAST_DAY` and `ADD_MONTHS` keep the time.
11. `ADD_MONTHS` from a month end lands on a month end (28 Feb 2023 + 1 = 31 Mar).
12. `BETWEEN ... AND DATE '2024-03-31'` excludes times later than midnight on the 31st.

> **Oracle vs. standard SQL / other databases**
>
> - `CONCAT` takes any number of arguments in MySQL and PostgreSQL; Oracle allows two.
> - Oracle treats `''` as NULL; PostgreSQL and SQL Server keep an empty string of length 0.
> - `SUBSTR`/`INSTR` are Oracle names; the standard has `SUBSTRING(s FROM n FOR m)` and
>   `POSITION(x IN s)`. SQL Server uses `SUBSTRING`, `CHARINDEX` and `LEN`.
> - `DATE` in Oracle includes a time; in the SQL standard, PostgreSQL and MySQL a `DATE` has no time.
> - `DATE + n` (days) is Oracle-specific; standard SQL adds `INTERVAL` values, which Oracle also supports.
> - `ADD_MONTHS`, `MONTHS_BETWEEN`, `NEXT_DAY`, `LAST_DAY` (Oracle) correspond to `DATEADD`/`DATEDIFF`
>   (SQL Server) and `+ INTERVAL`/`AGE` (PostgreSQL).
> - Python's `%` takes the sign of the divisor (`-7 % 3` = 2); Oracle's `MOD` takes the dividend's.
