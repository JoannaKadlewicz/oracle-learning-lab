-- Temat 4: Funkcje konwersji i wyrażenia warunkowe
-- Cel: Oracle Database 19c, schemat ORASTUDY (setup/01 + setup/02).
-- Sesja: setup/run_sql.sh ustawia NLS_DATE_FORMAT na 'YYYY-MM-DD HH24:MI:SS';
-- każdy przykład, który pokazuje datę, i tak używa jawnie TO_CHAR.

PROMPT === Example 1: NULL arithmetic and NULL-handling functions ===
SELECT e.employee_id,
       e.salary,
       e.commission_pct,
       e.salary * 12 * (1 + e.commission_pct)          AS annual_raw,
       e.salary * 12 * (1 + NVL(e.commission_pct, 0))  AS annual_nvl,
       NVL2(e.commission_pct, 'Commissioned', 'Base')  AS pay_type,
       COALESCE(e.commission_pct, e.salary / 100000, 0) AS coalesce_demo,
       NULLIF(e.salary, 6000)                           AS nullif_6000
FROM   employees e
WHERE  e.employee_id IN (100, 101, 104, 105)
ORDER  BY e.employee_id;

PROMPT === Example 2: CASE vs DECODE when comparing with NULL ===
SELECT e.employee_id,
       e.department_id,
       CASE e.department_id WHEN NULL THEN 'No dept' ELSE 'Has dept' END AS simple_case,
       CASE WHEN e.department_id IS NULL THEN 'No dept' ELSE 'Has dept' END AS searched_case,
       DECODE(e.department_id, NULL, 'No dept', 'Has dept')              AS decode_result
FROM   employees e
WHERE  e.employee_id IN (100, 108)
ORDER  BY e.employee_id;

PROMPT === Example 3: TO_CHAR format models and fm ===
SELECT TO_CHAR(DATE '2024-03-05', 'DD-MON-YYYY')         AS d1,
       TO_CHAR(DATE '2024-03-05', 'Day, DDth Month YYYY') AS d2_padded,
       TO_CHAR(DATE '2024-03-05', 'fmDay, DDth Month YYYY') AS d3_fm,
       TO_CHAR(1234.5, '9,999.99')                        AS n1,
       TO_CHAR(1234.5, '999.99')                          AS n2_too_small,
       TO_CHAR(0.5, '0.00')                               AS n3,
       TO_CHAR(0.5, '9.99')                               AS n4
FROM   dual;

PROMPT === Example 4: DATE always has a time component ===
SELECT o.order_id,
       TO_CHAR(o.order_date, 'YYYY-MM-DD HH24:MI:SS') AS order_ts
FROM   orders o
WHERE  o.order_date BETWEEN DATE '2024-03-01' AND DATE '2024-03-31'
ORDER  BY o.order_id;

PROMPT --- Fixed: half-open range
SELECT o.order_id,
       TO_CHAR(o.order_date, 'YYYY-MM-DD HH24:MI:SS') AS order_ts
FROM   orders o
WHERE  o.order_date >= DATE '2024-03-01'
AND    o.order_date <  DATE '2024-04-01'
ORDER  BY o.order_id;

PROMPT === Example 5: NVL argument data types ===
PROMPT --- 5a: works, the second argument is converted to the first argument's type
SELECT NVL(e.email, 'n/a') AS email_or_na
FROM   employees e
WHERE  e.employee_id = 108;

PROMPT --- 5b: fails, 'none' cannot be converted to NUMBER
SELECT NVL(e.commission_pct, 'none') AS commission
FROM   employees e
WHERE  e.employee_id = 100;

PROMPT --- 5c: fix with explicit conversion
SELECT NVL(TO_CHAR(e.commission_pct), 'none') AS commission
FROM   employees e
WHERE  e.employee_id = 100;

PROMPT === Example 6: TO_DATE with a format model vs implicit conversion ===
SELECT TO_CHAR(TO_DATE('31/03/2024', 'DD/MM/YYYY'), 'YYYY-MM-DD') AS explicit_ok
FROM   dual;

PROMPT --- 6b: implicit conversion depends on NLS_DATE_FORMAT (here YYYY-MM-DD HH24:MI:SS), so this fails
SELECT COUNT(*) AS cnt
FROM   orders o
WHERE  o.order_date > '31/03/2024';
