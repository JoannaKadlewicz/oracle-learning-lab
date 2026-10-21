# Temat 6: Wyświetlanie danych z wielu tabel (złączenia)

Środowisko: Oracle Database 19c, schemat ORASTUDY. Każdy wynik niżej został **wykonany**
17 października 2026 na przykładowych danych (w sesji wycofanej). Cele 7.1–7.5.

Fakty o danych używane niżej: 9 pracowników, 4 działy. Pracownik 108 (Grant) nie ma działu,
dział 40 (Research) nie ma pracowników, pracownik 100 (King) nie ma kierownika.

## 7.1 Rodzaje złączeń

| Składnia | Warunek złączenia | Kolumna złączenia w wyniku |
|---|---|---|
| `JOIN ... ON cond` | dowolny warunek | obie kopie, przy niejednoznaczności z kwalifikatorem (ORA-00918) |
| `JOIN ... USING (col, ...)` | równość na wymienionych kolumnach o tej samej nazwie | jedna kopia, **nie** może mieć kwalifikatora (ORA-25154) |
| `NATURAL JOIN` | równość na **wszystkich** kolumnach o tej samej nazwie | jedna kopia, nie może mieć kwalifikatora (ORA-25155) |
| `FROM a, b WHERE cond` | składnia Oracle/stara, warunek w WHERE | obie kopie |
| `CROSS JOIN` | brak | – |

`INNER` i `OUTER` to opcjonalne słowa kluczowe. Te cztery zapytania zwracają te same 8 wierszy:

```sql
SELECT e.last_name, d.department_name FROM employees e JOIN departments d ON e.department_id = d.department_id;
SELECT e.last_name, d.department_name FROM employees e JOIN departments d USING (department_id);
SELECT last_name, department_name     FROM employees NATURAL JOIN departments;
SELECT e.last_name, d.department_name FROM employees e, departments d WHERE e.department_id = d.department_id;
```

- `NATURAL JOIN ... ON` i `USING (d.department_id)` to błędy (USING przyjmuje proste nazwy: ORA-01748).
- `JOIN` bez ON/USING → ORA-00905: missing keyword.
- Dla złączeń wewnętrznych filtr w ON i w WHERE daje ten sam wynik.
- Złączenia wielu tabel są wyliczane od lewej do prawej; cztery tabele potrzebują trzech warunków złączenia.
  `customers → orders → order_items → products` z filtrem na Hardware zwraca 6 wierszy.
- Pułapka NATURAL JOIN: `employees e1 NATURAL JOIN employees e2` porównuje wszystkie 10 kolumn i
  zwraca tylko **3** wiersze, bo NULL w dowolnej kolumnie nigdy nie równa się NULL.

## 7.2 Złączenia zwrotne (self-join)

Ta sama tabela dwa razy, z dwoma aliasami. Role ustala warunek:

```sql
SELECT e.last_name, m.last_name AS manager
FROM   employees e
JOIN   employees m ON e.manager_id = m.employee_id;   -- 8 wierszy: King nie ma kierownika
```

- `LEFT JOIN employees m ...` zachowuje Kinga z kierownikiem NULL (9 wierszy).
- Odwrotnie (`e.employee_id = m.manager_id`) m staje się podwładnym: dla Kochhar
  zwraca Granta, Partners i Russella.
- Pogrupowane po kierowniku zwraca 3 wiersze: King 2, Kochhar 3, De Haan 3.

## 7.3 Złączenia nierównościowe (non-equijoin)

Złączenie na czymkolwiek innym niż `=`, zwykle na przedziale:

```sql
SELECT e.last_name, e.salary, g.grade
FROM   employees e
JOIN   salary_grades g ON e.salary BETWEEN g.min_salary AND g.max_salary;  -- 9 wierszy
```

Stopnie: A 3 (Partners, Lorentz, Grant), B 3, C 2, D 1. `BETWEEN` obejmuje granice i równa się
`>= AND <=`; `BETWEEN g.max_salary AND g.min_salary` nic nie zwraca. Z samą dolną granicą
(`ON e.salary >= g.min_salary`) każdy pracownik pasuje do kilku stopni: **19** wierszy.
Złączenia nierównościowe wymagają ON albo WHERE; USING i NATURAL JOIN tworzą tylko równość.

## 7.4 Złączenia zewnętrzne

| Zapytanie | Wiersze |
|---|---|
| `employees e JOIN departments d ON ...` | 8 |
| `employees e LEFT JOIN departments d ON ...` | 9 (dochodzi Grant) |
| `employees e RIGHT JOIN departments d ON ...` | 9 (dochodzi Research) |
| `employees e FULL JOIN departments d ON ...` | 10 |

Składnia Oracle: `(+)` stoi po stronie, której wierszy **może brakować**:

```sql
WHERE e.department_id = d.department_id(+)    -- = employees LEFT JOIN departments
```

- `(+)` po obu stronach → **ORA-01468**; FULL OUTER JOIN nie ma postaci z `(+)`.
- `(+)` w klauzuli WHERE zapytania, które używa też złączeń ANSI → **ORA-25156**.
  (19c przyjmuje `(+)` wewnątrz klauzuli ANSI `ON` i robi z niego złączenie zewnętrzne, ale nie mieszaj stylów.)
- W starej składni każdy warunek na tabeli opcjonalnej potrzebuje `(+)`:
  `AND e.salary(+) > 10000` zachowuje Research; bez `(+)` dział znika.

