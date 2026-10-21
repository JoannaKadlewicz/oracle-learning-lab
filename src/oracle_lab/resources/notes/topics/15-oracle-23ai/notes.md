# Topic 15: SQL Features New in Oracle 23ai (1Z0-171 only)

Environment: Oracle AI Database 23ai (release 23.26, FREEPDB1), schema ORASTUDY. Every example
below marked **(executed)** was run there; the "fails on 19c" results were run on 19.3 (ORAPDB1).
DDL examples (IF [NOT] EXISTS, BOOLEAN and VECTOR columns, domains, annotations,
DEFAULT ON NULL FOR INSERT AND UPDATE) were executed with temporary `LAB_N15_` objects that were
dropped afterwards. Schema privileges could only be checked for syntax and error codes (ORASTUDY
cannot create users), and RETURNING OLD/NEW was executed from Python with bind variables.
Section 17 of the objectives; topic t15 belongs to exam 1Z0-171 only.

## 17.1 SELECT without FROM, GROUP BY / HAVING aliases, VALUES constructor

```sql
SELECT SYSDATE - SYSDATE AS z;                -- 0           (executed; 19c: ORA-00923)
SELECT COUNT(*);                              -- 1           (executed)
SELECT COUNT(*) WHERE 1 = 0;                  -- 0, one row  (executed)
SELECT *;                                     -- ORA-54058   (executed)
```

```sql
SELECT e.department_id AS dept, COUNT(*) AS cnt      -- (executed) 20 → 3, 30 → 4
FROM   employees e
GROUP  BY dept
HAVING cnt > 2
ORDER  BY dept;
```

- Aliases work in GROUP BY and HAVING (and ORDER BY, as before); **not in WHERE** (ORA-00904).
- Only a bare alias: `GROUP BY band + 0` → ORA-00904; `GROUP BY cnt` for `COUNT(*) AS cnt` → ORA-00934.
- **Name conflict:** `SELECT e.department_id AS salary ... GROUP BY salary` groups by the
  *column* e.salary → ORA-00979 (executed).
- **GROUP BY position is parameter-gated.** With the default `group_by_position_enabled = FALSE`,
  `SELECT e.department_id, COUNT(*) ... GROUP BY 1` raises **ORA-03162** (executed); 1 is a
  constant. With the parameter TRUE it groups by the first column.

VALUES table constructor (executed):

```sql
SELECT * FROM (VALUES (1, 'a'), (2, 'b')) t (id, txt);        -- alias + column list required
WITH v (n) AS (VALUES (1), (2)) SELECT * FROM v;
INSERT INTO promotions (promo_id, promo_name) VALUES (1, 'A'), (2, 'B');
MERGE INTO products p USING (VALUES (11, 1000), (99, 5)) v (id, price)
ON (p.product_id = v.id)
WHEN MATCHED THEN UPDATE SET p.list_price = v.price
WHEN NOT MATCHED THEN INSERT (product_id, product_name, list_price) VALUES (v.id, 'New', v.price);
```

| Mistake | Error (executed) |
|---|---|
| no alias / alias without column list | ORA-00931 / ORA-63814 |
| rows with different numbers of values | ORA-63801 |
| column list longer than the rows | ORA-63815 |
| `(1), ('x')` in one column | ORA-01790 |

## 17.2 The BOOLEAN data type

```sql
CREATE TABLE lab_n15_t (id NUMBER, active BOOLEAN DEFAULT TRUE, flag BOOL);  -- BOOL = BOOLEAN (executed)
SELECT TRUE AND NULL, TRUE OR NULL, NOT NULL, FALSE AND NULL;               -- NULL, TRUE, NULL, FALSE (executed)
SELECT e.last_name, e.salary > 10000 AS high FROM employees e;               -- condition as a column (executed)
SELECT COUNT(*) FROM employees e WHERE (e.commission_pct > 0.1) IS NOT TRUE; -- 5 (executed)
```

- Values: TRUE, FALSE, NULL. A BOOLEAN column alone is a condition: `WHERE active`, `WHERE NOT active`.
- `TO_BOOLEAN` / insert into a BOOLEAN column accepts 'true'/'false', 'yes'/'no', 'on'/'off',
  't'/'f', 'y'/'n', '1'/'0' (any case) and numbers (0 = FALSE, any other = TRUE, so -5 → TRUE).
  `TO_BOOLEAN('maybe')` → **ORA-61800** (executed).
- `IS TRUE`, `IS FALSE`, `IS NOT TRUE`, `IS NOT FALSE` never return NULL; `NOT NULL` stays NULL.
  `IS UNKNOWN` is not supported (ORA-00908, executed).
