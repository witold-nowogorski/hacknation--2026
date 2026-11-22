# Dodanie nowego typu dokumentu

Nowy typ dodaje się wyłącznie konfiguracją: folder `config/doc_types/<typ>/` z dwoma plikami. Kod się nie zmienia; jedyny wyjątek to nowy rodzaj wartości (np. nowy format identyfikatora) – wtedy jeden normalizator w `VALUE_TYPES` (`src/value_types.py`).

Przykład poniżej to ogłoszenie o zamówieniu (BZP/TED). Sprawdzony: z tą konfiguracją potok rozpoznał wszystkie 8 ogłoszeń w danych (4 w `negatywne/`, 4 w sprawach) i wypełnił pola, a wynik żadnego innego z 226 dokumentów się nie zmienił.

## 1. `schema.json` – kształt wyjścia

Struktura JSON-a 1:1 z oczekiwanym formatem; w liściach nazwy typów wartości, listy jako jednoelementowe tablice (`[{...}]` = lista obiektów).

```json
{
  "OgloszenieZamowienia": {
    "numer_bzp": "bzp",
    "numer_ted": "ted",
    "nazwa_zamawiajacego": "text",
    "regon": "regon",
    "tytul": "text"
  }
}
```

Typy wartości: `text`, `person_name`, `email`, `nip`, `regon`, `krs`, `pesel`, `account`, `amount`, `date`, `ted`, `bzp`, `flag`, `reason_id`, `reason_description`, `party_type`. Każdy ma normalizator (np. `date`: „24 września 2026 r.” → `2026-09-24`), a typowane mają wzorzec kandydatów w tekście. Klucze najwyższego poziomu muszą różnić się od innych typów – po nich ewaluacja rozpoznaje typ referencji.

## 2. `doc_type.toml` – klasyfikacja i reguły pól

```toml
[classification]
min_score = 4                                   # minimalna suma wag

[classification.keywords]                       # fraza -> waga (ujemna = dowód przeciw)
"ogłoszenie o zamówieniu" = 3
"see the notice on ted" = 2
"sekcja i - zamawiający" = 2
"nabywca" = 1
"ogłoszenie nr" = 1

[fields."OgloszenieZamowienia.numer_bzp"]       # bez reguł: pierwszy kandydat typu w tekście

[fields."OgloszenieZamowienia.numer_ted"]

[fields."OgloszenieZamowienia.nazwa_zamawiajacego"]
labels = ['nazwa zamawiajacego\s*:', 'oficjalna nazwa\s*:']
cut = ['\s+e-?mail', '\s+sektor']               # tekst po etykiecie do końca linii albo cięcia

[fields."OgloszenieZamowienia.regon"]
labels = ['regon\b']
window = 40                                     # REGON najwyżej 40 znaków za etykietą

[fields."OgloszenieZamowienia.tytul"]
labels = ['tytul\s*:', '^\s*ogloszenie o zamowieniu (?:uslugi|dostawy|roboty budowlane)\s*$']
```

Zasady pisania reguł:
- Regexy etykiet, sekcji, cięć i klasyfikacji pisz małymi literami **bez polskich znaków** (`zamawiajacego`) – dopasowanie idzie po tekście złożonym, więc działa też na OCR bez ogonków.
- Etykiety są próbowane w kolejności z listy – najpierw najbardziej konkretne.
- Pole typowane (data, kwota, rachunek, NIP …) bierze pierwszego kandydata swojego typu po etykiecie; dwa pola tego samego typu rozdzielają się same (etykieta jednego kończy okno drugiego), np. rachunek nadawcy i odbiorcy.
- Pole bez etykiet bierze pierwszego kandydata w całym tekście (lub sekcji) – wygodne, ale ryzykowne, gdy wzorzec typu pasuje też do innych liczb; wtedy dodaj `labels`.
- Pełna lista opcji: `FieldRule` w `src/doc_types.py` (`sections`, `labels`, `pattern`, `cut`, `skip`, `window`, `multiple`, `exclude`, `classify`, `default`, `lookup`, `only_if`, `nth`), sekcje: `SectionRule`, zadania LLM: `LlmTaskRule` (patrz `config/doc_types/odwolanie/doc_type.toml`).

Config jest walidowany przy starcie: ścieżki pól muszą istnieć w `schema.json`, sekcje i pola, do których reguła się odwołuje, muszą być zdefiniowane, regexy muszą się kompilować – błąd zatrzymuje program z nazwą folderu.

## 3. Dane i pomiar

1. Dodaj przykłady: PDF i referencję `<nazwa>.json` obok niego (np. w `dane/przyklad_NN/`).
2. W `src/run.py` ustaw `MODE = "eval"` i uruchom `python -m src.run`.
3. Sprawdź w raporcie (`eval/reports/`, log): klasyfikację (macierz pomyłek – czy nowy typ nie „podbiera” innych dokumentów i negatywów), F1 pól nowego typu, „wartości w tekście” (sufit ekstrakcji) i najsłabsze pola z przykładami błędów w `traces/runs/<przebieg>/errors.jsonl`.
4. Pochodzenie każdej wartości (która reguła, strona, fragment) jest w `traces/runs/<przebieg>/traces/` – stamtąd najszybciej widać, którą regułę poprawić.
