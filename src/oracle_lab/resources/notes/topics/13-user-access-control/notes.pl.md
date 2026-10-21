# Temat 13: Kontrola dostępu użytkowników

Środowisko: Oracle Database 19c, schemat ORASTUDY. ORASTUDY nie może tworzyć użytkowników ani ról, więc
wyniki oznaczone jako **wykonane** pochodzą z nadań dla `PUBLIC` na tymczasowych tabelach `LAB_` (potem
usuniętych) oraz z widoków słownika `USER_` / `SESSION_`. Cała reszta to udokumentowane
zachowanie Oracle. Cele 14.1–14.3.

## Pojęcie

| | Uprawnienie systemowe | Uprawnienie obiektowe |
|---|---|---|
| Na co pozwala | Na rodzaj działania: `CREATE SESSION`, `CREATE TABLE`, `SELECT ANY TABLE` | Na działanie na **jednym obiekcie**: `SELECT ON hr.emp` |
| Składnia | `GRANT create_table TO u` (bez `ON`) | `GRANT SELECT ON t TO u` |
| Przekazanie dalej | `WITH ADMIN OPTION` | `WITH GRANT OPTION` |
| Odebranie kaskadowe? | **Nie** | **Tak**, wobec każdego, kto dostał je przez opcję nadawania |
| Widoczne w | `USER_SYS_PRIVS`, `SESSION_PRIVS` | `USER_TAB_PRIVS_MADE/RECD`, `USER_COL_PRIVS_MADE/RECD` |

**Rola** to nazwana grupa uprawnień systemowych, obiektowych i innych ról.
`PUBLIC` to specjalna grupa obejmująca każdego użytkownika, także tych utworzonych później.

## 14.1 Uprawnienia systemowe a obiektowe

- Logowanie wymaga **CREATE SESSION**; bez niego logowanie kończy się błędem ORA-01045.
- Właściciel ma wszystkie uprawnienia obiektowe do własnych obiektów bez żadnego nadania: może je odpytywać,
  modyfikować, zmieniać, indeksować, usuwać i **nadawać**. Utworzenie *nowego* obiektu (tabeli, widoku,
  synonimu, sekwencji) zawsze wymaga odpowiedniego uprawnienia systemowego, nawet na własnych danych.
- Uprawnienia `ANY` (`SELECT ANY TABLE`, `CREATE ANY TABLE`, `DROP ANY TABLE`) działają we wszystkich
  schematach. Przy domyślnym `O7_DICTIONARY_ACCESSIBILITY = FALSE` nie obejmują tabel słownika
  należących do SYS.
- Każdy użytkownik może zmienić **własne** hasło przez `ALTER USER me IDENTIFIED BY ...`.
  Zmiana hasła innego użytkownika wymaga uprawnienia systemowego `ALTER USER`.
- `WITH ADMIN OPTION`: odbiorca może nadawać uprawnienie *i odbierać je każdemu*.
  Odebranie go odbiorcy nie wpływa na użytkowników, którym odbiorca je nadał.

Wykonane jako ORASTUDY:

```sql
SELECT privilege, admin_option FROM user_sys_privs ORDER BY privilege;
-- CREATE SEQUENCE NO / CREATE SESSION NO / CREATE SYNONYM NO / CREATE TABLE NO / CREATE VIEW NO
GRANT CREATE TABLE TO PUBLIC;                     -- ORA-01031: brak ADMIN OPTION
GRANT CREATE VIEW TO PUBLIC WITH GRANT OPTION;    -- ORA-01939: only the ADMIN OPTION can be specified
SELECT COUNT(*) FROM sys.obj$;                    -- ORA-00942 (brak uprawnień: obiekt wygląda na nieistniejący)
```

## 14.2 Nadawanie uprawnień do tabel

```sql
GRANT SELECT, INSERT ON lab_t TO PUBLIC;                -- kilka uprawnień w jednym poleceniu
GRANT UPDATE (name, note) ON lab_t TO PUBLIC;           -- na poziomie kolumn: tylko INSERT, UPDATE, REFERENCES
GRANT REFERENCES (id) ON lab_t TO PUBLIC;
GRANT DELETE ON lab_t TO PUBLIC WITH GRANT OPTION;      -- GRANTABLE = YES
```

Wykonane wyniki:

| Polecenie | Wynik |
|---|---|
| `GRANT SELECT (name) ON lab_t TO PUBLIC` | ORA-00969: missing ON keyword (brak SELECT na poziomie kolumn; użyj widoku) |
| `REVOKE UPDATE (name) ON lab_t FROM PUBLIC` | ORA-01750: odebrać można tylko z całej tabeli |
| `REVOKE SELECT, INSERT ...`, gdy nadano tylko SELECT | ORA-01927 i **nic** nie jest odbierane |
| `GRANT ALL ON lab_t TO PUBLIC` | 12 wierszy: ALTER, DEBUG, DELETE, FLASHBACK, INDEX, INSERT, ON COMMIT REFRESH, QUERY REWRITE, READ, REFERENCES, SELECT, UPDATE |
| `GRANT UPDATE ON lab_seq TO PUBLIC` | ORA-02205: dla sekwencji tylko SELECT i ALTER |
| `GRANT INDEX ON lab_v TO PUBLIC` | ORA-02204: ALTER, INDEX i EXECUTE niedozwolone dla widoków |
| `GRANT EXECUTE ON lab_t TO PUBLIC` | ORA-02224 |
| `GRANT SELECT ON lab_t TO PUBLIC`, potem ponownie `WITH GRANT OPTION` | jeden wiersz, GRANTABLE podniesione do YES |
| `REVOKE GRANT OPTION FOR SELECT ON lab_t FROM PUBLIC` | ORA-00990 (standardowy SQL, nie Oracle) |
| `DROP TABLE lab_t PURGE` | jej nadania znikają z `USER_TAB_PRIVS_MADE` |

- Nadania na poziomie kolumn pojawiają się w `USER_COL_PRIVS_MADE`, a nie w `USER_TAB_PRIVS_MADE`.
  `REVOKE INSERT` na poziomie tabeli usuwa też nadania INSERT na kolumnach (wykonano).
- Przy samym INSERT na poziomie kolumn pozostałe kolumny dostają wartość domyślną albo NULL; kolumna
  NOT NULL bez wartości domyślnej sprawia, że takie wstawienia zawodzą.
- `REFERENCES` pozwala użytkownikowi utworzyć klucz obcy do twojej tabeli; nie można go nadać roli.
- Odebranie uprawnienia obiektowego **przechodzi kaskadowo** na nadania zrobione przez `WITH GRANT OPTION`.
- Brak uprawnień do obiektu → **ORA-00942** (Oracle ukrywa jego istnienie). Widzisz obiekt, ale brakuje ci
  konkretnego uprawnienia → **ORA-01031**.

## 14.3 Uprawnienia a role

```sql
CREATE ROLE clerk;                         -- wymaga CREATE ROLE (ORASTUDY: ORA-01031)
GRANT CREATE SESSION, SELECT ANY TABLE TO clerk;
GRANT SELECT, UPDATE ON hr.employees TO clerk;
GRANT clerk TO scott;                      -- WITH ADMIN OPTION pozwala scott nadawać tę rolę
```

- Jedno GRANT może wymieniać razem uprawnienia systemowe i role albo uprawnienia obiektowe na jednym
  obiekcie, ale **nie oba rodzaje naraz**: `GRANT CREATE VIEW, SELECT ON lab_t TO PUBLIC` → ORA-00990 (wykonano).
- Role nie są obiektami schematu (bez właściciela, bez wariantu `ANY` dla `CREATE ROLE`), można je zagnieżdżać,
  nadawać PUBLIC i chronić hasłem (`IDENTIFIED BY`).
- Role przekazuje się z **WITH ADMIN OPTION**. `WITH GRANT OPTION` nie może dostać
  rola (ORA-01926), ale może je dostać użytkownik albo PUBLIC (wykonano).
- Czas działania: nadania i odebrania uprawnień systemowych i obiektowych działają **natychmiast**. Rola
  nadana połączonemu użytkownikowi działa po `SET ROLE` albo w nowej sesji.
- Uprawnienia otrzymane przez rolę nie liczą się w PL/SQL z prawami definiującego, a
  utworzenie widoku na tabeli innego użytkownika wymaga nadania bezpośrednio właścicielowi widoku.
- Widoki: `SESSION_PRIVS` (efektywne teraz, łącznie z rolami), `SESSION_ROLES`, `USER_ROLE_PRIVS`
  (role nadane tobie), `ROLE_SYS_PRIVS` / `ROLE_TAB_PRIVS` (uprawnienia ról, do których masz dostęp).
  Twój schemat ćwiczeniowy nie ma ról: `USER_ROLE_PRIVS` i `SESSION_ROLES` nie zwracają wierszy (wykonano).

## Częste pułapki

1. `WITH GRANT OPTION` a `WITH ADMIN OPTION`: uprawnienia obiektowe a systemowe i role. Pomylenie daje ORA-01939 / ORA-00993.
2. Oczekiwanie, że odebranie uprawnienia systemowego działa kaskadowo (nie działa) albo że odebranie obiektowego nie działa kaskadowo (działa).
3. Przekonanie, że SELECT można nadać na kolumnach. Można tylko INSERT, UPDATE i REFERENCES; do odczytu wybranych kolumn użyj widoku.
4. Próba odebrania UPDATE z jednej kolumny (ORA-01750).
5. Przekonanie, że nadanie dla PUBLIC tworzy synonim. Inni użytkownicy nadal piszą `orastudy.lab_t`.
6. Założenie, że właściciel potrzebuje nadań na własnej tabeli albo że użytkownik z CREATE TABLE może też tworzyć widoki.
7. Mylenie ORA-00942 (brak jakichkolwiek uprawnień) z ORA-01031 (jakieś uprawnienie jest, ale nie to).
8. Oczekiwanie, że odebranie usunie obiekty utworzone w czasie posiadania uprawnienia. Nigdy tego nie robi.
9. `REVOKE` kilku uprawnień zawodzi w całości, jeśli któregoś nie nadano (ORA-01927).