- Sorting: FALSE < TRUE; NULLs last ascending (executed). `TO_CHAR(TRUE)` = 'TRUE', `TO_NUMBER(TRUE)` = 1.
- 19c: BOOLEAN only in PL/SQL; `CREATE TABLE ... (b BOOLEAN)` → ORA-00902, `SELECT TRUE FROM dual` → ORA-00904 (executed).

## 17.3 IF [NOT] EXISTS

```sql
CREATE TABLE IF NOT EXISTS lab_n15_t (...);     -- existing name: silent success, nothing changes
DROP TABLE IF EXISTS lab_n15_t PURGE;           -- missing object: silent success
ALTER TABLE IF EXISTS lab_n15_nope ADD (c NUMBER);   -- missing table: silent success
CREATE SEQUENCE IF NOT EXISTS lab_n15_s START WITH 100;  -- existing sequence keeps its old settings
```

All executed for tables, views, sequences, indexes, synonyms and domains.

| Statement | Result (executed) |
|---|---|
| `CREATE OR REPLACE VIEW IF NOT EXISTS ...` (also SYNONYM) | **ORA-11541** REPLACE and IF NOT EXISTS cannot coexist |
| `DROP TABLE IF NOT EXISTS t` | **ORA-11544** |
| `ALTER TABLE t ADD IF NOT EXISTS (c NUMBER)` | ORA-02000 (no column-level form) |
| `CREATE INDEX IF NOT EXISTS i ON t (other, cols)` when i exists | silent, index unchanged |
| 19c `DROP TABLE IF EXISTS t` / `CREATE TABLE IF NOT EXISTS` | ORA-00933 / ORA-00922 |

## 17.4 DML enhancements

```sql
UPDATE employees e SET e.salary = e.salary + 100           -- 4 rows (executed)
FROM   departments d
WHERE  d.department_id = e.department_id AND d.location = 'Warsaw';

DELETE FROM orders o FROM order_items oi WHERE o.order_id = oi.order_id;   -- 6 orders, not 9 (executed)
```

- The join to the target goes in WHERE; several FROM tables or ANSI joins are allowed.
- A target row matching several source rows in UPDATE → **ORA-30926** (executed, also with no
  WHERE at all). DELETE just deletes the row once.
- `RETURNING OLD e.salary, NEW e.salary INTO :a, :b` → 24000, 48000 (executed with binds).
  INSERT: OLD values are NULL; DELETE: NEW values are NULL (executed). Plain RETURNING in an
  UPDATE returns the new values.
- `DEFAULT ON NULL FOR INSERT AND UPDATE 'C'`: `UPDATE ... SET c = NULL` stores 'C' (executed).
  `DEFAULT ON NULL 'A'` = FOR INSERT ONLY: `SET a = NULL` → **ORA-01407** (executed). Both make the
  column NOT NULL. `FOR UPDATE` alone → ORA-02000. Dictionary: `DEFAULT_ON_NULL`,
  `DEFAULT_ON_NULL_UPD` in USER_TAB_COLUMNS.
- Multi-row `INSERT ... VALUES (...), (...)` is one statement: one duplicate key → ORA-00001 and
  no row inserted (executed). 19c: ORA-00933.

## 17.5 Schema privileges and DB_DEVELOPER_ROLE

```sql
GRANT SELECT ANY TABLE ON SCHEMA hr TO reporter;
GRANT INSERT ANY TABLE, UPDATE ANY TABLE ON SCHEMA hr TO app_user;
REVOKE SELECT ANY TABLE ON SCHEMA hr FROM reporter;
```

- Only ANY system privileges: `GRANT SELECT ON SCHEMA ...` and `GRANT CREATE TABLE ON SCHEMA ...`
  → ORA-00990 (executed). The SYS schema is excluded → ORA-41905 (executed).
- Covers objects created in the schema later (documented). The owner can grant on their own
  schema (executed: ORASTUDY's grant passed the privilege check and failed only with ORA-01917,
  grantee missing); others need GRANT ANY SCHEMA PRIVILEGE (exists in SYSTEM_PRIVILEGE_MAP).
- Views: DBA_SCHEMA_PRIVS, USER_SCHEMA_PRIVS (present in DICTIONARY).
- **DB_DEVELOPER_ROLE**: developer privileges in the own schema (CREATE TABLE, VIEW, SEQUENCE,
  PROCEDURE, TRIGGER, TYPE, SYNONYM, MATERIALIZED VIEW...) plus CREATE DOMAIN, CREATE MLE,
  CREATE JOB, DEBUG CONNECT SESSION; no ANY privileges, no UNLIMITED TABLESPACE. Listed from
  ROLE_SYS_PRIVS / ROLE_ROLE_PRIVS on 23.26 (in this release part of it comes through RESOURCE).

## 17.6 SQL domains and annotations

