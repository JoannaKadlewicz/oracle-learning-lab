# Temat 10: DDL do zarządzania tabelami i ich relacjami

Środowisko: Oracle Database 19c, schemat ORASTUDY. Wyniki i kody błędów niżej zostały
wykonane na tymczasowych tabelach `LAB_`, które potem usunięto (DDL robi COMMIT, więc
przykładowych tabel nigdy nie zmieniano). Wiersze o koszu i FLASHBACK opisują udokumentowane zachowanie. Cele 12.1–12.4 i 12.6–12.8 (12.5 TRUNCATE jest w
temacie 9). Tabel zewnętrznych (12.7) ORASTUDY nie może tworzyć (brak uprawnień do katalogów), więc
ta część opisuje tylko udokumentowane zachowanie.

## 12.1 Opisywanie tabel i praca z nimi

- Nazwy bez cudzysłowów: zaczynają się od litery; litery, cyfry, `_`, `$`, `#`; do 128 bajtów (19c);
  nie mogą być słowem zastrzeżonym; są zapisywane **wielkimi literami**. `lab_t10_x$h` działa; `lab_t10-x` → ORA-00922,
  `order` → ORA-00903, nazwa zaczynająca się od cyfry → błąd.
- Nazwy w cudzysłowie zachowują wielkość liter: po `CREATE TABLE "Staff"` zapytanie `SELECT * FROM staff` → **ORA-00942**;
  tak samo `"STAFF"`; działa tylko `"Staff"`.
- `DESCRIBE t` (SQL*Plus) / `USER_TAB_COLUMNS` pokazują kolumny, typy i dopuszczalność NULL.
- `ALTER TABLE t READ ONLY`: SELECT i DROP działają; INSERT, DELETE, TRUNCATE → **ORA-12081**.
- `DROP TABLE t` przenosi t do kosza (`FLASHBACK TABLE t TO BEFORE DROP`);
  `DROP TABLE t PURGE` nie. Tabela, do której odwołuje się klucz obcy → **ORA-02449**,
  chyba że z `CASCADE CONSTRAINTS` (usuwa ograniczenia kluczy obcych, a nie wiersze podrzędne).

## 12.2 Kolumny i typy danych

| Typ | Uwagi |
|---|---|
| `VARCHAR2(n)` | rozmiar wymagany (inaczej ORA-00906); maks. 4000 bajtów (32767 przy MAX_STRING_SIZE=EXTENDED) |
| `CHAR(n)` | stała długość, dopełniany spacjami; domyślny rozmiar 1; maks. 2000 bajtów |
| `NUMBER(p,s)` | łącznie p cyfr, s po przecinku; zwykły `NUMBER` = dowolna wartość |
| `DATE` | data + godzina z dokładnością do sekundy; `TIMESTAMP(n)` dodaje ułamki sekund |
| `CLOB`, `BLOB` | LOB-y: bez ORDER BY / GROUP BY / porównań (ORA-00932) |
| `LONG` | przestarzały; jeden na tabelę (ORA-01754) |

| Wyrażenie | Wynik |
|---|---|
| `CAST(12.345 AS NUMBER(5,2))` | `12.35` (zaokrąglone) |
| `CAST(1250.5 AS NUMBER(5,-2))` | `1300` (ujemna skala zaokrągla do setek) |
| `commission_pct NUMBER(3,2)` ustawione na 10 | **ORA-01438** (maks. 9.99) |
| `country_code CHAR(2)` ustawione na `'USA'` | **ORA-12899** value too large (nigdy nie jest obcinane) |

`ALTER TABLE ... MODIFY`: poszerzenie zawsze działa; zwężenie działa tylko wtedy, gdy wszystkie wartości się mieszczą
(**ORA-01441**); zmiana typu wymaga pustej kolumny (**ORA-01439**, nawet dla `'123'`).

## 12.3 Tworzenie tabel

```sql
CREATE TABLE lab_projects (
    project_id     NUMBER(6)    CONSTRAINT lab_projects_pk PRIMARY KEY,           -- na poziomie kolumny
    project_name   VARCHAR2(40) NOT NULL,
    status         VARCHAR2(10) DEFAULT 'NEW',
    department_id  NUMBER(4)    REFERENCES departments (department_id),
    CONSTRAINT lab_projects_uk UNIQUE (project_name, department_id)                -- na poziomie tabeli
);
```

