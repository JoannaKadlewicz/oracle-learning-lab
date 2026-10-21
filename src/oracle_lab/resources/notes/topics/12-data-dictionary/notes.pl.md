# Temat 12: Słownik danych

Środowisko: Oracle Database 19.3, schemat ORASTUDY. Wszystkie wyniki niżej zostały **wykonane**
17 października 2026 na przykładowym schemacie. Cel egzaminu: 15.1 używanie widoków słownika danych.

## Pojęcie

Słownik danych to zestaw tabel tylko do odczytu, należących do SYS, które Oracle sam utrzymuje
przy każdym wykonaniu DDL. Czytasz go przez widoki, dostępne przez publiczne synonimy.

| Prefiks | Pokazuje | Kolumna OWNER? |
|---|---|---|
| `USER_` | Obiekty, których jesteś właścicielem | Zwykle nie (to zawsze ty) |
| `ALL_` | Obiekty twoje albo te, do których masz uprawnienia | Tak |
| `DBA_` | Każdy obiekt w bazie danych | Tak; wymaga uprawnień takich jak SELECT ANY DICTIONARY |
| `V$` | Dynamiczne dane o wydajności działającej instancji | nie dotyczy |

`DICTIONARY` (synonim `DICT`) wymienia widoki słownika z opisem w `COMMENTS`
(pustym w tej ćwiczeniowej bazie, gdzie zapytanie niżej zwraca 12 nazw z komentarzami NULL);
`DICT_COLUMNS` opisuje ich kolumny. Sam `USER_TABLES` to widok SYS dostępny przez
synonim PUBLIC.

```sql
SELECT table_name, comments FROM dictionary WHERE table_name LIKE 'USER_IND%';
```

Nazwy są zapisane **wielkimi literami** (chyba że utworzono je w cudzysłowie):
`WHERE table_name = 'employees'` zwraca 0 wierszy; użyj `'EMPLOYEES'`.

## Widoki, które trzeba znać

| Widok | Jeden wiersz na | Kluczowe kolumny |
|---|---|---|
| `USER_OBJECTS` | Obiekt schematu | `OBJECT_NAME`, `OBJECT_TYPE`, `STATUS`, `CREATED`, `LAST_DDL_TIME` |
| `USER_TABLES` | Tabelę | `TABLE_NAME`, `NUM_ROWS` (ze statystyk, nie na bieżąco) |
| `USER_TAB_COLUMNS` | Kolumnę tabeli albo widoku | `COLUMN_ID`, `DATA_TYPE`, `DATA_LENGTH`, `DATA_PRECISION`, `DATA_SCALE`, `NULLABLE` |
| `USER_CONSTRAINTS` | Ograniczenie | `CONSTRAINT_TYPE`, `R_CONSTRAINT_NAME`, `DELETE_RULE`, `SEARCH_CONDITION(_VC)`, `INDEX_NAME`, `STATUS` |
| `USER_CONS_COLUMNS` | Kolumnę ograniczenia | `CONSTRAINT_NAME`, `COLUMN_NAME`, `POSITION` |
| `USER_INDEXES` | Indeks | `INDEX_TYPE`, `UNIQUENESS`, `VISIBILITY`, `STATUS` |
| `USER_IND_COLUMNS` | Kolumnę indeksu | `INDEX_NAME`, `COLUMN_NAME`, `COLUMN_POSITION` |
| `USER_VIEWS` | Widok | `TEXT` (LONG), `TEXT_VC` |
| `USER_SEQUENCES` | Sekwencję | `MIN_VALUE`, `MAX_VALUE`, `INCREMENT_BY`, `CYCLE_FLAG`, `CACHE_SIZE`, `LAST_NUMBER` |
| `USER_SYNONYMS` | Prywatny synonim | `SYNONYM_NAME`, `TABLE_OWNER`, `TABLE_NAME` |
| `USER_TAB_COMMENTS` / `USER_COL_COMMENTS` | Tabelę albo widok / kolumnę | `COMMENTS` (NULL do czasu `COMMENT ON`) |

Typy ograniczeń: `P` klucz główny, `U` unikalność, `R` klucz obcy, `C` CHECK **oraz NOT NULL**,
`V` widok WITH CHECK OPTION, `O` widok WITH READ ONLY.

## Przykład 1: ograniczenia tabeli EMPLOYEES

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

