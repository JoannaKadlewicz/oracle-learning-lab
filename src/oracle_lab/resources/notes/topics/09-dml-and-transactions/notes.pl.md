# Temat 9: Zarządzanie tabelami poleceniami DML (i transakcje)

Środowisko: Oracle Database 19c, schemat ORASTUDY. Wyniki niżej zostały wykonane: DML na
przykładowych tabelach w sesjach wycofanych, eksperymenty DDL na tymczasowych tabelach `LAB_`, które
potem usunięto. Uwagi o wyzwalaczach, high-water mark, blokadach i uprawnieniach opisują udokumentowane
zachowanie (ORASTUDY nie może tworzyć wyzwalaczy, a blokady wymagają dwóch sesji). Cele 10.1–10.5 i 12.5.

## 10.1 INSERT, UPDATE i DELETE

| Polecenie | Wynik |
|---|---|
| `INSERT INTO departments VALUES (50, 'Legal', NULL)` | 1 wiersz (bez listy kolumn: każda kolumna, w kolejności z tabeli) |
| `INSERT INTO departments VALUES (60, 'Legal')` | **ORA-00947**: not enough values |
| `INSERT INTO departments (department_name, department_id) VALUES ('Audit', 70)` | 1 wiersz (dowolna kolejność kolumn) |
| `INSERT INTO employees (employee_id, last_name, email) VALUES (200, 'Novak', 'ANOVAK')` | **ORA-01400** (hire_date jest NOT NULL, bez wartości domyślnej) |
| `UPDATE employees SET salary = 0 WHERE employee_id = 108` | **ORA-02290** check constraint violated |
| `UPDATE employees SET email = 'SKING' WHERE employee_id = 101` | **ORA-00001** unique constraint violated |
| `UPDATE employees SET department_id = 99 WHERE employee_id = 108` | **ORA-02291** parent key not found |
| `UPDATE employees SET salary = NULL WHERE employee_id = 108` | 1 wiersz: CHECK przepuszcza wynik UNKNOWN |
| `DELETE FROM customers WHERE customer_id = 1` | **ORA-02292** child record found |
| `DELETE FROM orders WHERE customer_id = 1` | 3 zamówienia i ich 3 pozycje przez ON DELETE CASCADE (zostaje 6 pozycji) |

- Pominięte kolumny dostają swoje `DEFAULT`, a bez niego NULL. `INSERT ... SELECT` nie ma słowa `VALUES`.
- `SET col = (podzapytanie)`: zero wierszy → NULL; więcej niż jeden wiersz → **ORA-01427**.
- Podzapytania widzą dane z początku polecenia (spójność odczytu na poziomie polecenia),
  więc skorelowany UPDATE nie widzi własnych wcześniejszych zmian wierszy.

```sql
UPDATE employees e
SET    e.salary = e.salary * 1.05
WHERE  e.salary < (SELECT AVG(i.salary) FROM employees i WHERE i.department_id = e.department_id);
-- 4 wiersze: 105, 106 (dział 20) i 104, 107 (dział 30). Grant (bez działu) nie jest zmieniany.
```

`DELETE FROM departments d WHERE d.department_id NOT IN (SELECT e.department_id FROM employees e)`
usuwa **0** wierszy: podzapytanie zawiera NULL, więc NOT IN nigdy nie jest TRUE.

## 10.2 Wstawianie do wielu tabel

| Postać | Działanie |
|---|---|
| `INSERT ALL INTO a ... INTO b ... SELECT` | bezwarunkowo: każde INTO dla każdego wiersza |
| `INSERT ALL WHEN c1 THEN INTO ... WHEN c2 THEN INTO ... [ELSE INTO ...]` | każde prawdziwe WHEN |
| `INSERT FIRST WHEN ... [ELSE ...]` | tylko pierwsze prawdziwe WHEN; zawsze warunkowe |

