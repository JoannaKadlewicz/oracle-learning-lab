# Ściąga: reguły, które egzamin sprawdza najczęściej

Czytaj ją wieczorami przed egzaminem. Każdy wynik w tabelach został wykonany 18 października 2026 na Oracle 19.3
i na Oracle 23ai (23.26); tam, gdzie się różnią, podano oba. Pozostałe reguły
są pokryte pytaniami w aplikacji sprawdzonymi w bazie danych albo pochodzą z dokumentacji Oracle.

## Kolejność wykonywania

`FROM/JOIN → WHERE → GROUP BY → HAVING → SELECT → DISTINCT → ORDER BY → OFFSET/FETCH`

- Aliasy kolumn istnieją od SELECT: można ich użyć w ORDER BY, nie w WHERE ani HAVING (19c), a
  w GROUP BY tylko w 23ai.
- `ORDER BY` może użyć aliasu, pozycji (`ORDER BY 2`) albo wyrażenia spoza listy
  SELECT (z wyjątkiem sytuacji po DISTINCT albo w zapytaniu złożonym).
- `NULLS LAST` jest domyślne przy sortowaniu rosnącym, `NULLS FIRST` przy malejącym.
- `FETCH FIRST 3 ROWS WITH TIES` wymaga ORDER BY, aby znaleźć remisy; samo `OFFSET 5 ROWS` pomija wiersze.

## NULL

| Wyrażenie | Wynik |
|---|---|
| `NULL = NULL`, `NULL <> 1` | nieznane: wiersz nie jest zwracany |
| `x NOT IN (1, NULL)` | nigdy prawda: 0 wierszy |
| `NULL IN (1, NULL)` | nieznane: 0 wierszy |
| `5 + NULL`, `'a' \|\| NULL` | NULL, ale `'a' \|\| NULL` = `'a'` |
| `LENGTH('')` | NULL (pusty tekst to NULL) |
| `DECODE(NULL, NULL, 'equal', 'not')` | `equal` (DECODE traktuje dwa NULL jako równe) |
| `CASE WHEN NULL = NULL THEN 'eq' ELSE 'ne' END` | `ne` |
| `COUNT(*)` a `COUNT(col)` | wszystkie wiersze a wartości różne od NULL |
| `AVG(col)` | pomija NULL: użyj `AVG(NVL(col, 0))`, aby liczyć je jako 0 |
| Operatory zbiorowe, `DISTINCT`, `GROUP BY` | traktują NULL jako równe sobie |

`NVL(a, b)` (ten sam typ), `NVL2(a, if_not_null, if_null)`, `NULLIF(a, b)` (NULL, gdy równe),
`COALESCE(a, b, c, ...)` (pierwsza wartość różna od NULL, kończy na pierwszym trafieniu).

## Funkcje, które trzeba umieć policzyć w pamięci

| Wyrażenie | Wynik |
|---|---|
| `ROUND(15.193, -1)` / `TRUNC(15.79, -1)` | 20 / 10 |
| `MOD(-7, 3)` / `REMAINDER(7, 4)` | -1 (znak dzielnej) / -1 (zaokrągla iloraz) |
| `INSTR('banana', 'a', -1)` | 6 (szuka wstecz, pozycja liczona od lewej) |
| `SUBSTR('database', -4, 2)` | `ba` |
| `LPAD('7', 3, '0')` / `TRIM(LEADING '0' FROM '0070')` | `007` / `70` |
| `ROUND(DATE '2024-07-16', 'MONTH')` | 2024-08-01 (dzień 16 i później zaokrągla w górę) |
| `ROUND(DATE '2024-07-01', 'YEAR')` | 2025-01-01 (lipiec i później zaokrągla w górę) |
| `ADD_MONTHS(DATE '2024-01-31', 1)` | 2024-02-29 (koniec miesiąca zostaje końcem miesiąca) |
| `MONTHS_BETWEEN(DATE '2024-03-31', DATE '2024-02-29')` | 1 (obie daty to końce miesięcy) |
| `TO_CHAR(DATE '2024-01-05', 'fmDay, Month DD')` | `Friday, January 5` (fm usuwa dopełnienie) |
| `RR` dla `49` / `50` (w tym stuleciu) | 2049 / 1950 |
| `date - date` / `date + 1` / `date + 1/24` | dni (NUMBER) / następny dzień / godzinę później |

## Funkcje grupujące

- Każda niezagregowana kolumna w SELECT musi być w GROUP BY (ORA-00979), ale kolumna z GROUP BY
  nie musi być wybrana.
- WHERE filtruje wiersze przed grupowaniem i nie może zawierać funkcji grupującej (ORA-00934); HAVING filtruje grupy.
- Funkcje grupujące można zagnieżdżać najwyżej na dwa poziomy i tylko z GROUP BY:
  `MAX(AVG(salary))` działa, `COUNT(MAX(AVG(salary)))` zgłasza ORA-00935.

## Złączenia

