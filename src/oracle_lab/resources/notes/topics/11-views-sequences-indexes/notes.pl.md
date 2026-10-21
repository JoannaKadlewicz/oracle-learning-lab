# Temat 11: Widoki, sekwencje, indeksy i synonimy

Środowisko: Oracle Database 19.3, schemat ORASTUDY. Każdy wynik i kod błędu niżej został
**wykonany** 17 października 2026 na kopiach przykładowych tabel (obiekty `LAB_`, potem usunięte).
Cele egzaminu: 11.1 indeksy, 11.2 synonimy, 11.3 sekwencje, 13.1 widoki.

## Widoki (13.1)

Widok to zapisane zapytanie. Nie przechowuje wierszy, więc jego usunięcie nigdy nie dotyka danych.

```sql
CREATE [OR REPLACE] [FORCE | NOFORCE] VIEW name [(col, ...)] AS
SELECT ...
[WITH CHECK OPTION | WITH READ ONLY];
```

| Reguła | Szczegóły |
|---|---|
| Wyrażenia potrzebują nazw | `SELECT salary * 12 FROM ...` w widoku: **ORA-00998** (użyj aliasu albo listy kolumn) |
| `ORDER BY` | Dozwolone w zapytaniu definiującym |
| `OR REPLACE` | Zmienia zapytanie i zachowuje nadania na widoku; na nazwie tabeli: **ORA-00955** |
| `ALTER VIEW` | Tylko `COMPILE` i ograniczenia widoku. `ALTER VIEW v AS SELECT ...`: **ORA-00922** |
| `FORCE` | Tworzy widok, nawet gdy brakuje tabeli bazowej; status `INVALID` |
| `NOFORCE` (domyślnie) | Brakująca tabela: **ORA-00942**, nic nie powstaje |
| `DROP VIEW v` | Zależne widoki zostają, ale stają się `INVALID` (**ORA-04063** przy odpytaniu); `DROP VIEW v CASCADE`: **ORA-00905** |

Widok FORCE sam się kompiluje przy pierwszym użyciu, gdy tabela już istnieje:

| Krok | `USER_OBJECTS.STATUS` widoku |
|---|---|
| `CREATE FORCE VIEW lab_v AS SELECT * FROM lab_missing` | INVALID |
| `SELECT * FROM lab_v` | **ORA-04063**: view has errors |
| `CREATE TABLE lab_missing (id NUMBER)`, potem `SELECT * FROM lab_v` | VALID, 0 wierszy |

### DML przez widoki

Wiersz widoku musi odpowiadać dokładnie jednemu wierszowi tabeli bazowej. Te elementy czynią widok niemodyfikowalnym
(**ORA-01732**: data manipulation operation not legal on this view):
`DISTINCT`, `GROUP BY` / funkcje grupujące, `ROWNUM`, operatory zbiorowe.
Nadal modyfikowalne: `WHERE`, aliasy kolumn, `ORDER BY`.

| Przez widok... | Wynik |
|---|---|
| UPDATE kolumny zdefiniowanej jako `salary * 12` | **ORA-01733**: virtual column not allowed here |
| DELETE z tego samego widoku | Działa (wiersz nadal odpowiada jednemu wierszowi tabeli) |
| Zmiana kolumny tabeli bez zachowania klucza w złączeniu | **ORA-01779** |
| INSERT wiersza spoza filtra `WITH CHECK OPTION` | **ORA-01402** |
| Dowolny DML na widoku `WITH READ ONLY` | **ORA-42399** |

W złączeniu `employees e JOIN departments d` tabela employees *zachowuje klucz* (każdy pracownik pojawia się
najwyżej raz), więc `SET salary = ...` działa, ale `SET department_name = ...` kończy się w 19c błędem ORA-01779.
(Oracle 21c to złagodził: pozwala na zmianę, gdy każdy wiersz docelowy zmienia się tylko raz, a w przeciwnym razie zgłasza
ORA-30926. Egzamin dotyczy 19c.)

`WITH CHECK OPTION` działa też na podzapytaniu użytym jako cel DML:

```sql
INSERT INTO (SELECT employee_id, last_name, hire_date, department_id
             FROM employees WHERE department_id = 30 WITH CHECK OPTION)
VALUES (900, 'Test', DATE '2024-01-01', 20);     -- ORA-01402
DELETE FROM (SELECT employee_id FROM employees WITH READ ONLY)
WHERE employee_id = 108;                          -- ORA-42399
```

