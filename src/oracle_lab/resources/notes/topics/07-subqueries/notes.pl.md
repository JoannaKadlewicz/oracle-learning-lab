# Temat 7: Podzapytania

Środowisko: Oracle Database 19c, schemat ORASTUDY. Każdy wynik niżej został **wykonany**
na przykładowych danych (przykłady DML wycofano).

## Pojęcie

Podzapytanie to SELECT zagnieżdżony w innym poleceniu. To, co możesz z nim zrobić, zależy od tego,
ile wierszy zwraca i czy odwołuje się do polecenia zewnętrznego.

| Rodzaj | Zwraca | Używaj z | Zła liczba wierszy |
|---|---|---|---|
| Jednowierszowe / skalarne | najwyżej 1 wiersz, 1 kolumnę | `=  <>  <  >  <=  >=`, lista SELECT, ORDER BY, SET | 2+ wiersze → ORA-01427; 0 wierszy → NULL |
| Wielowierszowe | dowolną liczbę wierszy | `IN`, `NOT IN`, `op ANY`, `op ALL`, `EXISTS` | nigdy nie ma błędu |
| Wielokolumnowe | kilka kolumn | `(a, b) IN (SELECT x, y ...)`, `SET (a, b) = (SELECT x, y ...)` | |
| Skorelowane | zależy od wiersza zewnętrznego | wszędzie; logicznie wykonywane raz na każdy wiersz zewnętrzny | |
| Widok inline | źródło wierszy | klauzula FROM; może mieć własne ORDER BY | |

## 8.1 Podzapytania jednowierszowe

```sql
SELECT e.last_name, e.salary
FROM   employees e
WHERE  e.salary > (SELECT AVG(e2.salary) FROM employees e2)    -- 9344.44
ORDER  BY e.salary DESC;
```

Wynik: King 24000, Kochhar 14000, De Haan 12000.

- `= (SELECT e2.salary FROM employees e2 WHERE e2.department_id = 20)` zgłasza
  **ORA-01427: single-row subquery returns more than one row** (dział 20 ma trzy osoby).
  Sprawdzenie odbywa się w czasie wykonania, więc to samo zapytanie może zadziałać na innych danych.
- Podzapytanie, które **nic nie znajdzie**, daje NULL: `WHERE e.salary <> (... employee_id = 999)`
  zwraca 0 wierszy i nie ma błędu.
- Na liście SELECT: `(SELECT MAX(e.salary) ... )` daje NULL dla Research, ale
  `(SELECT COUNT(*) ...)` daje **0**: agregat bez GROUP BY zawsze zwraca jeden wiersz.
- `MAX(AVG(salary)) ... GROUP BY department_id` zwija grupy do jednego wiersza (24000 → King).
- HAVING może porównywać z podzapytaniem:
  `HAVING AVG(e.salary) > (SELECT AVG(e2.salary) FROM employees e2)` → tylko dział 10.
- **Bez ORDER BY w podzapytaniu w WHERE**: ORA-00907 missing right parenthesis.
  ORDER BY *jest* dozwolone w widoku inline (`FROM (SELECT ... ORDER BY ...)`).
- Podzapytania skalarne są dozwolone w SELECT, WHERE, HAVING, ORDER BY, CASE, UPDATE SET i
  INSERT VALUES; **nie** w GROUP BY (ORA-22818), ograniczeniach CHECK ani wyrażeniach DEFAULT.

Przykład skorelowany (pracownicy powyżej średniej własnego działu):

```sql
SELECT e.last_name, e.department_id, e.salary
FROM   employees e
WHERE  e.salary > (SELECT AVG(e2.salary)
                   FROM   employees e2
                   WHERE  e2.department_id = e.department_id);
```

Wynik: Kochhar (20), De Haan (30), Hunold (30). Grant nie ma działu, więc jego średnia to
NULL, a porównanie daje UNKNOWN.

## 8.2 Podzapytania wielowierszowe

