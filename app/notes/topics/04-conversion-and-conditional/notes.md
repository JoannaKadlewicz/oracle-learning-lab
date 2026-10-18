# Topic 4: Conversion Functions and Conditional Expressions

Environment: Oracle Database 19.3, schema ORASTUDY, English (AMERICAN) session with
`NLS_DATE_FORMAT = 'YYYY-MM-DD HH24:MI:SS'`. The examples were **executed**, partly via
`setup/run_sql.sh topics/04-conversion-and-conditional/examples.sql`, partly in the study app.
Brackets `[...]` in a result show leading or trailing blanks.

Oracle is strict about types but will also convert silently, which is the main source of
trouble: implicit conversions depend on session NLS settings, and NULL propagates through
almost every expression. The exam probes both.

## 5.1 NVL, NULLIF, COALESCE (and NVL2, CASE, DECODE)

| Function | Returns | Key rule |
|---|---|---|
| `NVL(a, b)` | `b` if `a` is NULL | Exactly two arguments; `b` is converted to `a`'s type |
| `NVL2(a, x, y)` | `x` if `a` NOT NULL, else `y` | Not-null branch first; result has the type of `x` |
| `COALESCE(a, b, ...)` | First non-NULL | Any number of args, same type family (else **ORA-00932**); short-circuits |
| `NULLIF(a, b)` | NULL if `a = b`, else `a` | `a` cannot be the literal NULL (**ORA-00932**) |
| `CASE` | First matching branch | ANSI; simple CASE uses `=`, so `WHEN NULL` never matches |
| `DECODE(e, s1, r1, ..., default)` | Oracle-only | NULL = NULL is a match; no default → NULL |

NULL arithmetic: any arithmetic with NULL gives NULL.

```sql
e.salary * 12 * (1 + e.commission_pct)          -- NULL if commission is NULL
e.salary * 12 * (1 + NVL(e.commission_pct, 0))
```

| EMPLOYEE_ID | SALARY | COMMISSION_PCT | ANNUAL_RAW | ANNUAL_NVL | NULLIF(salary, 6000) |
|---|---|---|---|---|---|
| 100 | 24000 | NULL | NULL | 288000 | 24000 |
| 101 | 14000 | .3 | 218400 | 218400 | 14000 |
| 104 | 6000 | NULL | NULL | 72000 | NULL |
| 105 | 6000 | .2 | 86400 | 86400 | NULL |

`NULLIF` is the usual guard against division by zero: `x / NULLIF(y, 0)`.

CASE vs DECODE with NULL (employee 108 has no department):

| Expression | Result for 108 |
|---|---|
| `CASE e.department_id WHEN NULL THEN 'none' ELSE 'some' END` | `some` |
| `CASE WHEN e.department_id IS NULL THEN 'none' ELSE 'some' END` | `none` |
| `DECODE(e.department_id, NULL, 'none', 'some')` | `none` |

More rules, all executed:

- A searched CASE returns the **first** true branch: with `WHEN salary > 5000 THEN 'MID' WHEN salary > 10000 THEN 'HIGH'`
  King (24000) gets `MID`.
- All CASE results must be one type family: `CASE WHEN ... THEN 'none' ELSE e.commission_pct END` → **ORA-00932**.
- `DECODE(e.job_title, 'Programmer', 'IT', 'Sales Rep', 'Sales')` is NULL for 3 employees (no default).
- `NVL(e.commission_pct, 'none')` → **ORA-01722** (`'none'` → NUMBER). `NVL(TO_CHAR(e.commission_pct), 'none')` works.
- `NVL2(e.commission_pct, e.commission_pct, 'none')` → **ORA-01722**; `COALESCE(e.commission_pct, '0')` → **ORA-00932**;
  `NVL(e.email, 0)` and `NVL(e.commission_pct, '0')` work (the second argument is converted).

## 5.2 Implicit versus explicit conversion

| Expression | Result | Why |
|---|---|---|
| `'10' + 5` | `15` | `+` needs numbers: the string is converted |
| `'10' \|\| 5` | `105` | `\|\|` needs strings: the number is converted |
| `LENGTH(12345)` | `5` | LENGTH expects a string |
| `WHERE e.employee_id = '101'` | works | The string is converted to NUMBER |
| `WHERE e.email = 100` | **ORA-01722** | The *column* is converted to NUMBER, and `SKING` fails |
| `CASE WHEN '5' > '10' ...` | true | Two strings compare character by character |
| `'Hired: ' \|\| e.hire_date` | `Hired: 2015-06-17 00:00:00` | DATE → text via NLS_DATE_FORMAT |
| `o.order_date > '31/03/2024'` | **ORA-01861** | String → DATE via NLS_DATE_FORMAT, which expects `YYYY-MM-DD ...` |