```sql
INSERT ALL
  INTO promotions (promo_id, promo_name, discount_pct) VALUES (department_id, department_name, 10)
  INTO promotions (promo_id, promo_name, discount_pct) VALUES (department_id + 100, department_name, 20)
SELECT department_id, department_name FROM departments;     -- 8 wierszy (4 x 2)
```

Z progami `salary >= 10000` / `salary >= 5000` / `ELSE` INSERT FIRST wstawił po 3 wiersze do każdego progu;
INSERT ALL wstawiłby trzech najlepiej zarabiających także do środkowego progu.
Ograniczenia: widok jako cel → ORA-01702; `NEXTVAL` w podzapytaniu → ORA-02287 (w VALUES
działało); `INSERT FIRST` bez WHEN → ORA-00905. Tabele zdalne też są niedozwolone (zgodnie z dokumentacją).

## 10.3 MERGE

```sql
MERGE INTO customers c
USING (SELECT 3 AS id, 'Initech' AS name, 4000 AS lim FROM dual
       UNION ALL SELECT 4, 'Umbrella', 1500 FROM dual
       UNION ALL SELECT 6, 'Stark', 2500 FROM dual) s
ON (c.customer_id = s.id)
WHEN MATCHED THEN UPDATE SET c.credit_limit = s.lim
                  DELETE WHERE c.credit_limit < 2000
WHEN NOT MATCHED THEN INSERT (customer_id, customer_name, credit_limit) VALUES (s.id, s.name, s.lim);
```

Wynik: 3 zmieniony na 4000, 4 zmieniony na 1500, a potem **usunięty** (DELETE WHERE sprawdza nową
wartość), 6 wstawiony. Klient 5 (limit 1000) jest nietknięty: nie ma go w źródle.

- Każda z klauzul WHEN jest opcjonalna; każda może mieć własne `WHERE`.
- Zmiana kolumny z klauzuli ON → **ORA-38104**.
- Wiersz docelowy dopasowany przez kilka wierszy źródła → **ORA-30926** (unable to get a stable set of rows).
  Najpierw zagreguj źródło.

## 10.4 Transakcje

- Transakcja zaczyna się od pierwszego polecenia DML i kończy na COMMIT, ROLLBACK albo dowolnym
  poleceniu DDL/DCL (niejawny COMMIT) albo z końcem sesji.
- DDL robi COMMIT **przed** wykonaniem, więc nawet nieudane `CREATE TABLE` (ORA-00955, zajęta nazwa)
  zatwierdziło w naszym teście czekający INSERT, podobnie jak `COMMENT ON TABLE`. DDL z błędem
  składni (ORA-00907) **nie** zrobił COMMIT. `ALTER SESSION`, `LOCK TABLE` i `SAVEPOINT` też nie.
- **Wycofanie na poziomie polecenia:** nieudane polecenie jest cofane w całości; wcześniejsza praca zostaje
  niezatwierdzona, a transakcja pozostaje otwarta.

```sql
UPDATE employees SET salary = salary + 1000 WHERE employee_id = 100;   -- OK, czeka na COMMIT
UPDATE employees SET salary = salary - 5000 WHERE department_id = 30;  -- ORA-02290 (107 miałby -200)
-- King: 25000; dział 30: 12000, 9000, 6000, 4800 (bez zmian)
```

- Czytający nigdy nie czekają i nigdy nie widzą niezatwierdzonych danych innych sesji; piszący blokują wiersze,
  a czeka tylko drugi piszący **ten sam wiersz**.

## 10.5 Sterowanie transakcjami

```sql
UPDATE departments SET location = 'A' WHERE department_id = 10;
SAVEPOINT sp;
UPDATE departments SET location = 'B' WHERE department_id = 20;
SAVEPOINT sp;                         -- ta sama nazwa: savepoint przesuwa się tutaj
UPDATE departments SET location = 'C' WHERE department_id = 30;
ROLLBACK TO sp;                       -- 10 = A, 20 = B, 30 = Warsaw
```

