# Temat 3: Funkcje jednowierszowe

Środowisko: Oracle Database 19c, schemat ORASTUDY, sesja z `NLS_DATE_FORMAT = 'YYYY-MM-DD HH24:MI:SS'`,
`NLS_DATE_LANGUAGE = AMERICAN`. Każdy wynik niżej wykonano na przykładowych danych.
Nawiasy `[...]` w wyniku pokazują spacje na początku albo na końcu.

Funkcje jednowierszowe zwracają jedną wartość na wiersz. Mogą wystąpić w klauzulach SELECT, WHERE, ORDER BY,
HAVING i SET i nigdy nie zmieniają zapisanych danych.

## 4.1 Funkcje znakowe

| Wyrażenie | Wynik | Reguła |
|---|---|---|
| `UPPER('King')`, `LOWER('King')`, `INITCAP('o''neil mc-DONALD')` | `KING`, `king`, `O'Neil Mc-Donald` | INITCAP zaczyna nowe słowo po każdym znaku, który nie jest literą ani cyfrą |
| `CONCAT('a', 'b')` | `ab` | Dokładnie dwa argumenty; trzy zgłaszają **ORA-00909** |
| `LENGTH('De Haan')`, `LENGTH('')` | `7`, NULL | `''` to w Oracle NULL |
| `SUBSTR('ORACLE SQL', -3, 2)` | `SQ` | Ujemny start liczy od końca; długość nadal idzie w prawo |
| `SUBSTR('ORACLE', 0, 3)` | `ORA` | Pozycja 0 jest traktowana jak 1 |
| `SUBSTR('De Haan', 4, -4)` | NULL | Długość < 1 daje NULL |
| `INSTR('BANANA', 'AN', 1, 2)` | `4` | (tekst, szukane, start, wystąpienie); 0, jeśli nie znaleziono |
| `INSTR('BANANA', 'A', -1, 2)` | `4` | Ujemny start szuka wstecz od końca |
| `LPAD('42', 5, '*')`, `RPAD('42', 5, '*')` | `***42`, `42***` | Długość to długość *całości* |
| `LPAD('ORACLE', 3)` | `ORA` | Krótsza długość docelowa obcina (zostaje lewa część) |
| `LPAD('ab', 5)` | `[   ab]` | Domyślny znak dopełnienia to spacja |
| `REPLACE('banana', 'an')` | `ba` | Brak albo NULL jako zamiennik usuwa każde trafienie |
| `TRIM('x' FROM 'xxaxx')` | `a` | `TRIM([LEADING\|TRAILING\|BOTH] znak FROM s)` |
| `TRIM('xy' FROM 'xyaxy')` | **ORA-30001** | TRIM przyjmuje tylko jeden znak |
| `RTRIM('ORACLE', 'CLE')`, `LTRIM('ORACLE', 'CLE')` | `ORA`, `ORACLE` | LTRIM/RTRIM usuwają dowolne znaki *z zestawu* |

Wyszukiwanie bez rozróżniania wielkości liter: zamieniaj kolumnę, a nie tylko literał.

```sql
SELECT e.employee_id FROM employees e WHERE UPPER(e.last_name) = 'KING';   -- 100
SELECT e.employee_id FROM employees e WHERE e.last_name = 'KING';          -- brak wierszy
```

## 4.2 Arytmetyka na datach

DATE zawsze zawiera godzinę (z dokładnością do sekundy). Liczby dodawane do DATE to **dni**.

| Wyrażenie | Typ wyniku | Przykład |
|---|---|---|
| `DATE + n`, `DATE - n` | DATE | `DATE '2024-03-01' - 0.5` = `2024-02-29 12:00:00` |
| `DATE - DATE` | NUMBER (dni) | `DATE '2024-03-10' - DATE '2024-03-01'` = `9` |
| `DATE + DATE` | błąd | **ORA-00975: date + date not allowed** |
| `DATE + n/24`, `DATE + n/1440` | DATE | godziny, minuty: zamówienie 1006 `+ 90/1440` = `2024-04-01 01:00:00` |

```sql
SELECT o.order_date - DATE '2024-03-01'          AS diff,   -- 30.9791666...
       TRUNC(o.order_date - DATE '2024-03-01')   AS t       -- 30 (TRUNC liczbowy)
FROM   orders o WHERE o.order_id = 1006;
```

Godziny między dwiema datami DATE: `(d2 - d1) * 24`; od 09:30 do 18:00 daje `8.5`.

## 4.3 ROUND, TRUNC i MOD