- Klucz z kilku kolumn musi być poza definicją kolumny; dwie klauzule `PRIMARY KEY` przy kolumnach → **ORA-02260**.
- `DEFAULT` działa tylko wtedy, gdy kolumnę pominięto: jawny NULL jest zapisywany jako NULL
  (użyj `DEFAULT ON NULL`, 12c+). `MODIFY (status DEFAULT 'OPEN')` zmienia tylko przyszłe wstawienia.
  Wartość domyślna nie może odwoływać się do innej kolumny (**ORA-00904**).
- **CTAS** kopiuje kolumny, dane i tylko jawne ograniczenia NOT NULL (bez PK, UNIQUE, CHECK,
  FK i indeksów). `WHERE 1 = 2` kopiuje samą strukturę. Wyrażenia wymagają aliasu:
  `SELECT e.salary * 12 FROM ...` → **ORA-00998**.

## 12.4 Usuwanie kolumn i SET UNUSED

```sql
ALTER TABLE t DROP COLUMN notes;             -- jedna kolumna
ALTER TABLE t DROP (notes, fax);             -- kilka: nawiasy, bez słowa COLUMN
ALTER TABLE t SET UNUSED (notes);            -- szybko, nieodwracalnie, ukryte w USER_TAB_COLUMNS
ALTER TABLE t DROP UNUSED COLUMNS;           -- odzyskanie miejsca później
```

- `DROP COLUMN a, b` → ORA-00933; `DROP COLUMNS (a, b)` → ORA-02000. Ostatniej kolumny nie da się usunąć (**ORA-12983**).
- Kolumna klucza, do którego się odwołują, wymaga `CASCADE CONSTRAINTS` (inaczej **ORA-12992**).
- Nieużywane kolumny są liczone w `USER_UNUSED_COL_TABS`; ich nazwy można użyć ponownie.

## 12.6 Tabele tymczasowe

| | Globalna tabela tymczasowa | Prywatna tabela tymczasowa (18c+) |
|---|---|---|
| Definicja | trwała, współdzielona | tylko w sesji, w pamięci |
| Nazwa | dowolna | prefiks `ORA$PTT_` (parametr PRIVATE_TEMP_TABLE_PREFIX) |
| Domyślnie | `ON COMMIT DELETE ROWS` (DURATION `SYS$TRANSACTION`) | `ON COMMIT DROP DEFINITION` |
| Opcja | `ON COMMIT PRESERVE ROWS` (`SYS$SESSION`) | `ON COMMIT PRESERVE DEFINITION` |
| Słownik | `USER_TABLES.TEMPORARY = 'Y'` | `USER_PRIVATE_TEMP_TABLES` |

Po wstawieniu 3 wierszy do każdej GTT i COMMIT: tabela z DELETE ROWS ma 0 wierszy, tabela z PRESERVE ROWS
3 wiersze. Dane zawsze są prywatne dla sesji; indeksy na GTT są dozwolone.

## 12.7 Tabele zewnętrzne (udokumentowane zachowanie, nie wykonano)

```sql
CREATE TABLE ext_sales (id NUMBER, amount NUMBER)
ORGANIZATION EXTERNAL (
  TYPE ORACLE_LOADER               -- albo ORACLE_DATAPUMP
  DEFAULT DIRECTORY data_dir       -- obiekt DIRECTORY (do utworzenia potrzeba CREATE ANY DIRECTORY)
  ACCESS PARAMETERS (FIELDS TERMINATED BY ',')
  LOCATION ('sales.csv'))
REJECT LIMIT UNLIMITED;
```

Tylko do odczytu: bez DML, bez indeksów, bez wymuszanych kluczy. Plik jest czytany w czasie zapytania; dane skopiujesz
przez CTAS albo INSERT ... SELECT.

## 12.8 Zarządzanie ograniczeniami

| Ograniczenie | Dopuszcza NULL? | Uwagi |
|---|---|---|
| `NOT NULL` | nie | tylko na poziomie kolumny; dodasz je później przez `MODIFY (c NOT NULL)` |
| `UNIQUE` | tak, wiele NULL | tworzy/używa indeksu unikalnego |
| `PRIMARY KEY` | nie | jeden na tabelę; UNIQUE + NOT NULL |
| `FOREIGN KEY` | tak | wskazuje PK albo klucz UNIQUE; `ON DELETE CASCADE / SET NULL` |
| `CHECK` | przechodzi przy UNKNOWN | bez SYSDATE, USER, sekwencji i podzapytań |

