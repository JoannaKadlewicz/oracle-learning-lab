# Ćwiczenia do tematu 4

Schemat: ORASTUDY (`setup/01_create_tables.sql`, `setup/02_seed_data.sql`).
Uruchamiaj przez `setup/run_sql.sh <file.sql>`. Nie zaglądaj do `solutions.sql`, dopóki nie spróbujesz ich rozwiązać
(plik powstanie po oddaniu rozwiązań).

## Ćwiczenie 1 (podstawowe): wyświetlanie odporne na NULL

**Cel:** NVL / NVL2 i reguły typów.

Dla każdego pracownika zwróć:
- `employee_id`
- `commission_display`: prowizję jako tekst procentowy, na przykład `30%`, albo `No commission`, gdy jest NULL
- `has_manager`: `Y`, gdy `manager_id` nie jest NULL, w przeciwnym razie `N`

Posortuj po `employee_id`. Oczekiwany wynik: 9 wierszy; pracownik 101 pokazuje `30%`, pracownik 100 pokazuje `No commission` i `N`.

## Ćwiczenie 2 (średnie): przedziały pensji i formatowanie

**Cel:** CASE, maski liczb w TO_CHAR i formatowanie dat.

Dla pracowników działów 20 i 30 zwróć:
- `last_name`
- `salary_fmt`: pensję sformatowaną jak `$14,000.00`, bez spacji z przodu
- `band`: `HIGH`, gdy pensja >= 10000, `MID`, gdy pensja >= 5000, w przeciwnym razie `LOW`
- `hired`: datę zatrudnienia sformatowaną jak `March 2019` (bez dopełnienia)

Posortuj po pensji malejąco, potem po `last_name` rosnąco. Oczekiwany wynik: 7 wierszy.

## Ćwiczenie 3 (zaawansowane): przewidź, potem wyjaśnij

Zanim je uruchomisz, przewidź wynik każdego zapytania i wyjaśnij dlaczego. Potem je uruchom.

```sql
-- a)
SELECT DECODE(NULL, NULL, 'match', 'no match') AS r FROM dual;

-- b)
SELECT CASE NULL WHEN NULL THEN 'match' ELSE 'no match' END AS r FROM dual;

-- c)
SELECT COUNT(*) AS cnt
FROM   orders o
WHERE  TRUNC(o.order_date) = DATE '2024-03-31';

-- d)
SELECT NVL2(NULLIF('A', 'A'), 'x', 'y') AS r FROM dual;

-- e)
SELECT COALESCE(NULL, 1, 'two') AS r FROM dual;
```
