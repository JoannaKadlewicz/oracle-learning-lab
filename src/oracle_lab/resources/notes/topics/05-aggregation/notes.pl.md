# Temat 5: Raportowanie danych zagregowanych funkcjami grupującymi

Środowisko: Oracle Database 19c, schemat ORASTUDY. Każdy wynik niżej został **wykonany**
17 października 2026 na przykładowych danych (w sesji wycofanej). Cele 6.1–6.3.

## Pojęcie

Funkcja grupująca bierze wiele wierszy i zwraca jedną wartość. Bez `GROUP BY` cały wynik
`FROM`/`WHERE` to jedna grupa; z `GROUP BY` jest jeden wiersz wyniku na grupę.
Logiczna kolejność przetwarzania:

    FROM → WHERE → GROUP BY → HAVING → SELECT → ORDER BY

Prawie każda reguła w tym temacie wynika z tej kolejności.

## 6.1 Używanie funkcji grupujących

| Funkcja | Typy argumentów | NULL | Dla zera wierszy |
|---|---|---|---|
| `COUNT(*)` | wiersze | liczone | 0 |
| `COUNT(expr)`, `COUNT(DISTINCT expr)` | dowolne | pomijane | 0 |
| `SUM`, `AVG`, `STDDEV`, `VARIANCE` | tylko liczbowe | pomijane | NULL |
| `MIN`, `MAX` | liczba, tekst, data | pomijane | NULL |
| `LISTAGG(expr, delim) WITHIN GROUP (ORDER BY ...)` | dowolne | pomijane | NULL |

```sql
SELECT COUNT(*), COUNT(e.commission_pct), COUNT(DISTINCT e.commission_pct)
FROM   employees e;                                   -- 9, 4, 3
SELECT AVG(e.commission_pct), AVG(NVL(e.commission_pct, 0))
FROM   employees e;                                   -- .2, .0888...
SELECT SUM(e.salary), SUM(DISTINCT e.salary)
FROM   employees e;                                   -- 84100, 73300
SELECT MIN(e.last_name), MAX(e.commission_pct)
FROM   employees e;                                   -- De Haan, .3
```

- `DISTINCT` działa w każdej funkcji grupującej (`SUM(DISTINCT ...)`, `AVG(DISTINCT ...)`).
- `SUM(e.last_name)` → **ORA-01722: invalid number** (niejawna konwersja 'King').
- `LISTAGG(e.last_name, ', ') WITHIN GROUP (ORDER BY e.last_name)` dla działu 20 →
  `Kochhar, Partners, Russell`. 19c przyjmuje też `LISTAGG(DISTINCT ...)`.

**Pusta tabela** (`promotions` nie ma wierszy):

| Zapytanie | Wynik |
|---|---|
| `SELECT COUNT(*), COUNT(promo_id), SUM(discount_pct), MAX(promo_name) FROM promotions` | jeden wiersz: `0, 0, NULL, NULL` |
| `SELECT promo_name, COUNT(*) FROM promotions GROUP BY promo_name` | **brak wierszy** |
| `SELECT COUNT(*) FROM promotions HAVING COUNT(*) = 0` | jeden wiersz: `0` |

**Zagnieżdżanie** (najwyżej dwa poziomy, wymagane `GROUP BY`, wynik jednowierszowy):

```sql
SELECT MAX(AVG(e.salary)) FROM employees e GROUP BY e.department_id;   -- 24000
SELECT MAX(AVG(e.salary)) FROM employees e;                             -- ORA-00978
SELECT e.department_id, MAX(AVG(e.salary)) FROM employees e
GROUP  BY e.department_id;                                              -- ORA-00937
SELECT SUM(MAX(MIN(e.salary))) FROM employees e
GROUP  BY e.department_id;                                              -- ORA-00935
```

## 6.2 Tworzenie grup danych