- `ALTER TABLE t ADD CONSTRAINT n NOT NULL (c)` → ORA-00904; `ADD (c NOT NULL)` → ORA-02263; użyj
  `MODIFY (c NOT NULL)` albo `MODIFY c CONSTRAINT n NOT NULL`.
- Istniejące duplikaty: `ADD PRIMARY KEY` → **ORA-02437**.
- `ENABLE NOVALIDATE` sprawdza tylko nowy DML: `CHECK (id > 5) ENABLE NOVALIDATE` zostało przyjęte przy
  wierszach z id 1, a potem `INSERT ... VALUES (2)` zakończył się błędem ORA-02290. Samo `ENABLE` oznacza VALIDATE:
  ponowne włączenie po DISABLE zakończyło się błędem ORA-02293.
- Wyłączenie PK, do którego się odwołują: **ORA-02297**; `DISABLE PRIMARY KEY CASCADE` wyłączyło też FK.
- `CHECK (d > SYSDATE)` → **ORA-02436**. `DROP TABLE parent` → **ORA-02449**; z `CASCADE CONSTRAINTS`
  tabela podrzędna została, usunięto tylko jej ograniczenie FK.
- Błędy: ORA-00001 unikalność, ORA-01400 NULL do NOT NULL, ORA-02290 check, ORA-02291 brak
  rodzica, ORA-02292 istnieją dzieci.

## Częste pułapki

1. Definiowanie NOT NULL poza kolumną albo dodawanie go przez `ADD CONSTRAINT`.
2. Oczekiwanie, że CTAS skopiuje klucz główny, ograniczenia CHECK albo indeksy.
3. Zapomniany alias dla wyrażenia w CTAS (ORA-00998).
4. `DROP COLUMN a, b` zamiast `DROP (a, b)`.
5. Przekonanie, że jawny NULL dostaje wartość DEFAULT.
6. Oczekiwanie, że Oracle obetnie za długi tekst albo przytnie za dużą liczbę.
7. Zmiana typu kolumny, gdy ma dane (ORA-01439), nawet jeśli wartości dałoby się przekonwertować.
8. Przekonanie, że ON COMMIT PRESERVE ROWS sprawia, że wiersze GTT widzą inne sesje.
9. Mylenie ORA-02291 (dziecko bez rodzica) z ORA-02292 (rodzic z dziećmi).

> **Oracle a standardowy SQL / inne bazy danych**
> - `VARCHAR2` i `''` = NULL to specyfika Oracle; standardowy SQL używa `VARCHAR`.
> - Oracle używa `ALTER TABLE ... MODIFY`; PostgreSQL używa `ALTER COLUMN ... TYPE / SET NOT NULL`,
>   a SQL Server `ALTER COLUMN`.
> - DDL robi w Oracle COMMIT, więc `CREATE`/`ALTER`/`DROP` nie da się wycofać (w PostgreSQL się da).
> - Globalne tabele tymczasowe są zgodne ze standardem SQL; prywatne tabele tymczasowe, `SET UNUSED`,
>   tabele `READ ONLY` i kosz to specyfika Oracle.
> - Oracle nie ma `ON UPDATE CASCADE` dla kluczy obcych (MySQL i PostgreSQL mają).

## Więcej sprawdzonych wyników (19c i 23ai)

- Prywatne tabele tymczasowe: bez ograniczeń (nawet NOT NULL), bez DEFAULT, bez indeksu → **ORA-14451**;
  CTAS działa; nazwa bez `ORA$PTT_` → ORA-00903; GTT o nazwie `ora$ptt_...` → ORA-32463;
  `ON COMMIT DELETE ROWS` → ORA-00901. Utworzenie takiej tabeli **nie** zatwierdziło czekającego INSERT, a
  następny ROLLBACK usunął też tabelę (DROP DEFINITION).
- Globalne tabele tymczasowe: klucz obcy → **ORA-14455** (PK i CHECK są w porządku). Gdy sesje mają
  wiersze: `ALTER TABLE ... ADD` → ORA-14450, `DROP` → ORA-14452. `TRUNCATE` usuwa tylko twoje wiersze.
- Tabele zewnętrzne: brak obiektu DIRECTORY kończy się błędem przy CREATE (**ORA-06564**); PRIMARY KEY → ORA-30657.
- `DROP COLUMN` / `SET UNUSED` kolumny z wielokolumnowego PK albo CHECK → **ORA-12991**;
  `CASCADE CONSTRAINTS` usuwa całe ograniczenie. Kolumna klucza nadrzędnego → ORA-12992. Tabela READ ONLY
  → ORA-12081. Usunięcie kolumny usuwa jej jednokolumnowy indeks.