| Wyrażenie | Wynik | Uwaga |
|---|---|---|
| `ROUND(1234.567, -2)`, `TRUNC(1234.567, 1)` | `1200`, `1234.5` | Ujemna precyzja działa na lewo od przecinka |
| `ROUND(45.926, 1)`, `TRUNC(45.96, 1)`, `ROUND(45.96, 1)` | `45.9`, `45.9`, `46` | |
| `ROUND(-2.5)`, `ROUND(2.5)` | `-3`, `3` | Połówki są zaokrąglane od zera (NUMBER) |
| `TRUNC(-2.7)`, `FLOOR(-2.7)` | `-2`, `-3` | TRUNC idzie w stronę zera |
| `MOD(-7, 3)` | `-1` | Znak dzielnej |
| `MOD(10, 0)` | `10` | Bez błędu dzielenia przez zero |

`WHERE MOD(e.salary, 1000) = 0` zostawia 6 z 9 pracowników; `MOD(e.employee_id, 2) = 0` znajduje parzyste identyfikatory.

## 4.4 Funkcje dat

| Wyrażenie | Wynik |
|---|---|
| `ADD_MONTHS(DATE '2024-01-31', 1)` | `2024-02-29` (reguła ostatniego dnia) |
| `ADD_MONTHS(DATE '2023-02-28', 1)` | `2023-03-31` (28 lutego 2023 *jest* końcem miesiąca) |
| `ADD_MONTHS(DATE '2024-02-28', 1)` | `2024-03-28` |
| `MONTHS_BETWEEN(DATE '2024-03-31', DATE '2024-02-29')` | `1` (oba to końce miesięcy) |
| `MONTHS_BETWEEN(DATE '2024-03-16', DATE '2024-02-15')` | `1.0322...` (1 + 1/31) |
| `MONTHS_BETWEEN(DATE '2024-01-01', DATE '2024-03-01')` | `-2` (pierwsza wcześniejsza → wynik ujemny) |
| `NEXT_DAY(DATE '2024-03-05', 'TUESDAY')` (to wtorek) | `2024-03-12` (zawsze później) |
| `LAST_DAY(zamówienie 1006)` | `2024-03-31 23:30:00` (zachowuje godzinę) |
| `ROUND(DATE '2024-07-16', 'MM')`, `ROUND(DATE '2024-07-15', 'MM')` | `2024-08-01`, `2024-07-01` |
| `ROUND(DATE '2024-07-01', 'YYYY')`, `ROUND(DATE '2024-06-30', 'YYYY')` | `2025-01-01`, `2024-01-01` |
| `TRUNC(zamówienie 1006)`, `TRUNC(zamówienie 1006, 'MM')` | `2024-03-31 00:00:00`, `2024-03-01 00:00:00` |

Nazwy dni w NEXT_DAY zależą od `NLS_DATE_LANGUAGE`. `TRUNC(d, 'DAY')` zależy od `NLS_TERRITORY`
(pierwszego dnia tygodnia).

Wybór całego miesiąca, gdy daty DATE zawierają godziny:

```sql
WHERE o.order_date >= DATE '2024-03-01' AND o.order_date < DATE '2024-04-01'  -- 1004, 1005, 1006
WHERE TRUNC(o.order_date, 'MM') = DATE '2024-03-01'                           -- te same wiersze
WHERE o.order_date BETWEEN DATE '2024-03-01' AND DATE '2024-03-31'            -- pomija 1006 (23:30)
```

## Częste pułapki

1. `CONCAT` z trzema argumentami: ORA-00909. Użyj `||`.
2. `TRIM` z zestawem kilku znaków: ORA-30001. Użyj `LTRIM`/`RTRIM`.
3. `LTRIM`/`RTRIM` usuwają *zestaw* znaków, a nie przedrostek: `LTRIM('De Haan', 'De')` = `' Haan'`.
4. `SUBSTR(s, -3, 2)` czyta w prawo od trzeciego znaku od końca.
5. `INSTR` zwraca 0 (a nie NULL), gdy nic nie znajdzie.
6. `LENGTH('')` to NULL, a nie 0.
7. `ROUND(2.5)` = 3 (nie zaokrąglanie bankierskie); `TRUNC(-2.7)` = -2.
8. `MOD(10, 0)` = 10; `MOD(-7, 3)` = -1.
9. `DATE + DATE` to błąd; `DATE - DATE` to NUMBER, a nie INTERVAL.
10. `NEXT_DAY` nigdy nie zwraca tego samego dnia; `LAST_DAY` i `ADD_MONTHS` zachowują godzinę.
11. `ADD_MONTHS` z końca miesiąca trafia na koniec miesiąca (28 lutego 2023 + 1 = 31 marca).
12. `BETWEEN ... AND DATE '2024-03-31'` pomija godziny późniejsze niż północ 31-go.