```sql
SELECT e.department_id, COUNT(*) FROM employees e GROUP BY e.department_id;
-- 4 wiersze: 10 → 1, 20 → 3, 30 → 4, NULL → 1   (wszystkie NULL tworzą jedną grupę)
SELECT e.department_id, e.job_title, COUNT(*) FROM employees e
GROUP  BY e.department_id, e.job_title;   -- 6 wierszy, po jednym na każdą istniejącą kombinację
```

Reguły:

- Każde wyrażenie w SELECT, które nie jest agregatem, musi wystąpić w `GROUP BY`, inaczej
  **ORA-00979: not a GROUP BY expression**. W drugą stronę nie trzeba: kolumna z `GROUP BY`
  nie musi być wybrana.
- Stałe i funkcje grupowanych kolumn są w porządku: `SELECT UPPER(e.job_title) ... GROUP BY e.job_title`.
  Ale `SELECT e.job_title ... GROUP BY UPPER(e.job_title)` → ORA-00979.
- `GROUP BY` w 19c nie może używać aliasu z SELECT (**ORA-00904**) i nie działa po pozycjach:
  `GROUP BY 1` grupuje po stałej 1.
- `ORDER BY` w zapytaniu z grupowaniem może używać wyrażeń z GROUP BY, funkcji grupujących (także
  niewybranych), aliasów i pozycji. `ORDER BY e.salary` → ORA-00979;
  `ORDER BY 3` przy dwóch wybranych kolumnach → ORA-01785.
- Grupowanie nie sortuje. Kolejność gwarantuje tylko `ORDER BY`.
- `COUNT(c.country_code)` dla grupy NULL klientów to `0`, a `COUNT(*)` to `1`.

## 6.3 Filtrowanie wyników grup

| | `WHERE` | `HAVING` |
|---|---|---|
| Filtruje | wiersze, przed grupowaniem | grupy, po grupowaniu |
| Funkcje grupujące | niedozwolone (**ORA-00934**) | dozwolone, wybrane albo nie |
| Kolumny | dowolna kolumna | tylko wyrażenia z GROUP BY (inaczej ORA-00979) |
| Aliasy z SELECT | nie | nie (ORA-00904) |

```sql
SELECT e.department_id, COUNT(*)
FROM   employees e
WHERE  e.department_id IS NOT NULL      -- filtr wierszy
GROUP  BY e.department_id
HAVING COUNT(*) > 1;                    -- filtr grup: 20 → 3, 30 → 4
```

- `HAVING` bez `GROUP BY` jest dozwolone: `SELECT COUNT(*) FROM employees HAVING COUNT(*) > 5`
  zwraca jeden wiersz (`9`).
- Warunek na kolumnę z GROUP BY daje ten sam wynik w `WHERE` i w `HAVING`;
  naturalnym miejscem jest `WHERE` (usuwa wiersze, zanim zacznie się grupowanie).
- `GROUP BY AVG(e.salary)` → ORA-00934: funkcje grupujące należą tylko do SELECT, HAVING i ORDER BY.

## Częste pułapki

1. `COUNT(col)` i `AVG(col)` po cichu pomijają NULL: `AVG(commission_pct)` to .2, a nie .0889.
2. `SUM` z zera wierszy to NULL, a nie 0. Gdy potrzebujesz liczby, użyj `NVL(SUM(x), 0)`.
3. Agregat bez GROUP BY zawsze zwraca jeden wiersz, nawet z pustej tabeli;
   z GROUP BY puste wejście nie zwraca żadnych wierszy.
4. `COUNT(DISTINCT col)` nie liczy NULL; `GROUP BY col` tworzy grupę NULL.
5. Wybranie kolumny obok zagnieżdżonej funkcji grupującej (ORA-00937), zagnieżdżanie bez
   GROUP BY (ORA-00978) albo trzy poziomy (ORA-00935).