The last query can work in a session with a `DD/MM/YYYY` format, which is exactly why to avoid
implicit conversion. Prefer `DATE 'YYYY-MM-DD'` literals or `TO_DATE` / `TO_CHAR` / `TO_NUMBER`
with an explicit mask.

## 5.3 TO_CHAR, TO_NUMBER and TO_DATE

Dates (`DATE '2024-03-05'`, a Tuesday; order 1006 = `2024-03-31 23:30`):

| Mask | Result |
|---|---|
| `'DD-MON-YYYY'` | `05-MAR-2024` |
| `'Day'` | `[Tuesday  ]` (padded to 9, the length of Wednesday) |
| `'fmDD Month'` | `5 March` |
| `'Day, DDth Month YYYY'` | `Tuesday  , 05TH March     2024` (padded) |
| `'fmDay, DDth Month YYYY'` | `Tuesday, 5TH March 2024` |
| `'fmMonth ddth, YYYY'` | `March 5th, 2024` |
| `'Ddspth'`, `'DDSPTH'`, `'Ddsp'` | `Fifth`, `FIFTH`, `Five` |
| order 1006 `'HH24:MI'`, `'HH24:MM'`, `'HH:MI AM'` | `23:30`, `23:03` (MM = month!), `11:30 PM` |

- Case of the element controls case of output: `MON` → `MAR`, `Mon` → `Mar`; `DDth` → `05TH`, `ddth` → `05th`.
- `fm` removes padding and leading zeros, and toggles: a second `fm` turns it off again.
- Literal text goes in double quotes: `'DD "of" Month'`.
- AM and PM in a mask are interchangeable: both print the actual meridian.

Numbers:

| Expression | Result |
|---|---|
| `TO_CHAR(1234.5, '9,999.99')` | `[ 1,234.50]` (leading blank reserved for the sign) |
| `TO_CHAR(1234.5, 'fm9,999.99')` | `[1,234.5]` (fm also drops trailing zeros in 9 positions) |
| `TO_CHAR(1234.5, 'fm9,999.00')` | `[1,234.50]` |
| `TO_CHAR(1234.5, '999.99')` | `#######` (too small: no error, mask width + 1 hashes) |
| `TO_CHAR(0.5, '0.99')`, `TO_CHAR(0.5, '9.99')` | `[ 0.50]`, `[  .50]` |
| `TO_NUMBER('$1,234.50', '$9,999.99')` | `1234.5` (without the mask: **ORA-01722**) |

Strings to dates:

| Expression | Result |
|---|---|
| `TO_DATE('31/03/2024', 'DD/MM/YYYY')` | works in any session |
| `TO_DATE('2024/03/05', 'YYYY-MM-DD')`, `TO_DATE('2024-3-5', 'YYYY-MM-DD')` | work: punctuation and leading zeros are flexible |
| `TO_DATE('2024-3-5', 'fxYYYY-MM-DD')` | **ORA-01862**: `fx` requires an exact match |
| `TO_DATE('2024-02-30', 'YYYY-MM-DD')` | **ORA-01839**: date not valid for month |
| `TO_DATE('15-03-75', 'DD-MM-RR')`, `'DD-MM-YY'` | 1975, 2075 (current year 2000-2049) |

RR: in years 00-49 of a century, two-digit years 50-99 go to the previous century. YY always uses
the current century.

## 5.4 Nesting multiple functions

Nested single-row functions are evaluated from the innermost outward, and can be nested to any
depth (group functions: at most two levels).

```sql
SELECT UPPER(SUBSTR(LPAD(e.last_name, 8, '*'), 1, 4))     -- ****King -> **** -> ****
FROM   employees e WHERE e.employee_id = 100;

SELECT NVL(TO_CHAR(e.manager_id), 'No manager')            -- inner TO_CHAR makes the types match
FROM   employees e;

SELECT TO_CHAR(NEXT_DAY(ADD_MONTHS(e.hire_date, 6), 'FRIDAY'),
               'fmDay, Month ddth, YYYY')                  -- Friday, December 18th, 2015 for King
FROM   employees e WHERE e.employee_id = 100;
```