7 wierszy: ograniczenia NOT NULL mają typ C. Ich `SEARCH_CONDITION_VC` to `"LAST_NAME" IS NOT NULL`.
Sama kolumna `SEARCH_CONDITION` jest typu LONG i nie można jej użyć z `LIKE`.

## Przykład 2: klucze obce ze wskazywaną tabelą

`R_CONSTRAINT_NAME` przechowuje wskazywane **ograniczenie** (`ORDERS_CUSTOMER_FK` → `CUSTOMERS_PK`),
a nie tabelę. Złącz `USER_CONSTRAINTS` z samym sobą:

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

## Przykład 3: kolumny i ich rozmiary

| Kolumna (deklaracja) | DATA_TYPE | DATA_LENGTH | DATA_PRECISION, SCALE | NULLABLE |
|---|---|---|---|---|
| `employee_id NUMBER(6) PRIMARY KEY` | NUMBER | 22 | 6, 0 | N |
| `last_name VARCHAR2(25) NOT NULL` | VARCHAR2 | 25 | | N |
| `hire_date DATE NOT NULL` | DATE | 7 | | N |
| `salary NUMBER(8,2)` | NUMBER | 22 | 8, 2 | Y |

`DATA_LENGTH` to bajty zapisu: 22 dla każdego NUMBER, 7 dla DATE. Kolumna klucza głównego ma
`N` nawet bez ograniczenia NOT NULL.

## Przykład 4: jeden wiersz na kolumnę ograniczenia

`USER_CONS_COLUMNS WHERE table_name = 'ORDER_ITEMS'` zwraca 5 wierszy: `ORDER_ITEMS_PK` ma dwa
(ORDER_ID na pozycji 1, LINE_NO na pozycji 2), a dwa klucze obce i CHECK na quantity po jednym.
ORDER_ID występuje dwa razy (PK i FK).

## Inne sprawdzone fakty

- `USER_INDEXES WHERE table_name = 'EMPLOYEES'`: 2 wiersze (PK i UK); brak indeksu dla kluczy obcych.
- `USER_CONSTRAINTS.INDEX_NAME` dla `EMPLOYEES_EMAIL_UK` to `EMPLOYEES_EMAIL_UK`.
- `USER_OBJECTS WHERE object_type = 'CONSTRAINT'`: 0 wierszy; ograniczenia nie są obiektami schematu.
- `USER_TAB_COMMENTS` ma wiersz dla każdej tabeli, także bez komentarza (COMMENTS NULL).
- `UPDATE user_tables SET ...`: **ORA-02030**: can only select from fixed tables/views. Słownik zmienia się tylko przez DDL.
- `USER_SEQUENCES.LAST_NUMBER` po wydaniu 1, 2, 3 przy CACHE 20 to 21: wyprzedza
  wydane wartości. Nie ma kolumn CURRVAL ani NEXTVAL.
- `USER_CONSTRAINTS` i `USER_CONS_COLUMNS` mają kolumnę OWNER; `USER_TABLES` i `USER_OBJECTS` jej nie mają.

## Częste pułapki

1. Literały małymi literami w `WHERE table_name = ...` nic nie znajdują.
2. Ograniczenia NOT NULL mają typ `C`, a nie osobny typ.
3. `R_CONSTRAINT_NAME` to nazwa ograniczenia, a nie tabeli.
4. Kolumny ograniczeń są w `USER_CONS_COLUMNS`, kolumny indeksów w `USER_IND_COLUMNS`,
   kolumny tabel w `USER_TAB_COLUMNS`; `USER_COLUMNS` i `USER_COMMENTS` nie istnieją.
5. `USER_TAB_COLUMNS` obejmuje kolumny widoków; złącz z `USER_TABLES`, aby zostawić same tabele.
6. Widoki `USER_` pokazują tylko twoje obiekty, nawet jeśli masz dostęp do cudzych; użyj `ALL_`.
7. `NUM_ROWS` i `LAST_NUMBER` to nie liczniki na bieżąco.
8. Kolumn LONG (`SEARCH_CONDITION`, `TEXT`, `DATA_DEFAULT`) nie użyjesz w `LIKE`; użyj wersji `_VC`.

> **Oracle a standardowy SQL / inne bazy danych**
>
> - Standard SQL definiuje `INFORMATION_SCHEMA` (`TABLES`, `COLUMNS`, `TABLE_CONSTRAINTS`, ...),
>   które udostępniają PostgreSQL, MySQL i SQL Server. Oracle go nie ma; ma własne
>   widoki `USER_` / `ALL_` / `DBA_`.
> - Inne bazy danych inaczej zmieniają nazwy bez cudzysłowów: PostgreSQL zapisuje małymi literami, Oracle wielkimi.
> - `pg_catalog` z PostgreSQL, widoki `sys.` z SQL Server i widoki `V$` z Oracle są specyficzne dla produktu.

