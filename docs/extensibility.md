# Extensibility: new document types and fields without code

A document type is one folder, `config/doc_types/<type>/`, with two files. `load_doc_types` (`src/doc_types.py`) discovers every folder at startup; classifier, rules, LLM tasks, output model and evaluator pick it up with no code change.

| File | Defines |
|---|---|
| `schema.json` | output JSON shape; leaves name value types |
| `doc_type.toml` | classification keywords, text sections, field rules, optional LLM tasks |

Code changes only for a new **kind of value** (e.g. a new identifier format): one entry in `VALUE_TYPES` (`src/value_types.py`).

## Add a document type

Example: contract notice (BZP/TED). Tested: recognised all 8 notices in `dane/` (4 in `negatywne/`, 4 inside cases); results for the other 226 documents unchanged. Not committed, because the organiser expects `{}` for notices.

**1. Create `config/doc_types/ogloszenie/schema.json`** – shape exactly as the expected JSON; `[{...}]` = list of objects. Top-level keys must be unique across types (the evaluator identifies a reference's type by them).

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

Value types: `text`, `person_name`, `email`, `nip`, `regon`, `krs`, `pesel`, `account`, `amount`, `date`, `ted`, `bzp`, `flag`, `reason_id`, `reason_description`, `party_type`.

**2. Create `config/doc_types/ogloszenie/doc_type.toml`:**

```toml
[classification]
min_score = 4

[classification.keywords]                 # phrase -> weight; negative = evidence against
"ogłoszenie o zamówieniu" = 3
"sekcja i - zamawiający" = 2
"ogłoszenie nr" = 1

[fields."OgloszenieZamowienia.numer_bzp"]  # empty rule: first value of type `bzp` in the text
[fields."OgloszenieZamowienia.numer_ted"]

[fields."OgloszenieZamowienia.nazwa_zamawiajacego"]
labels = ['nazwa zamawiajacego\s*:', 'oficjalna nazwa\s*:']
cut = ['\s+e-?mail', '\s+sektor']

[fields."OgloszenieZamowienia.regon"]
labels = ['regon\b']
window = 40

[fields."OgloszenieZamowienia.tytul"]
labels = ['tytul\s*:']
```

**3. Run** `python -m src.run`. An invalid config stops at startup with the folder path and the reason (unknown field path, undefined section, regex that does not compile).

**4. Measure:** add PDFs with `<name>.json` references under `dane/`, set `MODE = "eval"` in `src/run.py`, run, check [evaluation](evaluation.md) output: confusion matrix (does the new type steal other documents?), per-field F1, `errors.jsonl`.

## Add a field to an existing type

1. Add the leaf to the type's `schema.json`, e.g. `"przelew_bankowy": {..., "waluta": "text"}`.
2. Optionally add `[fields."przelew_bankowy.waluta"]` to `doc_type.toml`. Without a rule the field is `null` in every output.

## Template (all options)

```toml
# config/doc_types/<type>/doc_type.toml
# Regexes (labels, sections, cut, skip, classify, when) are matched case-insensitively against
# text WITHOUT Polish diacritics: write 'odwolujac', not 'odwołując'. Keywords may keep diacritics.

[classification]
min_score = 3                             # minimum summed weight; ties -> {}
[classification.keywords]                 # searched in the first 2 pages
"<phrase>" = 2
[classification.head_keywords]            # searched only in the first 300 characters
"<phrase that means another type>" = -5

[sections.<name>]                         # a text span fields can be limited to
start = ['<regex>']                       # section starts after earliest match; empty = document start
end = ['<regex>']                         # ends at earliest match after start
max_chars = 1500

[fields."<Top>.<leaf>"]                   # path as in schema.json; lists: "Parties[].nip"
sections = ["<name>"]                     # tried in order; empty = whole text
labels = ['<regex>']                      # value follows a label; tried in order
pattern = '<regex with one group>'        # else: first candidate of the value type, else text to end of line
cut = ['<regex>']                         # end the free-text value early
skip = ['<regex>']                        # strip a neighbouring label at value start
window = 300                              # chars read after a label
nth = 0                                   # no label found: n-th candidate in the searched text
multiple = "no"                           # "segment" | "occurrences" for list fields
exclude = ["<earlier field>"]             # never repeat that field's value
only_if = { "<earlier field>" = "<value>" }
default = "<value>"
# alternatives to labels:
# classify = { <value> = ['<regex>'] }    # value whose regex matches earliest
# lookup = { source = "<earlier field>", table = { 1 = "<text>" } }

[[llm_tasks]]                             # optional; runs after rules, only with LLM_API_KEY set
name = "<task>"
kind = "extract"                          # or "nominative" (person_name fields only)
fields = ["<Top>.<leaf>"]
sections = ["<name>"]                     # context: first existing section, else document start
context_chars = 2000
mode = "fill"                             # "decide" = answer replaces the rule value
when = ['<regex>']                        # run only if it matches the context; empty = always
prompt = """<instruction in Polish>"""
```

Reference: `ClassificationRules`, `SectionRule`, `FieldRule`, `LlmTaskRule` in `src/doc_types.py`; working configs in `config/doc_types/{odwolanie,pelnomocnictwo,przelew}/`.
