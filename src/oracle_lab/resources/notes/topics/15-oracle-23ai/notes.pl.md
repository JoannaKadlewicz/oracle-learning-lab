# Temat 15: Nowe funkcje SQL w Oracle 23ai (tylko 1Z0-171)

Środowisko: Oracle AI Database 23ai (wydanie 23.26, FREEPDB1), schemat ORASTUDY. Każdy przykład
niżej oznaczony jako **(wykonano)** został tam uruchomiony; wyniki „zawodzi w 19c” uruchomiono na 19.3 (ORAPDB1).
Przykłady DDL (IF [NOT] EXISTS, kolumny BOOLEAN i VECTOR, domeny, adnotacje,
DEFAULT ON NULL FOR INSERT AND UPDATE) wykonano na tymczasowych obiektach `LAB_N15_`, które
potem usunięto. Uprawnienia do schematu dało się sprawdzić tylko pod kątem składni i kodów błędów (ORASTUDY
nie może tworzyć użytkowników), a RETURNING OLD/NEW wykonano z Pythona ze zmiennymi wiązanymi.
Dział 17 celów egzaminu; temat t15 należy tylko do egzaminu 1Z0-171.

## 17.1 SELECT bez FROM, aliasy w GROUP BY / HAVING, konstruktor VALUES

```sql
SELECT SYSDATE - SYSDATE AS z;                -- 0           (wykonano; 19c: ORA-00923)
SELECT COUNT(*);                              -- 1           (wykonano)
SELECT COUNT(*) WHERE 1 = 0;                  -- 0, jeden wiersz  (wykonano)
SELECT *;                                     -- ORA-54058   (wykonano)
```

```sql
SELECT e.department_id AS dept, COUNT(*) AS cnt      -- (wykonano) 20 → 3, 30 → 4
FROM   employees e
GROUP  BY dept
HAVING cnt > 2
ORDER  BY dept;
```

- Aliasy działają w GROUP BY i HAVING (oraz, jak wcześniej, w ORDER BY); **nie w WHERE** (ORA-00904).
- Tylko sam alias: `GROUP BY band + 0` → ORA-00904; `GROUP BY cnt` dla `COUNT(*) AS cnt` → ORA-00934.
- **Konflikt nazw:** `SELECT e.department_id AS salary ... GROUP BY salary` grupuje po
  *kolumnie* e.salary → ORA-00979 (wykonano).
- **GROUP BY po pozycji zależy od parametru.** Przy domyślnym `group_by_position_enabled = FALSE`
  `SELECT e.department_id, COUNT(*) ... GROUP BY 1` zgłasza **ORA-03162** (wykonano); 1 to
  stała. Przy parametrze TRUE grupuje po pierwszej kolumnie.

Konstruktor tabeli VALUES (wykonano):

```sql
SELECT * FROM (VALUES (1, 'a'), (2, 'b')) t (id, txt);        -- wymagany alias + lista kolumn
WITH v (n) AS (VALUES (1), (2)) SELECT * FROM v;
INSERT INTO promotions (promo_id, promo_name) VALUES (1, 'A'), (2, 'B');
MERGE INTO products p USING (VALUES (11, 1000), (99, 5)) v (id, price)
ON (p.product_id = v.id)
WHEN MATCHED THEN UPDATE SET p.list_price = v.price
WHEN NOT MATCHED THEN INSERT (product_id, product_name, list_price) VALUES (v.id, 'New', v.price);
```

| Błąd | Kod (wykonano) |
|---|---|
| brak aliasu / alias bez listy kolumn | ORA-00931 / ORA-63814 |
| wiersze z różną liczbą wartości | ORA-63801 |
| lista kolumn dłuższa niż wiersze | ORA-63815 |
| `(1), ('x')` w jednej kolumnie | ORA-01790 |

## 17.2 Typ danych BOOLEAN

```sql
CREATE TABLE lab_n15_t (id NUMBER, active BOOLEAN DEFAULT TRUE, flag BOOL);  -- BOOL = BOOLEAN (wykonano)
SELECT TRUE AND NULL, TRUE OR NULL, NOT NULL, FALSE AND NULL;               -- NULL, TRUE, NULL, FALSE (wykonano)
SELECT e.last_name, e.salary > 10000 AS high FROM employees e;               -- warunek jako kolumna (wykonano)
SELECT COUNT(*) FROM employees e WHERE (e.commission_pct > 0.1) IS NOT TRUE; -- 5 (wykonano)
```

