# Exam guide 2026: 1Z0-071 or 1Z0-171

Checked 2026-10-18. Oracle's own exam pages could not be loaded, so the facts below come from
third-party guides; confirm them on Oracle MyLearn before you book.

| | 1Z0-071 Oracle Database SQL | 1Z0-171 Oracle AI Database SQL Associate |
|---|---|---|
| Database version | 19c | 23ai (sold as "Oracle AI Database") |
| Questions | 63 multiple choice | 60 multiple choice |
| Time | 120 minutes | 120 minutes |
| Passing score | 63% (40 of 63) | 65% (39 of 60) |
| Multi-answer items | many "choose two/three" | many "choose two/three" |
| Scope | 16 sections, no published weights | the same SQL areas, plus 23ai features |
| In this app | track 1Z0-071, topics 1-14 | track 1Z0-171, topics 1-15 |

Switch tracks on the Overview page (Settings, Exam). Progress is kept for both, and each track has
its own mock exams.

**Which one?** If your work or employer runs 19c, or a course you follow is built for 1Z0-071, take
1Z0-071. If you start fresh in 2026, 1Z0-171 is the newer exam and tests the version Oracle
ships today. About 95% of the material is the same, so preparing for one prepares you for the other;
learn topic 15 and the "Oracle 23ai differences" sections of each topic note for 1Z0-171.

Third-party guides disagree on 1Z0-171's section weights. Functions (single-row, conversion,
aggregate) are given the largest share (about 25%) in every source, and retrieving and restricting data
and DDL come next. Spend your time accordingly.

## What changes between 19c and 23ai (all verified on both databases)

| Statement | 19c (1Z0-071) | 23ai (1Z0-171) |
|---|---|---|
| `SELECT 1 x` (no FROM) | ORA-00923 | returns 1 |
| `GROUP BY` / `HAVING` with a column alias | ORA-00904 | works |
| `GROUP BY 1` (a position) | ORA-00979 | ORA-03162, unless `group_by_position_enabled` is TRUE |
| `CONCAT('a','b','c')` | ORA-00909 | `abc` |
| `SUM` / `AVG` of INTERVAL values | ORA-00932 | an interval |
| `FROM (VALUES (1,'a'),(2,'b')) v(n,s)` | ORA-00903 | 2 rows |
| `TRUE`, `FALSE`, `AND`/`NOT` in the select list, BOOLEAN columns | ORA-00923 / ORA-00902 | BOOLEAN values |
| `CREATE TABLE IF NOT EXISTS`, `DROP TABLE IF EXISTS` | syntax error | no error if it exists / is missing |
| `VECTOR` data type, `VECTOR_DISTANCE` | ORA-00904 | available |
| Many syntax errors (`AS` before a table alias, ORDER BY inside a UNION branch, ON after CROSS JOIN) | ORA-00933 | ORA-03048 "SQL reserved word ... is not syntactically valid" |
| `JOIN` without `ON` / `USING` | ORA-00905 | ORA-02000 missing ON or USING keyword |

On the exam an answer such as "raises an error" depends on the version the exam tests: think in
19c for 1Z0-071 and in 23ai for 1Z0-171. The app shows questions whose answer changed only on
1Z0-071.

## On exam day

1. **Budget 1 minute 50 seconds a question.** At question 30 you should have about 63 minutes left.
   Mark long questions and come back; an unanswered question scores zero, so never leave a blank.
2. **Read "choose two" twice.** Count the answers you marked before moving on. There is no partial credit.
3. **Execute in your head, clause by clause:** FROM and joins, WHERE, GROUP BY, HAVING, SELECT,
   DISTINCT, ORDER BY, then OFFSET/FETCH. Most "what does it return" traps are an alias used too
   early or a filter applied at the wrong stage.
4. **Hunt for NULL.** Any NOT IN, outer join followed by a WHERE filter, arithmetic, aggregate or
   comparison with a nullable column is suspect.
5. **Look for the error first.** Before computing a result, check that the statement runs: a
   non-grouped column, a missing FROM (19c), a single-row subquery returning several rows,
   mismatched set-operator columns, an alias in WHERE.
6. **Eliminate absolute options.** Options with "always", "never", "only" are wrong more often than
   right; Oracle has an exception for nearly everything.

## Three-week plan with this app

| Week | Daily (45-60 min) | End of week |
|---|---|---|
| 1 | Today's plan on the Overview; one topic deck of flashcards; one exercise; read one topic note | Timed set of 20 questions on topics 1-7 |
| 2 | Today's plan; the Quiz filters "Which error?" and "Predict the output" for 15 minutes; two "Fix the bug" exercises | First full mock exam; review every wrong and guessed answer |
| 3 | Mistakes list first; weakest-topic flashcards; topic 15 for 1Z0-171 | Two more full mocks, at least 3 days apart, aiming at 80% on new questions |

Book the exam when the Progress page's "ready to book" checklist is complete: every objective
green, three uncontaminated mocks at 80%+, and "Sure" right at least 90% of the time.

Sources: https://www.aguidetocloud.com/cert-tracker/oracle-ai-database-sql/ ,
https://www.certificationbox.com/2026/07/21/oracle-1z0-171-ai-database-sql-associate-study-guide/ ,
https://www.examcert.app/blog/oracle-1z0-071-syllabus-2026/
