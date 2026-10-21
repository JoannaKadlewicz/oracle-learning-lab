"""Official 1Z0-071 exam sections and objectives.

Section and objective titles follow Oracle's exam guide for 1Z0-071 (Oracle Database SQL).
Checked on 2026-10-17 against a third-party restatement of the guide
(https://www.examcert.app/blog/oracle-1z0-071-syllabus-2026/), because Oracle's own pages
(https://education.oracle.com/oracle-database-sql/pexam_1Z0-071) did not load. Re-check against
Oracle's guide when possible. The same source states: 63 questions, 120 minutes, 63% to pass,
no published section weights.

Since 2025 Oracle also offers 1Z0-171, Oracle (AI) Database 23ai SQL Associate: 60 questions,
120 minutes, 65% to pass (checked 2026-10-18 against third-party guides, for example
https://www.aguidetocloud.com/cert-tracker/oracle-ai-database-sql/ and
https://www.certificationbox.com/2026/07/21/oracle-1z0-171-ai-database-sql-associate-study-guide/;
re-check against Oracle's exam page). It covers the same SQL areas as 1Z0-071 on Oracle 23ai, so
the app uses sections 1-16 for both exams and adds section 17 for the SQL features new in 23ai.
Their published weights disagree with each other, so mocks stay one question per objective first.

The exams themselves (code, size, pass mark, database) live in oracle_lab.exams.

Every question, flashcard and exercise has an "objective" key from OBJECTIVES.
"""

# Sections only on one exam; every other section belongs to both.
SECTION_EXAMS = {"17": ["1Z0-171"]}

SECTIONS = {
    "1": "Relational Database concepts",
    "2": "Retrieving Data using the SQL SELECT Statement",
    "3": "Restricting and Sorting Data",
    "4": "Using Single-Row Functions to Customize Output",
    "5": "Using Conversion Functions and Conditional Expressions",
    "6": "Reporting Aggregated Data Using Group Functions",
    "7": "Displaying Data from Multiple Tables",
    "8": "Using Subqueries to Solve Queries",
    "9": "Using SET Operators",
    "10": "Managing Tables using DML statements",
    "11": "Managing Indexes Synonyms and Sequences",
    "12": "Use DDL to manage tables and their relationships",
    "13": "Managing Views",
    "14": "Controlling User Access",
    "15": "Managing Objects with Data Dictionary Views",
    "16": "Managing Data in Different Time Zones",
    "17": "SQL Features New in Oracle 23ai",
}

OBJECTIVES = {
    "1.1": "Theoretical and physical aspects of a relational database",
    "1.2": "Relating SELECT clauses to components of an ERD",
    "1.3": "The relationship between a database and SQL",
    "2.1": "The SQL SELECT statement",
    "2.2": "Column aliases",
    "2.3": "Concatenation, literal character strings and the alternative quote operator",
    "2.4": "The DISTINCT keyword",
    "2.5": "Arithmetic expressions and NULL values",
    "3.1": "Rules of precedence for operators in an expression",
    "3.2": "Limiting rows returned in a SQL statement",
    "3.3": "Substitution variables",
    "3.4": "The DEFINE and VERIFY commands",
    "3.5": "Sorting data",
    "4.1": "Manipulating strings with character functions in SELECT and WHERE",
    "4.2": "Performing arithmetic with date data",
    "4.3": "ROUND, TRUNC and MOD",
    "4.4": "Manipulating dates with date functions",
    "5.1": "NVL, NULLIF and COALESCE",
    "5.2": "Implicit versus explicit data type conversion",
    "5.3": "TO_CHAR, TO_NUMBER and TO_DATE",
    "5.4": "Nesting multiple functions",
    "6.1": "Using group functions",
    "6.2": "Creating groups of data",
    "6.3": "Restricting group results",
    "7.1": "Various types of joins",
    "7.2": "Self-joins",
    "7.3": "Non-equijoins",
    "7.4": "OUTER joins",
    "7.5": "Cartesian products",
    "8.1": "Single-row subqueries",
    "8.2": "Multiple-row subqueries",
    "8.3": "Updating and deleting rows using correlated subqueries",
    "9.1": "Matching the SELECT statements",
    "9.2": "UNION and UNION ALL",
    "9.3": "INTERSECT",
    "9.4": "MINUS",
    "9.5": "ORDER BY in set operations",
    "10.1": "INSERT, UPDATE and DELETE operations",
    "10.2": "Multi-table inserts",
    "10.3": "MERGE statements",
    "10.4": "Managing database transactions",
    "10.5": "Controlling transactions",
    "11.1": "Managing indexes",
    "11.2": "Managing synonyms",
    "11.3": "Managing sequences",
    "12.1": "Describing and working with tables",
    "12.2": "Columns and data types",
    "12.3": "Creating tables",
    "12.4": "Dropping columns and setting a column UNUSED",
    "12.5": "Truncating tables",
    "12.6": "Temporary tables",
    "12.7": "External tables",
    "12.8": "Managing constraints",
    "13.1": "Creating, modifying and dropping views",
    "14.1": "System privileges versus object privileges",
    "14.2": "Granting privileges on tables",
    "14.3": "Granting privileges versus granting roles",
    "15.1": "Using data dictionary views",
    "16.1": "CURRENT_DATE, CURRENT_TIMESTAMP and LOCALTIMESTAMP",
    "16.2": "INTERVAL data types",
    "17.1": "SELECT without FROM, GROUP BY and HAVING with column aliases, the VALUES table constructor",
    "17.2": "The BOOLEAN data type",
    "17.3": "IF [NOT] EXISTS in DDL statements",
    "17.4": "DML enhancements: joins in UPDATE and DELETE, RETURNING OLD and NEW, DEFAULT ON NULL",
    "17.5": "Schema privileges and the DB_DEVELOPER_ROLE",
    "17.6": "SQL domains and annotations",
    "17.7": "The VECTOR data type and similarity search",
    "17.8": "New and extended functions in 23ai",
}
