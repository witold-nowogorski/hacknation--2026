# Odwołania2json

**From documents to data. Intelligent transformation of KIO appeals into a JSON model**

# Running the project

Requirements: Python 3.13+, no GPU. The `czynnosc_powod_id` field (reason for the appeal) and names in the nominative case are decided by the **Bielik-11B** model through the PSNC API (servers in Poland), which needs a key in the `.env` file. Without a key you can run the variant without an LLM (`rules-v1`, see below).

## Installation

```bash
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
echo "LLM_API_KEY=<key>" > .env    # LLM API key
```

On the first run, the Docling models (page layout, tables, OCR – about 0.7 GB) are downloaded into the `models/` folder; later runs work without downloading.

## 1. Processing a folder of documents (locally, without a server)

Put the PDFs in the `input/` folder – in any layout: directly in it, in case folders, or nested deeper – and run:

```bash
python -m src.run
```

```
input/                           output/
├── loose.pdf              ──►   ├── loose.json
├── case1/                       ├── case1/
│   ├── odwolanie.pdf            │   ├── odwolanie.json
│   └── przelew.PDF              │   └── przelew.json
└── archive/2026/                └── archive/2026/
    └── pelnomocnictwo.pdf           └── pelnomocnictwo.json
```

- Every PDF (`.pdf` in any letter case) gets a JSON with the same name, at the same relative path in `output/`. A document that is not an appeal, a power of attorney or a bank transfer confirmation gets `{}`.
- Other files are skipped (the log says how many); hidden files such as `.DS_Store` are ignored.
- The source of every value (rule or LLM task, page, text snippet) is written separately to `traces/production/`, in the same tree.
- A different input or output folder: change two constants at the top of `src/run.py`:

  ```python
  INPUT_DIR = Path("/path/to/pdfs")
  OUTPUT_DIR = Path("/path/to/results")
  ```

- Without an LLM (no API key): set `RUN_EXPERIMENT = "rules-v1"` in `src/run.py`.

## 2. API server (Swagger)

```bash
python -m uvicorn src.api:app --port 8000
```

Documentation and endpoint testing in the browser: **http://localhost:8000/docs** (Swagger UI; also `/redoc` and the `/openapi.json` schema).

| Endpoint | What it does |
|---|---|
| `GET /health` | whether the server is running |
| `GET /experiments` | available processing variants (default `hybrid-v1`, without an LLM `rules-v1`) |
| `POST /documents?experiment=hybrid-v1` | one or more PDFs → for each: document type, output JSON, source of every value |

```bash
curl -F "files=@input/case1/odwolanie.pdf" -F "files=@input/case1/przelew.pdf" \
     "http://localhost:8000/documents?experiment=hybrid-v1"
```

Uploaded files are processed in a temporary folder – nothing is written to `output/`.

## 3. Web interface (optional)

With the API server running, in a second terminal:

```bash
python -m streamlit run src/web_app.py
```

**http://localhost:8501** – drop in PDFs, choose a variant, click "Przetwórz" (Process); view the JSON and the source of every value, download single files or everything as a ZIP.

More: architecture and quality results – [docs/architecture.md](docs/architecture.md), adding a new document type with configuration only – [docs/nowy_typ_dokumentu.md](docs/nowy_typ_dokumentu.md) (both in Polish).

# Short description of the challenge

Every year, thousands of documents containing key information about procurement procedures, contractors, attorneys and actions of contracting authorities enter the public procurement system. Most often these are text documents whose key information is laid out in many different ways, usually on the first three pages. The goal of the challenge is to build a solution that automatically turns a multi-document administrative case into a consistent, structured JSON data model ready for further use by public administration IT systems.

# 1. Introduction

The Public Procurement Office (Urząd Zamówień Publicznych) is responsible for the functioning of the public procurement system in Poland and supports market participants in applying the law correctly. One element of this system is appeal proceedings before the National Appeal Chamber (Krajowa Izba Odwoławcza, KIO).

An appeal case is not a single document. It is a set of many related documents containing information about contractors, contracting authorities, attorneys, procedures, payments, procedural actions and other elements that require further processing.

Today, most of these documents are PDF files with varied structure. Some are created electronically, others are scans of paper documents. The information needed to handle a case is spread across many documents and is often written in different ways.

For a person, understanding such documentation is relatively easy. For IT systems, however, it is a big challenge. To automate further processes, the data must first be transformed into a structured form.

In practice, this means moving from the model:

**many PDF documents → content analysis → information identification → JSON data model**

The challenge is therefore about building a solution that automatically transforms multi-document administrative cases into a canonical data model that public administration systems can use further.

The most interesting solutions may become the basis for pilot deployments carried out by the Public Procurement Office.

# 2. The challenge

Design and implement a solution that:

1.  takes a PDF document that is part of an appeal: the document with the content of the appeal, a power of attorney, a bank transfer confirmation
2.  recognises the type of the document
3.  extracts the business information relevant to that document type,
4.  generates a JSON for each document that conforms to https://github.com/Urzad-Zamowien-Publicznych/hacknation-2026/blob/main/oczekiwane-json

