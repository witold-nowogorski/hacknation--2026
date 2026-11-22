# CLAUDE.md

Instructions for AI coding agents (and humans) working in this repository.
Read this file fully before writing code. When a rule here conflicts with a habit, the rule wins.

## 1. Project in one paragraph

**Odwołania2json** (HackNation 2026, UZP challenge) converts KIO appeal cases (PDF) into JSON.
Input: PDFs anywhere under `<input>` (other files are skipped). Output: `<output>/<same relative path>/<same file name>.json`.
Each PDF is classified as one of the document types (`odwolanie`, `pelnomocnictwo`, `przelew`);
anything else produces an empty JSON (`{}`). Expected output formats live in
`dane/oczekiwane-json/`, training cases with reference JSONs in `dane/przyklad_NN/`
(treat organiser data as read-only).

Scoring that drives design decisions:
- **F1 on a hidden test set of real cases** – the main metric. Do not overfit to synthetic training data.
- **Smaller LLM = more points** – prefer deterministic rules; use the LLM only where judgement is needed.
- **New document types via configuration only** – no code changes to add a type.
- **Transparency** – it must be possible to explain where each extracted value came from.

Hard constraints: Python 3.13+, open-source components only, runs on a CPU-only laptop
(16 GB RAM), LLM via an API hosted in the EU/EEA, install with `pip install -r requirements.txt`.
The challenge expects `input/` and `output/` folders in the application root.

## 2. Running

```bash
pip install -r requirements.txt
python -m src.run                      # from the repo root; settings are constants in src/run.py
```

- Entry point is a Python module. **No shell/batch wrapper scripts.**
- **No argparse / CLI flags.** Runtime settings are plain constants at the top of `src/run.py`
  (`MODE`, `INPUT_DIR`, `OUTPUT_DIR`, `MODELS_DIR`). Domain configuration (document types,
  prompts, schemas) lives in `config/`, not in code.
- Docling models are stored in `models/` and downloaded automatically on first run
  (`src/text_extraction/docling_models.py`).

## 3. Folder structure

```
src/                      application package (imported as `src`)
  run.py                  entry point and runtime settings
  text_extraction/        PDF -> text/markdown (Docling), local model management
  <stage>/                one subpackage per pipeline stage (classification, extraction, ...)
config/doc_types/<type>/  everything specific to a document type: schema, prompt, hints, dictionaries
dane/                     data
  przyklad_NN/            training cases: PDFs + reference JSONs   (organiser, read-only)
  negatywne/              documents that must produce {}            (organiser, read-only)
  oczekiwane-json/        expected output formats                   (organiser, read-only)
  szablon-aplikacja/      organiser's sample input/output           (organiser, read-only)
input/  output/           application input and output (root, as the challenge expects); output holds ONLY scored JSON
eval/                     F1 evaluation and committed reports
tests/                    pytest tests, mirroring module names (test_<module>.py)
docs/                     architecture and "how to add a document type"
models/ .cache/ traces/   generated, git-ignored
```

Rules:
- **One subpackage per pipeline stage**, named after what it does (`text_extraction`,
  `classification`, `extraction`, `evaluation`). Inside, one module per responsibility.
  Don't create a subpackage for a single small function, and don't nest deeper than
  `src/<stage>/<module>.py` without a clear reason.
- **Names say what is inside.** No `utils.py`, `helpers.py`, `common.py`, `misc.py`.
  Shared code goes into a module named after its domain (`normalize.py`, `validators.py`).
- Data flows one way: `run → stages`. Stages do not import `run` or each other's internals;
  they communicate through typed data objects.
- Paths are derived from one place (settings in `run.py`) and passed down – modules do not
  compute repo-relative paths with `Path(__file__).parents[...]` on their own.
- Debug/provenance artifacts go to `traces/` or `.cache/`, never to the output folder.

## 4. Core principles

1. **Minimal and readable over clever.** Write the simplest code that is correct.
   A reader should understand a function without jumping to five other files.
2. **No duplicated logic.** Before writing something, search the codebase (`grep`) for an
   existing implementation. One place for each rule (e.g. NIP validation, date normalisation).
3. **Few, meaningful helpers.** Extract a function only when it is reused, or when it gives a
   name to a non-obvious block. Do not create one-line wrappers, pass-through functions or
   "manager"/"handler" classes that only forward calls.
4. **Configuration over code for domain knowledge.** Document-type specifics (fields, prompts,
   keywords, enum dictionaries) belong in `config/doc_types/`. Code must not contain
   `if doc_type == "odwolanie"` branches.
5. **YAGNI.** Implement what the current phase needs. No speculative abstractions, plugin
   systems, base classes with one subclass, or options nobody sets.
