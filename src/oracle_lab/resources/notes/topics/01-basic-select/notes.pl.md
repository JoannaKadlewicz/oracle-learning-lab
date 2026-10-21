# Temat 1: Pojęcia relacyjne i podstawowy SELECT

Środowisko: Oracle Database 19c, schemat ORASTUDY. Każdy wynik pokazany niżej został
**wykonany** na przykładowych danych (wycofany, nic się nie zmieniło). Formatowanie SQL*Plus
(szerokości kolumn, puste miejsce dla NULL) to sposób wyświetlania w kliencie, a nie zapisane dane.

## 1.1 Pojęcia relacyjnej bazy danych

| Model logiczny (ERD) | Relacyjny / SQL | Zapis fizyczny |
|---|---|---|
| Encja | Tabela | Segment w przestrzeni tabel |
| Atrybut | Kolumna (jeden typ danych) | Bajty w blokach danych |
| Wystąpienie | Wiersz (bez gwarantowanej kolejności) | Fragment wiersza z ROWID |
| Unikalny identyfikator | Klucz główny (UNIQUE + NOT NULL, jeden na tabelę) | Zwykle indeks unikalny |
| Związek | Klucz obcy (pasuje do klucza rodzica albo jest NULL) | — |

- Związki są zapisane jako **wartości**, a nie wskaźniki: `employees.department_id = departments.department_id`.
- Klucz obcy może być NULL (pracownik 108 Grant nie ma działu). Wartość bez rodzica kończy się błędem:

```sql
INSERT INTO employees (employee_id, last_name, hire_date, department_id)
VALUES (900, 'Novak', DATE '2024-01-10', 99);
-- ORA-02291: integrity constraint (ORASTUDY.EMPLOYEES_DEPARTMENT_FK) violated - parent key not found
```

- Pliki danych i przestrzenie tabel są fizyczne; SQL nigdy nie wymienia ich w zapytaniu.

## 1.2 Klauzule SELECT a ERD

- **Projekcja** (wybór atrybutów) = lista SELECT. **Selekcja** (wybór wierszy) = WHERE.
  **Złączenie** (przejście po związku) = FROM z kilkoma tabelami i warunkiem złączenia.
- 1:M: klucz obcy trafia po stronie *wielu* (employees przechowuje department_id).
- M:N: tabela pośrednia. `order_items` łączy orders i products; jej klucz główny
  `ORDER_ITEMS_PK` to `(order_id, line_no)`, z kluczami obcymi do obu rodziców.
- Związek opcjonalny („może”) = FK dopuszczający NULL; obowiązkowy („musi”) = FK NOT NULL.

## 1.3 Baza danych a SQL

| Kategoria | Polecenia |
|---|---|
| DML | SELECT, INSERT, UPDATE, DELETE, MERGE |
| DDL | CREATE, ALTER, DROP, RENAME, TRUNCATE, COMMENT (automatyczny COMMIT) |
| DCL | GRANT, REVOKE |
| Sterowanie transakcją | COMMIT, ROLLBACK, SAVEPOINT |

- SQL jest deklaratywny: o sposobie dostępu do danych decyduje optymalizator.
- Słowa kluczowe i identyfikatory bez cudzysłowów nie rozróżniają wielkości liter (zapisywane WIELKIMI LITERAMI); dane tak.
  `select E.Last_Name FROM Employees e where e.last_name = 'KING'` działa i zwraca **0 wierszy**.
- `;` to znak końca polecenia w kliencie (SQL*Plus, SQL Developer), a nie część polecenia.

## 2.1 Polecenie SELECT

```sql
SELECT *            FROM departments;        -- wszystkie kolumny, w kolejności z tabeli
SELECT e.*, e.salary FROM employees e;       -- * razem z innymi elementami musi mieć kwalifikator
```

- `SELECT *, salary FROM employees` → **ORA-00923**: FROM keyword not found where expected.
- `FROM employees AS e` → **ORA-00933**: SQL command not properly ended (AS jest tylko dla aliasów kolumn).
- Logiczna kolejność przetwarzania: FROM → WHERE → GROUP BY → HAVING → SELECT → ORDER BY.
- `DUAL` to jednowierszowa tabela do wyrażeń; 19c wymaga `FROM dual` (23ai sprawia, że FROM jest opcjonalne).
- `DESCRIBE employees` to polecenie SQL*Plus: Name, Null?, Type. Nie pokazuje innych ograniczeń.

## 2.2 Aliasy kolumn

```sql
SELECT e.salary * 12 AS annual, e.salary "Monthly Pay" FROM employees e ORDER BY annual;
```

- AS jest opcjonalne. Cudzysłowy zachowują wielkość liter, spacje i słowa zastrzeżone.
- Alias działa w ORDER BY, ale nie w WHERE / GROUP BY / HAVING tego samego zapytania
  (`WHERE annual > 100000` → **ORA-00904**).
- `SELECT e.last_name "Name" ... ORDER BY name` → **ORA-00904**: alias to `Name`, a nie `NAME`.
- `SELECT e.salary 'pay'` → **ORA-00923**: apostrofy tworzą tekst, a nie alias.

## 2.3 Konkatenacja i literały

| Wyrażenie | Wynik |
|---|---|
| `'It''s done'` | `It's done` |
| `q'[It's done]'`, `q'{O'Neil}'`, `q'!O'Neil!'` | tekst z apostrofem |
| `e.last_name \|\| NULL \|\| '!'` (King) | `King!` |
| `e.last_name \|\| ' earns ' \|\| e.salary` (Ernst) | `Ernst earns 6000` |
| `CONCAT(e.last_name, ', ', e.first_name)` | **ORA-00909** w 19c (tylko 2 argumenty) |

