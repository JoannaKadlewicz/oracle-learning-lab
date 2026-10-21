# Temat 8: Operatory zbiorowe

Środowisko: Oracle Database 19c, schemat ORASTUDY. Każdy wynik niżej został **wykonany**
na przykładowych danych.

## Pojęcie

Operatory zbiorowe łączą wyniki dwóch albo więcej poleceń SELECT („gałęzi”) w jedno zapytanie złożone.

| Operator | Zwraca | Duplikaty | Przemienny |
|---|---|---|---|
| `UNION` | wiersze z dowolnej gałęzi | usuwane | tak |
| `UNION ALL` | wszystkie wiersze z obu gałęzi | zachowywane | tak (jako multizbiór) |
| `INTERSECT` | wiersze zwracane przez obie gałęzie | usuwane | tak |
| `MINUS` | wiersze pierwszej gałęzi, których nie ma w drugiej | usuwane | **nie** |

Oracle 19c ma tylko te cztery. `EXCEPT`, `MINUS ALL`, `INTERSECT ALL` pojawiły się w 21c.

## 9.1 Dopasowanie poleceń SELECT

- Ta sama **liczba kolumn** w każdej gałęzi, inaczej **ORA-01789: query block has incorrect
  number of result columns**.
- Odpowiadające sobie kolumny muszą być w tej samej **grupie typów danych** (liczbowe, znakowe, daty).
  `employee_id UNION last_name` → **ORA-01790: expression must have same datatype as
  corresponding expression**. Nie ma niejawnej konwersji NUMBER → VARCHAR2; użyj `TO_CHAR`.
- Nazwy, długości i precyzje nie muszą się zgadzać: `department_id NUMBER(4)` z
  `salary NUMBER(8,2)`, `VARCHAR2(30)` z `VARCHAR2(25)` są w porządku.
- `NULL` pasuje do każdej kolumny, więc to zwykły wypełniacz:

```sql
SELECT e.last_name, e.salary FROM employees e
UNION ALL
SELECT c.customer_name, NULL FROM customers c;      -- 14 wierszy
```

- **Nagłówki pochodzą z pierwszego SELECT.** Dla
  `SELECT e.last_name AS name, e.salary ... UNION SELECT c.customer_name AS customer, c.credit_limit AS amount ...`
  kolumny to `NAME, SALARY`.
- **Kolejność**: wszystkie operatory zbiorowe są równe i działają od lewej do prawej (standardowy SQL daje
  pierwszeństwo INTERSECT). Użyj nawiasów, żeby to zapisać jawnie.
- **Wartości NULL są sobie równe**, gdy operatory zbiorowe porównują wiersze (inaczej niż przy `=`).

## 9.2 UNION i UNION ALL

```sql
SELECT e.department_id FROM employees e
UNION
SELECT d.department_id FROM departments d;   -- 5 wierszy: 10, 20, 30, 40, NULL
```

To samo zapytanie z `UNION ALL` zwraca 13 wierszy (9 + 4).

- UNION usuwa duplikaty także **wewnątrz** gałęzi: `job_title UNION <pusta gałąź>` → 5 wierszy, a nie 9.
- `country_code UNION ...` dla US, GB, US, PL, NULL → 4 wiersze (zostaje jeden NULL).
- `A UNION B` ≡ `SELECT DISTINCT * FROM (A UNION ALL B)` ≡ `B UNION A`.
- UNION ALL jest tańszy (bez usuwania duplikatów). Żaden z nich nie gwarantuje kolejności bez ORDER BY.

## 9.3 INTERSECT

```sql
SELECT o.sales_rep_id FROM orders o
INTERSECT
SELECT e.employee_id FROM employees e WHERE e.department_id = 20;   -- 105, 106
```

- Tylko różne wiersze: 5 zamówień przyjętych przez tych dwóch przedstawicieli zwija się do 2 wartości.
- NULL pasuje do NULL: `department_id INTERSECT department_id pracowników z prowizją` → 20 i NULL.
  Złączenie albo `IN` zwróciłoby tylko 20.
- `A INTERSECT B` ≡ `A WHERE key IN (B)`, gdy klucz jest unikalny i nie jest NULL; zwykłe złączenie powtarza wiersze.

Przykład kolejności działania:

```sql
SELECT d.department_id FROM departments d
UNION
SELECT e.department_id FROM employees e
INTERSECT
SELECT e.department_id FROM employees e WHERE e.salary > 10000;
```

Oracle: `(departments UNION employees) INTERSECT {10, 20, 30}` → **3 wiersze**.
Standardowy SQL najpierw policzyłby INTERSECT i zwrócił 4 wiersze.

## 9.4 MINUS

```sql
SELECT d.department_id FROM departments d MINUS SELECT e.department_id FROM employees e;  -- 40
SELECT e.department_id FROM employees e MINUS SELECT d.department_id FROM departments d;  -- NULL
```

- Kierunek ma znaczenie. Drugie zapytanie zwraca NULL pracownika 108, bo departments nie ma NULL.
- NULL w drugiej gałęzi **nie** czyści wyniku, jak robi to `NOT IN`.
  Pierwsze zapytanie powyżej jest równoważne NOT EXISTS, NOT IN z odfiltrowanym NULL i
  LEFT JOIN ... WHERE e.employee_id IS NULL; zwykłe NOT IN zwraca 0 wierszy.