6. Aliasy: tylko w ORDER BY, nigdy w WHERE, GROUP BY ani HAVING (19c).
7. `GROUP BY 1` to nie „pierwsza kolumna”.
8. Filtr na funkcji grupującej w WHERE (ORA-00934), zwykła kolumna w HAVING (ORA-00979).

> **Oracle a standardowy SQL / inne bazy danych**
>
> - MySQL (bez `ONLY_FULL_GROUP_BY`) pozwala wybierać niegrupowane kolumny i zwraca
>   dowolną wartość; Oracle zawsze zgłasza ORA-00979.
> - `GROUP BY 1` / `GROUP BY alias` z PostgreSQL, MySQL i SQL Server nie są poprawne
>   w Oracle 19c. Oracle 23ai dodaje aliasy i pozycje w GROUP BY (pozycje wymagają
>   `group_by_position_enabled`).
> - Zagnieżdżone agregaty, takie jak `MAX(AVG(x))`, to rozszerzenie Oracle; standard (i
>   PostgreSQL) wymagają podzapytania.
> - `LISTAGG` to agregacja tekstów w Oracle (i w SQL:2016); PostgreSQL używa `STRING_AGG`,
>   MySQL `GROUP_CONCAT`.
> - Oracle traktuje `''` jak NULL, więc `COUNT(col)` pomija też puste teksty.

## Różnice w Oracle 23ai (1Z0-171)

Wykonano na Oracle AI Database 23ai Free (23.26) na tych samych przykładowych danych. Wszystko,
czego tu nie wymieniono (obsługa NULL, formy COUNT, reguły zagnieżdżania, ORA-00934/00937/00978), działa
dokładnie jak w 19c.

| Polecenie | 19c | 23ai |
|---|---|---|
| `SELECT e.department_id AS dept, COUNT(*) FROM employees e GROUP BY dept` | ORA-00904 | 4 wiersze: aliasy dozwolone w GROUP BY |
| `... GROUP BY e.department_id HAVING cnt > 1` (cnt to alias z SELECT) | ORA-00904 | 2 wiersze (20 → 3, 30 → 4) |
| `... GROUP BY dept HAVING dept > 10` | ORA-00904 | 2 wiersze |
| `SELECT e.department_id AS dept FROM employees e WHERE dept > 10` | ORA-00904 | **nadal ORA-00904**: WHERE nigdy nie widzi aliasów |
| `SELECT e.department_id, COUNT(*) FROM employees e GROUP BY 1` | ORA-00979 (1 to stała) | **ORA-03162** (pozycje są domyślnie wyłączone) |
| to samo po `ALTER SESSION SET group_by_position_enabled = TRUE` | ORA-02248 (nie ma takiego parametru) | 4 wiersze: GROUP BY 1 działa po pozycji |
| `SELECT e.department_id, COUNT(*) FROM employees e GROUP BY ALL` | ORA-00936 | 4 wiersze: grupuje po każdym wyrażeniu z SELECT, które nie jest agregatem |
| `SELECT e.department_id, e.job_title, SUM(e.salary) ... GROUP BY e.department_id` | ORA-00979: not a GROUP BY expression | ORA-00979 z nazwą kolumny: `"E"."JOB_TITLE": must appear in the GROUP BY clause or be used in an aggregate function` |

- `group_by_position_enabled` ma w 23ai domyślnie wartość `FALSE`, więc na egzaminie zakładaj, że
  `GROUP BY 1` to błąd, chyba że pytanie mówi, że parametr jest ustawiony.
- `GROUP BY ALL` działa też z wyrażeniami: `SELECT TO_CHAR(e.hire_date, 'YYYY') AS yr,
  COUNT(*) FROM employees e GROUP BY ALL` → 7 wierszy.
- Wyniki agregatów są identyczne; między bazami różniła się tylko kolejność wierszy nieposortowanego
  wyniku GROUP BY (kolejne przypomnienie, że grupowanie nie sortuje).