## Więcej sprawdzonych faktów (18 października 2026, 19c i 23ai)

- `SELECT owner FROM user_tables`: **ORA-00904**. `SELECT ... FROM dba_tables` jako ORASTUDY: **ORA-00942** (brak uprawnień wygląda jak brak widoku).
- `USER_VIEWS.TEXT LIKE ...`: **ORA-00932** (LONG); użyj `TEXT_VC`.
- Liczby w przykładowym schemacie: 10 kolumn w `EMPLOYEES`, 5 ograniczeń na `ORDERS`, 10 indeksów
  (9 PK + 1 UK, bez indeksów FK), 3 kolumny `NULLABLE = 'N'` w employees (łącznie z PK),
  9 wierszy w `USER_CATALOG` (bez indeksów), 10 wierszy w `USER_COL_COMMENTS` dla employees (wszystkie NULL).
- `USER_OBJECTS WHERE object_name = 'EMPLOYEES_PK'`: jeden wiersz, typ `INDEX` (ograniczenie nie jest obiektem).
- `USER_CONSTRAINTS.STATUS` to ENABLED/DISABLED; `VALIDATED` i `GENERATED` ('USER NAME') to osobne kolumny.
- `DATA_TYPE` zawiera precyzję dla typów daty i czasu: `TIMESTAMP(0) WITH LOCAL TIME ZONE`.
- Indeks funkcyjny: `USER_IND_COLUMNS.COLUMN_NAME` to ukryta kolumna w stylu `SYS_NC00011$`;
  wyrażenie `UPPER("LAST_NAME")` jest w `USER_IND_EXPRESSIONS`.
- `USER_UPDATABLE_COLUMNS` pokazuje UPDATABLE/INSERTABLE/DELETABLE dla każdej kolumny widoku (NO dla `salary * 12`).
- Ponowne `COMMENT ON` nadpisuje, `IS ''` czyści, działa na widokach (TABLE_TYPE VIEW);
  `COMMENT ON INDEX`: **ORA-32594**.
- `USER_SEQUENCES` nie ma kolumn START_WITH, CURRVAL ani NEXTVAL.
- Krótkie publiczne synonimy: DICT, CAT, TABS, COLS, IND, OBJ, SEQ, SYN (właściciel PUBLIC, cel to widoki SYS).

## Różnice w Oracle 23ai (1Z0-171)

Sprawdzono na Oracle 23ai Free (23.26), ten sam schemat ORASTUDY.

- `DICTIONARY` jest dużo większy (5798 wierszy wobec 970 w naszej 19c), a jego `COMMENTS` są wypełnione
  (na przykład USER_CATALOG: "Tables, Views, Synonyms and Sequences owned by the user"); w naszej instancji 19c
  są NULL. 23ai wymienia też krótkie synonimy (TABS, CAT, COLS...) jako wiersze DICTIONARY; 19c nie.
- Nowe widoki słownika: `USER_ANNOTATIONS_USAGE` (adnotacje na tabelach, kolumnach, widokach, indeksach),
  `USER_DOMAINS` i `USER_DOMAIN_COLS` (domeny przypadków użycia danych), `USER_JSON_DUALITY_VIEWS`,
  `USER_PROPERTY_GRAPHS`, `USER_PG_COMMENTS`. W 19c zgłaszają ORA-00942.
- Nowe kolumny: `USER_TAB_COLUMNS.DOMAIN_NAME`, `USER_VIEWS.DUALITY_VIEW` (19c: ORA-00904).
- Komunikaty błędów wymieniają obiekt albo mają nowe brzmienie, kody bez zmian: ORA-00942 `table or view "SYS"."DBA_TABLES" does not exist`,
  ORA-00932 `expression is of data type LONG, which is incompatible with expected data type CHAR`.
- `CREATE ... IF NOT EXISTS` / `DROP ... IF EXISTS` zostawiają słownik bez zmian, gdy obiekt
  już istnieje / go nie ma, bez błędu (zobacz temat 11).
- Bez zmian: nazwy wielkimi literami, zakres USER_/ALL_/DBA_, typy ograniczeń, widoki komentarzy, kolumny USER_SEQUENCES.