`LENGTH(TRIM(LPAD('ab', 5)))` = 2: LPAD pads with blanks, TRIM removes them again.
`NVL(e.manager_id, 'No manager')` fails (ORA-01722) and `TO_CHAR(NVL(...))` converts too late.

## Common traps

1. Expecting `CASE x WHEN NULL` to match NULLs (it never does; DECODE does).
2. Mixing types: `NVL`/`NVL2` convert to the type of the first (NVL2: second) argument and may raise
   ORA-01722; `COALESCE` and `CASE` raise ORA-00932 instead.
3. Forgetting `NVL2` order: the second argument is for NOT NULL.
4. `DECODE` without a default returns NULL for unmatched values.
5. A searched CASE stops at the first true branch: order the conditions from most to least selective.
6. Comparing a VARCHAR2 column with a number converts the column (ORA-01722, no index use).
7. Relying on implicit string-to-date conversion (depends on NLS_DATE_FORMAT).
8. `MM` (month) vs `MI` (minutes); `HH` is 12-hour, `HH24` is 24-hour.
9. Forgetting the padding of `Day`/`Month` and the leading sign blank in number masks.
10. `fm` with `9` after the decimal point drops trailing zeros; use `0` for fixed decimals.
11. Assuming `TO_CHAR` with a too-small mask errors; it returns `#`s.
12. Using `BETWEEN` with date-only bounds on `DATE` columns holding times.

> **Oracle vs. standard SQL / other databases**
>
> - Portable (ANSI): `CASE`, `COALESCE`, `NULLIF`, `CAST(x AS type)`.
> - Oracle-specific: `NVL`, `NVL2`, `DECODE`, `TO_CHAR`/`TO_DATE`/`TO_NUMBER` format models, `DUAL`.
>   SQL Server uses `ISNULL`, `CONVERT` and `FORMAT`; MySQL uses `IFNULL`, `DATE_FORMAT`, `STR_TO_DATE`;
>   PostgreSQL has `TO_CHAR`/`TO_DATE` with similar masks but no `NVL`.
> - Oracle treats the empty string `''` as NULL (unlike PostgreSQL and SQL Server), so
>   `NVL('', 'x')` returns `x`.
> - Oracle silently converts between strings and numbers/dates in comparisons; PostgreSQL is stricter and
>   raises a type error for many of the same comparisons.

## Oracle 23ai differences (1Z0-171)

Executed on Oracle AI Database 23ai (23.26, schema ORASTUDY) and compared with 19c. NVL, NVL2,
NULLIF, COALESCE, CASE, DECODE, implicit conversion rules and TO_CHAR/TO_DATE/TO_NUMBER format
models (fm, fx, RR/YY, L, G/D, PR, MI) give the same results and the same ORA- codes.

| Expression | 19c | 23ai |
|---|---|---|
| `NVL(e.commission_pct, 'none')` | ORA-01722: invalid number | ORA-01722: unable to convert string value containing 'n' to a number |
| `NULLIF(1, 'a')` | ORA-00932: inconsistent datatypes | ORA-00932: expression ('a') is of data type CHAR, which is incompatible with expected data type NUMBER |
| `TO_DATE(' 5-MAR-2024', 'fxDD-MON-YYYY')` | ORA-01858 | ORA-01858 (reworded message) |
| `TO_CHAR(TRUE)`, `TO_NUMBER(TRUE)`, `TO_NUMBER(FALSE)` | ORA-00904 (no BOOLEAN) | `TRUE`, `1`, `0` |
| `TO_BOOLEAN('yes')`, `TO_BOOLEAN(0)` | ORA-00904 | TRUE, FALSE |
| `'10' + TRUE` | ORA-00904 | `11` (BOOLEAN converts implicitly to 1/0) |
| `CASE WHEN 1 = 1 THEN TRUE ELSE FALSE END`, `DECODE(TRUE, TRUE, 'y', 'n')` | ORA-00904 | TRUE, `y` |
| `WHERE e.salary > 5000 IS TRUE` | ORA-00933 | 6 rows |

- Same codes, new wording: exam answers about ORA-01722, ORA-00932, ORA-01830, ORA-01843 and
  ORA-01858 stay valid; only the message text names the offending value or type.
- BOOLEAN (TRUE/FALSE, TO_BOOLEAN, IS TRUE) is a 23ai feature, covered in t15.