- Porównuje się wiersze, a nie encje: `job_title MINUS job_title działu 20` → President,
  IT Manager, Programmer (stanowisko Sales Rep Granta znika, choć Grant nie jest w dziale 20).

## 9.5 ORDER BY w operacjach zbiorowych

- Tylko **jedno** ORDER BY, po **ostatnim** SELECT; sortuje cały wynik.
  `SELECT ... ORDER BY e.last_name UNION SELECT ...` → **ORA-00933: SQL command not properly ended**.
- Dozwolone: pozycje (`ORDER BY 2 DESC`), nazwy kolumn albo aliasy z pierwszego zapytania (`ORDER BY name`, `salary`).
- Niedozwolone: alias z drugiej gałęzi (`ORDER BY cust` → **ORA-00904**), kolumna z kwalifikatorem
  tabeli (`ORDER BY e.last_name` → **ORA-00904**), pozycja większa niż liczba kolumn
  (`ORDER BY 3` → **ORA-01785**).
- DESC domyślnie stawia NULL **na początku**:

```sql
SELECT e.last_name AS name, e.salary AS amount FROM employees e WHERE e.department_id = 20
UNION ALL
SELECT c.customer_name, c.credit_limit FROM customers c
ORDER  BY 2 DESC, 1;
```

| NAME | AMOUNT |
|---|---|
| Initech | NULL |
| Kochhar | 14000 |
| Russell | 6000 |
| Acme Corp | 5000 |
| ... | ... |

Dodaj `NULLS LAST`, aby przenieść Initech na koniec.

## Częste pułapki

1. Założenie, że nagłówki albo nazwy w ORDER BY pochodzą z ostatniego SELECT. Pochodzą z pierwszego.
2. ORDER BY w środkowej gałęzi (ORA-00933) albo z aliasem tabeli / aliasem z drugiej gałęzi (ORA-00904).
3. Oczekiwanie niejawnej konwersji NUMBER/VARCHAR2 między gałęziami (ORA-01790).
4. Przekonanie, że NULL nigdy nie pasuje w operatorach zbiorowych. Pasuje, inaczej niż w złączeniach i IN.
5. Traktowanie MINUS jako przemiennego albo oczekiwanie, że zachowa duplikaty.
6. Czytanie `A UNION B INTERSECT C` z kolejnością działań ze standardowego SQL.
7. Przekonanie, że wynik UNION jest posortowany. Kolejność gwarantuje tylko ORDER BY.
8. Liczenie wyników UNION bez zwinięcia duplikatów wewnątrz jednej gałęzi.

> **Oracle a standardowy SQL / inne bazy danych**
> - Oracle używa `MINUS`; standard (oraz PostgreSQL, SQL Server, Oracle 21c+) używa `EXCEPT`.
> - Standardowy SQL, PostgreSQL i SQL Server dają `INTERSECT` wyższe pierwszeństwo niż `UNION`/`EXCEPT`;
>   Oracle wylicza wszystkie operatory zbiorowe od lewej do prawej.
> - `INTERSECT ALL` / `EXCEPT ALL` istnieją w standardzie i w PostgreSQL, a w Oracle dopiero od 21c.
> - Oracle sortuje NULL jak największą wartość (na początku przy DESC); SQL Server jak najmniejszą.

## Różnice w Oracle 23ai (1Z0-171)

Sprawdzono na Oracle AI Database 23ai (FREEPDB1) z tymi samymi przykładowymi danymi.

- **EXCEPT, EXCEPT ALL, MINUS ALL i INTERSECT ALL** działają (dostępne od 21c). W 19c
  `EXCEPT` zgłasza ORA-00933, a `MINUS ALL` / `INTERSECT ALL` zgłaszają ORA-00928 missing SELECT keyword.
  - `EXCEPT` to synonim `MINUS`: `orders.customer_id EXCEPT klienci z GB` → 1, 3, 5.
  - `MINUS ALL` odejmuje wystąpienia: identyfikatory klientów zamówień 1, 1, 1, 2, 2, 3, 5 `MINUS ALL`
    klienci (każdy identyfikator raz) → **1, 1, 2** (3 wiersze; zwykłe MINUS → 0 wierszy).
  - `INTERSECT ALL` zachowuje mniejszą liczbę wystąpień: identyfikatory klientów zamówień
    `INTERSECT ALL` klienci → 1, 2, 3, 5 (4 wiersze).
- **Kolejność działania się nie zmieniła**: `departments UNION employees INTERSECT najlepiej zarabiający` nadal
  zwraca w 23ai 3 wiersze (od lewej do prawej), a nie 4 wiersze, jak przy kolejności ze standardowego SQL.
- **ORDER BY w środkowej gałęzi** zgłasza **ORA-03048** (SQL reserved word 'UNION' is not
  syntactically valid following ...) zamiast ORA-00933. ORA-00907 (ORDER BY wewnątrz gałęzi
  w nawiasie), ORA-00904 (alias z drugiej gałęzi albo kolumna `e.` w ORDER BY),
  ORA-01785 (wyrażenie w ORDER BY albo pozycja większa niż liczba kolumn), ORA-01789 i
  ORA-01790 są takie same jak w 19c.
- **Kolejność wyniku UNION jest inna.** W 19c przykładowe zapytania UNION akurat wracały posortowane
  (10, 20, 30, 40, NULL); w 23ai to samo zapytanie zwróciło 10, 20, 30, NULL, 40. Żadna wersja
  nie gwarantuje kolejności bez ORDER BY.