- `||` traktuje NULL jak pusty tekst; liczby i daty są konwertowane niejawnie.
- Ograniczniki q-quote: `[]`, `{}`, `()`, `<>` zamykają się swoją parą; każdy inny znak się powtarza.

## 2.4 DISTINCT

- Dotyczy **całego wiersza**: `SELECT DISTINCT department_id, job_title` → 6 wierszy.
- Wartości NULL tworzą jedną grupę: `SELECT DISTINCT commission_pct` → 4 wiersze (.3, .2, .15, NULL).
- `UNIQUE` to synonim w Oracle. DISTINCT musi stać zaraz po SELECT
  (`SELECT department_id, DISTINCT job_title` → **ORA-00936**).

## 2.5 Arytmetyka i NULL

| Wyrażenie (pracownik 104, pensja 6000) | Wynik |
|---|---|
| `e.salary + 100 * 12` | `7200` |
| `(e.salary + 100) * 12` | `73200` |
| `24000 * 12 + 24000 * 12 * NULL` (King) | NULL |
| `100 / NULL` | NULL |
| `e.salary / NVL(e.commission_pct, 0)` | **ORA-01476**: divisor is equal to zero |

- `*` `/` przed `+` `-`, poza tym od lewej do prawej. NULL to nie 0 ani spacja.
- W Oracle `''` **to** NULL.

## Częste pułapki

1. Użycie aliasu kolumny w WHERE (ORA-00904) albo zapisanie go w apostrofach (ORA-00923).
2. Alias w cudzysłowie w mieszanej wielkości liter, użyty bez cudzysłowu w ORDER BY.
3. `AS` przed aliasem tabeli (ORA-00933).
4. Przekonanie, że DISTINCT dotyczy tylko pierwszej kolumny albo że usuwa NULL.
5. Oczekiwanie, że `NULL + x` to `x` (to NULL), a `NULL || 'x'` to NULL (to `x`).
6. Zapominanie o kolejności działań: `salary + 100 * 12`.
7. Ucieczka ukośnikiem (`'It\'s'`): Oracle jej nie ma; podwój apostrof albo użyj `q'[...]'`.
8. Założenie, że bez ORDER BY wiersze wracają w kolejności wstawiania.

> **Oracle a standardowy SQL / inne bazy danych**
>
> - `FROM` jest obowiązkowe w 19c (`FROM dual`); PostgreSQL, SQL Server, MySQL i Oracle 23ai pozwalają na `SELECT 1`.
> - `''` to NULL w Oracle; w PostgreSQL, SQL Server i MySQL to pusty tekst.
> - `||` ignoruje NULL w Oracle; w standardowym SQL i PostgreSQL `'a' || NULL` to NULL.
>   SQL Server łączy teksty przez `+`, MySQL przez `CONCAT()` (`||` to domyślnie OR).
> - Alternatywne cudzysłowy `q'[...]'` i synonim `UNIQUE` dla DISTINCT istnieją tylko w Oracle.
> - `AS` przed aliasem tabeli przyjmuje większość innych baz danych, ale nie Oracle.
> - Identyfikatory bez cudzysłowów są zamieniane na WIELKIE LITERY w Oracle (standard), a na małe w PostgreSQL.

## Różnice w Oracle 23ai (1Z0-171)

Każdy punkt poniżej wykonano na Oracle 23ai (FREEPDB1) i, dla porównania, na 19c.

| Polecenie | 19c | 23ai |
|---|---|---|
| `SELECT 2 + 3 * 4` (bez FROM) | **ORA-00923** | `14`: FROM jest opcjonalne |
| `SELECT TRUE FROM dual` | **ORA-00904** "TRUE": invalid identifier | `TRUE` (typ danych BOOLEAN) |
| `CONCAT('a', 'b', 'c')` | **ORA-00909** (tylko 2 argumenty) | `abc` |
| `FROM employees AS e` | **ORA-00933** | **ORA-03048**: SQL reserved word 'AS' is not syntactically valid ... |
| `... ORDER BY e.last_name WHERE ...` | **ORA-00933** | **ORA-03048** |
| `SELECT e.department_id, DISTINCT e.job_title` | **ORA-00936** | **ORA-03045**: DISTINCT or UNIQUE keyword in select_list |
| `SELECT e.salary * 12 AS annual ... GROUP BY annual` | **ORA-00904** | 7 wierszy: GROUP BY przyjmuje alias |
| `SELECT e.salary * 12 AS annual ... HAVING annual > 100000` | **ORA-00904** | **ORA-00979** (nadal błąd) |

- Bez zmian w 23ai: alias w WHERE nadal zgłasza **ORA-00904**; `||` nadal ignoruje NULL;
  `''` to nadal NULL; `NULL / 0` to nadal NULL; reguły aliasów (ORA-00923 dla `2024_pay`, `'pay'`).
- Wiele komunikatów jest dłuższych i wymienia obiekty, których dotyczą, z tymi samymi kodami:
  ORA-00932 "expression is of data type DATE, which is incompatible with expected data type NUMBER",
  ORA-00001 "... violated on table ORASTUDY.ORDER_ITEMS columns (ORDER_ID, LINE_NO)",
  ORA-00942 "table or view "ORASTUDY"."X" does not exist". SQL*Plus 23 dodaje wiersz `Help:` z adresem URL.
