# Temat 2: Filtrowanie i sortowanie danych

Środowisko: Oracle Database 19c, schemat ORASTUDY. Każdy wynik SQL pokazany niżej został
**wykonany** na przykładowych danych (wycofany, nic się nie zmieniło). Zmienne podstawienia,
DEFINE i VERIFY to funkcje SQL*Plus (oraz skryptów SQLcl / SQL Developer): nie da się ich
uruchomić w aplikacji, więc ta część opisuje udokumentowane zachowanie SQL*Plus.

## 3.1 Kolejność operatorów

| Kolejność | Operatory |
|---|---|
| 1 | Arytmetyczne `*` `/`, potem `+` `-` oraz `\|\|` |
| 2 | Porównania: `=` `<>` `<` `>` `<=` `>=`, `IS [NOT] NULL`, `LIKE`, `[NOT] BETWEEN`, `[NOT] IN` |
| 3 | `NOT` |
| 4 | `AND` |
| 5 | `OR` |

```sql
WHERE e.job_title = 'Sales Rep' OR e.job_title = 'Programmer' AND e.salary > 5000
-- = Sales Rep OR (Programmer AND salary > 5000)  -> 5 wierszy: 103, 104, 105, 106, 108
```

`WHERE NOT e.department_id = 30 AND e.salary > 5000` zwróciło **3 wiersze** (100, 101, 105):
NOT dotyczy tylko pierwszego porównania, a Grant (dział NULL) i tak daje UNKNOWN.

## 3.2 Ograniczanie wierszy

- `BETWEEN a AND b` obejmuje granice (`>= a AND <= b`); `BETWEEN 10 AND 5` nic nie znajduje.
- `IN (lista)` to łańcuch `=` połączonych przez OR. `NOT IN (10, 20, NULL)` zwróciło **0 wierszy**;
  `IN (10, 20, NULL)` zwróciło 5 pracowników działów 10 i 20.
- `LIKE`: `%` = dowolny ciąg znaków, `_` = dokładnie jeden znak, z rozróżnianiem wielkości liter.
  `LIKE '_o%'` → Kochhar, Lorentz. Dosłowny znak wieloznaczny: `LIKE '%\_%' ESCAPE '\'`.
- NULL: działają tylko `IS NULL` / `IS NOT NULL`. `commission_pct = NULL` zwraca 0 wierszy, bez błędu.
- Daty zawierają godzinę: `order_date BETWEEN DATE '2024-03-01' AND DATE '2024-03-31'` zwróciło
  2 zamówienia (1004, 1005) i pominęło 1006 o 23:30. Użyj `>= DATE '2024-03-01' AND < DATE '2024-04-01'` (3 zamówienia).

Klauzula ograniczania wierszy (12c+), stosowana po ORDER BY:

```sql
ORDER BY e.employee_id OFFSET 2 ROWS FETCH NEXT 2 ROWS ONLY;   -- 102, 103
ORDER BY e.salary FETCH FIRST 2 ROWS WITH TIES;                -- 108, 106, 107 (3 wiersze)
ORDER BY e.salary DESC FETCH FIRST 25 PERCENT ROWS ONLY;      -- 3 wiersze (2,25 zaokrąglone w górę)
```

- `FIRST`/`NEXT` oraz `ROW`/`ROWS` są wymienne. Samo `OFFSET` zwraca resztę.
- `WITH TIES` ma sens tylko z ORDER BY i porównuje wszystkie klucze ORDER BY.
- `ROWNUM` jest nadawany przed ORDER BY; `WHERE ROWNUM > 1` zwróciło **0 wierszy**.

## 3.3 Zmienne podstawienia (SQL*Plus)

| Składnia | Działanie |
|---|---|
| `&name` | Pyta o wartość, jeśli `name` nie jest zdefiniowana; wartość jest użyta raz i nie jest zapamiętywana |
| `&&name` | Pyta, jeśli nie jest zdefiniowana, a potem ją **definiuje**; kolejne `&name`/`&&name` już nie pytają |
| `'&name'` | Apostrofy zostają w poleceniu, więc użytkownik wpisuje `King`, a nie `'King'` |

- Podstawienie to zwykła **zamiana tekstu po stronie klienta** przed wysłaniem polecenia:
  może podmienić wartość, kolumnę, nazwę tabeli albo cały warunek (`ORDER BY &col`).
- `WHERE last_name = &name` z wpisanym `King` staje się `= King` → ORA-00904 "KING": invalid identifier.
- `&` wewnątrz tekstu (`'R&D'`) nadal jest prefiksem podstawienia. `SET DEFINE OFF` wyłącza
  podstawianie; `SET DEFINE ON` je przywraca (`SET DEFINE ^` zmienia znak prefiksu).

## 3.4 DEFINE, UNDEFINE i VERIFY

```text
SQL> DEFINE dept_id = 20
SQL> DEFINE dept_id
DEFINE DEPT_ID         = "20" (CHAR)
SQL> SELECT last_name FROM employees WHERE department_id = &dept_id;
old   1: SELECT last_name FROM employees WHERE department_id = &dept_id
new   1: SELECT last_name FROM employees WHERE department_id = 20
SQL> UNDEFINE dept_id
```