Detailed data structure:
https://github.com/Urzad-Zamowien-Publicznych/hacknation-2026/blob/main/oczekiwane-json/odwolanie.json

training sets:
https://github.com/Urzad-Zamowien-Publicznych/hacknation-2026/blob/main/dane

# 3. Expected result

The expected result is a working application that loads a PDF file and returns JSON files in the agreed format and structure.

The solution should include:

### Document processing module

Responsible for:

- analysing documents,

- classifying documents based on their content (note! the file name may vary – do not rely on the file name),

- extracting information,

- building the data model.

### Execution interface

An interface that allows running the application through a CLI, a wrapper script (e.g. a ```start.bat``` file) or another similar solution.

Adding a GUI to the application will earn extra points, but is not required. The effectiveness of identifying information is more important.

### Input/output folders

Folders named ```input``` and ```output```, located in the root folder of the application. The ```input``` folder will be used to pass the analysed files to the application, while the ```output``` folder will contain the resulting JSON files.

### Output

JSON files in the ```./output``` folder, arranged in a tree structure, where each resulting **JSON is named the same as the file in the input folder it corresponds to**:

```
│output
├── case1
│   ├── odwolanie_nr_1.json
│   ├── pelnomocnictwo_nr_1.json
│   ├── pelnomocnictwo_nr_2.json
│   └── przelew_nr_1.json
├── case2
│   ├── odwolanie_nr_2.json
│   ├── pelnomocnictwo_nr_3.json
│   └── przelew_nr_2.json
├── case3
...
```
```
│input
├── case1
│   ├── odwolanie_nr_1.pdf
│   ├── pelnomocnictwo_nr_1.pdf
│   ├── pelnomocnictwo_nr_2.pdf
│   └── przelew_nr_1.pdf
├── case2
│   ├── odwolanie_nr_2.pdf
│   ├── pelnomocnictwo_nr_3.pdf
│   └── przelew_nr_2.pdf
├── case3
...
```

# 4. Formal requirements

The project submitted for evaluation should include:

- the project title,

- a GitHub link to a working prototype that allows uploading documents and reading the results of information extraction.

Additionally, participants may provide:

- the project repository,

- technical documentation, including a description of the LLM used,

- the results of their own quality tests.

# 5. Technical requirements

The solution must:

- be developed in **Python 3.13+**

- include a ```requirements.txt``` file that allows quick installation of the remaining project dependencies (e.g. with ```pip install```)

- use only open-source components (including open-source language models),

- be able to run in a local (on-premise) environment without a GPU (LLM through an API).

Solutions that are especially rewarded:

- allow configuring new document classes without modifying the source code (only through configuration files),

- support transparency of the data extraction process.

# 6. Testing and validation

The evaluation will be carried out on two datasets:

### Training set

Provided to participants during the challenge, available in the dane directory. The dataset also contains categories of documents that should NOT be identified (they should return an empty `.json` file).

Negative data (documents that should not be classified) is placed in selected examples and in the https://github.com/Urzad-Zamowien-Publicznych/hacknation-2026/tree/main/dane/negatywne directory.

### Test set

Not shared with participants.

The test set will contain complete administrative cases prepared by the organiser.

The results generated by the solution will be compared with a reference dataset prepared by subject-matter experts.

The main quality measure will be the [F1 score](https://en.wikipedia.org/wiki/F-score).

## Parameters of the machine the solutions will be tested on
About 30 teams are interested. We have to change the planned evaluation method. Stay tuned.

If the delivered solution uses an LLM, it should use an API and be delivered with an API key. We promise not to use it for any purpose other than the testing process. The API must be provided by a company whose Privacy Policy states the scope and location of data processing, and from servers located in the EU/EEA.

# 7. Evaluation criteria

Stage 1 – preselection:

### 1. Data extraction quality (F1 score) – 100%

Evaluation of how well the results match the reference data on the unknown test set.

Stage 2 – final selection:

### 1. Data extraction quality (F1 score) – 50%

Evaluation of how well the results match the reference data on the unknown test set.

### 2. Flexibility and extensibility of the solution – 50%

The evaluation will include:
* 1–20 points for the power of the LLM. The more powerful the model, measured in billions of parameters, the fewer points. In other words, we want to find a balance between extraction effectiveness and costs. More information below.
* 1–20 points for how easy it is to add new document types and new data classes without rebuilding the whole system.
* 1–10 points for other interesting features added to the application (e.g. a GUI)

#### LLM scoring
Following discussions with participants and reports of potential ways of manipulation, we are working on new guidelines. Stay tuned.

# Exceptions

## OCR through an API
You may use local OCR or OCR through an API. If through an API, its parameters will be counted as for an LLM and taken into account in the evaluation.

## Maximum processing time
Your solution will be tested on 150 PDF files. The maximum processing time for the whole set is 45 minutes.