> **Oracle a standardowy SQL / inne bazy danych**
> - Oracle nie ma `REVOKE GRANT OPTION FOR` (standardowy SQL, PostgreSQL); odbierz i nadaj ponownie.
> - Oracle nie ma `CASCADE` / `RESTRICT` przy odbieraniu uprawnień obiektowych: kaskada przez opcję nadawania jest automatyczna.
>   (`CASCADE CONSTRAINTS` istnieje tylko dla REFERENCES, aby usunąć zależne klucze obce.)
> - Użytkownicy i schematy odpowiadają sobie jeden do jednego w Oracle; w PostgreSQL i SQL Server schemat to osobny obiekt
>   i wymaga własnych uprawnień `USAGE` / do schematu.
> - SELECT na poziomie kolumn istnieje w PostgreSQL i SQL Server, ale nie w Oracle.
> - Uprawnienia systemowe `ANY` i `WITH ADMIN OPTION` to terminy specyficzne dla Oracle; SQL Server używa
>   uprawnień serwera/bazy danych, takich jak `CONTROL`.

## Różnice w Oracle 23ai (1Z0-171)

Wykonano jako ORASTUDY na Oracle 23ai (FREEPDB1), chyba że oznaczono jako *udokumentowane*.

- **Uprawnienia do schematu.** Uprawnienie `ANY` można ograniczyć do jednego schematu i obejmuje ono obiekty
  utworzone tam później. Właściciel może je nadać na własnym schemacie bez dodatkowych uprawnień:

  ```sql
  GRANT SELECT ANY TABLE ON SCHEMA orastudy TO PUBLIC;                -- ok
  GRANT INSERT ANY TABLE, UPDATE ANY TABLE ON SCHEMA orastudy TO PUBLIC;
  GRANT CREATE ANY TABLE ON SCHEMA orastudy TO PUBLIC;                -- ok (postać z ANY)
  GRANT CREATE TABLE ON SCHEMA orastudy TO PUBLIC;                    -- ORA-00990
  GRANT SELECT ANY TABLE ON SCHEMA sys TO PUBLIC;                     -- ORA-41905: niedozwolone na SYS
  GRANT SELECT ANY TABLE ON SCHEMA hr TO PUBLIC;                      -- ORA-25705: schemat nie istnieje
  SELECT * FROM user_schema_privs;      -- USERNAME, PRIVILEGE, SCHEMA, ADMIN_OPTION, ...
  SELECT * FROM session_schema_privs;   -- PRIVILEGE, SCHEMA
  REVOKE SELECT ANY TABLE ON SCHEMA orastudy FROM PUBLIC;
  ```

  `WITH ADMIN OPTION` jest przyjmowane przy uprawnieniu do schematu. W 19c każde z tych poleceń
  kończy się błędem ORA-00990, a `USER_SCHEMA_PRIVS` nie istnieje (ORA-00942).
- **DB_DEVELOPER_ROLE.** Predefiniowana rola dla programistów aplikacji. (Sprawdzono na koncie, które ją
  ma; twój schemat ćwiczeniowy jej nie ma, ma kilka uprawnień CREATE nadanych bezpośrednio.) `ROLE_SYS_PRIVS` wymienia CREATE SESSION, CREATE DOMAIN, CREATE JOB,
  CREATE MLE, CREATE ASSERTION, DEBUG CONNECT SESSION i podobne, bez uprawnień `ANY`, a
  `ROLE_ROLE_PRIVS` pokazuje, że nadano jej RESOURCE (SODA_APP dla RESOURCE). CONNECT i RESOURCE
  nadal istnieją.
- Przez tę rolę `SESSION_PRIVS` ma o 22 uprawnienia więcej niż `USER_SYS_PRIVS`; bez ról
  (twój schemat ćwiczeniowy albo dowolne konto 19c bez ról) obie listy są zgodne. `SET ROLE NONE` zostawia tylko nadania bezpośrednie.
- Posiadanie roli bez ADMIN OPTION nie wystarcza, aby ją nadać (sprawdzono na koncie, które ma tę rolę):
  `GRANT db_developer_role TO PUBLIC` → ORA-01932.
- Dokładniejsze komunikaty błędów, w większości przypadków te same kody: ORA-01927 brzmi "A privilege cannot be
  revoked if you did not grant it.", ORA-00942 wymienia obiekt (`table or view "SYS"."DBA_SYS_PRIVS"
  does not exist`). DML bez uprawnienia na widocznej tabeli zmienił kod:
  `UPDATE sys.dual SET dummy = 'Y'` daje ORA-41900: missing UPDATE privilege on "SYS"."DUAL"
  zamiast ORA-01031 z 19c.
- Bez zmian (wykonano w obu): nadania przez synonim są zapisywane na tabeli bazowej,
  `REVOKE ALL` się udaje, nawet gdy nadano tylko część uprawnień, ORA-01917 dla nieznanego
  odbiorcy, ORA-01926/01939/00993 dla złego `WITH ... OPTION`.