Opcje są zapisywane jako ograniczenia widoku w `USER_CONSTRAINTS`: typ `V` dla CHECK OPTION,
typ `O` dla READ ONLY.

## Sekwencje (11.3)

`CREATE SEQUENCE s;` daje START WITH 1, INCREMENT BY 1, MINVALUE 1, MAXVALUE z 28 dziewiątek,
NOCYCLE, CACHE 20 (`USER_SEQUENCES`: `CACHE_SIZE` 20, `CYCLE_FLAG` N).

| Polecenie | Wynik |
|---|---|
| `SELECT s.CURRVAL` przed jakimkolwiek `NEXTVAL` w sesji | **ORA-08002** |
| `SELECT s.NEXTVAL a, s.CURRVAL b, s.NEXTVAL c FROM dual` (nowa sekwencja) | `1, 1, 1`: jeden przyrost na wiersz |
| Sekwencja NOCYCLE po przekroczeniu MAXVALUE | **ORA-08004** |
| `START WITH 5 INCREMENT BY 5 MINVALUE 1 MAXVALUE 15 CYCLE NOCACHE` | 5, 10, 15, **1**: wraca do MINVALUE |
| `CREATE SEQUENCE s MAXVALUE 3 CYCLE` (domyślne CACHE 20) | **ORA-04013**: CACHE musi być mniejsze niż jeden cykl |
| `ALTER SEQUENCE s START WITH 100` | **ORA-02283** |
| `ALTER SEQUENCE s MAXVALUE 20`, gdy wydano już 50 | **ORA-04009** |
| `ALTER SEQUENCE s INCREMENT BY 10 / CYCLE / CACHE 50` | Dozwolone, wpływa na przyszłe wartości |
| `ALTER SEQUENCE s RESTART START WITH 1` | Dozwolone od 18c |

Gdzie mogą się pojawić `NEXTVAL` / `CURRVAL`: lista SELECT zapytania najwyższego poziomu, `INSERT ... VALUES`,
lista SELECT w `INSERT ... SELECT`, `UPDATE ... SET` i `DEFAULT` kolumny (12c).
Niedozwolone (**ORA-02287**): `WHERE`, `DISTINCT`, `GROUP BY`, `ORDER BY`, operatory zbiorowe,
podzapytania, definicje widoków.

Sekwencje nie są transakcyjne: ROLLBACK nie oddaje wartości, więc luki są normalne.

## Indeksy (11.1)

| Rodzaj | Składnia | Słownik |
|---|---|---|
| B-drzewo (domyślnie) | `CREATE INDEX i ON t (col)` | `UNIQUENESS` NONUNIQUE |
| Unikalny | `CREATE UNIQUE INDEX i ON t (col)` | `UNIQUENESS` UNIQUE |
| Złożony | `CREATE INDEX i ON t (department_id, salary)` | `USER_IND_COLUMNS.COLUMN_POSITION` 1, 2 |
| Funkcyjny | `CREATE INDEX i ON t (UPPER(last_name))` | `INDEX_TYPE` FUNCTION-BASED NORMAL, wyrażenie w `USER_IND_EXPRESSIONS` |
| Niewidoczny | `... INVISIBLE` albo `ALTER INDEX i INVISIBLE` | `VISIBILITY` INVISIBLE; nadal aktualizowany przez DML |

- Ograniczenia PRIMARY KEY i UNIQUE tworzą indeks o nazwie ograniczenia. Klucze obce nie:
  `employees` ma tylko `EMPLOYEES_PK` i `EMPLOYEES_EMAIL_UK`.
- Jednokolumnowy indeks unikalny dopuszcza dowolną liczbę NULL (pracownik 108 i nowy wiersz mogą oba mieć email NULL).
- Te same kolumny w tej samej kolejności drugi raz: **ORA-01408**. Inna kolejność to inny indeks.
- `DROP INDEX` na indeksie wymuszającym PK/UK: **ORA-02429**. Zamiast tego usuń ograniczenie.
- `DROP TABLE` usuwa jej indeksy i ograniczenia; widoki i synonimy na niej zostają (INVALID).

## Synonimy (11.2)

```sql
CREATE [OR REPLACE] [PUBLIC] SYNONYM name FOR [schema.]object;
DROP [PUBLIC] SYNONYM name;
```

