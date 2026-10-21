# Temat 14: Strefy czasowe i interwały

Środowisko: Oracle Database 19c, schemat ORASTUDY. Wszystkie wyniki niżej zostały **wykonane**.
Wyrażenia używają jawnych stref, więc nie zależą od strefy czasowej sesji; tam, gdzie
wynik zależy od sesji (`ALTER SESSION SET TIME_ZONE`), jest to napisane.
Tabela `events`: `starts_at TIMESTAMP(0) WITH TIME ZONE`, `logged_at TIMESTAMP(0) WITH LOCAL
TIME ZONE`, `duration INTERVAL DAY(2) TO SECOND(0)`, `warranty INTERVAL YEAR(2) TO MONTH`.
Cele 16.1–16.2.

## Pojęcie: typy daty i czasu

| Typ | Przechowuje | Pokazywany jako |
|---|---|---|
| `DATE` | data + godzina z dokładnością do sekundy, bez strefy | jak zapisano |
| `TIMESTAMP(p)` | + ułamki sekund, bez strefy | jak zapisano |
| `TIMESTAMP WITH TIME ZONE` | + przesunięcie (`+01:00`) albo region (`Europe/Warsaw`) | we własnej strefie |
| `TIMESTAMP WITH LOCAL TIME ZONE` | normalizowany do `DBTIMEZONE`, strefa nie jest zachowywana | w strefie czasowej **sesji** |
| `INTERVAL YEAR(p) TO MONTH` | lata i miesiące | `+01-06` |
| `INTERVAL DAY(p) TO SECOND(s)` | dni, godziny, minuty, sekundy | `+02 10:30:00` |

## 16.1 CURRENT_DATE, CURRENT_TIMESTAMP i LOCALTIMESTAMP

| Funkcja | Typ danych (wykonano przez CTAS) | Używana strefa czasowa |
|---|---|---|
| `SYSDATE` | DATE | system operacyjny hosta bazy danych |
| `SYSTIMESTAMP` | TIMESTAMP(6) WITH TIME ZONE | system operacyjny hosta bazy danych |
| `CURRENT_DATE` | DATE | sesja |
| `CURRENT_TIMESTAMP` | TIMESTAMP(6) WITH TIME ZONE | sesja |
| `LOCALTIMESTAMP` | TIMESTAMP(6) | sesja |

- Po `ALTER SESSION SET TIME_ZONE = '-05:00'`: CURRENT_DATE 15:03, SYSDATE 20:03,
  `CURRENT_TIMESTAMP` 15:03 -05:00, `SYSTIMESTAMP` 20:03 +00:00. `SESSIONTIMEZONE` się zmienia; `DBTIMEZONE` nie.
- `CAST(CURRENT_TIMESTAMP AS TIMESTAMP) = LOCALTIMESTAMP` jest prawdziwe: ta sama chwila, ta sama strefa.
- `CURRENT_TIMESTAMP(0)` / `LOCALTIMESTAMP(2)` przyjmują precyzję ułamków sekund.

Przeliczanie i sprawdzanie stref:

| Wyrażenie | Wynik |
|---|---|
| `TIMESTAMP '2024-01-15 08:00:00 Europe/Warsaw' AT TIME ZONE 'America/New_York'` | 02:00 EST |
| `... AT TIME ZONE '+05:30'` (lipiec) | 11:30 +05:30 |
| `FROM_TZ(TIMESTAMP '2024-07-01 12:00:00', '-04:00')` | 12:00 -04:00 (dołącza strefę, nie przelicza) |
| `FROM_TZ(DATE '2024-07-01', 'UTC')` | ORA-00932: expected TIMESTAMP got DATE |
| `TO_TIMESTAMP_TZ('2024-07-01 12:00 -04:00', 'YYYY-MM-DD HH24:MI TZH:TZM') AT TIME ZONE 'Asia/Tokyo'` | 2024-07-02 01:00 |
| `SYS_EXTRACT_UTC(TIMESTAMP '2024-03-31 23:30:00 America/New_York')` | 2024-04-01 03:30 |
| `TZ_OFFSET('-05:00')`, `TZ_OFFSET('UTC')` | -05:00, +00:00 |
| `TZ_OFFSET(SYSTIMESTAMP)` | ORA-01882: timezone region not found |
| `... AT TIME ZONE 'Mars/Base'` | ORA-01882 |

`TZ_OFFSET('Europe/Warsaw')` zwraca przesunięcie obowiązujące **dzisiaj** (+01:00 albo +02:00).

EXTRACT na `events.starts_at`:

| wydarzenie | zapisane | `TIMEZONE_REGION` | `TIMEZONE_HOUR` | `TIMEZONE_ABBR` | `HOUR` |
|---|---|---|---|---|---|
| 1 | 2024-03-31 01:30 Europe/Warsaw | Europe/Warsaw | 1 | CET | **0** |
| 2 | 2024-02-29 09:00 +00:00 | UNKNOWN | 0 | UNK | 9 |
| 3 | 2024-03-31 23:30 America/New_York | America/New_York | -4 | EDT | **3** |

EXTRACT pól HOUR/DAY/... z wartości ze strefą czasową zwraca pola w **UTC** (wydarzenie 3: dzień 1,
godzina 3). `TO_CHAR(starts_at, 'HH24')` i `CAST(starts_at AS DATE)` zachowują czas lokalny (23:30).

Czas letni przy nazwach regionów (Warszawa zmieniła czas o 02:00 31 marca 2024):

- `TIMESTAMP '2024-03-31 02:30:00 Europe/Warsaw'` → **ORA-01878** (ta godzina lokalna nie istnieje).
- `TIMESTAMP '2024-03-31 01:30:00 Europe/Warsaw' + INTERVAL '1' HOUR` → 03:30 CEST.
- `TIMESTAMP '2024-03-31 01:30:00 Europe/Warsaw' = TIMESTAMP '2024-03-31 00:30:00 UTC'` → równe
  (porównania używają chwili w UTC); z `+02:00` zamiast tego → nierówne.
- `logged_at` (WITH LOCAL TIME ZONE) wydarzenia 3 pokazuje 2024-04-01 05:30 w sesji +02:00,
  2024-03-31 22:30 w sesji -05:00 i 2024-04-01 03:30 w UTC.

## 16.2 Typy danych INTERVAL

| Wyrażenie | Wynik |
|---|---|
| `INTERVAL '1-6' YEAR TO MONTH`, `INTERVAL '18' MONTH`, `TO_YMINTERVAL('01-06')`, `NUMTOYMINTERVAL(18, 'MONTH')` | +01-06 |
| `INTERVAL '2 10:30:00' DAY TO SECOND`, `TO_DSINTERVAL('2 10:30:00')` | +02 10:30:00 |
| `INTERVAL '90' MINUTE`, `NUMTODSINTERVAL(90, 'MINUTE')` | +00 01:30:00 |
| `NUMTODSINTERVAL(100, 'HOUR')`, `INTERVAL '100' HOUR` | +04 04:00:00 |
| `INTERVAL '123' DAY` | ORA-01873 (domyślna precyzja wiodąca 2; użyj `DAY(3)`) |
| `INTERVAL '1 25' DAY TO HOUR` / `INTERVAL '1-12' YEAR TO MONTH` | ORA-01850 / ORA-01843 |
| `NUMTODSINTERVAL(1, 'MONTH')`, `NUMTOYMINTERVAL(1, 'DAY')` | ORA-01760 |
| `TO_YMINTERVAL('1.5')` | ORA-01867; ISO `TO_YMINTERVAL('P1Y2M')` działa |
| `INTERVAL '1-6' YEAR TO MONTH + INTERVAL '8' MONTH` | +02-02 |
| `INTERVAL '1-6' YEAR TO MONTH / 2`, `INTERVAL '1' DAY * 1.5` | +00-09, +01 12:00:00 |
| `INTERVAL '1' DAY + INTERVAL '1' MONTH` | ORA-30081 |
| `EXTRACT(HOUR FROM INTERVAL '2 10:30:00' DAY TO SECOND)` | 10 (jedno pole, a nie suma) |
| `SUM(duration)` | ORA-00932 w 19c (23ai dodaje SUM/AVG dla interwałów) |

Typy wyników arytmetyki na datach i czasie (wykonano przez CTAS):

| Wyrażenie | Typ wyniku |
|---|---|
| `TIMESTAMP - TIMESTAMP` | INTERVAL DAY TO SECOND (`+02 02:30:00`) |
| `TIMESTAMP - DATE` | INTERVAL DAY TO SECOND |
| `DATE - DATE` | NUMBER (dni) |
| `TIMESTAMP + 1` | **DATE** |
| `TIMESTAMP + INTERVAL '1' HOUR` | TIMESTAMP |
| `DATE + INTERVAL '1' HOUR` | DATE |

Arytmetyka miesięcy nie dopasowuje dnia:

- `DATE '2024-01-31' + INTERVAL '1' MONTH` → ORA-01839; `DATE '2024-03-31' - INTERVAL '1' MONTH` → ORA-01839.
- `DATE '2024-02-29' + INTERVAL '1' YEAR` → ORA-01839, ale `+ INTERVAL '4' YEAR` → 2028-02-29.
- `ADD_MONTHS(DATE '2024-02-29', 12)` → 2025-02-28 (ADD_MONTHS przechodzi na ostatni dzień miesiąca).

