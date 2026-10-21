# Temat 4: Funkcje konwersji i wyrażenia warunkowe

Środowisko: Oracle Database 19.3, schemat ORASTUDY, sesja angielska (AMERICAN) z
`NLS_DATE_FORMAT = 'YYYY-MM-DD HH24:MI:SS'`. Przykłady zostały **wykonane**, częściowo przez
`setup/run_sql.sh topics/04-conversion-and-conditional/examples.sql`, częściowo w aplikacji.
Nawiasy `[...]` w wyniku pokazują spacje na początku albo na końcu.

Oracle pilnuje typów, ale potrafi też konwertować po cichu, i to jest główne źródło
kłopotów: konwersje niejawne zależą od ustawień NLS sesji, a NULL przechodzi przez
prawie każde wyrażenie. Egzamin sprawdza jedno i drugie.

## 5.1 NVL, NULLIF, COALESCE (oraz NVL2, CASE, DECODE)

| Funkcja | Zwraca | Kluczowa reguła |
|---|---|---|
| `NVL(a, b)` | `b`, gdy `a` jest NULL | Dokładnie dwa argumenty; `b` jest konwertowane na typ `a` |
| `NVL2(a, x, y)` | `x`, gdy `a` NIE jest NULL, w przeciwnym razie `y` | Najpierw gałąź dla wartości różnej od NULL; wynik ma typ `x` |
| `COALESCE(a, b, ...)` | Pierwszą wartość różną od NULL | Dowolna liczba argumentów z tej samej rodziny typów (inaczej **ORA-00932**); kończy na pierwszym trafieniu |
| `NULLIF(a, b)` | NULL, gdy `a = b`, w przeciwnym razie `a` | `a` nie może być literałem NULL (**ORA-00932**) |
| `CASE` | Pierwszą pasującą gałąź | ANSI; prosty CASE używa `=`, więc `WHEN NULL` nigdy nie pasuje |
| `DECODE(e, s1, r1, ..., default)` | Tylko w Oracle | NULL = NULL to trafienie; brak wartości domyślnej → NULL |

Arytmetyka z NULL: każde działanie z NULL daje NULL.

```sql
e.salary * 12 * (1 + e.commission_pct)          -- NULL, gdy prowizja jest NULL
e.salary * 12 * (1 + NVL(e.commission_pct, 0))
```

| EMPLOYEE_ID | SALARY | COMMISSION_PCT | ANNUAL_RAW | ANNUAL_NVL | NULLIF(salary, 6000) |
|---|---|---|---|---|---|
| 100 | 24000 | NULL | NULL | 288000 | 24000 |
| 101 | 14000 | .3 | 218400 | 218400 | 14000 |
| 104 | 6000 | NULL | NULL | 72000 | NULL |
| 105 | 6000 | .2 | 86400 | 86400 | NULL |

`NULLIF` to typowa ochrona przed dzieleniem przez zero: `x / NULLIF(y, 0)`.

CASE a DECODE wobec NULL (pracownik 108 nie ma działu):

| Wyrażenie | Wynik dla 108 |
|---|---|
| `CASE e.department_id WHEN NULL THEN 'none' ELSE 'some' END` | `some` |
| `CASE WHEN e.department_id IS NULL THEN 'none' ELSE 'some' END` | `none` |
| `DECODE(e.department_id, NULL, 'none', 'some')` | `none` |

Więcej reguł, wszystkie wykonane:

- CASE z warunkami zwraca **pierwszą** prawdziwą gałąź: przy `WHEN salary > 5000 THEN 'MID' WHEN salary > 10000 THEN 'HIGH'`
  King (24000) dostaje `MID`.