- Wartości: TRUE, FALSE, NULL. Sama kolumna BOOLEAN jest warunkiem: `WHERE active`, `WHERE NOT active`.
- `TO_BOOLEAN` / wstawienie do kolumny BOOLEAN przyjmuje 'true'/'false', 'yes'/'no', 'on'/'off',
  't'/'f', 'y'/'n', '1'/'0' (w dowolnej wielkości liter) oraz liczby (0 = FALSE, każda inna = TRUE, więc -5 → TRUE).
  `TO_BOOLEAN('maybe')` → **ORA-61800** (wykonano).
- `IS TRUE`, `IS FALSE`, `IS NOT TRUE`, `IS NOT FALSE` nigdy nie zwracają NULL; `NOT NULL` pozostaje NULL.
  `IS UNKNOWN` nie jest obsługiwane (ORA-00908, wykonano).
- Sortowanie: FALSE < TRUE; NULL na końcu przy sortowaniu rosnącym (wykonano). `TO_CHAR(TRUE)` = 'TRUE', `TO_NUMBER(TRUE)` = 1.
- 19c: BOOLEAN tylko w PL/SQL; `CREATE TABLE ... (b BOOLEAN)` → ORA-00902, `SELECT TRUE FROM dual` → ORA-00904 (wykonano).

## 17.3 IF [NOT] EXISTS

```sql
CREATE TABLE IF NOT EXISTS lab_n15_t (...);     -- istniejąca nazwa: ciche powodzenie, nic się nie zmienia
DROP TABLE IF EXISTS lab_n15_t PURGE;           -- brak obiektu: ciche powodzenie
ALTER TABLE IF EXISTS lab_n15_nope ADD (c NUMBER);   -- brak tabeli: ciche powodzenie
CREATE SEQUENCE IF NOT EXISTS lab_n15_s START WITH 100;  -- istniejąca sekwencja zachowuje stare ustawienia
```

Wszystko wykonano dla tabel, widoków, sekwencji, indeksów, synonimów i domen.

| Polecenie | Wynik (wykonano) |
|---|---|
| `CREATE OR REPLACE VIEW IF NOT EXISTS ...` (także SYNONYM) | **ORA-11541** REPLACE and IF NOT EXISTS cannot coexist |
| `DROP TABLE IF NOT EXISTS t` | **ORA-11544** |
| `ALTER TABLE t ADD IF NOT EXISTS (c NUMBER)` | ORA-02000 (brak postaci na poziomie kolumn) |
| `CREATE INDEX IF NOT EXISTS i ON t (other, cols)`, gdy i istnieje | bez komunikatu, indeks bez zmian |
| 19c `DROP TABLE IF EXISTS t` / `CREATE TABLE IF NOT EXISTS` | ORA-00933 / ORA-00922 |

## 17.4 Rozszerzenia DML

```sql
UPDATE employees e SET e.salary = e.salary + 100           -- 4 wiersze (wykonano)
FROM   departments d
WHERE  d.department_id = e.department_id AND d.location = 'Warsaw';

DELETE FROM orders o FROM order_items oi WHERE o.order_id = oi.order_id;   -- 6 zamówień, a nie 9 (wykonano)
```

- Złączenie z tabelą docelową trafia do WHERE; dozwolonych jest kilka tabel w FROM albo złączenia ANSI.
- Wiersz docelowy pasujący w UPDATE do kilku wierszy źródła → **ORA-30926** (wykonano, także całkiem bez
  WHERE). DELETE po prostu usuwa wiersz raz.
- `RETURNING OLD e.salary, NEW e.salary INTO :a, :b` → 24000, 48000 (wykonano ze zmiennymi wiązanymi).
  INSERT: wartości OLD to NULL; DELETE: wartości NEW to NULL (wykonano). Zwykłe RETURNING w
  UPDATE zwraca nowe wartości.
- `DEFAULT ON NULL FOR INSERT AND UPDATE 'C'`: `UPDATE ... SET c = NULL` zapisuje 'C' (wykonano).
  `DEFAULT ON NULL 'A'` = FOR INSERT ONLY: `SET a = NULL` → **ORA-01407** (wykonano). Obie czynią
  kolumnę NOT NULL. Samo `FOR UPDATE` → ORA-02000. Słownik: `DEFAULT_ON_NULL`,
  `DEFAULT_ON_NULL_UPD` w USER_TAB_COLUMNS.