```sql
CREATE DOMAIN lab_n15_email AS VARCHAR2(100)
    CONSTRAINT lab_n15_email_ck CHECK (REGEXP_LIKE(lab_n15_email, '^[^@]+@[^@]+$'))
    DISPLAY LOWER(lab_n15_email)
    ORDER   UPPER(lab_n15_email)
    ANNOTATIONS (Description 'Email address');
CREATE TABLE lab_n15_c (
    id    NUMBER ANNOTATIONS (Hidden),
    mail  DOMAIN lab_n15_email            -- or: mail lab_n15_email, or VARCHAR2(100) DOMAIN ...
) ANNOTATIONS (Owner 'HR', Display 'Contacts');
```

(executed)

| Action | Result (executed) |
|---|---|
| insert 'bad' into mail | **ORA-11534** check constraint ... due to domain constraint ... violated |
| `DOMAIN_DISPLAY(mail)` for 'Ann@Example.com' | 'ann@example.com' (stored value unchanged) |
| `DOMAIN_NAME(mail)` / `DOMAIN_NAME(id)` | '<your schema>.LAB_N15_EMAIL' / NULL |
| `DOMAIN_ORDER(mail)` | 'ANN@EXAMPLE.COM' |
| `DROP DOMAIN` while used | **ORA-11502** |
| `DROP DOMAIN ... FORCE` | column keeps type and data, DOMAIN_NAME becomes NULL |

- Dictionary: USER_DOMAINS (DATA_DISPLAY, DATA_ORDER), USER_DOMAIN_CONSTRAINTS,
  USER_DOMAIN_COLS, USER_TAB_COLUMNS.DOMAIN_NAME.
- **USER_ANNOTATIONS_USAGE**: OBJECT_NAME, OBJECT_TYPE, COLUMN_NAME (NULL = table level),
  DOMAIN_NAME, ANNOTATION_NAME (uppercase), ANNOTATION_VALUE (NULL for `Hidden`). Columns using a
  domain show the domain's annotations. Change them with
  `ALTER TABLE t ANNOTATIONS (ADD Version '2', DROP Owner)` or `MODIFY (c ANNOTATIONS (...))`.
  Annotations are metadata only, never enforced.

## 17.7 VECTOR and similarity search

```sql
CREATE TABLE lab_n15_vec (id NUMBER, emb VECTOR(3, FLOAT32), any_v VECTOR, v2 VECTOR(*, INT8));
INSERT INTO lab_n15_vec (id, emb) VALUES (1, '[1,2,3]');          -- string converted
SELECT VECTOR_DIMENSION_COUNT(TO_VECTOR('[1,2,3,4]'));           -- 4
SELECT VECTOR_DISTANCE(VECTOR('[1,0]'), VECTOR('[0,1]'), COSINE);  -- 1
SELECT VECTOR_DISTANCE(VECTOR('[0,0]'), VECTOR('[3,4]'), EUCLIDEAN);  -- 5
SELECT t.name
FROM   (VALUES ('a', VECTOR('[1,0]')), ('b', VECTOR('[0,1]')), ('c', VECTOR('[1,1]'))) t (name, v)
ORDER  BY VECTOR_DISTANCE(t.v, VECTOR('[1,0.2]'), EUCLIDEAN)
FETCH  FIRST 2 ROWS ONLY;                                           -- a, c
CREATE VECTOR INDEX lab_n15_vi ON lab_n15_vec (emb)
    ORGANIZATION NEIGHBOR PARTITIONS DISTANCE COSINE WITH TARGET ACCURACY 90;   -- IVF index
```

(all executed)

| Metric | [0,0] vs [3,4] or example | Notes |
|---|---|---|
| COSINE (default) | [1,0] vs [0,1] = 1 | 1 - cosine similarity; zero vector gives NaN |
| EUCLIDEAN | 5 | L2_DISTANCE |
| EUCLIDEAN_SQUARED | 25 | |
| MANHATTAN | 7 | L1_DISTANCE |
| DOT | [1,2]·[3,4] → -11 | negated dot product; INNER_PRODUCT gives 11 |
| HAMMING | number of different dimensions | |

- Errors (executed): wrong dimension count → **ORA-51803**; vectors of different sizes in
  VECTOR_DISTANCE → ORA-51808; ORDER BY / = / GROUP BY on a vector → **ORA-22848**; INT8 value 300
  → ORA-51806.
- `FETCH APPROX FIRST n ROWS ONLY` allows an approximate search through a vector index (HNSW
  in-memory neighbor graph or IVF neighbor partitions); exact search is the plain FETCH FIRST.

## 17.8 New and extended functions

