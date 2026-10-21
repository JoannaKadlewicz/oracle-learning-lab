# Przewodnik po egzaminach 2026: 1Z0-071 czy 1Z0-171

Sprawdzono 18 października 2026. Własnych stron egzaminów Oracle nie udało się wczytać, więc fakty niżej pochodzą
z przewodników zewnętrznych; potwierdź je na Oracle MyLearn, zanim się zapiszesz.

| | 1Z0-071 Oracle Database SQL | 1Z0-171 Oracle AI Database SQL Associate |
|---|---|---|
| Wersja bazy danych | 19c | 23ai (sprzedawana jako "Oracle AI Database") |
| Pytania | 63 pytania zamknięte | 60 pytań zamkniętych |
| Czas | 120 minut | 120 minut |
| Próg zdania | 63% (40 z 63) | 65% (39 z 60) |
| Pytania wielokrotnego wyboru | wiele „wybierz dwie/trzy” | wiele „wybierz dwie/trzy” |
| Zakres | 16 działów, bez opublikowanych wag | te same obszary SQL plus funkcje 23ai |
| W tej aplikacji | ścieżka 1Z0-071, tematy 1-14 | ścieżka 1Z0-171, tematy 1-15 |

Ścieżkę zmienisz na górze menu (oraz w Ustawieniach). Postępy są zapisywane dla obu, a każda ścieżka ma
własne egzaminy próbne.

**Który wybrać?** Jeśli w pracy albo u pracodawcy działa 19c albo kurs, z którego korzystasz, jest przygotowany pod 1Z0-071, wybierz
1Z0-071. Jeśli zaczynasz od zera w 2026, 1Z0-171 to nowszy egzamin i sprawdza wersję, którą Oracle
dostarcza dziś. Około 95% materiału jest takie samo, więc przygotowanie do jednego przygotowuje do drugiego;
do 1Z0-171 naucz się tematu 15 i części „Różnice w Oracle 23ai” w notatkach każdego tematu.

Przewodniki zewnętrzne różnią się co do wag działów 1Z0-171. Funkcje (jednowierszowe, konwersji,
agregujące) mają największy udział (około 25%) w każdym źródle, a następne są pobieranie i filtrowanie danych
oraz DDL. Rozplanuj czas odpowiednio.

## Co się zmienia między 19c a 23ai (wszystko sprawdzone w obu bazach)

| Polecenie | 19c (1Z0-071) | 23ai (1Z0-171) |
|---|---|---|
| `SELECT 1 x` (bez FROM) | ORA-00923 | zwraca 1 |
| `GROUP BY` / `HAVING` z aliasem kolumny | ORA-00904 | działa |
| `GROUP BY 1` (pozycja) | ORA-00979 | ORA-03162, chyba że `group_by_position_enabled` ma wartość TRUE |
| `CONCAT('a','b','c')` | ORA-00909 | `abc` |
| `SUM` / `AVG` wartości INTERVAL | ORA-00932 | interwał |
| `FROM (VALUES (1,'a'),(2,'b')) v(n,s)` | ORA-00903 | 2 wiersze |
| `TRUE`, `FALSE`, `AND`/`NOT` na liście SELECT, kolumny BOOLEAN | ORA-00923 / ORA-00902 | wartości BOOLEAN |
| `CREATE TABLE IF NOT EXISTS`, `DROP TABLE IF EXISTS` | błąd składni | bez błędu, gdy obiekt istnieje / go nie ma |
| Typ danych `VECTOR`, `VECTOR_DISTANCE` | ORA-00904 | dostępne |
| Wiele błędów składni (`AS` przed aliasem tabeli, ORDER BY w gałęzi UNION, ON po CROSS JOIN) | ORA-00933 | ORA-03048 "SQL reserved word ... is not syntactically valid" |
| `JOIN` bez `ON` / `USING` | ORA-00905 | ORA-02000 missing ON or USING keyword |

Na egzaminie odpowiedź w rodzaju „zgłasza błąd” zależy od wersji, którą sprawdza egzamin: myśl kategoriami
19c przy 1Z0-071 i 23ai przy 1Z0-171. Aplikacja pokazuje pytania, których odpowiedź się zmieniła, tylko na
1Z0-071.

## W dniu egzaminu

1. **Przeznacz 1 minutę 50 sekund na pytanie.** Przy pytaniu 30 powinno ci zostać około 63 minut.
   Oznaczaj długie pytania i wracaj do nich; pytanie bez odpowiedzi daje zero punktów, więc nigdy nie zostawiaj pustego.
2. **Czytaj „wybierz dwie” dwa razy.** Policz zaznaczone odpowiedzi, zanim przejdziesz dalej. Nie ma punktów częściowych.
3. **Wykonuj zapytanie w głowie, klauzula po klauzuli:** FROM i złączenia, WHERE, GROUP BY, HAVING, SELECT,
   DISTINCT, ORDER BY, potem OFFSET/FETCH. Większość pułapek typu „co to zwraca” to alias użyty za
   wcześnie albo filtr zastosowany na złym etapie.
4. **Szukaj NULL.** Każde NOT IN, złączenie zewnętrzne z filtrem w WHERE, arytmetyka, agregat albo
   porównanie z kolumną dopuszczającą NULL jest podejrzane.
5. **Najpierw szukaj błędu.** Zanim policzysz wynik, sprawdź, czy polecenie się wykona:
   niegrupowana kolumna, brak FROM (19c), podzapytanie jednowierszowe zwracające kilka wierszy,
   niedopasowane kolumny operatora zbiorowego, alias w WHERE.
6. **Odrzucaj opcje absolutne.** Opcje z „zawsze”, „nigdy”, „tylko” częściej są błędne niż
   poprawne; Oracle ma wyjątek prawie od wszystkiego.

## Trzytygodniowy plan z tą aplikacją

| Tydzień | Codziennie (45-60 min) | Na koniec tygodnia |
|---|---|---|
| 1 | Plan na ekranie Dziś; jedna talia fiszek z tematu; jedno ćwiczenie; przeczytanie notatek do jednego tematu | Zestaw na czas: 20 pytań z tematów 1-7 |
| 2 | Plan na ekranie Dziś; filtry quizu „Jaki błąd?” i „Przewidź wynik” przez 15 minut; dwa ćwiczenia „Napraw błąd” | Pierwszy pełny egzamin próbny; przejrzyj każdą błędną i zgadniętą odpowiedź |
| 3 | Najpierw lista błędów; fiszki z najsłabszych tematów; temat 15 do 1Z0-171 | Dwa kolejne pełne egzaminy próbne w odstępie co najmniej 3 dni, z celem 80% na nowych pytaniach |

Zapisz się na egzamin, gdy lista „Czas zapisać się na egzamin?” na ekranie Postępy będzie pełna: każdy cel
na zielono, trzy rzetelne egzaminy próbne z wynikiem 80%+ i co najmniej 90% trafności przy „Pewne”.

Źródła: https://www.aguidetocloud.com/cert-tracker/oracle-ai-database-sql/ ,
https://www.certificationbox.com/2026/07/21/oracle-1z0-171-ai-database-sql-associate-study-guide/ ,
https://www.examcert.app/blog/oracle-1z0-071-syllabus-2026/
