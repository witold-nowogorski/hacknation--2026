# Infrastructure

Runs on-premise on a CPU-only machine. The only outbound traffic at run time is the LLM API (EU).

## Components

| Component | Role | Licence |
|---|---|---|
| Python 3.13+ | runtime | PSF |
| `docling` | PDF → text, layout, tables, reading order | MIT |
| `rapidocr` + `onnxruntime` | local OCR for scanned pages (Polish) | Apache-2.0 / MIT |
| `pydantic` | config validation, output models, LLM answer validation | MIT |
| `openai` (SDK only) | client for the OpenAI-compatible LLM endpoint | Apache-2.0 |
| `fastapi`, `uvicorn`, `python-multipart` | HTTP API | MIT / BSD-3 / Apache-2.0 |
| `streamlit`, `httpx` | web UI | Apache-2.0 / BSD-3 |
| `json5`, `pandas` | reading organiser JSON with comments; reports | Apache-2.0 / BSD-3 |
| `pytest` | tests | MIT |
| **Bielik-11B-v3.0-Instruct** | LLM (open weights, 11B dense, Polish) | [TODO: confirm licence on the model card] |
| PSNC LLM API (`https://llm.hpc.psnc.pl/v1`) | hosts the model; Poznań, Poland (EU) | service |

Versions: lower-bounded in `requirements.txt`.

## Hardware

| Resource | Requirement | Measured |
|---|---|---|
| CPU | x86-64 or ARM64, no GPU | Apple M4, 4 conversion threads (`ConversionSettings.num_threads`) |
| RAM | 16 GB | peak ~4.8 GB |
| Disk | ~1 GB | Docling models in `models/`: 730 MB; plus `.venv`, `.cache/` |
| Time | 150 PDFs ≤ 45 min (challenge limit) | 0.4 s/digital PDF, 3.4 s/scan (avg); estimate 1–9 min for 150 PDFs |

## Network

| When | Destination | Purpose |
|---|---|---|
| first run only | model repositories used by `docling.utils.model_downloader` | download layout, TableFormer, RapidOCR models into `models/` |
| each new LLM request | `llm.hpc.psnc.pl:443` | Bielik-11B calls; cached in `.cache/llm/`, so repeated runs send nothing |
| local only | `localhost:8000` (API), `localhost:8501` (UI) | UI binds to localhost, usage stats off (`.streamlit/config.toml`) |

Offline: with `models/` present and no `LLM_API_KEY`, the system runs fully offline in rules-only mode (`rules-v1` quality).

## Environment variables

There is no `.env.example`; `src/run.py` loads `KEY=value` lines from `.env` (git-ignored). Real environment variables take precedence.

| Variable | Required | Default | Description |
|---|---|---|---|
| `LLM_API_KEY` | no | – | API key for the PSNC endpoint. Unset: LLM tasks are skipped with a warning; `MODE = "eval"` refuses to evaluate an LLM experiment |
| `DOCLING_ARTIFACTS_PATH` | no (set by the app) | `models/` | set by `use_local_models`; do not set manually |

All other settings are Python constants, not environment variables:

| Where | Setting |
|---|---|
| `src/run.py` | `MODE`, `INPUT_DIR`, `OUTPUT_DIR`, `RUN_EXPERIMENT`, `EVAL_EXPERIMENTS`, `EVAL_CASES`, `LOG_LEVEL`, LLM endpoints (`LlmSettings`) |
| `LlmSettings` (`src/inference/llm_client.py`) | `temperature=0.0`, `max_tokens=200`, `timeout_s=20`, `max_retries=1`, `max_consecutive_failures=3`, `api_key_env="LLM_API_KEY"` |
| `ConversionSettings` (`src/text_extraction/models.py`) | `max_pages=2`, `table_mode="accurate"`, `ocr_lang=("pl",)`, `num_threads=4`, `document_timeout_s=120` |
| `src/web_app.py` | `API_URL="http://localhost:8000"`, `TIMEOUT_S=600` |

## Generated folders (git-ignored)

| Folder | Contents | Safe to delete |
|---|---|---|
| `models/` | Docling models | yes (re-downloaded) |
| `.cache/docling/`, `.cache/llm/` | conversions, LLM answers keyed by hash of input + settings | yes (next run is cold) |
| `traces/` | provenance per document, eval run artifacts | yes |
| `output/` | scored JSON only | yes |