> **Oracle a standardowy SQL / inne bazy danych**
>
> - `CONCAT` przyjmuje dowolną liczbę argumentów w MySQL i PostgreSQL; Oracle pozwala na dwa.
> - Oracle traktuje `''` jak NULL; PostgreSQL i SQL Server zachowują pusty tekst o długości 0.
> - `SUBSTR`/`INSTR` to nazwy z Oracle; standard ma `SUBSTRING(s FROM n FOR m)` i
>   `POSITION(x IN s)`. SQL Server używa `SUBSTRING`, `CHARINDEX` i `LEN`.
> - `DATE` w Oracle zawiera godzinę; w standardzie SQL, PostgreSQL i MySQL `DATE` nie ma godziny.
> - `DATE + n` (dni) to specyfika Oracle; standardowy SQL dodaje wartości `INTERVAL`, które Oracle też obsługuje.
> - `ADD_MONTHS`, `MONTHS_BETWEEN`, `NEXT_DAY`, `LAST_DAY` (Oracle) odpowiadają `DATEADD`/`DATEDIFF`
>   (SQL Server) oraz `+ INTERVAL`/`AGE` (PostgreSQL).
> - `%` w Pythonie przyjmuje znak dzielnika (`-7 % 3` = 2); `MOD` w Oracle przyjmuje znak dzielnej.

## Różnice w Oracle 23ai (1Z0-171)

Wykonano na Oracle AI Database 23ai (23.26, schemat ORASTUDY) i porównano z 19c. Cała reszta
tego tematu (SUBSTR, INSTR, TRIM, ROUND/TRUNC/MOD na liczbach, arytmetyka na DATE,
ADD_MONTHS, MONTHS_BETWEEN, NEXT_DAY, LAST_DAY, ROUND/TRUNC na datach) działa tak samo.

| Wyrażenie | 19c | 23ai |
|---|---|---|
| `CONCAT(e.first_name, ' ', e.last_name)` | **ORA-00909** | `Steven King` (dowolna liczba argumentów, co najmniej 2) |
| `CONCAT('a', NULL, 'b')`, `CONCAT(1, 2, 3)` | **ORA-00909** | `ab`, `123` |
| `CONCAT('a')` | **ORA-00909** | **ORA-00909** (nadal potrzeba dwóch albo więcej) |
| `CEIL(TO_DATE('2024-03-05 13:00', ...))`, `FLOOR(...)` | **ORA-00932** | `2024-03-06 00:00:00`, `2024-03-05 00:00:00` |
| `CEIL(d, 'MM')` dla 2024-03-05 13:00, `FLOOR(d, 'MM')` | **ORA-00909** | `2024-04-01`, `2024-03-01` (CEIL z dokładnego początku miesiąca zostaje bez zmian) |
| `CEIL(TIMESTAMP '2024-03-05 13:00:00')`, `FLOOR(ts, 'YYYY')` | błąd | `2024-03-06 00:00:00`, `2024-01-01 00:00:00` |
| `ROUND(INTERVAL '1 13:00:00' DAY TO SECOND)`, `TRUNC(...)` | **ORA-00932** | `+02 00:00:00`, `+01 00:00:00` |
| `ROUND(INTERVAL '1-7' YEAR TO MONTH)`, `TRUNC(...)`, `FLOOR(...)`, `CEIL(...)` | **ORA-00932** | `+02-00`, `+01-00`, `+01-00`, `+02-00` |
| `SELECT UPPER('a');` (bez FROM) | **ORA-00923** | `A` (FROM DUAL jest opcjonalne) |

- Kody błędów się nie zmieniły, ale komunikaty w 23ai są bardziej opisowe: `DATE * 2` daje
  *ORA-00932: expression is of data type DATE, which is incompatible with expected data type NUMBER*,
  a `TRUNC('2024-03-05')` daje *ORA-01722: unable to convert string value containing ...*.
- `DATE + DATE` nadal zgłasza **ORA-00975**, `DATE - DATE` to nadal NUMBER, a `DATE - TIMESTAMP`
  nadal INTERVAL DAY TO SECOND.
- Nowość w 23ai, omówiona w t15: `TIME_BUCKET(DATE '2024-03-05', INTERVAL '7' DAY, DATE '2024-03-01')`
  = `2024-03-01`.