- `ROLLBACK TO s1` zachowuje s1 i transakcję, ale usuwa późniejsze savepointy:
  następne `ROLLBACK TO s2` zgłasza **ORA-01086**.
- `ROLLBACK` (bez TO) cofa wszystko i usuwa wszystkie savepointy. Nie ma częściowego COMMIT.

## 12.5 Obcinanie tabel (TRUNCATE)

| | DELETE | TRUNCATE |
|---|---|---|
| Rodzaj | DML | DDL (niejawny COMMIT) |
| WHERE | tak | nie |
| Wycofanie | tak, do COMMIT | nie |
| Wyzwalacze DML | uruchamiają się | nie uruchamiają się |
| Miejsce | high-water mark zostaje | high-water mark resetowany |

- Tabela nadrzędna, do której wierszy odwołują się wiersze podrzędne przez **włączony** klucz obcy:
  `TRUNCATE` → **ORA-02266**. (W naszej bazie 19c ten sam TRUNCATE udał się, gdy tabela
  podrzędna była pusta.)
- `TRUNCATE TABLE parent CASCADE` (12c+) obciął obie tabele, gdy FK był ON DELETE CASCADE;
  przy zwykłym FK i wierszach podrzędnych zakończył się błędem **ORA-14705**.
- Struktura, ograniczenia, indeksy i nadania zostają. Tabela innego użytkownika wymaga DROP ANY TABLE.

## Częste pułapki

1. `NOT IN` z NULL w podzapytaniu: DELETE/UPDATE dotyka 0 wierszy.
2. Oczekiwanie, że ograniczenie CHECK odrzuci NULL (nie odrzuca; dodaj NOT NULL).
3. Liczby wierszy INSERT FIRST a INSERT ALL, gdy warunki WHEN się nakładają.
4. Przekonanie, że `DELETE WHERE` w MERGE może usunąć wiersze, które nie zostały dopasowane i zmienione.
5. Zmiana kolumny użytej w klauzuli ON polecenia MERGE (ORA-38104).
6. Przekonanie, że nieudane polecenie wycofuje całą transakcję (wycofuje tylko polecenie).
7. Dowolne DDL w środku transakcji ją zatwierdza i usuwa wszystkie savepointy, więc późniejsze
   `ROLLBACK TO` kończy się błędem ORA-01086.
8. TRUNCATE tabeli nadrzędnej z wierszami podrzędnymi zawodzi (ORA-02266); DELETE zgłosiłby ORA-02292.

> **Oracle a standardowy SQL / inne bazy danych**
> - Oracle nie ma autocommit w bazie danych: klient (SQL Developer, SQL*Plus z
>   `SET AUTOCOMMIT ON`) może zatwierdzać za ciebie. psql z PostgreSQL i SQL Server domyślnie mają autocommit.
> - DDL jest transakcyjne w PostgreSQL (można je wycofać); w Oracle zawsze robi COMMIT.
> - `INSERT ALL` / `INSERT FIRST` to rozszerzenia Oracle. `MERGE` to SQL:2003; gałąź
>   `DELETE WHERE` wewnątrz WHEN MATCHED jest specyficzna dla Oracle.
> - Oracle traktuje `''` jak NULL: wstawienie `''` do department_name zgłosiło ORA-01400.
> - `TRUNCATE ... CASCADE` istnieje też w PostgreSQL, ale tam obcina tabele
>   odwołujące się niezależnie od reguł ON DELETE.

## Więcej sprawdzonych wyników (19c i 23ai)

- Warunkowe `INSERT ALL` z nakładającymi się klauzulami WHEN: 3 osoby zarabiające 10000+ i 4 osoby
  z prowizją dały **7** wierszy (pracownik 101 dwa razy); `INSERT FIRST` dałoby 6.
- WHEN i VALUES wstawiania do wielu tabel widzą tylko listę SELECT podzapytania:
  `VALUES (employee_id, last_name, 10)` bez wybranego `last_name` → **ORA-00904**.
