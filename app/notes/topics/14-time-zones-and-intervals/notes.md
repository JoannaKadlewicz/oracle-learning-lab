# Topic 14: Time Zones and Intervals

Environment: Oracle Database 19c, schema ORASTUDY. All results below were **executed**.
Expressions use explicit zones so that they do not depend on the session time zone; where a
result does depend on the session (`ALTER SESSION SET TIME_ZONE`), this is stated.
Table `events`: `starts_at TIMESTAMP(0) WITH TIME ZONE`, `logged_at TIMESTAMP(0) WITH LOCAL
TIME ZONE`, `duration INTERVAL DAY(2) TO SECOND(0)`, `warranty INTERVAL YEAR(2) TO MONTH`.
Objectives 16.1–16.2.

## Concept: the datetime types

| Type | Stores | Shown as |
|---|---|---|
| `DATE` | date + time to the second, no zone | as stored |
| `TIMESTAMP(p)` | + fractional seconds, no zone | as stored |
| `TIMESTAMP WITH TIME ZONE` | + offset (`+01:00`) or region (`Europe/Warsaw`) | in its own zone |
| `TIMESTAMP WITH LOCAL TIME ZONE` | normalized to `DBTIMEZONE`, zone not kept | in the **session** time zone |
| `INTERVAL YEAR(p) TO MONTH` | years and months | `+01-06` |
| `INTERVAL DAY(p) TO SECOND(s)` | days, hours, minutes, seconds | `+02 10:30:00` |

## 16.1 CURRENT_DATE, CURRENT_TIMESTAMP and LOCALTIMESTAMP

| Function | Data type (executed via CTAS) | Time zone used |
|---|---|---|
| `SYSDATE` | DATE | database host OS |
| `SYSTIMESTAMP` | TIMESTAMP(6) WITH TIME ZONE | database host OS |
| `CURRENT_DATE` | DATE | session |
| `CURRENT_TIMESTAMP` | TIMESTAMP(6) WITH TIME ZONE | session |
| `LOCALTIMESTAMP` | TIMESTAMP(6) | session |

- After `ALTER SESSION SET TIME_ZONE = '-05:00'`: CURRENT_DATE 15:03, SYSDATE 20:03,
  `CURRENT_TIMESTAMP` 15:03 -05:00, `SYSTIMESTAMP` 20:03 +00:00. `SESSIONTIMEZONE` changes; `DBTIMEZONE` does not.
- `CAST(CURRENT_TIMESTAMP AS TIMESTAMP) = LOCALTIMESTAMP` is true: same instant, same zone.
- `CURRENT_TIMESTAMP(0)` / `LOCALTIMESTAMP(2)` take a fractional-second precision.

Converting and inspecting zones:

| Expression | Result |
|---|---|
| `TIMESTAMP '2024-01-15 08:00:00 Europe/Warsaw' AT TIME ZONE 'America/New_York'` | 02:00 EST |
| `... AT TIME ZONE '+05:30'` (July) | 11:30 +05:30 |
| `FROM_TZ(TIMESTAMP '2024-07-01 12:00:00', '-04:00')` | 12:00 -04:00 (attaches, does not convert) |
| `FROM_TZ(DATE '2024-07-01', 'UTC')` | ORA-00932: expected TIMESTAMP got DATE |
| `TO_TIMESTAMP_TZ('2024-07-01 12:00 -04:00', 'YYYY-MM-DD HH24:MI TZH:TZM') AT TIME ZONE 'Asia/Tokyo'` | 2024-07-02 01:00 |
| `SYS_EXTRACT_UTC(TIMESTAMP '2024-03-31 23:30:00 America/New_York')` | 2024-04-01 03:30 |
| `TZ_OFFSET('-05:00')`, `TZ_OFFSET('UTC')` | -05:00, +00:00 |
| `TZ_OFFSET(SYSTIMESTAMP)` | ORA-01882: timezone region not found |
| `... AT TIME ZONE 'Mars/Base'` | ORA-01882 |

`TZ_OFFSET('Europe/Warsaw')` returns the offset in force **today** (+01:00 or +02:00).

EXTRACT on `events.starts_at`:

| event | stored | `TIMEZONE_REGION` | `TIMEZONE_HOUR` | `TIMEZONE_ABBR` | `HOUR` |
|---|---|---|---|---|---|
| 1 | 2024-03-31 01:30 Europe/Warsaw | Europe/Warsaw | 1 | CET | **0** |
| 2 | 2024-02-29 09:00 +00:00 | UNKNOWN | 0 | UNK | 9 |
| 3 | 2024-03-31 23:30 America/New_York | America/New_York | -4 | EDT | **3** |

EXTRACT of HOUR/DAY/... from a value with a time zone returns **UTC** fields (event 3: day 1,
hour 3). `TO_CHAR(starts_at, 'HH24')` and `CAST(starts_at AS DATE)` keep local time (23:30).

Daylight saving time with region names (Warsaw switched at 02:00 on 2024-03-31):

- `TIMESTAMP '2024-03-31 02:30:00 Europe/Warsaw'` → **ORA-01878** (that local time does not exist).
- `TIMESTAMP '2024-03-31 01:30:00 Europe/Warsaw' + INTERVAL '1' HOUR` → 03:30 CEST.
- `TIMESTAMP '2024-03-31 01:30:00 Europe/Warsaw' = TIMESTAMP '2024-03-31 00:30:00 UTC'` → equal
  (comparisons use the UTC instant); with `+02:00` instead → not equal.