- Prywatne synonimy wymagają `CREATE SYNONYM`; publiczne `CREATE PUBLIC SYNONYM` (ORASTUDY: **ORA-01031**).
- Synonim to tylko alias: niczego nie nadaje.
- Cele: tabele, widoki, sekwencje (`SELECT syn.NEXTVAL FROM dual` działa), procedury, inne synonimy.
  Nie indeksy, ograniczenia ani kolumny.
- Cel nie jest sprawdzany przy tworzeniu: `CREATE SYNONYM lab_g FOR lab_ghost` się udaje, a użycie
  zgłasza **ORA-00980**: synonym translation is no longer valid.
- Synonimy dzielą przestrzeń nazw z tabelami, widokami i sekwencjami: ta sama nazwa co twoja tabela: **ORA-00955**.
- Rozwiązywanie nazwy bez kwalifikatora: najpierw twój schemat (łącznie z prywatnymi synonimami), potem synonimy publiczne.

## Częste pułapki

1. `ALTER VIEW` nie zmieni zapytania; użyj `CREATE OR REPLACE VIEW` (zachowuje nadania).
2. Usunięcie widoku albo synonimu nigdy nie wpływa na dane ani na tabelę bazową.
3. Widok z wyrażeniem bez aliasu to błąd, a nie automatycznie nazwana kolumna.
4. Błędy `WITH CHECK OPTION` to ORA-01402; błędy `WITH READ ONLY` to w 19c ORA-42399.
5. CYCLE zaczyna od MINVALUE, a nie od START WITH.
6. `CURRVAL` jest per sesja i wymaga najpierw `NEXTVAL`; dwa `NEXTVAL` w jednym wierszu zwracają tę samą wartość.
7. START WITH nie da się zmienić; MAXVALUE nie może spaść poniżej bieżącej wartości.
8. Klucze obce nie dostają automatycznie indeksu; UNIQUE nie oznacza NOT NULL.
9. Niewidoczny indeks jest nadal aktualizowany przez DML i można go znów uczynić VISIBLE; nie jest usuwany.
10. `CREATE SYNONYM` nie nadaje uprawnień i nie sprawdza celu.

> **Oracle a standardowy SQL / inne bazy danych**
>
> - Widoki, `WITH CHECK OPTION` i `CREATE VIEW` to standardowy SQL. `WITH READ ONLY`, `FORCE` i
>   `CREATE OR REPLACE VIEW` to rozszerzenia Oracle (PostgreSQL i MySQL też mają `OR REPLACE`).
> - `CREATE SEQUENCE` jest w standardzie (SQL:2003), ale standard oraz PostgreSQL / SQL Server używają
>   `NEXT VALUE FOR s` albo `nextval('s')`; Oracle używa `s.NEXTVAL` i `s.CURRVAL`. MySQL nie ma
>   sekwencji (AUTO_INCREMENT). Oracle 12c oferuje też kolumny identity.
> - `CREATE INDEX` w ogóle nie jest częścią standardu SQL; każdy produkt ma własną składnię.
>   Indeksy funkcyjne w PostgreSQL nazywają się indeksami na wyrażeniach.
> - Synonimy są specyficzne dla Oracle (i SQL Server); PostgreSQL używa zamiast nich `search_path` albo widoków.

## Więcej sprawdzonych faktów (18 października 2026, 19c i 23ai)

