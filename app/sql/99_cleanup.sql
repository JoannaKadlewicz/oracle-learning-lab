-- DESTRUCTIVE: drops all learning schema tables and their data.
-- Run as ORASTUDY only when you want to rebuild the schema from scratch.
-- PURGE skips the recycle bin, so FLASHBACK TABLE cannot restore these tables.

DROP TABLE events        PURGE;
DROP TABLE promotions    PURGE;
DROP TABLE order_items   PURGE;
DROP TABLE orders        PURGE;
DROP TABLE products      PURGE;
DROP TABLE customers     PURGE;
DROP TABLE employees     PURGE;
DROP TABLE departments   PURGE;
DROP TABLE salary_grades PURGE;

-- To remove the user entirely (as a DBA user in ORAPDB1):
--   DROP USER orastudy CASCADE;