## Częste pułapki

1. EXTRACT(HOUR ...) z TIMESTAMP WITH TIME ZONE jest w UTC, a nie w czasie lokalnym.
2. EXTRACT(HOUR FROM DATE) kończy się błędem (ORA-30076); na DATE działają tylko YEAR, MONTH, DAY.
3. Mieszanie interwałów YEAR TO MONTH i DAY TO SECOND (ORA-30081).
4. `+ INTERVAL 'n' MONTH/YEAR` w dniach 29–31 może zakończyć się błędem ORA-01839; ADD_MONTHS nigdy.
5. Domyślna precyzja wiodąca to 2: `INTERVAL '123' DAY` kończy się błędem.
6. SYSDATE/SYSTIMESTAMP podążają za systemem operacyjnym serwera, a nie za SESSIONTIMEZONE ani DBTIMEZONE.
7. FROM_TZ dołącza strefę; AT TIME ZONE przelicza. FROM_TZ wymaga TIMESTAMP, a nie DATE.
8. TIMESTAMP + 1 po cichu staje się DATE i traci ułamki sekund.
9. Nazwa regionu stosuje reguły czasu letniego (godziny z przerwy kończą się błędem ORA-01878); stałe przesunięcie nie.
10. TIMESTAMP WITH LOCAL TIME ZONE nie pamięta pierwotnej strefy; pokazywana wartość
    zależy od sesji.

> **Oracle a standardowy SQL / inne bazy danych**
> - `CURRENT_DATE`, `CURRENT_TIMESTAMP`, `LOCALTIMESTAMP`, `EXTRACT`, `AT TIME ZONE` i literały
>   interwałów to ANSI. `SYSDATE`, `SYSTIMESTAMP`, `FROM_TZ`, `TZ_OFFSET`, `NUMTODSINTERVAL` i
>   `TO_YMINTERVAL` są specyficzne dla Oracle.
> - `CURRENT_DATE` w Oracle to DATE **z** godziną; w standardowym SQL i w PostgreSQL to sama data.
> - PostgreSQL ma jeden typ `interval`, który łączy miesiące i dni i dopasowuje `'2024-01-31' + interval '1 month'`
>   do 2024-02-29; Oracle zgłasza ORA-01839. SQL Server nie ma typu interwału (`DATEADD` / `DATEDIFF`).
> - `timestamptz` z PostgreSQL działa jak WITH LOCAL TIME ZONE w Oracle (zapisuje UTC, pokazuje strefę sesji);
>   WITH TIME ZONE w Oracle zachowuje pierwotną strefę, jak `datetimeoffset` w SQL Server (tylko przesunięcia).

## Różnice w Oracle 23ai (1Z0-171)

Wykonano na Oracle 23ai (FREEPDB1) i 19c na tych samych wierszach `events`.

- **SUM i AVG dla interwałów.** 19c przyjmuje tylko liczby (ORA-00932: expected NUMBER got
  INTERVAL DAY TO SECOND); 23ai agreguje interwały bezpośrednio. Wartości NULL są pomijane, a pusty
  zbiór daje NULL:

  | Wyrażenie | 19c | 23ai |
  |---|---|---|
  | `SUM(e.duration)` | ORA-00932 | +01 02:15:00 |
  | `AVG(e.duration)` | ORA-00932 | +00 08:45:00 |
  | `SUM(e.warranty)` / `AVG(e.warranty)` | ORA-00932 | +01-06 / +00-09 |
  | `MIN(e.duration)` / `MAX(e.duration)` | +00 00:45:00 / +01 00:00:00 | to samo |

  W 19c najpierw zamień na liczbę (`EXTRACT(DAY ...) * 1440 + EXTRACT(HOUR ...) * 60 + ...`;
  `e.duration * 1440` to nadal interwał) i zamień sumę z powrotem przez NUMTODSINTERVAL.
- Kody błędów dla pomyłek z datami i interwałami są w obu wersjach te same (ORA-01839,
  ORA-01873, ORA-30076, ORA-30081, ORA-01867, ORA-01850). Niektóre treści są dłuższe w 23ai, na przykład
  ORA-00932 dla `duration > 1`: "expression (1) is of data type NUMBER, which is incompatible with
  expected data type INTERVAL DAY TO SECOND".
- Wyniki dotyczące stref czasowych (AT TIME ZONE, FROM_TZ, TZ_OFFSET, EXTRACT w UTC, przerwy przy zmianie czasu) zgadzały się w obu
  wersjach dla każdego przykładu z tych notatek.