6. **Measure, don't guess.** Any change that can affect extraction quality is checked with
   the F1 evaluator before and after. Report the numbers.
7. **Deterministic first, LLM second.** Use regex/validation for structured values
   (NIP, REGON, KRS, PESEL, IBAN, amounts, dates); use the LLM for interpretation.

## 5. Python style

Target **Python 3.13**. Follow PEP 8 and the conventions below.

Typing
- Type-hint all function signatures and public attributes. Use modern syntax:
  `list[str]`, `dict[str, int]`, `X | None` – not `List`, `Optional`.
- Model structured data with `@dataclass(frozen=True, slots=True)` (internal) or Pydantic
  (validated external data: LLM output, config files). No loose `dict` passed across modules.
- Use `enum.StrEnum` / `Literal` for closed sets of values.

Idioms
- `pathlib.Path` for all paths – never `os.path` or string concatenation.
- f-strings for formatting; `logging` for diagnostics – never `print` in library code
  (`print` is acceptable only for final user-facing output in `run.py`).
- Comprehensions over `map`/`filter` with lambdas; but a plain loop beats a nested comprehension.
- `match` statements for multi-branch dispatch on values/shapes, not long `if/elif` chains.
- Context managers (`with`) for files and resources. Always pass `encoding="utf-8"`.
- `json.dumps(..., ensure_ascii=False, indent=2)` – output must keep Polish characters.
- Early returns over nested `if`s. Keep functions short (guideline: ≤ 30 lines) and flat.
- Module-level constants in `UPPER_CASE`; no mutable module-level state.
- Imports: stdlib, third-party, local – separated by blank lines. Local imports are absolute
  from the package root: `from src.text_extraction.docling_models import use_local_models`.
  No wildcard imports, no re-exports through `__init__.py` unless deliberate.
- Heavy imports (Docling, torch) inside the function that needs them only when it
  measurably improves startup; otherwise at the top of the module.

Naming
- Descriptive, unabbreviated names: `appeal_text`, not `at` or `txt2`.
- Functions are verbs (`extract_fields`), data objects are nouns (`ExtractedDocument`).
- Domain terms from the organiser's schema stay in Polish exactly as in the JSON
  (`czynnosc_powod_id`, `pelnomocnik`); code identifiers around them are English.

Comments and docstrings
- Code explains *what*; comments explain *why* (a business rule, an edge case in the data).
- Short docstring for every public function/class: one line, plus details only if non-obvious.
- Keep docstrings and module comments in sync with the code (run commands, paths).
- No commented-out code, no TODOs without context, no comments restating the code.

## 6. Reliability

- **Fail loudly on programmer errors, degrade gracefully on bad documents.** A single
  unreadable PDF must not stop the batch: log the error with the file name, write `{}`, continue.
- Catch specific exceptions only. Never `except Exception: pass`.
- Validate at the boundaries: config files on load, LLM responses against the schema
  (Pydantic), final JSON against the expected structure before writing.
- Missing values are `null`, never invented. Whether `null` or a best guess scores better
  for an uncertain field is decided by the evaluator, not by intuition.
- Deterministic output: same input → same JSON (temperature 0, sorted iteration where order matters).
- Cache expensive steps (Docling conversion, LLM calls) in `.cache/` keyed by file hash + settings,
  so evaluation runs are fast and reproducible.
- Never commit secrets. API keys come from environment variables / `.env` (git-ignored).

## 7. Testing and evaluation

- `pytest`, tests in `tests/`. Test pure logic (normalisers, validators, parsers, F1 metric)
  with small inline examples. Do not unit-test third-party libraries.
- Extraction quality is tested by the evaluator on `dane/`, not by brittle unit tests.
- Keep a held-out subset of training cases for honest checks; don't tune on it.
- Before finishing a task: `python -m src.run` starts, tests pass, and – if extraction
  changed – F1 is reported.

## 8. Dependencies

- Add a dependency only if it removes meaningful code or risk. Prefer the standard library.
- Every dependency must be open source and pinned with a lower bound in `requirements.txt`.
- One tool per job (Docling for PDF conversion – do not add a second PDF library
  without a stated reason).

## 9. Working agreement for agents

- Read the relevant modules before changing them; follow existing patterns.
- Keep changes focused on the task. No drive-by refactors or reformatting of unrelated code.
- Prefer editing existing files over creating new ones.
- Do not add files the task did not ask for (scripts, wrappers, example configs, READMEs).
- After a change, state what was verified and what was not.
- Do not modify organiser data in `dane/`. Do not write into the output folder except via the pipeline.
- Commit only when asked. Small commits with imperative messages ("Add NIP validator").
