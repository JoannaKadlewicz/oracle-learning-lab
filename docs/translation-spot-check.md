# Translation spot-check list

Every translation passes the automatic checks: `oracle-lab validate --static --lang pl --complete` and
`--lang en --complete` report 0 problems, and `tests/test_translation_coverage.py`,
`tests/test_i18n.py` and `tests/test_i18n_frontend.py` enforce that nothing is missing. Those checks
cover structure (option counts, SQL byte-identical outside comments, placeholders, every item and
field present), not meaning. These are the items most worth a human look, with why.

## Word choices that recur across the app

| # | Where | Source | Translation | Why look |
|---|---|---|---|---|
| 1 | Confidence buttons, calibration table, notes | Sure / Think so / Guessing | Pewne / Raczej tak / Zgaduję | Keys stay S, T, G in Polish. "Pewne" is neuter (agrees with "odpowiedź" only loosely); check it reads naturally on the buttons |
| 2 | Flashcard ratings | Again / Hard / Medium / Easy | Jeszcze raz / Trudne / Średnie / Łatwe | Taken from the plan; keys 1-4 unchanged |
| 3 | Sidebar section and the mock exam bar | Review | Przegląd | One catalog key serves both the "Review" nav section and the exam's "Review" button |
| 4 | Verdicts, meters, mock report | Correct / Wrong | Poprawnie / Błędnie | One key each for table labels and verdict titles |
| 5 | Role tags (Settings, Admin) | Learner | Uczący się | Grammatically generic masculine; "Osoba ucząca się" is neutral but long |
| 6 | Today and Progress | Ready to book the exam(?) | Czas zapisać się na egzamin(?) | Rephrased to avoid the gendered "Gotowy" |
| 7 | Guides list | Mistakes, Progress (guide titles) | Błędy, Postępy | Same words as two sidebar items; the guides are a log template and a progress table |
| 8 | Badges | Clean run, Lab master, Schema builder, Exam ready | Czysta seria, Mistrzostwo laboratorium, Budowanie schematów, Gotowość do egzaminu | Badge names are short and playful in English; the Polish ones are neutral |
| 9 | Topic names (`content/i18n/pl/_pack.json`) | Restricting and sorting, Joins, Data dictionary | Filtrowanie i sortowanie, Złączenia, Słownik danych | Shown on every page |
| 10 | Objectives 7.2-7.4 | Self-joins, Non-equijoins, OUTER joins | Złączenia zwrotne (self-join), nierównościowe (non-equijoin), zewnętrzne (OUTER) | English terms kept in brackets for the exam vocabulary |

## Content worth reading against the source

| # | Item | Why look |
|---|---|---|
| 11 | `q14-localtimestamp-same`, `q14-compare-tstz-literals` | Options `same`, `different`, `later`, `not later` stay English: they are the string literals the SQL returns |
| 12 | `q13-scenario-pass-on` | "Team lead LEAD ... her team" became "Liderka zespołu LEAD ... swojego zespołu" (feminine, as in the source) |
| 13 | `q12-uppercase` and the other t12 questions | Dictionary view and column names stay English inside Polish sentences |
| 14 | `q15-update-from-syntax` | All options are multi-line SQL and are copied unchanged |
| 15 | `q14-num-to-interval-valid`, `q14-eighteen-months` | Fractions written with a comma in prose ("19,2 miesiąca") but a period in SQL and results |
| 16 | `lab-n15-fix-is-not-true` | "treats unknown as 'not greater'" became „niewiększą”; check the wording of the hint |
| 17 | `lab-t12-fix-object-types` and other "Fix:" exercises | Titles start with "Napraw:" |
| 18 | t13 explanations quoting ORA messages | ORA texts stay English, as required |

## English flashcards (Polish source)

| # | Item | Why look |
|---|---|---|
| 19 | Samples such as `c001`, `c002` (`AS teraz`, `AS suma`, `AS tekst`) | Column aliases inside the SQL stay Polish: the rules forbid changing SQL outside comments |
| 20 | `c1111` | "ORDER BY w" (w is the column name) became "ORDER BY w for ..." |
| 21 | `c1059`, `c008` | Quoting and backslash examples; check the escapes read the same |
| 22 | `c1706` | Arrows (A→B→C) kept as in the source |
| 23 | `c1751`-`c1779` (topic 15) | Longest cards, most new 23ai terminology |

## Notes and guides

| # | File | Why look |
|---|---|---|
| 24 | `docs/exam-guide-2026.pl.md` | The source says "Switch tracks on the Overview page (Settings, Exam)"; the Polish names where the app really offers it (top of the menu, and Settings). Also UI names in the three-week plan use the Polish labels ("Jaki błąd?", "Przewidź wynik", "Napraw błąd") |
| 25 | `docs/cheat-sheet.pl.md` | The most-read page; check the NULL table and the function table |
| 26 | `topics/04-.../examples.pl.sql` | Only the four header comments are translated; `PROMPT` lines stay English by rule |
| 27 | `topics/02-.../notes.pl.md` | The SQL*Plus session block is unchanged English output |
| 28 | `topics/15-oracle-23ai/notes.pl.md` | "(executed)" became "(wykonano)" inside SQL comments |

## Interface strings with grammar to verify

| # | Key | Polish | Why look |
|---|---|---|---|
| 29 | `{n} open` (badge aria-label) | Otwarte: {n} | Avoids number agreement |
| 30 | `{database}, {questions} questions, {minutes} min` | {database}, pytania: {questions}, {minutes} min | Avoids "63 pytania / 60 pytań" agreement in a non-plural key |
| 31 | `Every {n} days` (flashcard status) | Co {n} dzień / dni | Intervals can be fractional (2.5) |
| 32 | `Estimated accuracy {pct}%, from {n} answers' worth of recent evidence` | ... (waga: {n}) | Evidence can be fractional; rephrased as a weight |
| 33 | `{n} study days in total` with n = 0 | 0 dni nauki łącznie | Zero takes the "many" form in Polish |