- Wstawianie do wielu tabel, które trafi na ORA-00001 w jednym wierszu, nie zostawia **żadnych** wierszy (wycofanie na poziomie polecenia).
- MERGE `ON (1 = 0)` wstawia każdy wiersz źródła. NULL po obu stronach warunku ON to
  NOT MATCHED, więc działa gałąź INSERT (klient 5 → ORA-00001).
- MERGE `UPDATE SET ... WHERE s.lim > c.credit_limit DELETE WHERE c.credit_limit < 2500`: dopasowany
  wiersz pominięty przez WHERE w UPDATE nie jest usuwany, nawet jeśli spełnia warunek DELETE.
- `ROLLBACK TO a` dwa razy z rzędu działa; `ROLLBACK TO` savepointu z literówką → ORA-01086, nic nie jest cofane.
- Dwie sesje: `FOR UPDATE NOWAIT` na zablokowanym wierszu → **ORA-00054**; po tym, jak blokujący wykonał
  `ROLLBACK TO` savepointu sprzed swojego UPDATE, wiersz można było znowu zablokować;
  `FOR UPDATE OF e.salary` w złączeniu zostawił wiersz departments niezablokowany.
  `TRUNCATE` wykonany przez sesję B, gdy A ma niezatwierdzony DML w tabeli → ORA-00054 (DDL nie czeka).
- `TRUNCATE TABLE missing_table` (ORA-00942) i tak zatwierdził czekający INSERT.

## Różnice w Oracle 23ai (1Z0-171)

Sprawdzono na Oracle 23ai Free (23.26) z tym samym schematem; wszystko, czego tu nie wymieniono, działało jak w 19c
(reguły savepointów, wycofanie na poziomie polecenia, ORA-38104, ORA-30926, ORA-02292, liczby wierszy INSERT ALL / FIRST).

| 23ai | 19c |
|---|---|
| `INSERT INTO promotions VALUES (5, 'A', 10), (6, 'B', 15)` wstawia 2 wiersze (powtórzony klucz na liście → ORA-00001, nie zostaje żaden wiersz) | **ORA-00933** |
| `MERGE INTO promotions p USING (VALUES (1, 'A', 5), (2, 'B', 6)) s (id, n, d) ON ...` działa | niedostępne |
| `UPDATE employees e SET ... FROM departments d WHERE ...` (3 wiersze z Londynu), `DELETE FROM order_items oi FROM orders o WHERE ...` | użyj podzapytań |
| `CREATE TABLE IF NOT EXISTS` (tabela istnieje) i `DROP TABLE IF EXISTS` (tabeli brak) kończą się powodzeniem bez zmian **i nadal zatwierdzają** czekający INSERT | ORA-00922 / ORA-00933 |
| `FOR UPDATE WAIT 1` na zablokowanym wierszu → **ORA-00054** po upływie czasu | **ORA-30006** |
| `b NUMBER DEFAULT ON NULL FOR INSERT AND UPDATE 7`: `UPDATE ... SET b = NULL` zapisuje 7 | ORA-00936 przy CREATE |

- Komunikaty błędów są dłuższe: ORA-00001 wymienia tabelę i kolumny, ORA-30926 wymienia wiersz
  ("attempted to update the same row ... twice"), ORA-00054 wymienia rodzaj blokady.
- Niektóre błędy składni dostają nowe kody: drugie `VALUES` albo `DELETE ... ORDER BY` → **ORA-03048**
  (19c ORA-00933); `INSERT FIRST` bez WHEN → **ORA-02000** missing WHEN keyword (19c ORA-00905);
  `WHEN MATCHED THEN DELETE WHERE ...` bez UPDATE → ORA-02000 (19c ORA-00905).
- Wielowierszowe VALUES, `IF [NOT] EXISTS`, złączenia w UPDATE/DELETE i RETURNING OLD/NEW są omówione w temacie 15.