- Samo `DEFINE` wypisuje wszystkie zmienne (łącznie z predefiniowanymi `_DATE`, `_USER`, ...).
- DEFINE zawsze tworzy zmienną typu **CHAR**; istnieje ona do UNDEFINE albo do końca sesji.
- `SET VERIFY ON` (domyślnie) wypisuje wiersze `old`/`new`; `SET VERIFY OFF` je ukrywa, ale
  podstawienie nadal zachodzi.

## 3.5 Sortowanie

- `ASC` jest domyślne; ASC/DESC dotyczy tylko jednego elementu (`ORDER BY a DESC, b` sortuje b rosnąco).
- NULL sortuje się jak największa wartość: na końcu przy ASC, na początku przy DESC. Zmienisz to przez `NULLS FIRST/LAST`.
- ORDER BY może użyć kolumny spoza listy SELECT, wyrażenia, aliasu albo numeru pozycji:
  `SELECT last_name, department_id ... ORDER BY 2 DESC, 1` stawia **Granta** (dział NULL) na początku.
- Przy DISTINCT ORDER BY musi używać wybranych elementów: `SELECT DISTINCT job_title ... ORDER BY salary`
  → **ORA-01791**: not a SELECTed expression. Pozycja spoza listy → **ORA-01785**.
- Bez ORDER BY kolejność wierszy nie jest gwarantowana.

## Częste pułapki

1. `OR` zmieszane z `AND` bez nawiasów.
2. `= NULL`, `IN (NULL)`, `NOT IN (..., NULL)`: wszystkie po cichu nic nie zwracają.
3. BETWEEN z odwróconymi granicami albo z górną granicą bez godziny na kolumnach DATE.
4. LIKE rozróżnia wielkość liter; bez ESCAPE `_` to znak wieloznaczny, a nie podkreślnik.
5. `ROWNUM > 1` albo ROWNUM z ORDER BY w tym samym bloku zapytania.
6. Zapominanie, że DESC stawia NULL na początku.
7. `&name` bez apostrofów dla tekstu; przekonanie, że `SET VERIFY OFF` wyłącza pytania (nie wyłącza; robi to `SET DEFINE OFF`).
8. Przekonanie, że `&` zapamiętuje wartość: zmienną definiują tylko `&&`, DEFINE i ACCEPT.

> **Oracle a standardowy SQL / inne bazy danych**
>
> - `OFFSET ... FETCH` to ISO SQL:2008 i działa w Oracle 12c+, PostgreSQL, SQL Server 2012+.
>   MySQL i PostgreSQL mają też `LIMIT`; SQL Server ma `TOP`. Oracle 19c nie ma żadnego z nich.
> - Kolejność NULL: Oracle i PostgreSQL traktują NULL jako największą wartość; SQL Server i MySQL jako najmniejszą.
>   `NULLS FIRST/LAST` istnieje w Oracle i PostgreSQL, nie ma go w SQL Server ani MySQL.
> - `LIKE` rozróżnia wielkość liter w Oracle i PostgreSQL; przy domyślnych collation
>   w SQL Server i MySQL jej nie rozróżnia. Ucieczka w nawiasach `[_]` z SQL Server nie jest składnią Oracle.
> - `ROWNUM` istnieje tylko w Oracle.
> - Zmienne podstawienia to funkcja klienta (SQL*Plus, SQLcl, SQL Developer), a nie SQL;
>   inne klienty używają zmiennych wiązanych (`:name`) albo własnej składni zmiennych.

## Różnice w Oracle 23ai (1Z0-171)

Każdy punkt poniżej wykonano na Oracle 23ai (FREEPDB1), łącznie z SQL*Plus, i, dla porównania, na 19c.

| Polecenie | 19c | 23ai |
|---|---|---|
| `... FETCH FIRST 2 ROWS ONLY OFFSET 1 ROWS` | **ORA-00933** | **ORA-03049**: SQL keyword 'OFFSET' is not syntactically valid ... |
| `... ORDER BY e.salary NULLS FIRST DESC` | **ORA-00933** | **ORA-03048** (napisz `DESC NULLS FIRST`) |
| `... FROM employees e LIMIT 3` | **ORA-00933** | **ORA-03049**: nadal brak klauzuli LIMIT |
| `WHERE TRUE` | **ORA-00920** | wszystkie wiersze (warunek BOOLEAN) |
| `WHERE (e.salary > 5000) IS TRUE` | **ORA-00933** | 6 wierszy |
| `ORDER BY e.department_id FETCH FIRST 2 PARTITION BY e.department_id, 1 ROWS ONLY` | **ORA-00905** | 2 wiersze (100, 101): ograniczanie wierszy w partycjach |
| `'Total: ' \|\| 10 + 5` | **ORA-01722**: invalid number | **ORA-01722**: unable to convert string value containing 'T' to a number |

- Bez zmian w 23ai: kolejność AND/OR/NOT, `||` na tym samym poziomie co `+`/`-`, wszystkie wyniki
  ograniczania wierszy (ułamki obcinane, PERCENT zaokrąglane w górę, WITH TIES), ROWNUM, kolejność NULL,
  ORA-01791 i ORA-01785.
- SQL*Plus 23 zachowuje się jak SQL*Plus 19c dla `&`, `&&`, kropki kończącej nazwę (`&pre.loyees`),
  `DEFINE job = Sales Rep` (zapisuje tylko `Sales`), SET VERIFY (tylko wiersze ze zmienną) i
  SET DEFINE OFF (SP2-0552); komunikat o błędzie dostaje dodatkowy wiersz `Help:` z adresem URL.
