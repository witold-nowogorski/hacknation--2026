# Odwołania2json – solution overview

**From a PDF case file to JSON data: fast, cheap, and with proof of where every value came from.**

## The problem

A KIO appeal case is a set of PDFs: the appeal, the power of attorney, the payment confirmation, and other documents that must not be recognised. Some are created digitally, some are scans. File names and layouts can be anything. Today, people copy the data out of them by hand.

## The solution

Odwołania2json recognises the type of each document from its content and saves it as JSON in the UZP format. A document it does not recognise gets `{}`.

Design rule: **rules first, a language model only where understanding is needed.**

1. **Reading.** The open-source Docling library reads the first two pages (all the reference data is there). Local OCR runs only on pages without a text layer. Everything runs on a CPU.
2. **Classification.** Weighted keywords from the configuration. Robust to OCR errors: matching ignores Polish characters, and "this is not that type" phrases are checked only in the document header.
3. **Rule-based extraction.** Labels, patterns and checksums for values with a fixed format: NIP, REGON, KRS, PESEL, bank accounts, amounts, dates, BZP and TED numbers.
4. **Data model.** A Pydantic model is generated automatically from each type's `schema.json`. It normalises values, provides the full output structure, and gives the JSON Schema for the LLM.
5. **LLM only for judgement.** A small open model (Bielik-11B, hosted by PSNC in Poznań, EU) gets a short piece of text and only the fields that need interpretation, e.g. what the appeal is about. At most one call per document, temperature 0. The value returned by the model must appear in the document, otherwise we write `null`.

## Why it is good

- **Extend without code.** Everything about a document type lives in `config/doc_types/<type>/`: keywords, output structure, an optional prompt. A new document type means new config files, no code changes.
- **Transparent.** For every value we record where it came from: the method (rule, LLM, derived), the page and the text snippet. The cache keeps each prompt next to the model's answer.
- **Low cost.** Deterministic rules do most of the work, so an 11B model is enough instead of models with hundreds of billions of parameters.
- **Quality is measured, not guessed.** Our own F1 evaluator (strict and normalised) reports results separately for digital documents, scans and negatives. Every report includes the git commit and the full configuration.

## Results (226 organiser documents: 184 digital, 30 scans, 12 negatives)

| Metric | Result |
|---|---|
| F1 | **[to fill in from the latest report]** |
| Classification accuracy | 100% on all sets |
| Reference values present in the extracted text | 99.0% (2026 of 2046) |
| Time to read a document | 0.4 s (digital), 3.4 s (scan), CPU only |
| Estimate for 150 PDFs | 1–9 min (limit is 45 min); peak memory about 4.8 GB |

## Meeting the requirements

Python 3.13, install with `pip install -r requirements.txt`, start with `python -m src.run`. Open-source components only (Docling, RapidOCR, Pydantic, Bielik). Runs locally without a GPU; the LLM is an API hosted in the EU. Uses the `input/` and `output/` folders and keeps the case folder structure and file names.

Odwołania2json is a base for a general UZP tool that pulls data out of PDF documents: new documents are added through configuration, quality is measured by the evaluator, and every value can be explained.