| Operator | Znaczenie | To samo co | Puste podzapytanie |
|---|---|---|---|
| `IN` / `= ANY` | równe jednej z wartości | | FALSE |
| `NOT IN` / `<> ALL` | różne od wszystkich | | TRUE |
| `> ANY` | większe od co najmniej jednej | `> MIN` | FALSE |
| `> ALL` | większe od każdej | `> MAX` | TRUE |
| `< ANY` | mniejsze od co najmniej jednej | `< MAX` | FALSE |
| `< ALL` | mniejsze od każdej | `< MIN` | TRUE |

Dział 30 zarabia 12000, 9000, 6000, 4800:
`salary > ALL (...)` → 2 wiersze (King, Kochhar); `salary > ANY (...)` → 6;
`salary < ANY (...)` → 6; wobec działu 40 (pustego) `> ALL` → wszystkie 9, `> ANY` → 0.

**Pułapka NOT IN.** Pracownik 108 ma dział NULL, więc

```sql
SELECT d.department_name FROM departments d
WHERE  d.department_id NOT IN (SELECT e.department_id FROM employees e);   -- 0 wierszy
```

`x NOT IN (10, 20, 30, NULL)` = `x<>10 AND x<>20 AND x<>30 AND x<>NULL`, a ostatnia część
zawsze daje UNKNOWN. Poprawki, które zwracają **Research**:

```sql
... NOT IN (SELECT e.department_id FROM employees e WHERE e.department_id IS NOT NULL)
... WHERE NOT EXISTS (SELECT 1 FROM employees e WHERE e.department_id = d.department_id)
```

NULL na liście `IN` jest nieszkodliwy: zapytanie IN z `10, 20, 30, 40, NULL` nadal zwraca 8 pracowników.

**EXISTS** sprawdza tylko, czy jakiś wiersz wraca; lista SELECT nie ma znaczenia
(`SELECT NULL`, `SELECT 1`, `SELECT *` działają tak samo). Pracownicy, którzy kimś kierują:
`WHERE EXISTS (SELECT NULL FROM employees r WHERE r.manager_id = e.employee_id)` → King,
Kochhar, De Haan.

**Porównanie parami**: `WHERE (e.department_id, e.salary) IN (SELECT department_id, MAX(salary) ... GROUP BY department_id)`.

**IN a EXISTS a JOIN**: klienci z zamówieniami. IN, `= ANY` i EXISTS zwracają 4 klientów,
każdego raz; zwykły JOIN zwraca 7 wierszy (Acme Corp trzy razy), chyba że dodasz DISTINCT.

## 8.3 Skorelowane UPDATE i DELETE

```sql
UPDATE order_items i
SET    i.unit_price = (SELECT p.list_price FROM products p WHERE p.product_id = i.product_id)
WHERE  i.unit_price < (SELECT p.list_price FROM products p WHERE p.product_id = i.product_id);
-- 4 zmienione wiersze; pozycja Consulting Hour (list_price NULL) jest nietknięta

DELETE FROM orders o
WHERE  NOT EXISTS (SELECT 1 FROM order_items i WHERE i.order_id = o.order_id);
-- 1 usunięty wiersz: zamówienie 1007
```

Reguły:
- **Brak klauzuli WHERE = zmieniany jest każdy wiersz.** Wiersze bez dopasowania dostają NULL:
  `SET c.credit_limit = (SELECT SUM(...) ... WHERE o.customer_id = c.customer_id)` ustawia
  Umbrella (bez zamówień) na NULL. COUNT dałby 0. Powtórz warunek korelacji w
  `WHERE EXISTS (...)`, aby zmieniać tylko pasujące wiersze.
- **Spójność odczytu na poziomie polecenia**: każde wyliczenie podzapytania widzi dane z
  początku polecenia. `SET salary = (SELECT AVG(...) z tego samego działu)` daje każdemu w
  dziale 30 dokładnie 7950, niezależnie od tego, który wiersz jest zmieniany pierwszy. Podobnie
  usunięcie pozycji poniżej średniej ilości w zamówieniu usuwa dokładnie 2 pozycje (1001/1, 1004/2).
