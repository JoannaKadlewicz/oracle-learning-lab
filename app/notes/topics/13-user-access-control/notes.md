# Topic 13: Controlling User Access

Environment: Oracle Database 19c, schema ORASTUDY. ORASTUDY cannot create users or roles, so
results marked **executed** come from grants to `PUBLIC` on temporary `LAB_` tables (dropped
afterwards) and from the `USER_` / `SESSION_` dictionary views. Everything else is documented
Oracle behavior. Objectives 14.1–14.3.

## Concept

| | System privilege | Object privilege |
|---|---|---|
| What it allows | A kind of action: `CREATE SESSION`, `CREATE TABLE`, `SELECT ANY TABLE` | An action on **one object**: `SELECT ON hr.emp` |
| Syntax | `GRANT create_table TO u` (no `ON`) | `GRANT SELECT ON t TO u` |
| Pass it on | `WITH ADMIN OPTION` | `WITH GRANT OPTION` |
| Revoke cascades? | **No** | **Yes** to everyone who got it through the grant option |
| Listed in | `USER_SYS_PRIVS`, `SESSION_PRIVS` | `USER_TAB_PRIVS_MADE/RECD`, `USER_COL_PRIVS_MADE/RECD` |

A **role** is a named group of system privileges, object privileges and other roles.
`PUBLIC` is a special group that contains every user, including users created later.

## 14.1 System vs object privileges

- Logging in needs **CREATE SESSION**; without it the logon fails with ORA-01045.
- An owner has every object privilege on its own objects without any grant: it can query,
  modify, alter, index, drop and **grant** them. Creating a *new* object (table, view,
  synonym, sequence) always needs the matching system privilege, even on your own data.
- `ANY` privileges (`SELECT ANY TABLE`, `CREATE ANY TABLE`, `DROP ANY TABLE`) work across
  schemas. With the default `O7_DICTIONARY_ACCESSIBILITY = FALSE` they do not cover SYS
  dictionary tables.
- Every user can change **their own** password with `ALTER USER me IDENTIFIED BY ...`.
  Changing another user's password needs the `ALTER USER` system privilege.
- `WITH ADMIN OPTION`: the grantee can grant the privilege *and revoke it from anyone*.
  Revoking it from the grantee does not affect the users the grantee granted it to.

Executed as ORASTUDY:

```sql
SELECT privilege, admin_option FROM user_sys_privs ORDER BY privilege;
-- CREATE SEQUENCE NO / CREATE SESSION NO / CREATE SYNONYM NO / CREATE TABLE NO / CREATE VIEW NO
GRANT CREATE TABLE TO PUBLIC;                     -- ORA-01031: no ADMIN OPTION
GRANT CREATE VIEW TO PUBLIC WITH GRANT OPTION;    -- ORA-01939: only the ADMIN OPTION can be specified
SELECT COUNT(*) FROM sys.obj$;                    -- ORA-00942 (no privilege: object looks absent)
```

## 14.2 Granting privileges on tables

```sql
GRANT SELECT, INSERT ON lab_t TO PUBLIC;                -- several privileges in one statement
GRANT UPDATE (name, note) ON lab_t TO PUBLIC;           -- column-level: INSERT, UPDATE, REFERENCES only
GRANT REFERENCES (id) ON lab_t TO PUBLIC;
GRANT DELETE ON lab_t TO PUBLIC WITH GRANT OPTION;      -- GRANTABLE = YES
```

Executed results:

| Statement | Result |
|---|---|
| `GRANT SELECT (name) ON lab_t TO PUBLIC` | ORA-00969: missing ON keyword (no column-level SELECT; use a view) |
| `REVOKE UPDATE (name) ON lab_t FROM PUBLIC` | ORA-01750: revoke from the whole table only |
| `REVOKE SELECT, INSERT ...` when only SELECT was granted | ORA-01927, and **nothing** is revoked |
| `GRANT ALL ON lab_t TO PUBLIC` | 12 rows: ALTER, DEBUG, DELETE, FLASHBACK, INDEX, INSERT, ON COMMIT REFRESH, QUERY REWRITE, READ, REFERENCES, SELECT, UPDATE |
| `GRANT UPDATE ON lab_seq TO PUBLIC` | ORA-02205: only SELECT and ALTER for sequences |
| `GRANT INDEX ON lab_v TO PUBLIC` | ORA-02204: ALTER, INDEX and EXECUTE not allowed for views |
| `GRANT EXECUTE ON lab_t TO PUBLIC` | ORA-02224 |
| `GRANT SELECT ON lab_t TO PUBLIC` then again `WITH GRANT OPTION` | one row, GRANTABLE upgraded to YES |
| `REVOKE GRANT OPTION FOR SELECT ON lab_t FROM PUBLIC` | ORA-00990 (standard SQL, not Oracle) |
| `DROP TABLE lab_t PURGE` | its grants disappear from `USER_TAB_PRIVS_MADE` |

- Column-level grants appear in `USER_COL_PRIVS_MADE`, not in `USER_TAB_PRIVS_MADE`.
  A table-level `REVOKE INSERT` also removes column-level INSERT grants (executed).
- With column-level INSERT only, the other columns get their default or NULL; a NOT NULL
  column without a default makes such inserts fail.
- `REFERENCES` lets a user create a foreign key to your table; it cannot be granted to a role.
- Revoking an object privilege **cascades** to grants made through `WITH GRANT OPTION`.
- No privilege on an object → **ORA-00942** (Oracle hides its existence). You see the object but lack the
  specific privilege → **ORA-01031**.

## 14.3 Privileges vs roles

```sql
CREATE ROLE clerk;                         -- needs CREATE ROLE (ORASTUDY: ORA-01031)
GRANT CREATE SESSION, SELECT ANY TABLE TO clerk;
GRANT SELECT, UPDATE ON hr.employees TO clerk;
GRANT clerk TO scott;                      -- WITH ADMIN OPTION lets scott grant the role
```

- One GRANT can list system privileges and roles together, or object privileges on one
  object, but **not both kinds**: `GRANT CREATE VIEW, SELECT ON lab_t TO PUBLIC` → ORA-00990 (executed).
- Roles are not schema objects (no owner, no `ANY` variant of `CREATE ROLE`), can be nested,
  can be granted to PUBLIC and can be password-protected (`IDENTIFIED BY`).
- Roles are passed on with **WITH ADMIN OPTION**. `WITH GRANT OPTION` cannot be given to a
  role (ORA-01926) but can be given to a user or PUBLIC (executed).
- Timing: system and object privilege grants and revokes take effect **immediately**. A role
  granted to a connected user takes effect after `SET ROLE` or a new session.
- Privileges received through a role do not count inside definer's-rights PL/SQL, and
  creating a view on another user's table needs a direct grant to the view owner.
- Views: `SESSION_PRIVS` (effective now, including roles), `SESSION_ROLES`, `USER_ROLE_PRIVS`
  (roles granted to you), `ROLE_SYS_PRIVS` / `ROLE_TAB_PRIVS` (privileges of roles you can access).
  ORASTUDY has no roles: `USER_ROLE_PRIVS` and `SESSION_ROLES` return no rows (executed).

## Common traps

1. `WITH GRANT OPTION` vs `WITH ADMIN OPTION`: object vs system privileges and roles. Mixing them gives ORA-01939 / ORA-00993.
2. Expecting a revoke to cascade for a system privilege (it does not) or not to cascade for an object privilege (it does).
3. Thinking SELECT can be granted on columns. Only INSERT, UPDATE and REFERENCES can; use a view for column-level reads.
4. Trying to revoke UPDATE from one column (ORA-01750).
5. Thinking that granting to PUBLIC creates a synonym. Other users still write `orastudy.lab_t`.
6. Assuming an owner needs grants on its own table, or that a user with CREATE TABLE can also create views.
7. Confusing ORA-00942 (no privilege at all) with ORA-01031 (some privilege, but not this one).
8. Expecting a revoke to drop objects created while the privilege was held. It never does.
9. `REVOKE` of several privileges fails completely if one of them was not granted (ORA-01927).