**ON a WHERE** dla tabeli opcjonalnej:

```sql
SELECT d.department_name, COUNT(e.employee_id)
FROM   departments d
LEFT JOIN employees e ON e.department_id = d.department_id AND e.salary > 10000
GROUP  BY d.department_name;     -- 4 wiersze, Research 0
-- ten sam filtr w WHERE: 3 wiersze, Research znika (NULL > 10000 nie jest prawdą)
```

- Anti-join: `departments d LEFT JOIN employees e ON ... WHERE e.employee_id IS NULL` →
  `Research`.
- `COUNT(*)` liczy wiersz uzupełniony NULL-ami (Research → 1); `COUNT(e.employee_id)` → 0.

## 7.5 Iloczyny kartezjańskie

Każdy wiersz w parze z każdym wierszem: wiersze(A) × wiersze(B).

- `departments CROSS JOIN salary_grades` → 16. `CROSS JOIN ... ON` → ORA-00933.
- `FROM employees e, departments d WHERE e.salary > 10000` → 3 × 4 = **12** (brak warunku złączenia).
- `JOIN ... ON 1 = 1` → 16.
- `employees NATURAL JOIN orders` → **63**: brak wspólnych nazw kolumn, więc w ogóle brak warunku.

## Częste pułapki

1. Kwalifikator przy kolumnie USING/NATURAL (ORA-25154 / ORA-25155) albo jego brak przy kolumnie z ON,
   która istnieje w obu tabelach (ORA-00918).
2. NATURAL JOIN łączy po *każdej* kolumnie o tej samej nazwie albo po żadnej (iloczyn kartezjański).
3. Filtrowanie tabeli opcjonalnej w WHERE zamienia złączenie zewnętrzne w wewnętrzne.
4. `COUNT(*)` po złączeniu zewnętrznym liczy niedopasowane wiersze jako 1.
5. `(+)` oznacza stronę niepełną, czyli przeciwną niż strona wskazana przez LEFT/RIGHT.
6. Kierunek złączenia zwrotnego ustala warunek, a nie nazwy aliasów.
7. Złączenia po przedziałach powielają wiersze, gdy przedziały zachodzą na siebie, i gubią je, gdy są luki.
8. N tabel potrzebuje co najmniej N − 1 warunków złączenia.

> **Oracle a standardowy SQL / inne bazy danych**
>
> - `(+)` istnieje tylko w Oracle; ANSI `LEFT/RIGHT/FULL OUTER JOIN` (obsługiwane od Oracle 9i) jest
>   przenośne i tego używają inne bazy danych. Oracle zaleca postać ANSI.
> - MySQL nie ma `FULL OUTER JOIN`; Oracle i PostgreSQL go mają.
> - W MySQL `JOIN` bez ON jest dozwolone (działa jak CROSS JOIN); Oracle zgłasza ORA-00905.
> - SQL Server nie ma `NATURAL JOIN` ani `USING`; Oracle, PostgreSQL i MySQL je mają.
> - Oracle obsługuje też `CROSS APPLY` / `OUTER APPLY` i `LATERAL` (12c+), których nie ma
>   w celach 1Z0-071.

## Różnice w Oracle 23ai (1Z0-171)

Wykonano na Oracle AI Database 23ai Free (23.26) na tych samych przykładowych danych. Wyniki złączeń
(liczby wierszy złączeń wewnętrznych, zewnętrznych, zwrotnych, nierównościowych i krzyżowych) są identyczne; różnice
dotyczą tego, co przyjmuje operator `(+)`, oraz niektórych kodów i komunikatów błędów.

| Polecenie | 19c | 23ai |
|---|---|---|
| `employees e JOIN departments d ON e.department_id = d.department_id(+)` | przyjęte, działa jak LEFT JOIN (9 wierszy) | **ORA-25156**: `(+)` nie jest dozwolony także wewnątrz klauzuli ANSI ON |
| `WHERE e.department_id(+) = d.department_id OR e.salary(+) > 20000` | ORA-01719 | działa (każdy człon OR ma `(+)`) |
| `WHERE e.department_id(+) = d.department_id OR d.department_id = 40` | ORA-01719 | **ORA-25556**: człon OR bez `(+)` nie jest dozwolony |
| `employees e INNER JOIN departments d` (bez ON/USING) | ORA-00905: missing keyword | **ORA-02000**: missing ON or USING keyword |
| `departments d CROSS JOIN salary_grades g ON ...` | ORA-00933 | **ORA-03048**: SQL reserved word 'ON' is not syntactically valid |
| `SELECT last_name FROM employees e JOIN employees m ON ...` | ORA-00918: column ambiguously defined | ORA-00918 z nazwą kolumny (`LAST_NAME: column ambiguously specified`) |

Bez zmian w 23ai (sprawdzone): ORA-25154 dla kolumny USING z kwalifikatorem (także `e.*`),
ORA-25155 dla kolumny NATURAL JOIN z kwalifikatorem, ORA-01468 dla `(+)` po obu stronach,
ORA-25156 dla `(+)` w WHERE obok złączeń ANSI, ORA-00904 dla klauzuli ON, która odwołuje się do
tabeli dołączanej później, a `(+)` z listą stałych w IN (`e.job_title(+) IN (...)`) działa
w obu wersjach.