- Wielowierszowe `INSERT ... VALUES (...), (...)` to jedno polecenie: jeden powtórzony klucz → ORA-00001 i
  żaden wiersz nie zostaje wstawiony (wykonano). 19c: ORA-00933.

## 17.5 Uprawnienia do schematu i DB_DEVELOPER_ROLE

```sql
GRANT SELECT ANY TABLE ON SCHEMA hr TO reporter;
GRANT INSERT ANY TABLE, UPDATE ANY TABLE ON SCHEMA hr TO app_user;
REVOKE SELECT ANY TABLE ON SCHEMA hr FROM reporter;
```

- Tylko uprawnienia systemowe ANY: `GRANT SELECT ON SCHEMA ...` i `GRANT CREATE TABLE ON SCHEMA ...`
  → ORA-00990 (wykonano). Schemat SYS jest wyłączony → ORA-41905 (wykonano).
- Obejmuje obiekty utworzone później w schemacie (zgodnie z dokumentacją). Właściciel może nadawać na własnym
  schemacie (wykonano: nadanie ORASTUDY przeszło kontrolę uprawnień i zawiodło tylko z ORA-01917,
  bo nie ma odbiorcy); inni potrzebują GRANT ANY SCHEMA PRIVILEGE (istnieje w SYSTEM_PRIVILEGE_MAP).
- Widoki: DBA_SCHEMA_PRIVS, USER_SCHEMA_PRIVS (obecne w DICTIONARY).
- **DB_DEVELOPER_ROLE**: uprawnienia programisty we własnym schemacie (CREATE TABLE, VIEW, SEQUENCE,
  PROCEDURE, TRIGGER, TYPE, SYNONYM, MATERIALIZED VIEW...) plus CREATE DOMAIN, CREATE MLE,
  CREATE JOB, DEBUG CONNECT SESSION; bez uprawnień ANY i bez UNLIMITED TABLESPACE. Wypisane z
  ROLE_SYS_PRIVS / ROLE_ROLE_PRIVS w 23.26 (w tym wydaniu część z nich pochodzi z RESOURCE).

## 17.6 Domeny SQL i adnotacje

```sql
CREATE DOMAIN lab_n15_email AS VARCHAR2(100)
    CONSTRAINT lab_n15_email_ck CHECK (REGEXP_LIKE(lab_n15_email, '^[^@]+@[^@]+$'))
    DISPLAY LOWER(lab_n15_email)
    ORDER   UPPER(lab_n15_email)
    ANNOTATIONS (Description 'Email address');
CREATE TABLE lab_n15_c (
    id    NUMBER ANNOTATIONS (Hidden),
    mail  DOMAIN lab_n15_email            -- albo: mail lab_n15_email, albo VARCHAR2(100) DOMAIN ...
) ANNOTATIONS (Owner 'HR', Display 'Contacts');
```

(wykonano)

| Działanie | Wynik (wykonano) |
|---|---|
| wstawienie 'bad' do mail | **ORA-11534** check constraint ... due to domain constraint ... violated |
| `DOMAIN_DISPLAY(mail)` dla 'Ann@Example.com' | 'ann@example.com' (zapisana wartość bez zmian) |
| `DOMAIN_NAME(mail)` / `DOMAIN_NAME(id)` | '<your schema>.LAB_N15_EMAIL' / NULL |
| `DOMAIN_ORDER(mail)` | 'ANN@EXAMPLE.COM' |
| `DROP DOMAIN`, gdy domena jest używana | **ORA-11502** |
| `DROP DOMAIN ... FORCE` | kolumna zachowuje typ i dane, DOMAIN_NAME staje się NULL |

- Słownik: USER_DOMAINS (DATA_DISPLAY, DATA_ORDER), USER_DOMAIN_CONSTRAINTS,
  USER_DOMAIN_COLS, USER_TAB_COLUMNS.DOMAIN_NAME.
- **USER_ANNOTATIONS_USAGE**: OBJECT_NAME, OBJECT_TYPE, COLUMN_NAME (NULL = poziom tabeli),
  DOMAIN_NAME, ANNOTATION_NAME (wielkimi literami), ANNOTATION_VALUE (NULL dla `Hidden`). Kolumny używające
  domeny pokazują adnotacje domeny. Zmienisz je przez
  `ALTER TABLE t ANNOTATIONS (ADD Version '2', DROP Owner)` albo `MODIFY (c ANNOTATIONS (...))`.
  Adnotacje to tylko metadane, nigdy nie są wymuszane.