> **Oracle vs. standard SQL / other databases**
> - Oracle has no `REVOKE GRANT OPTION FOR` (standard SQL, PostgreSQL); revoke and grant again.
> - Oracle has no `CASCADE` / `RESTRICT` on object REVOKE: the cascade through the grant option is automatic.
>   (`CASCADE CONSTRAINTS` exists only for REFERENCES, to drop dependent foreign keys.)
> - Users and schemas are one-to-one in Oracle; in PostgreSQL and SQL Server a schema is a separate object
>   and needs its own `USAGE` / schema permissions.
> - Column-level SELECT exists in PostgreSQL and SQL Server but not in Oracle.
> - `ANY` system privileges and `WITH ADMIN OPTION` are Oracle-specific terms; SQL Server uses
>   server/database permissions such as `CONTROL`.

## Oracle 23ai differences (1Z0-171)

Executed as ORASTUDY on Oracle 23ai (FREEPDB1) unless marked *documented*.

- **Schema privileges.** An `ANY` privilege can be limited to one schema, and it covers objects
  created there later. An owner may grant them on its own schema without extra privileges:

  ```sql
  GRANT SELECT ANY TABLE ON SCHEMA orastudy TO PUBLIC;                -- ok
  GRANT INSERT ANY TABLE, UPDATE ANY TABLE ON SCHEMA orastudy TO PUBLIC;
  GRANT CREATE ANY TABLE ON SCHEMA orastudy TO PUBLIC;                -- ok (the ANY form)
  GRANT CREATE TABLE ON SCHEMA orastudy TO PUBLIC;                    -- ORA-00990
  GRANT SELECT ANY TABLE ON SCHEMA sys TO PUBLIC;                     -- ORA-41905: not allowed on SYS
  GRANT SELECT ANY TABLE ON SCHEMA hr TO PUBLIC;                      -- ORA-25705: schema does not exist
  SELECT * FROM user_schema_privs;      -- USERNAME, PRIVILEGE, SCHEMA, ADMIN_OPTION, ...
  SELECT * FROM session_schema_privs;   -- PRIVILEGE, SCHEMA
  REVOKE SELECT ANY TABLE ON SCHEMA orastudy FROM PUBLIC;
  ```

  `WITH ADMIN OPTION` is accepted on a schema privilege. On 19c every one of these statements
  fails with ORA-00990 and `USER_SCHEMA_PRIVS` does not exist (ORA-00942).
- **DB_DEVELOPER_ROLE.** A predefined role for application developers. ORASTUDY has it as a default
  role (`USER_ROLE_PRIVS`). `ROLE_SYS_PRIVS` lists CREATE SESSION, CREATE DOMAIN, CREATE JOB,
  CREATE MLE, CREATE ASSERTION, DEBUG CONNECT SESSION and similar, with no `ANY` privileges, and
  `ROLE_ROLE_PRIVS` shows that RESOURCE is granted to it (SODA_APP to RESOURCE). CONNECT and RESOURCE
  still exist.
- Through the role, `SESSION_PRIVS` has 22 privileges more than `USER_SYS_PRIVS`; on 19c, where
  ORASTUDY has no roles, the two lists match. `SET ROLE NONE` leaves only the 8 direct grants.
- Holding a role without ADMIN OPTION is not enough to grant it:
  `GRANT db_developer_role TO PUBLIC` → ORA-01932.
- More precise error messages, same codes in most cases: ORA-01927 reads "A privilege cannot be
  revoked if you did not grant it.", ORA-00942 names the object (`table or view "SYS"."DBA_SYS_PRIVS"
  does not exist`). DML without the privilege on a visible table changed code:
  `UPDATE sys.dual SET dummy = 'Y'` gives ORA-41900: missing UPDATE privilege on "SYS"."DUAL"
  instead of 19c's ORA-01031.
- Unchanged (executed on both): grants through a synonym are recorded on the base table,
  `REVOKE ALL` succeeds even when only some privileges were granted, ORA-01917 for an unknown
  grantee, ORA-01926/01939/00993 for the wrong `WITH ... OPTION`.
