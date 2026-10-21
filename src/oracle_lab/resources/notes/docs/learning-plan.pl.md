# Plan nauki: 1Z0-071 Oracle Database SQL

Cel: Oracle Database SQL Certified Associate (1Z0-071)
Środowisko ćwiczeń: Oracle Database 19c (19.3.0), kontener Docker `oracle19.3`, PDB `ORAPDB1`

> **Stan weryfikacji:** Obszary tematyczne niżej odpowiadają powszechnie publikowanej
> strukturze 1Z0-071 (przewodnik Oracle Press, firmy szkoleniowe). **Nie zostały jeszcze
> porównane** z oficjalną stroną tematów egzaminu:
> https://education.oracle.com/oracle-database-sql/pexam_1Z0-071
> Do zrobienia: otwórz oficjalną stronę, porównaj ją z tą listą i oznacz każdy wiersz jako sprawdzony.
>
> **Format egzaminu (częściowo sprawdzony, 17 października 2026):** strona egzaminu w Oracle MyLearn, tak jak zwraca ją
> wyszukiwarka (samej strony nie udało się pobrać), podaje 63 pytania zamknięte,
> 120 minut, próg zdania 63%. Źródła zewnętrzne podają zgodność z wersją do 19c.
> **Otwarte pytanie:** jedna z list na education.oracle.com oznacza 1Z0-071 dopiskiem "Retiring Exam".
> Przed zapisem sprawdź na oficjalnej stronie datę wycofania albo egzamin, który go zastępuje.
>
> Źródła: https://mylearn.oracle.com/ou/exam/oracle-database-sql-1z0-071/105037/110647/170369 ,
> https://education.oracle.com/pt_BR/oracle-database-sql-certified-associate/trackp_457

## Obszary tematyczne

Kolejność to proponowana kolejność nauki, a nie waga na egzaminie.

| # | Temat | Kluczowe kwestie specyficzne dla Oracle | Sprawdzone |
|---|---|---|---|
| 1 | Pojęcia relacyjne i podstawowy SELECT | `DUAL`, aliasy kolumn, `DISTINCT`, konkatenacja `\|\|`, q-quote `q'[...]'`, arytmetyka z NULL | Nie |
| 2 | Filtrowanie i sortowanie danych | `BETWEEN`, `IN`, `LIKE` z `ESCAPE`, `IS NULL`, kolejność operatorów, `NULLS FIRST/LAST`, `FETCH FIRST ... ROWS [WITH TIES]`, `OFFSET`, zmienne podstawienia `&` / `&&` | Nie |
| 3 | Funkcje jednowierszowe | Znakowe (`SUBSTR`, `INSTR`, `LPAD`, `TRIM`, `REPLACE`), liczbowe (`ROUND`, `TRUNC`, `MOD`), dat (`SYSDATE`, `ADD_MONTHS`, `MONTHS_BETWEEN`, `LAST_DAY`, `NEXT_DAY`, `ROUND/TRUNC` na datach), arytmetyka na datach | Nie |
| 4 | Funkcje konwersji i wyrażenia warunkowe | `TO_CHAR`, `TO_DATE`, `TO_NUMBER`, modele formatu, `fm`, konwersja niejawna i NLS, `NVL`, `NVL2`, `NULLIF`, `COALESCE`, `CASE`, `DECODE` | Nie |
| 5 | Agregacja | Funkcje grupujące i NULL, `COUNT(*)` a `COUNT(col)`, `GROUP BY`, `HAVING`, zagnieżdżanie funkcji grupujących (najwyżej 2 poziomy), `LISTAGG` | Nie |
| 6 | Złączenia | Złączenia ANSI, `USING`, `NATURAL JOIN`, `ON`, złączenie zwrotne, złączenie nierównościowe, złączenia zewnętrzne, `CROSS JOIN`, rozpoznawanie starej składni `(+)` | Nie |
| 7 | Podzapytania | Jednowierszowe a wielowierszowe, `ANY`/`ALL`, `IN` / `NOT IN` z NULL, podzapytania skorelowane, `EXISTS`, podzapytania skalarne, widoki inline, `WITH` | Nie |
| 8 | Operatory zbiorowe | `UNION`, `UNION ALL`, `INTERSECT`, `MINUS`, reguły dopasowania kolumn, miejsce `ORDER BY` | Nie |
| 9 | DML i transakcje | `INSERT`, `UPDATE`, `DELETE`, `MERGE`, wstawianie do wielu tabel `INSERT ALL/FIRST`, `COMMIT`, `ROLLBACK`, `SAVEPOINT`, niejawny COMMIT przy DDL, spójność odczytu, `SELECT ... FOR UPDATE` | Nie |
| 10 | DDL: tabele i ograniczenia | Typy danych (`VARCHAR2`, `NUMBER(p,s)`, `DATE`, `TIMESTAMP`, `CHAR`, `CLOB`), `CREATE TABLE AS SELECT`, `ALTER TABLE`, ograniczenia (PK, FK, `ON DELETE CASCADE/SET NULL`, UNIQUE, CHECK, NOT NULL), `DROP` / `TRUNCATE`, kosz i `FLASHBACK TABLE`, kolumny nieużywane | Nie |
| 11 | Inne obiekty schematu | Widoki (proste a złożone, `WITH CHECK OPTION`, `WITH READ ONLY`), sekwencje (`NEXTVAL`/`CURRVAL`, luki), synonimy, indeksy (w tym niewidoczne), tabele tymczasowe, tabele zewnętrzne | Nie |
| 12 | Słownik danych | Widoki `USER_` / `ALL_` / `DBA_`, `USER_TABLES`, `USER_CONSTRAINTS`, `USER_TAB_COLUMNS`, `DICTIONARY`, komentarze | Nie |
| 13 | Kontrola dostępu użytkowników | Uprawnienia systemowe a obiektowe, `GRANT` / `REVOKE`, `WITH GRANT OPTION` a `WITH ADMIN OPTION`, role, `PUBLIC` | Nie |
| 14 | Strefy czasowe i interwały | `TIMESTAMP WITH [LOCAL] TIME ZONE`, `CURRENT_TIMESTAMP` a `SYSTIMESTAMP`, `INTERVAL YEAR TO MONTH` / `DAY TO SECOND`, `EXTRACT`, `FROM_TZ` | Nie |

## Proponowana kolejność

1. **Tydzień 1:** tematy 1–4 (zapytania do jednej tabeli; duży nacisk na NULL i konwersje)
2. **Tydzień 2:** tematy 5–8 (agregacja, złączenia, podzapytania, operatory zbiorowe)
3. **Tydzień 3:** tematy 9–11 (DML, transakcje, DDL, obiekty schematu)
4. **Tydzień 4:** tematy 12–14, potem mieszane egzaminy próbne i powtórka z `docs/mistakes.md`

Dopasuj tempo do swojego planu; przy wcześniejszym doświadczeniu z SQL tematy 1, 2 i 6 pójdą zapewne szybko,
a główne ryzyko to zachowanie specyficzne dla Oracle (obsługa NULL, konwersja niejawna, automatyczny COMMIT przy DDL,
reguły ograniczeń i widoków).

## Sposób pracy z każdym tematem

Dla każdego tematu utwórz `topics/<nn-topic-name>/` z plikami `notes.md`, `examples.sql`,
`exercises.md` i `solutions.sql` (rozwiązania dopiero po próbie rozwiązania ćwiczeń).
Postępy zapisuj w `docs/progress.md` tylko na prośbę, z dowodami.