## 17.7 VECTOR i wyszukiwanie podobieństwa

```sql
CREATE TABLE lab_n15_vec (id NUMBER, emb VECTOR(3, FLOAT32), any_v VECTOR, v2 VECTOR(*, INT8));
INSERT INTO lab_n15_vec (id, emb) VALUES (1, '[1,2,3]');          -- tekst jest konwertowany
SELECT VECTOR_DIMENSION_COUNT(TO_VECTOR('[1,2,3,4]'));           -- 4
SELECT VECTOR_DISTANCE(VECTOR('[1,0]'), VECTOR('[0,1]'), COSINE);  -- 1
SELECT VECTOR_DISTANCE(VECTOR('[0,0]'), VECTOR('[3,4]'), EUCLIDEAN);  -- 5
SELECT t.name
FROM   (VALUES ('a', VECTOR('[1,0]')), ('b', VECTOR('[0,1]')), ('c', VECTOR('[1,1]'))) t (name, v)
ORDER  BY VECTOR_DISTANCE(t.v, VECTOR('[1,0.2]'), EUCLIDEAN)
FETCH  FIRST 2 ROWS ONLY;                                           -- a, c
CREATE VECTOR INDEX lab_n15_vi ON lab_n15_vec (emb)
    ORGANIZATION NEIGHBOR PARTITIONS DISTANCE COSINE WITH TARGET ACCURACY 90;   -- indeks IVF
```

(wszystko wykonano)

| Metryka | [0,0] wobec [3,4] albo przykład | Uwagi |
|---|---|---|
| COSINE (domyślna) | [1,0] wobec [0,1] = 1 | 1 - podobieństwo kosinusowe; wektor zerowy daje NaN |
| EUCLIDEAN | 5 | L2_DISTANCE |
| EUCLIDEAN_SQUARED | 25 | |
| MANHATTAN | 7 | L1_DISTANCE |
| DOT | [1,2]·[3,4] → -11 | iloczyn skalarny ze zmienionym znakiem; INNER_PRODUCT daje 11 |
| HAMMING | liczba różniących się wymiarów | |

- Błędy (wykonano): zła liczba wymiarów → **ORA-51803**; wektory różnych rozmiarów w
  VECTOR_DISTANCE → ORA-51808; ORDER BY / = / GROUP BY na wektorze → **ORA-22848**; wartość 300 w INT8
  → ORA-51806.
- `FETCH APPROX FIRST n ROWS ONLY` pozwala na wyszukiwanie przybliżone przez indeks wektorowy (graf sąsiadów HNSW
  w pamięci albo partycje sąsiadów IVF); wyszukiwanie dokładne to zwykłe FETCH FIRST.

## 17.8 Nowe i rozszerzone funkcje

| Wyrażenie (wykonano w 23ai) | Wynik | 19c (wykonano) |
|---|---|---|
| `CONCAT('a', 'b', 'c', NULL, 'd')` | 'abcd' | ORA-00909 |
| `SUM(ev.duration)`, `AVG(ev.duration)` | +01 02:15:00, +00 08:45:00 | ORA-00932 |
| `SUM(ev.warranty)` (YEAR TO MONTH) | +01-06 | ORA-00932 |
| `CEIL(DATE '2024-03-15', 'MM')` / `FLOOR(..., 'MM')` | 2024-04-01 / 2024-03-01 | ORA-00909 |
| `TRUNC(INTERVAL '1 23:00:00' DAY TO SECOND)` | +01 00:00:00 | ORA-00932 |
| `CEIL(INTERVAL '1-7' YEAR TO MONTH)` | +02-00 | ORA-00932 |
| `BOOLEAN_AND_AGG(x)`, `BOOLEAN_OR_AGG(x)` dla TRUE, FALSE, NULL | FALSE, TRUE | - |
| `TIME_BUCKET(DATE '2024-03-15', INTERVAL '7' DAY, DATE '2024-01-01')` | 2024-03-11 | - |

`BOOL_AND` / `BOOL_OR` (nazwy z PostgreSQL) → ORA-00904. TIME_BUCKET, `GROUP BY ALL`, `QUALIFY`,
`COUNT(*) FILTER (WHERE ...)` i `UUID()` też zadziałały w 23.26, ale dodano je w aktualizacjach 23ai
po pierwszym wydaniu 23ai; pytania z nich nie korzystają.