- Jeśli podzapytanie w SET zwróci dla któregoś wiersza 2+ wiersze: **ORA-01427**, a całe polecenie jest
  wycofywane (bez częściowej zmiany).
- Kilka kolumn naraz: `SET (i.unit_price, i.quantity) = (SELECT p.list_price, 1 FROM ...)`.
  Bez nawiasów: ORA-00927; za mało kolumn w podzapytaniu: ORA-00947.
- NULL zwrócony przez podzapytanie przechodzi przez ograniczenie `CHECK (salary > 0)` (UNKNOWN to nie naruszenie).

## Częste pułapki

1. `NOT IN` z NULL gdziekolwiek w podzapytaniu → brak wierszy. `NOT EXISTS` jest odporne na NULL.
2. `=` z podzapytaniem, które może zwrócić kilka wierszy → ORA-01427 (w czasie wykonania, zależnie od danych).
3. `> ANY` to `> MIN`, a nie `> MAX`; `< ALL` to `< MIN`.
4. `ALL` na pustym zbiorze to TRUE (wszystkie wiersze), `ANY` na pustym zbiorze to FALSE (brak wierszy).
5. Puste podzapytanie skalarne → NULL, ale podzapytanie skalarne z `COUNT(*)` → 0.
6. ORDER BY w podzapytaniu w WHERE → ORA-00907.
7. Skorelowany UPDATE bez WHERE zeruje (NULL) niedopasowane wiersze.
8. Oczekiwanie, że skorelowany UPDATE/DELETE widzi własne wcześniejsze zmiany wierszy. Nie widzi.
9. JOIN zamiast IN/EXISTS powiela wiersze zewnętrzne, gdy tabela wewnętrzna ma kilka dopasowań.

> **Oracle a standardowy SQL / inne bazy danych**
> - `ANY`, `SOME` i `ALL`, `EXISTS`, porównanie wierszy `(a, b) IN (SELECT ...)` i podzapytania skalarne to standardowy SQL;
>   SQL Server nie obsługuje porównania wierszy w IN.
> - `SET (a, b) = (SELECT ...)` obsługują Oracle i PostgreSQL; SQL Server używa zamiast tego `UPDATE ... FROM`,
>   a MySQL nie pozwala w podzapytaniu czytać zmienianej tabeli (błąd 1093), na co Oracle pozwala.
> - `MAX(AVG(x))` (zagnieżdżone agregaty) istnieje tylko w Oracle; gdzie indziej użyj widoku inline.
> - Oracle nie zgłasza „no data found” dla pustego podzapytania skalarnego; to błąd `SELECT INTO` w PL/SQL.

## Różnice w Oracle 23ai (1Z0-171)

Sprawdzono na Oracle AI Database 23ai (FREEPDB1) z tymi samymi przykładowymi danymi. Semantyka podzapytań
się nie zmieniła: każdy wynik powyżej (NOT IN z NULL → 0 wierszy, `> ALL` / `> ANY`, puste
podzapytanie skalarne → NULL, spójność odczytu w skorelowanym DML, ORA-01427 w WHERE i na
liście SELECT, ORA-00907 dla ORDER BY w podzapytaniu w WHERE, ORA-22818 dla podzapytania w
GROUP BY, ORA-00947 / ORA-00913 / ORA-00927 w `SET (a, b) = ...`, ORA-02292 w skorelowanym
DELETE) jest taki sam w 23ai. Różnią się tylko niektóre kody błędów:

- Skorelowany UPDATE, którego podzapytanie w SET zwraca kilka wierszy dla jednego wiersza
  (`SET e.salary = (SELECT e2.salary ... WHERE e2.department_id = e.department_id)`), zgłasza
  **ORA-30926** (unable to update the same row twice) zamiast ORA-01427 (od 21c).
  Polecenie nadal zawodzi jako całość i nic nie jest zmieniane.
- `SET (i.unit_price, i.quantity) = SELECT 1, 1 FROM dual` (podzapytanie bez nawiasów):
  19c ORA-01767 (UPDATE ... SET expression must be a subquery), 23ai **ORA-00906** missing left
  parenthesis.