- Po `SET UNUSED (note)`: `ADD (note DATE)` działa, `DROP COLUMN note` → ORA-00904, USER_TAB_COLS
  pokazuje ukrytą kolumnę `SYS_C00002_...$`. Późniejsze `DROP COLUMN` dowolnej kolumny usunęło też
  nieużywane kolumny (USER_UNUSED_COL_TABS był potem pusty).
- `PRIMARY KEY DEFERRABLE INITIALLY DEFERRED`: dwa równe klucze wstawiły się bez problemu, `COMMIT` → **ORA-02091**,
  a tabela była pusta; `SET CONSTRAINT ... IMMEDIATE` → ORA-00001, ale wiersze zostały. Indeks
  klucza jest NONUNIQUE. `SET CONSTRAINT` na ograniczeniu nieodraczalnym → ORA-02447;
  `MODIFY CONSTRAINT ... DEFERRABLE` to błąd składni (odraczalność ustala się przy tworzeniu).
- `pid NOT NULL REFERENCES parent ON DELETE SET NULL`: usunięcie rodzica z dziećmi → ORA-01407.
- FK do kolumny bez PK/UNIQUE → ORA-02270; do kolumny innego typu → ORA-02267.
  `ON UPDATE CASCADE` / `ON DELETE RESTRICT` nie istnieją (błąd składni). LOB w PK/UNIQUE → ORA-02329.
- Identity: `GENERATED ALWAYS` → ORA-32795 przy INSERT, ORA-32796 przy UPDATE; `BY DEFAULT` z
  jawnym NULL → ORA-01400; `BY DEFAULT ON NULL` go wypełnia; druga kolumna identity → ORA-30669.
- CTAS: `(id PRIMARY KEY, name) AS SELECT ...` działa; typy danych na liście → ORA-01773; zła liczba
  nazw → ORA-01730. Wartości domyślne i identity nie są kopiowane; NOT NULL (także wynikające z DEFAULT ON NULL
  albo identity) jest kopiowane.

## Różnice w Oracle 23ai (1Z0-171)

Sprawdzono na Oracle 23ai Free (23.26) na tymczasowych tabelach `LAB_N10_`; cała reszta tego tematu
(tabele tymczasowe, ograniczenia odraczalne, ORA-12991, kolumny identity, reguły CTAS) działała jak w 19c.

| 23ai | 19c |
|---|---|
| `CREATE TABLE IF NOT EXISTS t (...)`, gdy t istnieje: bez błędu, **zostaje stara definicja** (nowa lista kolumn jest ignorowana); polecenie i tak robi COMMIT | ORA-00922 |
| `DROP TABLE IF EXISTS t PURGE`, gdy t nie istnieje: bez błędu | ORA-00933 |
| `flag BOOLEAN DEFAULT FALSE`; wstawienie `'yes'` zapisało TRUE | ORA-00904 przy CREATE |
| `b NUMBER DEFAULT ON NULL FOR INSERT AND UPDATE 7`: UPDATE na NULL zapisuje 7 (USER_TAB_COLUMNS.DEFAULT_ON_NULL_UPD) | ORA-00936; DEFAULT ON NULL obejmuje tylko INSERT |
| USER_TAB_COLUMNS.DATA_DEFAULT_VC: wartość domyślna jako VARCHAR2 (DATA_DEFAULT to LONG) | kolumna nie istnieje |

- Do 4096 kolumn na tabelę tylko z parametrem inicjalizacyjnym `MAX_COLUMNS = EXTENDED`.
  Nasza baza 23ai ma domyślne `STANDARD`, a tabela z 1001 kolumnami zakończyła się błędem ORA-01792 dokładnie
  tak jak w 19c.
- Nie ma tego w tej wersji: `ALTER TABLE t ADD IF NOT EXISTS (...)` (ORA-02000), `DROP COLUMN IF EXISTS`
  (ORA-03048) i `CREATE OR REPLACE TABLE` (ORA-00922).
- Nowe kody niektórych błędów składni: `ON UPDATE CASCADE` → ORA-02000 (19c ORA-00905);
  `MODIFY CONSTRAINT ... DEFERRABLE` → ORA-03049 (19c ORA-00933). Komunikaty ORA-00001 i ORA-00942
  wymieniają teraz tabelę (i kolumny).
