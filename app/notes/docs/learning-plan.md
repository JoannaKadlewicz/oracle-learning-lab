# Learning Plan: 1Z0-071 Oracle Database SQL

Target: Oracle Database SQL Certified Associate (1Z0-071)
Practice environment: Oracle Database 19c (19.3.0), Docker container `oracle19.3`, PDB `ORAPDB1`

> **Verification status:** The topic areas below follow the commonly published
> structure of 1Z0-071 (Oracle Press study guide, training providers). They have
> **not yet been checked** against the official exam topics page:
> https://education.oracle.com/oracle-database-sql/pexam_1Z0-071
> Action: open the official page, compare it with this list, and mark each row verified.
>
> **Exam format (partially verified, 2026-10-17):** Oracle MyLearn's exam page, as returned
> by search (the page itself could not be fetched), states 63 multiple-choice questions,
> 120 minutes, 63% passing score. Third-party sources state validation up to 19c.
> **Open question:** an education.oracle.com listing labels 1Z0-071 with a "Retiring Exam"
> notice. Check the official page for a retirement date or successor exam before booking.
>
> Sources: https://mylearn.oracle.com/ou/exam/oracle-database-sql-1z0-071/105037/110647/170369 ,
> https://education.oracle.com/pt_BR/oracle-database-sql-certified-associate/trackp_457

## Topic Areas

Order is a suggested learning sequence, not exam weighting.

| # | Topic | Key Oracle-specific points | Verified |
|---|---|---|---|
| 1 | Relational concepts and basic SELECT | `DUAL`, column aliases, `DISTINCT`, `\|\|` concatenation, q-quote `q'[...]'`, arithmetic with NULL | No |
| 2 | Restricting and sorting data | `BETWEEN`, `IN`, `LIKE` with `ESCAPE`, `IS NULL`, operator precedence, `NULLS FIRST/LAST`, `FETCH FIRST ... ROWS [WITH TIES]`, `OFFSET`, substitution variables `&` / `&&` | No |
| 3 | Single-row functions | Character (`SUBSTR`, `INSTR`, `LPAD`, `TRIM`, `REPLACE`), number (`ROUND`, `TRUNC`, `MOD`), date (`SYSDATE`, `ADD_MONTHS`, `MONTHS_BETWEEN`, `LAST_DAY`, `NEXT_DAY`, `ROUND/TRUNC` on dates), date arithmetic | No |
| 4 | Conversion functions and conditional expressions | `TO_CHAR`, `TO_DATE`, `TO_NUMBER`, format models, `fm`, implicit conversion and NLS, `NVL`, `NVL2`, `NULLIF`, `COALESCE`, `CASE`, `DECODE` | No |
| 5 | Aggregation | Group functions and NULLs, `COUNT(*)` vs `COUNT(col)`, `GROUP BY`, `HAVING`, nesting group functions (max 2 levels), `LISTAGG` | No |
| 6 | Joins | ANSI joins, `USING`, `NATURAL JOIN`, `ON`, self-join, non-equijoin, outer joins, `CROSS JOIN`, legacy `(+)` syntax recognition | No |
| 7 | Subqueries | Single-row vs multi-row, `ANY`/`ALL`, `IN` / `NOT IN` with NULLs, correlated subqueries, `EXISTS`, scalar subqueries, inline views, `WITH` | No |
| 8 | Set operators | `UNION`, `UNION ALL`, `INTERSECT`, `MINUS`, column matching rules, `ORDER BY` placement | No |
| 9 | DML and transactions | `INSERT`, `UPDATE`, `DELETE`, `MERGE`, multitable `INSERT ALL/FIRST`, `COMMIT`, `ROLLBACK`, `SAVEPOINT`, implicit commit on DDL, read consistency, `SELECT ... FOR UPDATE` | No |
| 10 | DDL: tables and constraints | Data types (`VARCHAR2`, `NUMBER(p,s)`, `DATE`, `TIMESTAMP`, `CHAR`, `CLOB`), `CREATE TABLE AS SELECT`, `ALTER TABLE`, constraints (PK, FK, `ON DELETE CASCADE/SET NULL`, UNIQUE, CHECK, NOT NULL), `DROP` / `TRUNCATE`, recycle bin and `FLASHBACK TABLE`, unused columns | No |
| 11 | Other schema objects | Views (simple vs complex, `WITH CHECK OPTION`, `WITH READ ONLY`), sequences (`NEXTVAL`/`CURRVAL`, gaps), synonyms, indexes (incl. invisible), temporary tables, external tables | No |
| 12 | Data dictionary | `USER_` / `ALL_` / `DBA_` views, `USER_TABLES`, `USER_CONSTRAINTS`, `USER_TAB_COLUMNS`, `DICTIONARY`, comments | No |
| 13 | User access control | System vs object privileges, `GRANT` / `REVOKE`, `WITH GRANT OPTION` vs `WITH ADMIN OPTION`, roles, `PUBLIC` | No |
| 14 | Time zones and intervals | `TIMESTAMP WITH [LOCAL] TIME ZONE`, `CURRENT_TIMESTAMP` vs `SYSTIMESTAMP`, `INTERVAL YEAR TO MONTH` / `DAY TO SECOND`, `EXTRACT`, `FROM_TZ` | No |

## Suggested Sequence

1. **Week 1:** Topics 1–4 (single-table querying; heavy focus on NULLs and conversions)
2. **Week 2:** Topics 5–8 (aggregation, joins, subqueries, sets)
3. **Week 3:** Topics 9–11 (DML, transactions, DDL, schema objects)
4. **Week 4:** Topics 12–14, then mixed mock exams and review of `docs/mistakes.md`

Adjust pace to your schedule; with prior SQL experience, Topics 1, 2, and 6 are likely quick and
the main risks are Oracle-specific behavior (NULL handling, implicit conversion, DDL auto-commit,
constraint and view rules).

## Per-Topic Workflow

For each topic, create `topics/<nn-topic-name>/` with `notes.md`, `examples.sql`,
`exercises.md`, and `solutions.sql` (solutions only after attempting the exercises).
Record progress in `docs/progress.md` only on request, with evidence.