- `logged_at` (WITH LOCAL TIME ZONE) of event 3 shows 2024-04-01 05:30 in a +02:00 session,
  2024-03-31 22:30 in a -05:00 session, and 2024-04-01 03:30 in UTC.

## 16.2 INTERVAL data types

| Expression | Result |
|---|---|
| `INTERVAL '1-6' YEAR TO MONTH`, `INTERVAL '18' MONTH`, `TO_YMINTERVAL('01-06')`, `NUMTOYMINTERVAL(18, 'MONTH')` | +01-06 |
| `INTERVAL '2 10:30:00' DAY TO SECOND`, `TO_DSINTERVAL('2 10:30:00')` | +02 10:30:00 |
| `INTERVAL '90' MINUTE`, `NUMTODSINTERVAL(90, 'MINUTE')` | +00 01:30:00 |
| `NUMTODSINTERVAL(100, 'HOUR')`, `INTERVAL '100' HOUR` | +04 04:00:00 |
| `INTERVAL '123' DAY` | ORA-01873 (default leading precision 2; use `DAY(3)`) |
| `INTERVAL '1 25' DAY TO HOUR` / `INTERVAL '1-12' YEAR TO MONTH` | ORA-01850 / ORA-01843 |
| `NUMTODSINTERVAL(1, 'MONTH')`, `NUMTOYMINTERVAL(1, 'DAY')` | ORA-01760 |
| `TO_YMINTERVAL('1.5')` | ORA-01867; ISO `TO_YMINTERVAL('P1Y2M')` works |
| `INTERVAL '1-6' YEAR TO MONTH + INTERVAL '8' MONTH` | +02-02 |
| `INTERVAL '1-6' YEAR TO MONTH / 2`, `INTERVAL '1' DAY * 1.5` | +00-09, +01 12:00:00 |
| `INTERVAL '1' DAY + INTERVAL '1' MONTH` | ORA-30081 |
| `EXTRACT(HOUR FROM INTERVAL '2 10:30:00' DAY TO SECOND)` | 10 (one field, not the total) |
| `SUM(duration)` | ORA-00932 in 19c (23ai adds SUM/AVG over intervals) |

Result types of datetime arithmetic (executed via CTAS):

| Expression | Result type |
|---|---|
| `TIMESTAMP - TIMESTAMP` | INTERVAL DAY TO SECOND (`+02 02:30:00`) |
| `TIMESTAMP - DATE` | INTERVAL DAY TO SECOND |
| `DATE - DATE` | NUMBER (days) |
| `TIMESTAMP + 1` | **DATE** |
| `TIMESTAMP + INTERVAL '1' HOUR` | TIMESTAMP |
| `DATE + INTERVAL '1' HOUR` | DATE |

Month arithmetic does not adjust the day:

- `DATE '2024-01-31' + INTERVAL '1' MONTH` → ORA-01839; `DATE '2024-03-31' - INTERVAL '1' MONTH` → ORA-01839.
- `DATE '2024-02-29' + INTERVAL '1' YEAR` → ORA-01839, but `+ INTERVAL '4' YEAR` → 2028-02-29.
- `ADD_MONTHS(DATE '2024-02-29', 12)` → 2025-02-28 (ADD_MONTHS moves to the last day of the month).

## Common traps

1. EXTRACT(HOUR ...) of a TIMESTAMP WITH TIME ZONE is in UTC, not local time.
2. EXTRACT(HOUR FROM a DATE) fails (ORA-30076); only YEAR, MONTH, DAY work on DATE.
3. Mixing YEAR TO MONTH and DAY TO SECOND intervals (ORA-30081).
4. `+ INTERVAL 'n' MONTH/YEAR` on day 29–31 can fail with ORA-01839; ADD_MONTHS never does.
5. The default leading precision is 2: `INTERVAL '123' DAY` fails.
6. SYSDATE/SYSTIMESTAMP follow the server OS, not SESSIONTIMEZONE or DBTIMEZONE.
7. FROM_TZ attaches a zone; AT TIME ZONE converts. FROM_TZ needs a TIMESTAMP, not a DATE.
8. TIMESTAMP + 1 silently becomes a DATE and loses fractional seconds.
9. A region name applies daylight saving rules (gap times fail with ORA-01878); a fixed offset does not.
10. TIMESTAMP WITH LOCAL TIME ZONE does not remember the original zone; the displayed value
    depends on the session.

> **Oracle vs. standard SQL / other databases**
> - `CURRENT_DATE`, `CURRENT_TIMESTAMP`, `LOCALTIMESTAMP`, `EXTRACT`, `AT TIME ZONE` and interval
>   literals are ANSI. `SYSDATE`, `SYSTIMESTAMP`, `FROM_TZ`, `TZ_OFFSET`, `NUMTODSINTERVAL` and
>   `TO_YMINTERVAL` are Oracle-specific.
> - Oracle's `CURRENT_DATE` is a DATE **with** a time; in standard SQL and PostgreSQL it is a date only.
> - PostgreSQL has one `interval` type that mixes months and days and adjusts `'2024-01-31' + interval '1 month'`
>   to 2024-02-29; Oracle raises ORA-01839. SQL Server has no interval type (`DATEADD` / `DATEDIFF`).
> - PostgreSQL's `timestamptz` behaves like Oracle's WITH LOCAL TIME ZONE (stores UTC, shows the session zone);
>   Oracle's WITH TIME ZONE keeps the original zone, like SQL Server's `datetimeoffset` (offsets only).
