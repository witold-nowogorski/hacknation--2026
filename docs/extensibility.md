# Adding a new document type

A new type is added with configuration only: a folder `config/doc_types/<type>/` with two files. The code does not change. The only exception is a new kind of value (for example a new identifier format) – then you add one normaliser to `VALUE_TYPES` (`src/value_types.py`).

The example below is a contract notice (BZP/TED). It was tested: with this config the pipeline recognised all 8 notices in the data (4 in `negatywne/`, 4 inside cases) and filled their fields, and the result for none of the other 226 documents changed.

## 1. `schema.json` – the output shape

The JSON structure exactly as in the expected format. Leaves hold value type names. Lists are written as one-element arrays (`[{...}]` = a list of objects).

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

Value types: `text`, `person_name`, `email`, `nip`, `regon`, `krs`, `pesel`, `account`, `amount`, `date`, `ted`, `bzp`, `flag`, `reason_id`, `reason_description`, `party_type`. Each has a normaliser (e.g. `date`: "24 września 2026 r." → `2026-09-24`), and the typed ones also have a pattern for finding candidates in the text. Top-level keys must be different from other types – the evaluator uses them to tell which type a reference file is.

## 2. `doc_type.toml` – classification and field rules

```toml
[classification]
min_score = 4                                   # minimum total weight

[classification.keywords]                       # phrase -> weight (negative = evidence against)
"ogłoszenie o zamówieniu" = 3
"see the notice on ted" = 2
"sekcja i - zamawiający" = 2
"nabywca" = 1
"ogłoszenie nr" = 1

[fields."OgloszenieZamowienia.numer_bzp"]       # no rules: first candidate of this type in the text

[fields."OgloszenieZamowienia.numer_ted"]

[fields."OgloszenieZamowienia.nazwa_zamawiajacego"]
labels = ['nazwa zamawiajacego\s*:', 'oficjalna nazwa\s*:']
cut = ['\s+e-?mail', '\s+sektor']               # text after the label up to end of line or a cut

[fields."OgloszenieZamowienia.regon"]
labels = ['regon\b']
window = 40                                     # REGON at most 40 characters after the label

[fields."OgloszenieZamowienia.tytul"]
labels = ['tytul\s*:', '^\s*ogloszenie o zamowieniu (?:uslugi|dostawy|roboty budowlane)\s*$']
```

Tips for writing rules:
- Write regexes for labels, sections, cuts and classification in lowercase **without Polish characters** (`zamawiajacego`). Matching runs on a "folded" copy of the text, so it also works on OCR output that lost the accents.
- Labels are tried in list order – put the most specific ones first.
- A typed field (date, amount, account, NIP …) takes the first candidate of its type after the label. Two fields of the same type separate themselves (one field's label ends the other's search window), e.g. sender and recipient account.
- A field without labels takes the first candidate in the whole text (or section). Handy, but risky when the pattern also matches other numbers – then add `labels`.
- All options: `FieldRule` in `src/doc_types.py` (`sections`, `labels`, `pattern`, `cut`, `skip`, `window`, `multiple`, `exclude`, `classify`, `default`, `lookup`, `only_if`, `nth`); sections: `SectionRule`; LLM tasks: `LlmTaskRule` (see `config/doc_types/odwolanie/doc_type.toml`).

The config is checked at startup: field paths must exist in `schema.json`, sections and fields used by a rule must be defined, and regexes must compile. Any error stops the program and names the folder.

## 3. Data and measuring

1. Add examples: a PDF with a reference `<name>.json` next to it (e.g. in `dane/przyklad_NN/`).
2. In `src/run.py` set `MODE = "eval"` and run `python -m src.run`.
3. Check the report (`eval/reports/`, the log): classification (confusion matrix – does the new type "steal" other documents or negatives?), F1 of the new type's fields, "values in text" (the upper limit for extraction), and the weakest fields with error examples in `traces/runs/<run>/errors.jsonl`.
4. Where each value came from (which rule, page, snippet) is in `traces/runs/<run>/traces/` – the fastest way to see which rule to fix.
