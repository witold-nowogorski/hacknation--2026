# Architecture

Generic code in `src/`, all document-type knowledge in `config/doc_types/`. Rule: deterministic rules first, LLM only where judgement is needed.

## Data flow

```mermaid
sequenceDiagram
    participant R as src/run.py
    participant T as text_extraction
    participant C as classification
    participant X as extraction
    participant L as LLM API (PSNC, EU)
    R->>T: InputDocument (PDF path)
    T->>T: Docling, first 2 pages; RapidOCR on pages without text layer (cached in .cache/docling)
    T->>C: ExtractedDocument (text blocks + page numbers)
    C->>C: weighted keywords from doc_type.toml
    alt no type / tie / below min_score
        C-->>R: {} 
    else type
        C->>X: doc type
        X->>X: sections + field rules → candidates normalised by value type
        X->>L: llm_tasks: text snippet + JSON schema, temperature 0 (cached in .cache/llm)
        L-->>X: validated answer; value must occur in snippet
        X->>X: Pydantic model from schema.json → full JSON structure
        X-->>R: Extraction(data, sources)
    end
    R->>R: output/<path>.json + traces/production/<path>.json
```

A failing PDF (broken file, conversion timeout) raises `DocumentProcessingError`; `Pipeline.run` logs it with the file name, writes `{}` and continues.

## Modules

| Stage | Module | Responsibility |
|---|---|---|
| entry | `src/run.py` | settings (`MODE`, paths in `Workspace`), experiment list, `.env` loading |
| interfaces | `src/api.py`, `src/web_app.py` | FastAPI (`/documents`, `/experiments`, `/health`); Streamlit client of the API |
| pipeline | `src/pipeline/` | `Pipeline` (ABC; timing + error policy), `StagedPipeline`, `PipelineConfig`, output/trace writers |
| 1. text | `src/text_extraction/` | `DoclingTextExtractor`, `ConversionSettings`, local model management (`models/`) |
| 2. classify | `src/classification/` | `KeywordClassifier` |
| 3. extract | `src/extraction/` | `RuleExtractor` (rules), `LlmTasks` (LLM), `output_model.py` (Pydantic from schema), `provenance.py` |
| LLM | `src/inference/llm_client.py` | `LlmClient`: OpenAI-compatible API, JSON-schema answers, disk cache, token accounting |
| config | `src/doc_types.py`, `src/value_types.py` | load + validate `config/doc_types/*`; `VALUE_TYPES` (normalisers, candidate regexes) |
| quality | `src/evaluation/`, `src/experiments/` | F1, coverage, run artifacts, reports (see [evaluation.md](evaluation.md)) |

Dependencies point one way: `run → pipeline → stages`. Stages exchange typed objects (`ExtractedDocument`, `Classification`, `Extraction`) and do not import each other.

## Stages

**Text.** Docling converts only the first `max_pages = 2` (all reference values are there), TableFormer `accurate` (tables become `label | value` rows), RapidOCR (`pl`) only for pages without a text layer, 4 threads, 120 s timeout per document.

**Classification.** Per type: sum of weights of `keywords` found in the first 2 pages + `head_keywords` found in the first 300 characters. Matching ignores case, whitespace and Polish diacritics (OCR-robust). Best type wins if it reaches `min_score` and is not tied; otherwise `{}`.

**Rules** (`RuleExtractor`). Regexes run on a folded copy of the text (lowercase, no diacritics, same character positions); values are read from the original text. A field is read by `lookup`, `classify`, `labels` or from section start; the value is a `pattern` group, the first candidate of the field's value type, or free text to end of line. Full option list: `FieldRule` in `src/doc_types.py`.

**LLM tasks** (`LlmTasks`, configured as `[[llm_tasks]]`). Run after rules:
- `extract` – asks about a section snippet; `mode = "decide"` replaces the rule value, `"fill"` fills only nulls. Used for `czynnosc_powod_id` (code 1–12).
- `nominative` – rewrites person names to the nominative case; rejected if a word stem changes.

Answers are constrained by a JSON schema derived from the value types and validated with Pydantic; one retry, then the rule value stays. After 3 consecutive API failures the client stops calling for the rest of the run.

**Output model.** `build_output_model` creates a Pydantic model from `schema.json`. A recognised document always gets the full structure (missing values `null`, one item per list), matching the organiser's templates.

## Transparency (provenance)

Every non-null output value has a `ValueSource` (`src/extraction/provenance.py`): `path`, `value`, `source` (`rule` / `llm` / `derived` / `default`), `detail` (which label, pattern, class or LLM task), `page`, `snippet` (±50 chars).

- Batch mode: `traces/production/<case>/<file>.json`; eval runs: `traces/runs/<run id>/traces/`; API: `sources` field in the response; UI: table next to the JSON.
- LLM calls: each `.cache/llm/` entry stores the full request (model, prompt, schema), the answer, tokens and latency.
- Checked on 226 documents: every non-empty output value has a matching trace entry.

Real trace entry (`przyklad_01/przelew.pdf`):

```json
{"path": "przelew_bankowy.na_rachunek", "value": "68438223049992295262834736", "source": "rule",
 "detail": "label rachunek odbiorcy", "page": 1,
 "snippet": "zelewu Rachunek odbiorcy Aurelink Automatyka S.A. PL68438223049992295262834736 ul. Rybacka 79, ..."}
```

## Decisions (ADR)

| Decision | Why | Alternative rejected |
|---|---|---|
| Docling for PDF → text | layout, tables, reading order and OCR in one open-source (MIT) library, CPU-only | separate PDF + OCR libraries |
| RapidOCR (ONNX) | pip-installable, Polish, no system packages, no API (OCR via API would count as model size) | Tesseract (system install) |
| Convert only 2 pages | pages 3+ hold no reference values; appeal scans 12.6–13.7 s → 5.9–6.9 s | full document |
| Keyword classifier | 100% accuracy on 226 docs, zero tokens, explainable scores | LLM / embeddings classifier |
| Rules before LLM | identifiers, dates, amounts are format-bound; scoring rewards smaller LLMs | LLM-first extraction |
| Bielik-11B-v3.0 | best F1 among tested PSNC models and the smallest dense one (see [evaluation.md](evaluation.md)) | Mistral-24B, Gemma-26B-A4B, Qwen-27B |
| `openai` SDK, no framework | OpenAI-compatible endpoint is all we need; fewer dependencies | LangChain |
| TOML + JSON config, Pydantic validation | `tomllib` is stdlib; errors fail at startup with the folder path | YAML (extra dependency) |
| Output model generated from `schema.json` | new type needs no Python class | hand-written models per type |
| Disk cache keyed by hash + settings | reproducible, fast evaluation runs; deterministic output | no cache |