| Polecenie | Wynik |
|---|---|
| `CREATE SYNONYM s FOR employees`, gdy `s` istnieje | **ORA-00955**; `CREATE OR REPLACE SYNONYM` zmienia cel |
| `ALTER SYNONYM s FOR departments` | **ORA-00922** (ALTER SYNONYM nie zmieni celu) |
| `DROP SYNONYM dict` (DICT jest tylko publiczny) | **ORA-01434**: private synonym to be dropped does not exist |
| `CREATE SYNONYM s FOR employees.last_name`, potem użycie | Utworzony (czytany jako schemat EMPLOYEES, obiekt LAST_NAME); użycie: **ORA-00980** |
| Tabela usunięta, a potem utworzona ponownie z tą samą nazwą | Synonim w międzyczasie INVALID, potem działa i znów jest VALID |
| `GENERATED ALWAYS AS IDENTITY`: jawna wartość (nawet NULL) / UPDATE | **ORA-32795** / **ORA-32796** |
| `GENERATED BY DEFAULT AS IDENTITY`: jawny NULL | **ORA-01400**; `BY DEFAULT ON NULL` go wypełnia |
| Druga kolumna identity | **ORA-30669** |
| Kolumna identity w słowniku | `IDENTITY_COLUMN` YES, `NULLABLE` N, sekwencja `ISEQ$$_nnnnn` usuwana razem z tabelą |
| `DEFAULT seq.NEXTVAL` po `DROP SEQUENCE seq` | Wstawienia kończą się błędem **ORA-02289** |
| `NEXTVAL` z `ORDER BY`, w widoku inline, z `DISTINCT`, w `WHERE` | **ORA-02287** |
| `ADD CONSTRAINT ... UNIQUE (email)`, gdy istnieje nieunikalny indeks na email | Używa tego indeksu (`INDEX_NAME`), bez nowego indeksu; `DROP INDEX` potem **ORA-02429** |
| Drugi indeks na `(email)`, unikalny albo nie | **ORA-01408**; dozwolony, jeśli `INVISIBLE` (tylko jeden widoczny na listę kolumn) |
| `DROP PRIMARY KEY` / `DROP PRIMARY KEY KEEP INDEX` | Usuwa / zachowuje indeks utworzony przez Oracle dla klucza |
| `INSERT INTO (SELECT employee_id, last_name FROM employees)` | **ORA-01400** na hire_date |
| Widok `WITH CHECK OPTION`, który nie pokazuje department_id, wstawienie | **ORA-01402** (kolumna dostaje NULL) |
| `DELETE` przez `employees JOIN departments` | Usuwa tylko z employees (tabela zachowująca klucz) |
| `CREATE OR REPLACE VIEW` bez CHECK OPTION | Ograniczenie widoku typu V znika |
| `CREATE VIEW v (a, b) AS SELECT one_column ...` | **ORA-01730** |
| `WHERE ROWNUM <= 3 ORDER BY salary` | Najpierw ROWNUM, potem sortowanie: zły top-N; sortuj w widoku inline |

## Różnice w Oracle 23ai (1Z0-171)

Sprawdzono na Oracle 23ai Free (23.26), ten sam schemat ORASTUDY, obiekty `LAB_N11_` potem usunięte.

- **`IF NOT EXISTS` / `IF EXISTS`**: `CREATE VIEW | SEQUENCE | INDEX | SYNONYM | TABLE IF NOT EXISTS`
  oraz `DROP ... IF EXISTS` działają. W 19c to błędy składni (ORA-00905, ORA-00933, ORA-00969).
- `IF NOT EXISTS` nic nie robi, gdy nazwa istnieje, **nawet jeśli definicja jest inna**:
  `CREATE INDEX IF NOT EXISTS i ON t (name)` po `i ON t (id)` zachowuje stary indeks;
  `CREATE SEQUENCE IF NOT EXISTS s START WITH 50` zachowuje istniejącą `s` (LAST_NUMBER 1).
- `CREATE OR REPLACE VIEW IF NOT EXISTS ...`: **ORA-11541** (REPLACE i IF NOT EXISTS nie mogą wystąpić razem).
- `SELECT s.NEXTVAL;` działa bez `FROM dual` (19c: ORA-00923).
- Zmiana kolumny tabeli bez zachowania klucza w widoku złączenia: **ORA-30926**, gdy wiersz zmieniłby się
  dwa razy (19c: zawsze ORA-01779).
- Zmienione komunikaty, te same kody: ORA-04013 "The CACHE value may not exceed the CYCLE value.",
  ORA-08002 "Sequence ... is not yet defined in this session."
- Adnotacje: `name VARCHAR2(20) ANNOTATIONS (display 'Name')` jest wymieniona w `USER_ANNOTATIONS_USAGE`
  (ANNOTATION_NAME `DISPLAY`, COLUMN_NAME `NAME`). Domeny: `CREATE DOMAIN` pojawia się w `USER_DOMAINS`,
  a `USER_TAB_COLUMNS` ma kolumnę `DOMAIN_NAME`. Żadnej z tych rzeczy nie ma w 19c (ORA-00942 / ORA-00904).
- Bez zmian: reguły synonimów, kolumny identity, ORA-01408, ORA-02429, KEEP INDEX, błędy CHECK OPTION i READ ONLY.