| Expression (executed on 23ai) | Result | 19c (executed) |
|---|---|---|
| `CONCAT('a', 'b', 'c', NULL, 'd')` | 'abcd' | ORA-00909 |
| `SUM(ev.duration)`, `AVG(ev.duration)` | +01 02:15:00, +00 08:45:00 | ORA-00932 |
| `SUM(ev.warranty)` (YEAR TO MONTH) | +01-06 | ORA-00932 |
| `CEIL(DATE '2024-03-15', 'MM')` / `FLOOR(..., 'MM')` | 2024-04-01 / 2024-03-01 | ORA-00909 |
| `TRUNC(INTERVAL '1 23:00:00' DAY TO SECOND)` | +01 00:00:00 | ORA-00932 |
| `CEIL(INTERVAL '1-7' YEAR TO MONTH)` | +02-00 | ORA-00932 |
| `BOOLEAN_AND_AGG(x)`, `BOOLEAN_OR_AGG(x)` over TRUE, FALSE, NULL | FALSE, TRUE | - |
| `TIME_BUCKET(DATE '2024-03-15', INTERVAL '7' DAY, DATE '2024-01-01')` | 2024-03-11 | - |

`BOOL_AND` / `BOOL_OR` (PostgreSQL names) → ORA-00904. TIME_BUCKET, `GROUP BY ALL`, `QUALIFY`,
`COUNT(*) FILTER (WHERE ...)` and `UUID()` also ran on 23.26 but were added in 23ai release updates
after the first 23ai release; they are not used in the questions.

## Common traps

1. Assuming `GROUP BY 1` groups by position: off by default (ORA-03162).
2. An alias with the same name as a table column: GROUP BY uses the column.
3. Using a SELECT alias in WHERE: still ORA-00904.
4. Forgetting the column list after a VALUES alias: `t (a, b)` is required.
5. `NOT (cond)` versus `(cond) IS NOT TRUE` when cond can be NULL.
6. Combining OR REPLACE with IF NOT EXISTS (ORA-11541); `DROP ... IF NOT EXISTS` (ORA-11544).
7. Expecting IF NOT EXISTS to update an existing object's definition.
8. UPDATE ... FROM with several matches per target row (ORA-30926); missing the join to the target.
9. Counting join rows instead of target rows after DELETE ... FROM.
10. Thinking plain DEFAULT ON NULL also covers UPDATE (it is FOR INSERT ONLY; ORA-01407).
11. Granting `SELECT ON SCHEMA` instead of `SELECT ANY TABLE ON SCHEMA` (ORA-00990).
12. Expecting DISPLAY to change what a plain SELECT returns; it only affects DOMAIN_DISPLAY.
13. Sorting or comparing vectors directly (ORA-22848); sort by VECTOR_DISTANCE.
14. Expecting COSINE distance 0 for perpendicular vectors (it is 1; identical direction is 0).

## 19c vs 23ai

| Feature | 19c | 23ai |
|---|---|---|
| `SELECT 1;` (no FROM) | ORA-00923 | works |
| GROUP BY / HAVING alias | ORA-00904 | works |
| GROUP BY position | ORA-00979 | ORA-03162 unless group_by_position_enabled = TRUE |
| `VALUES (...), (...)` in INSERT / FROM / MERGE | ORA-00933 / ORA-00903 / ORA-00928 | works |
| BOOLEAN column, TRUE/FALSE literals | ORA-00902 / ORA-00904 | works |
| `IS TRUE`, TO_BOOLEAN | ORA-00933 / ORA-00904 | works |
| `IF [NOT] EXISTS` | ORA-00933 / ORA-00922 | works |
| UPDATE / DELETE ... FROM | ORA-00933 | works |
| RETURNING OLD / NEW | - | works |
| DEFAULT ON NULL | FOR INSERT only | adds FOR INSERT AND UPDATE |
| Schema privileges, DB_DEVELOPER_ROLE | - | new |
| Domains, annotations | - | new |
| VECTOR, VECTOR_DISTANCE | - | new |
| CONCAT with 3+ arguments | ORA-00909 | works |
| SUM/AVG of INTERVAL | ORA-00932 | works |
| CEIL/FLOOR of DATE, ROUND/TRUNC/CEIL/FLOOR of INTERVAL | ORA-00909 / ORA-00932 | works |

## What 1Z0-171 adds over 1Z0-071

1Z0-171 (Oracle AI Database SQL Associate, 60 questions, 120 minutes, 65% to pass) covers the
same SQL fundamentals as 1Z0-071 (sections 1-16) but expects 23ai behavior, so some 19c "error"
answers become valid statements (GROUP BY alias, SELECT without FROM). Section 17 adds the new
syntax: the VALUES constructor, BOOLEAN, IF [NOT] EXISTS, UPDATE/DELETE with joins, RETURNING
OLD/NEW, DEFAULT ON NULL FOR INSERT AND UPDATE, schema privileges and DB_DEVELOPER_ROLE, SQL
domains and annotations, VECTOR similarity search, and the extended functions above.