## Częste pułapki

1. Założenie, że `GROUP BY 1` grupuje po pozycji: domyślnie wyłączone (ORA-03162).
2. Alias o tej samej nazwie co kolumna tabeli: GROUP BY używa kolumny.
3. Użycie aliasu z SELECT w WHERE: nadal ORA-00904.
4. Zapomniana lista kolumn po aliasie VALUES: `t (a, b)` jest wymagane.
5. `NOT (cond)` a `(cond) IS NOT TRUE`, gdy cond może być NULL.
6. Łączenie OR REPLACE z IF NOT EXISTS (ORA-11541); `DROP ... IF NOT EXISTS` (ORA-11544).
7. Oczekiwanie, że IF NOT EXISTS zaktualizuje definicję istniejącego obiektu.
8. UPDATE ... FROM z kilkoma dopasowaniami na wiersz docelowy (ORA-30926); brak złączenia z tabelą docelową.
9. Liczenie wierszy złączenia zamiast wierszy docelowych po DELETE ... FROM.
10. Przekonanie, że zwykłe DEFAULT ON NULL obejmuje też UPDATE (to FOR INSERT ONLY; ORA-01407).
11. Nadanie `SELECT ON SCHEMA` zamiast `SELECT ANY TABLE ON SCHEMA` (ORA-00990).
12. Oczekiwanie, że DISPLAY zmieni to, co zwraca zwykły SELECT; wpływa tylko na DOMAIN_DISPLAY.
13. Bezpośrednie sortowanie albo porównywanie wektorów (ORA-22848); sortuj po VECTOR_DISTANCE.
14. Oczekiwanie odległości COSINE równej 0 dla wektorów prostopadłych (wynosi 1; ten sam kierunek to 0).

## 19c a 23ai

| Funkcja | 19c | 23ai |
|---|---|---|
| `SELECT 1;` (bez FROM) | ORA-00923 | działa |
| alias w GROUP BY / HAVING | ORA-00904 | działa |
| GROUP BY po pozycji | ORA-00979 | ORA-03162, chyba że group_by_position_enabled = TRUE |
| `VALUES (...), (...)` w INSERT / FROM / MERGE | ORA-00933 / ORA-00903 / ORA-00928 | działa |
| kolumna BOOLEAN, literały TRUE/FALSE | ORA-00902 / ORA-00904 | działa |
| `IS TRUE`, TO_BOOLEAN | ORA-00933 / ORA-00904 | działa |
| `IF [NOT] EXISTS` | ORA-00933 / ORA-00922 | działa |
| UPDATE / DELETE ... FROM | ORA-00933 | działa |
| RETURNING OLD / NEW | - | działa |
| DEFAULT ON NULL | tylko FOR INSERT | dochodzi FOR INSERT AND UPDATE |
| Uprawnienia do schematu, DB_DEVELOPER_ROLE | - | nowe |
| Domeny, adnotacje | - | nowe |
| VECTOR, VECTOR_DISTANCE | - | nowe |
| CONCAT z 3+ argumentami | ORA-00909 | działa |
| SUM/AVG dla INTERVAL | ORA-00932 | działa |
| CEIL/FLOOR dla DATE, ROUND/TRUNC/CEIL/FLOOR dla INTERVAL | ORA-00909 / ORA-00932 | działa |

## Co 1Z0-171 dodaje do 1Z0-071

1Z0-171 (Oracle AI Database SQL Associate, 60 pytań, 120 minut, 65% do zdania) obejmuje
te same podstawy SQL co 1Z0-071 (działy 1-16), ale oczekuje zachowania 23ai, więc niektóre odpowiedzi
„błąd” z 19c stają się poprawnymi poleceniami (alias w GROUP BY, SELECT bez FROM). Dział 17 dodaje nową
składnię: konstruktor VALUES, BOOLEAN, IF [NOT] EXISTS, UPDATE/DELETE ze złączeniami, RETURNING
OLD/NEW, DEFAULT ON NULL FOR INSERT AND UPDATE, uprawnienia do schematu i DB_DEVELOPER_ROLE, domeny
SQL i adnotacje, wyszukiwanie podobieństwa VECTOR oraz rozszerzone funkcje powyżej.