- Wszystkie wyniki CASE muszą należeć do jednej rodziny typów: `CASE WHEN ... THEN 'none' ELSE e.commission_pct END` → **ORA-00932**.
- `DECODE(e.job_title, 'Programmer', 'IT', 'Sales Rep', 'Sales')` daje NULL dla 3 pracowników (brak wartości domyślnej).
- `NVL(e.commission_pct, 'none')` → **ORA-01722** (`'none'` → NUMBER). `NVL(TO_CHAR(e.commission_pct), 'none')` działa.
- `NVL2(e.commission_pct, e.commission_pct, 'none')` → **ORA-01722**; `COALESCE(e.commission_pct, '0')` → **ORA-00932**;
  `NVL(e.email, 0)` i `NVL(e.commission_pct, '0')` działają (drugi argument jest konwertowany).

## 5.2 Konwersja niejawna a jawna

| Wyrażenie | Wynik | Dlaczego |
|---|---|---|
| `'10' + 5` | `15` | `+` wymaga liczb: tekst jest konwertowany |
| `'10' \|\| 5` | `105` | `\|\|` wymaga tekstów: liczba jest konwertowana |
| `LENGTH(12345)` | `5` | LENGTH oczekuje tekstu |
| `WHERE e.employee_id = '101'` | działa | Tekst jest konwertowany na NUMBER |
| `WHERE e.email = 100` | **ORA-01722** | Na NUMBER konwertowana jest *kolumna*, a `SKING` zawodzi |
| `CASE WHEN '5' > '10' ...` | prawda | Dwa teksty porównuje się znak po znaku |
| `'Hired: ' \|\| e.hire_date` | `Hired: 2015-06-17 00:00:00` | DATE → tekst według NLS_DATE_FORMAT |
| `o.order_date > '31/03/2024'` | **ORA-01861** | Tekst → DATE według NLS_DATE_FORMAT, który oczekuje `YYYY-MM-DD ...` |

Ostatnie zapytanie może zadziałać w sesji z formatem `DD/MM/YYYY`, i właśnie dlatego warto unikać
konwersji niejawnej. Wybieraj literały `DATE 'YYYY-MM-DD'` albo `TO_DATE` / `TO_CHAR` / `TO_NUMBER`
z jawną maską.

## 5.3 TO_CHAR, TO_NUMBER i TO_DATE

Daty (`DATE '2024-03-05'`, wtorek; zamówienie 1006 = `2024-03-31 23:30`):

| Maska | Wynik |
|---|---|
| `'DD-MON-YYYY'` | `05-MAR-2024` |
| `'Day'` | `[Tuesday  ]` (dopełnione do 9, długości słowa Wednesday) |
| `'fmDD Month'` | `5 March` |
| `'Day, DDth Month YYYY'` | `Tuesday  , 05TH March     2024` (dopełnione) |
| `'fmDay, DDth Month YYYY'` | `Tuesday, 5TH March 2024` |
| `'fmMonth ddth, YYYY'` | `March 5th, 2024` |
| `'Ddspth'`, `'DDSPTH'`, `'Ddsp'` | `Fifth`, `FIFTH`, `Five` |
| zamówienie 1006 `'HH24:MI'`, `'HH24:MM'`, `'HH:MI AM'` | `23:30`, `23:03` (MM = miesiąc!), `11:30 PM` |

- Wielkość liter elementu decyduje o wielkości liter wyniku: `MON` → `MAR`, `Mon` → `Mar`; `DDth` → `05TH`, `ddth` → `05th`.
- `fm` usuwa dopełnienie i zera z przodu i działa jak przełącznik: drugie `fm` znowu je wyłącza.
- Dosłowny tekst piszesz w cudzysłowie: `'DD "of" Month'`.
- AM i PM w masce są wymienne: oba drukują faktyczną porę dnia.

Liczby:

| Wyrażenie | Wynik |
|---|---|
| `TO_CHAR(1234.5, '9,999.99')` | `[ 1,234.50]` (spacja z przodu zarezerwowana na znak) |
| `TO_CHAR(1234.5, 'fm9,999.99')` | `[1,234.5]` (fm usuwa też zera na końcu w pozycjach 9) |
| `TO_CHAR(1234.5, 'fm9,999.00')` | `[1,234.50]` |
| `TO_CHAR(1234.5, '999.99')` | `#######` (za mała maska: bez błędu, szerokość maski + 1 znaków #) |
| `TO_CHAR(0.5, '0.99')`, `TO_CHAR(0.5, '9.99')` | `[ 0.50]`, `[  .50]` |
| `TO_NUMBER('$1,234.50', '$9,999.99')` | `1234.5` (bez maski: **ORA-01722**) |

Teksty na daty:

| Wyrażenie | Wynik |
|---|---|
| `TO_DATE('31/03/2024', 'DD/MM/YYYY')` | działa w każdej sesji |
| `TO_DATE('2024/03/05', 'YYYY-MM-DD')`, `TO_DATE('2024-3-5', 'YYYY-MM-DD')` | działają: znaki rozdzielające i zera z przodu są elastyczne |
| `TO_DATE('2024-3-5', 'fxYYYY-MM-DD')` | **ORA-01862**: `fx` wymaga dokładnego dopasowania |
| `TO_DATE('2024-02-30', 'YYYY-MM-DD')` | **ORA-01839**: data nieprawidłowa dla miesiąca |
| `TO_DATE('15-03-75', 'DD-MM-RR')`, `'DD-MM-YY'` | 1975, 2075 (bieżący rok 2000-2049) |

RR: w latach 00-49 danego stulecia dwucyfrowe lata 50-99 trafiają do poprzedniego stulecia. YY zawsze używa
bieżącego stulecia.

## 5.4 Zagnieżdżanie wielu funkcji

Zagnieżdżone funkcje jednowierszowe są wyliczane od najbardziej wewnętrznej na zewnątrz i można je zagnieżdżać
dowolnie głęboko (funkcje grupujące: najwyżej dwa poziomy).

```sql
SELECT UPPER(SUBSTR(LPAD(e.last_name, 8, '*'), 1, 4))     -- ****King -> **** -> ****
FROM   employees e WHERE e.employee_id = 100;

SELECT NVL(TO_CHAR(e.manager_id), 'No manager')            -- wewnętrzne TO_CHAR wyrównuje typy
FROM   employees e;

SELECT TO_CHAR(NEXT_DAY(ADD_MONTHS(e.hire_date, 6), 'FRIDAY'),
               'fmDay, Month ddth, YYYY')                  -- Friday, December 18th, 2015 dla Kinga
FROM   employees e WHERE e.employee_id = 100;
```

`LENGTH(TRIM(LPAD('ab', 5)))` = 2: LPAD dopełnia spacjami, TRIM znów je usuwa.
`NVL(e.manager_id, 'No manager')` kończy się błędem (ORA-01722), a `TO_CHAR(NVL(...))` konwertuje za późno.

## Częste pułapki

1. Oczekiwanie, że `CASE x WHEN NULL` dopasuje NULL (nigdy tego nie robi; DECODE tak).
2. Mieszanie typów: `NVL`/`NVL2` konwertują na typ pierwszego (NVL2: drugiego) argumentu i mogą zgłosić
   ORA-01722; `COALESCE` i `CASE` zgłaszają zamiast tego ORA-00932.
3. Zapominanie o kolejności w `NVL2`: drugi argument jest dla wartości NOT NULL.
4. `DECODE` bez wartości domyślnej zwraca NULL dla niedopasowanych wartości.
5. CASE z warunkami zatrzymuje się na pierwszej prawdziwej gałęzi: ustawiaj warunki od najbardziej do najmniej wybiórczych.
6. Porównanie kolumny VARCHAR2 z liczbą konwertuje kolumnę (ORA-01722, bez użycia indeksu).
7. Poleganie na niejawnej konwersji tekstu na datę (zależy od NLS_DATE_FORMAT).
8. `MM` (miesiąc) a `MI` (minuty); `HH` to zegar 12-godzinny, `HH24` 24-godzinny.
9. Zapominanie o dopełnieniu `Day`/`Month` i o spacji na znak z przodu w maskach liczb.
10. `fm` z `9` po przecinku usuwa zera na końcu; dla stałej liczby miejsc po przecinku użyj `0`.
11. Założenie, że `TO_CHAR` ze zbyt małą maską zgłasza błąd; zwraca znaki `#`.
12. Używanie `BETWEEN` z granicami bez godziny na kolumnach `DATE` zawierających godziny.

> **Oracle a standardowy SQL / inne bazy danych**
>
> - Przenośne (ANSI): `CASE`, `COALESCE`, `NULLIF`, `CAST(x AS type)`.
> - Specyficzne dla Oracle: `NVL`, `NVL2`, `DECODE`, modele formatu `TO_CHAR`/`TO_DATE`/`TO_NUMBER`, `DUAL`.
>   SQL Server używa `ISNULL`, `CONVERT` i `FORMAT`; MySQL używa `IFNULL`, `DATE_FORMAT`, `STR_TO_DATE`;
>   PostgreSQL ma `TO_CHAR`/`TO_DATE` z podobnymi maskami, ale nie ma `NVL`.
> - Oracle traktuje pusty tekst `''` jak NULL (inaczej niż PostgreSQL i SQL Server), więc
>   `NVL('', 'x')` zwraca `x`.
> - Oracle po cichu konwertuje między tekstami a liczbami/datami w porównaniach; PostgreSQL jest bardziej rygorystyczny i
>   zgłasza błąd typu w wielu takich porównaniach.

## Różnice w Oracle 23ai (1Z0-171)

Wykonano na Oracle AI Database 23ai (23.26, schemat ORASTUDY) i porównano z 19c. NVL, NVL2,
NULLIF, COALESCE, CASE, DECODE, reguły konwersji niejawnej i modele formatu TO_CHAR/TO_DATE/TO_NUMBER
(fm, fx, RR/YY, L, G/D, PR, MI) dają te same wyniki i te same kody ORA-.

| Wyrażenie | 19c | 23ai |
|---|---|---|
| `NVL(e.commission_pct, 'none')` | ORA-01722: invalid number | ORA-01722: unable to convert string value containing 'n' to a number |
| `NULLIF(1, 'a')` | ORA-00932: inconsistent datatypes | ORA-00932: expression ('a') is of data type CHAR, which is incompatible with expected data type NUMBER |
| `TO_DATE(' 5-MAR-2024', 'fxDD-MON-YYYY')` | ORA-01858 | ORA-01858 (zmieniony komunikat) |
| `TO_CHAR(TRUE)`, `TO_NUMBER(TRUE)`, `TO_NUMBER(FALSE)` | ORA-00904 (brak BOOLEAN) | `TRUE`, `1`, `0` |
| `TO_BOOLEAN('yes')`, `TO_BOOLEAN(0)` | ORA-00904 | TRUE, FALSE |
| `'10' + TRUE` | ORA-00904 | `11` (BOOLEAN konwertuje się niejawnie na 1/0) |
| `CASE WHEN 1 = 1 THEN TRUE ELSE FALSE END`, `DECODE(TRUE, TRUE, 'y', 'n')` | ORA-00904 | TRUE, `y` |
| `WHERE e.salary > 5000 IS TRUE` | ORA-00933 | 6 wierszy |

- Te same kody, nowe sformułowania: odpowiedzi egzaminacyjne o ORA-01722, ORA-00932, ORA-01830, ORA-01843 i
  ORA-01858 pozostają aktualne; tylko treść komunikatu wymienia błędną wartość albo typ.
- BOOLEAN (TRUE/FALSE, TO_BOOLEAN, IS TRUE) to funkcja 23ai, omówiona w t15.
