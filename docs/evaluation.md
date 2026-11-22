# Evaluation

## Procedure

```bash
# in src/run.py: MODE = "eval"; optionally EVAL_EXPERIMENTS = ["rules-v1", "hybrid-v1"], EVAL_CASES = ["przyklad_01"]
python -m src.run
```

| Eval set (`EVAL_SETS`) | Files | Documents |
|---|---|---|
| `synthetic` | `dane/przyklad_*/*.pdf` (text layer; includes negatives inside cases) | 184 |
| `negatives` | `dane/negatywne/*.pdf` | 12 |
| `scans` | `dane/skany/*/*/*.pdf` (OCR path) | 30 |

- Reference = `<name>.json` next to the PDF; no reference → expected `{}`.
- Expected type is detected from the reference's top-level keys (as in `schema.json`), never from the file name.
- No train/holdout split: nothing is trained, and a holdout from the same synthetic generator says little about the real test set. Real-data risk is tracked via the `scans` set.

## F1 calculation (`src/evaluation/metrics.py`)

Both JSONs are flattened to scalar leaves (`Odwolujacy[].nip`). Per leaf:

| Expected | Predicted | Count |
|---|---|---|
| value | equal value | TP |
| value | different value | FP + FN |
| value | null / missing | FN |
| null / missing | value | FP |
| null | null | ignored |

List items are paired greedily by most matching leaves (order-independent). Wrong document type and values on negative documents need no special case: their leaves just don't match. Counts are summed over all leaves of all documents (micro-average): `F1 = 2TP / (2TP + FP + FN)`.

Also reported:
- **strict** (exact JSON equality) and **normalised** (case/whitespace-insensitive) F1; equal in the current results.
- **coverage** – share of reference values present in the extracted text: upper bound for extraction, checks conversion/OCR.
- classification confusion matrix, per-set / per-type / per-field scores, conversion time, LLM tokens.

Outputs:

| Path | Contents |
|---|---|
| `eval/reports/<run id>.json` (committed) | git commit, full `PipelineConfig`, snapshot of `config/doc_types/*`, all scores |
| `traces/runs/<run id>/` | `output/`, `traces/`, `documents.jsonl`, `errors.jsonl` (expected vs predicted per wrong leaf), `run.log` |

## Results

226 documents, strict. Reports: `eval/reports/20261122-084517_rules-v1.json`, `eval/reports/20261122-084518_hybrid-v1.json`.

| Metric | `rules-v1` | `hybrid-v1` |
|---|---|---|
| **F1** | 0.950 | **0.954** |
| Precision / Recall | 0.967 / 0.934 | 0.970 / 0.938 |
| TP / FP / FN | – | 2195 / 67 / 146 |
| Classification accuracy | 100% | 100% |
| Coverage (values in text) | 99.0% (2026/2046) | 99.0% |
| LLM per run (cold) | – | 70 calls, 39 854 prompt + 1 218 completion tokens, 22 s |

### By set

| Set | `rules-v1` | `hybrid-v1` | Avg / max conversion |
|---|---|---|---|
| synthetic | 0.969 | 0.973 | 0.42 s / 0.92 s |
| scans | 0.822 | 0.822 | 3.43 s / 7.09 s |
| negatives | 16/16 → `{}`, 0 invented values | same | 1.75 s / 5.38 s |

### By document type

| Type | Docs | `rules-v1` F1 | `hybrid-v1` F1 | P / R (`hybrid-v1`) |
|---|---|---|---|---|
| `odwolanie` | 70 | 0.959 | 0.965 | 0.979 / 0.951 |
| `pelnomocnictwo` | 70 | 0.921 | 0.921 | 0.947 / 0.897 |
| `przelew` | 70 | 0.958 | 0.958 | 0.973 / 0.944 |
| none (negatives) | 16 | correct | correct | – |

### Weakest fields (`hybrid-v1`, F1 < 0.93)

| Field | F1 | Cause |
|---|---|---|
| `Zamawiajacy[].prowadzacy_postepowanie` | 0.00 | set only with several contracting authorities (2 of 60 appeals) |
| `mocodawca[].podpisujacy[].imie_nazwisko` | 0.82 | consortia with several signatories, column layouts |
| `Odwolujacy[].nazwa` | 0.90 | second appellant in consortia |
| `Zamawiajacy[].nazwa` | 0.91 | name boundaries in headers |
| `mocodawca[].data.nazwa` | 0.92 | consortia |
| `OdwolanieKIO.czynnosc_powod_id`, `czynnosc_opis` | 0.92 | scans without the "Zamawiający w dniu …" sentence (rules alone: 0.86) |
| `mocodawca[].data.krs` | 0.93 | consortia |
| `przelew_bankowy.z_rachunku` | 0.93 | column order in 2 transfer layouts |
| `przelew_bankowy.tytul`, `ZamowieniePubliczne.tytul` | 0.93 | free-text boundaries, OCR character errors on scans |

All other 25 fields: 0.93–1.00. Full table: `scores.by_field` in the report.

### LLM comparison (same tasks, cold run, PSNC)

| Model | Size | F1 | `czynnosc_powod_id` F1 | Tokens / doc | LLM time | Invalid answers |
|---|---|---|---|---|---|---|
| **Bielik-11B-v3.0** | 11B dense | **0.954** | **0.921** | 182 | 22 s | 0 |
| Mistral-Small-3.2 | 24B dense | 0.952 | 0.892 | 139 | 25 s | 0 |
| Qwen3.8-27B | 27B dense | 0.952 | 0.892 | 255 | 256 s | 17 |
| gemma-4-26B-A4B | 26B MoE (4B active) | 0.949 | 0.835 | 133 | 10 s | 0 |

Hidden test set: [TODO: fill in after the organiser publishes results].
