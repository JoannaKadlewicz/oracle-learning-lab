-- (The accounts behind private practice schemas are made on every start by ../23ai-start/.)
-- Runs once when the Oracle 23ai container creates its database (gvenzl/oracle-free initdb hook).
-- Gives the learning user what the exercises need, including 23ai SQL domains.
ALTER SESSION SET CONTAINER = FREEPDB1;
GRANT CREATE SESSION, CREATE TABLE, CREATE VIEW, CREATE SEQUENCE, CREATE SYNONYM,
      CREATE DOMAIN, CREATE PROCEDURE, UNLIMITED TABLESPACE TO orastudy;