- Kolumny `NATURAL JOIN` i `USING` nie mogą mieć kwalifikatora z aliasem tabeli (ORA-25155 przy NATURAL, ORA-25154 przy USING).
- Złączenie zewnętrzne z następującym `WHERE inner_table.col = ...` staje się z powrotem złączeniem wewnętrznym; umieść
  warunek w `ON`, aby zachować niedopasowane wiersze.
- `(+)` stoi po stronie, której może brakować; nie da się nim wyrazić pełnego złączenia zewnętrznego.
- Złączenie zwrotne wymaga dwóch aliasów; złączenie nierównościowe używa w warunku `BETWEEN` albo `>`/`<`.
- Brak warunku złączenia daje iloczyn kartezjański: wiersze(A) × wiersze(B).

## Podzapytania

- `=` z podzapytaniem, które zwraca więcej niż jeden wiersz: ORA-01427 w czasie wykonania.
- `> ALL (...)` oznacza więcej niż maksimum; `< ANY (...)` oznacza mniej niż maksimum.
- `NOT IN (podzapytanie)` nie zwraca wierszy, jeśli podzapytanie zwraca jakikolwiek NULL; `NOT EXISTS` nie ma tego problemu.
- Podzapytanie skalarne, które nie zwraca wiersza, daje NULL.

## Operatory zbiorowe

- Ta sama liczba kolumn (ORA-01789) i grupy typów według pozycji (ORA-01790; bez niejawnej zamiany NUMBER na tekst).
- Nazwy kolumn pochodzą z pierwszego SELECT; ORDER BY tylko raz, na końcu.
- `UNION`, `INTERSECT`, `MINUS` usuwają duplikaty; `UNION ALL` je zachowuje i nie sortuje.
- Wszystkie operatory zbiorowe mają równe pierwszeństwo i działają z góry na dół, chyba że użyto nawiasów.

## DML, transakcje, DDL

- DDL (CREATE, ALTER, DROP, TRUNCATE, GRANT) zatwierdza otwartą transakcję, nawet gdy zawiedzie
  po analizie składni.
- `ROLLBACK TO SAVEPOINT s` zachowuje pracę sprzed `s`, a transakcja pozostaje otwarta.
- `TRUNCATE` to DDL: bez WHERE, bez wycofania, nie uruchamia wyzwalaczy DELETE, zachowuje strukturę tabeli.
- `MERGE`: jeden wiersz docelowy zmieniany przez dwa wiersze źródła zgłasza ORA-30926.
- `INSERT ALL` sprawdza każdą klauzulę WHEN; `INSERT FIRST` kończy na pierwszym prawdziwym WHEN.
- Ograniczenia: NOT NULL tylko jako ograniczenie kolumny; FOREIGN KEY może wskazywać PRIMARY KEY albo
  klucz UNIQUE; `ON DELETE CASCADE` / `ON DELETE SET NULL`; UNIQUE dopuszcza kilka NULL.
- `CREATE TABLE ... AS SELECT` kopiuje tylko ograniczenia NOT NULL.
- `SET UNUSED` działa od razu i nie da się go cofnąć; `DROP UNUSED COLUMNS` usuwa dane później.

## Widoki, sekwencje, indeksy, synonimy

- DML przez widok jest niemożliwy, gdy widok używa funkcji grupujących, GROUP BY, DISTINCT,
  ROWNUM albo (dla INSERT) pomija kolumny NOT NULL bez wartości domyślnych.
- `WITH CHECK OPTION` odrzuca zmiany, po których wiersz zniknąłby z widoku.
- `CURRVAL` przed pierwszym `NEXTVAL` w sesji: ORA-08002. Wycofany NEXTVAL nie wraca: luki są normalne.
- Ograniczenia PRIMARY KEY i UNIQUE automatycznie tworzą indeks; klucze obce nie.
- Prywatny synonim jest rozwiązywany przed publicznym o tej samej nazwie.

## Uprawnienia

- `WITH ADMIN OPTION` (uprawnienia systemowe, role): odebranie nie działa kaskadowo.
- `WITH GRANT OPTION` (uprawnienia obiektowe): odebranie przechodzi kaskadowo na użytkowników, którym odbiorca je nadał.
- Aby utworzyć widok albo procedurę na tabeli innego użytkownika, potrzebujesz uprawnienia nadanego bezpośrednio (nie przez rolę).

## Strefy czasowe

- `SYSDATE`/`SYSTIMESTAMP`: czas serwera bazy danych. `CURRENT_DATE`/`CURRENT_TIMESTAMP`/`LOCALTIMESTAMP`: strefa czasowa sesji.
- `LOCALTIMESTAMP` nie ma strefy czasowej; `CURRENT_TIMESTAMP` ma.
- `TIMESTAMP WITH LOCAL TIME ZONE` zapisuje wartość znormalizowaną do strefy bazy danych i pokazuje ją w strefie sesji.
- `INTERVAL YEAR TO MONTH` dla miesięcy i lat, `INTERVAL DAY TO SECOND` dla dni aż do ułamków sekund.
- Dodanie `INTERVAL '1' MONTH` do 31 stycznia zgłasza ORA-01839; `ADD_MONTHS` nie.
