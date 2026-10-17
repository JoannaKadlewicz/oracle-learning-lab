# Topic 12: The Data Dictionary

Environment: Oracle Database 19.3, schema ORASTUDY. All results below were **executed** on
2026-10-17 against the sample schema. Exam objective: 15.1 using data dictionary views.

## Concept

The data dictionary is a set of read-only tables owned by SYS that Oracle maintains itself
whenever you run DDL. You read it through views, reached through public synonyms.

| Prefix | Shows | OWNER column? |
|---|---|---|
| `USER_` | Objects you own | Usually not (it is always you) |
| `ALL_` | Objects you own or have privileges on | Yes |
| `DBA_` | Every object in the database | Yes; needs privileges such as SELECT ANY DICTIONARY |
| `V$` | Dynamic performance data about the running instance | n/a |

`DICTIONARY` (synonym `DICT`) lists the dictionary views with a description in `COMMENTS`
(empty in this practice database, where the query below returns 12 names with NULL comments);
`DICT_COLUMNS` describes their columns. `USER_TABLES` itself is a SYS view reached through a
PUBLIC synonym.

```sql
SELECT table_name, comments FROM dictionary WHERE table_name LIKE 'USER_IND%';
```

Names are stored in **uppercase** (unless created with double quotes):
`WHERE table_name = 'employees'` returns 0 rows; use `'EMPLOYEES'`.

## The views to know

| View | One row per | Key columns |
|---|---|---|
| `USER_OBJECTS` | Schema object | `OBJECT_NAME`, `OBJECT_TYPE`, `STATUS`, `CREATED`, `LAST_DDL_TIME` |
| `USER_TABLES` | Table | `TABLE_NAME`, `NUM_ROWS` (from statistics, not live) |
| `USER_TAB_COLUMNS` | Column of a table or view | `COLUMN_ID`, `DATA_TYPE`, `DATA_LENGTH`, `DATA_PRECISION`, `DATA_SCALE`, `NULLABLE` |
| `USER_CONSTRAINTS` | Constraint | `CONSTRAINT_TYPE`, `R_CONSTRAINT_NAME`, `DELETE_RULE`, `SEARCH_CONDITION(_VC)`, `INDEX_NAME`, `STATUS` |
| `USER_CONS_COLUMNS` | Constraint column | `CONSTRAINT_NAME`, `COLUMN_NAME`, `POSITION` |
| `USER_INDEXES` | Index | `INDEX_TYPE`, `UNIQUENESS`, `VISIBILITY`, `STATUS` |
| `USER_IND_COLUMNS` | Index column | `INDEX_NAME`, `COLUMN_NAME`, `COLUMN_POSITION` |
| `USER_VIEWS` | View | `TEXT` (LONG), `TEXT_VC` |
| `USER_SEQUENCES` | Sequence | `MIN_VALUE`, `MAX_VALUE`, `INCREMENT_BY`, `CYCLE_FLAG`, `CACHE_SIZE`, `LAST_NUMBER` |
| `USER_SYNONYMS` | Private synonym | `SYNONYM_NAME`, `TABLE_OWNER`, `TABLE_NAME` |
| `USER_TAB_COMMENTS` / `USER_COL_COMMENTS` | Table or view / column | `COMMENTS` (NULL until `COMMENT ON`) |

Constraint types: `P` primary key, `U` unique, `R` foreign key, `C` check **and NOT NULL**,
`V` view WITH CHECK OPTION, `O` view WITH READ ONLY.

## Example 1: constraints of EMPLOYEES

```sql
SELECT constraint_name, constraint_type FROM user_constraints
WHERE  table_name = 'EMPLOYEES' ORDER BY constraint_type, constraint_name;
```

| CONSTRAINT_NAME | TYPE |
|---|---|
| EMPLOYEES_HIRE_DATE_NN | C |
| EMPLOYEES_LAST_NAME_NN | C |
| EMPLOYEES_SALARY_CK | C |
| EMPLOYEES_PK | P |
| EMPLOYEES_DEPARTMENT_FK | R |
| EMPLOYEES_MANAGER_FK | R |
| EMPLOYEES_EMAIL_UK | U |

7 rows: NOT NULL constraints are type C. Their `SEARCH_CONDITION_VC` is `"LAST_NAME" IS NOT NULL`.
`SEARCH_CONDITION` itself is LONG and cannot be used with `LIKE`.

## Example 2: foreign keys with the referenced table

`R_CONSTRAINT_NAME` holds the referenced **constraint** (`ORDERS_CUSTOMER_FK` → `CUSTOMERS_PK`),
not the table. Join `USER_CONSTRAINTS` to itself:

```sql
SELECT c.table_name, c.constraint_name, r.table_name AS referenced_table, c.delete_rule
FROM   user_constraints c
JOIN   user_constraints r ON r.constraint_name = c.r_constraint_name
WHERE  c.constraint_type = 'R'
ORDER  BY c.table_name, c.constraint_name;
```

| TABLE_NAME | CONSTRAINT_NAME | REFERENCED_TABLE | DELETE_RULE |
|---|---|---|---|
| EMPLOYEES | EMPLOYEES_DEPARTMENT_FK | DEPARTMENTS | NO ACTION |
| EMPLOYEES | EMPLOYEES_MANAGER_FK | EMPLOYEES | NO ACTION |
| ORDERS | ORDERS_CUSTOMER_FK | CUSTOMERS | NO ACTION |
| ORDERS | ORDERS_SALES_REP_FK | EMPLOYEES | NO ACTION |
| ORDER_ITEMS | ORDER_ITEMS_ORDER_FK | ORDERS | CASCADE |
| ORDER_ITEMS | ORDER_ITEMS_PRODUCT_FK | PRODUCTS | NO ACTION |

## Example 3: columns and their sizes

| Column (declared) | DATA_TYPE | DATA_LENGTH | DATA_PRECISION, SCALE | NULLABLE |
|---|---|---|---|---|
| `employee_id NUMBER(6) PRIMARY KEY` | NUMBER | 22 | 6, 0 | N |
| `last_name VARCHAR2(25) NOT NULL` | VARCHAR2 | 25 | | N |
| `hire_date DATE NOT NULL` | DATE | 7 | | N |
| `salary NUMBER(8,2)` | NUMBER | 22 | 8, 2 | Y |

`DATA_LENGTH` is bytes of storage: 22 for every NUMBER, 7 for DATE. The primary key column is
`N` even without a NOT NULL constraint.

## Example 4: one row per constraint column

`USER_CONS_COLUMNS WHERE table_name = 'ORDER_ITEMS'` returns 5 rows: `ORDER_ITEMS_PK` has two
(ORDER_ID position 1, LINE_NO position 2), and the two foreign keys and the quantity CHECK one each.
ORDER_ID appears twice (PK and FK).

## Other facts checked

- `USER_INDEXES WHERE table_name = 'EMPLOYEES'`: 2 rows (PK and UK); no index for foreign keys.
- `USER_CONSTRAINTS.INDEX_NAME` for `EMPLOYEES_EMAIL_UK` is `EMPLOYEES_EMAIL_UK`.
- `USER_OBJECTS WHERE object_type = 'CONSTRAINT'`: 0 rows; constraints are not schema objects.
- `USER_TAB_COMMENTS` has a row for every table even without a comment (COMMENTS NULL).
- `UPDATE user_tables SET ...`: **ORA-02030**: can only select from fixed tables/views. Change the dictionary with DDL only.
- `USER_SEQUENCES.LAST_NUMBER` after issuing 1, 2, 3 with CACHE 20 is 21: it runs ahead of
  the issued values. There is no CURRVAL or NEXTVAL column.
- `USER_CONSTRAINTS` and `USER_CONS_COLUMNS` do have an OWNER column; `USER_TABLES` and `USER_OBJECTS` do not.

## Common traps

1. Lowercase literals in `WHERE table_name = ...` find nothing.
2. NOT NULL constraints are type `C`, not a separate type.
3. `R_CONSTRAINT_NAME` is a constraint name, not a table name.
4. Constraint columns are in `USER_CONS_COLUMNS`, index columns in `USER_IND_COLUMNS`,
   table columns in `USER_TAB_COLUMNS`; `USER_COLUMNS` and `USER_COMMENTS` do not exist.
5. `USER_TAB_COLUMNS` includes view columns; join to `USER_TABLES` for tables only.
6. `USER_` views show only your objects, even ones you were granted access to; use `ALL_`.
7. `NUM_ROWS` and `LAST_NUMBER` are not live counters.
8. LONG columns (`SEARCH_CONDITION`, `TEXT`, `DATA_DEFAULT`) cannot be used in `LIKE`; use the `_VC` versions.

> **Oracle vs. standard SQL / other databases**
>
> - The SQL standard defines `INFORMATION_SCHEMA` (`TABLES`, `COLUMNS`, `TABLE_CONSTRAINTS`, ...),
>   which PostgreSQL, MySQL and SQL Server provide. Oracle does not; it has its own
>   `USER_` / `ALL_` / `DBA_` views.
> - Other databases fold unquoted names differently: PostgreSQL stores lowercase, Oracle uppercase.
> - PostgreSQL's `pg_catalog`, SQL Server's `sys.` views and Oracle's `V$` views are product-specific.
