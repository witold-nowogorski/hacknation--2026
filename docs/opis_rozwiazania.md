# Odwołania2json – opis rozwiązania

**Od sprawy w PDF do danych JSON: szybko, tanio i z dowodem pochodzenia każdej wartości.**

## Problem

Sprawa odwoławcza KIO to kilka PDF-ów (odwołanie, pełnomocnictwo, potwierdzenie przelewu i dokumenty, których nie wolno rozpoznać). Część powstaje elektronicznie, część to skany. Nazwy plików i układy są dowolne. Dziś dane z nich przepisuje się ręcznie.

## Rozwiązanie

Odwołania2json rozpoznaje typ każdego dokumentu po treści i zapisuje go jako JSON w kanonicznym formacie UZP. Dokument nierozpoznany dostaje `{}`.

Zasada projektowa: **reguły najpierw, model językowy tylko tam, gdzie potrzebne jest zrozumienie.**

1. **Odczyt.** Open-source'owy Docling czyta dwie pierwsze strony (tam są wszystkie dane referencyjne). Lokalny OCR włącza się tylko na stronach bez warstwy tekstowej. Działa na CPU.
2. **Klasyfikacja.** Ważone słowa kluczowe z konfiguracji, odporne na błędy OCR (dopasowanie bez polskich znaków, frazy wykluczające tylko w nagłówku).
3. **Ekstrakcja regułami.** Etykiety, wzorce i sumy kontrolne dla wartości o stałym formacie: NIP, REGON, KRS, PESEL, rachunki, kwoty, daty, numery BZP i TED.
4. **Model danych.** Model Pydantic jest generowany automatycznie ze `schema.json` danego typu. Normalizuje wartości, daje pełną strukturę wyjścia i JSON Schema dla LLM.
5. **LLM tylko do oceny.** Mały otwarty model (Bielik-11B, hostowany w PSNC Poznań, UE) dostaje wycinek tekstu i wyłącznie pola wymagające interpretacji, np. czego dotyczy zarzut odwołania. Najwyżej jedno wywołanie na dokument, temperatura 0. Wartość zwrócona przez model musi wystąpić w dokumencie, inaczej zapisujemy `null`.

## Dlaczego warto

- **Rozszerzalność bez kodu.** Cała wiedza o typie dokumentu leży w `config/doc_types/<typ>/`: słowa kluczowe, struktura wyjścia, opcjonalny prompt. Nowy typ dokumentu to nowe pliki konfiguracyjne, bez zmian w kodzie.
- **Transparentność.** Dla każdej wartości zapisujemy ślad pochodzenia: metodę (reguła, LLM, wyprowadzenie), stronę i fragment tekstu. Cache przechowuje prompt obok odpowiedzi modelu.
- **Niski koszt.** Większość pracy wykonują deterministyczne reguły, więc wystarcza model 11B zamiast modeli rzędu setek miliardów parametrów.
- **Jakość mierzona, nie zgadywana.** Własny ewaluator F1 (ścisły i po normalizacji) raportuje wyniki osobno dla dokumentów cyfrowych, skanów i negatywów. Każdy raport zawiera commit i pełną konfigurację.

## Wyniki (226 dokumentów organizatora: 184 cyfrowe, 30 skanów, 12 negatywów)

| Miara | Wynik |
|---|---|
| F1 | **[do uzupełnienia z ostatniego raportu]** |
| Trafność klasyfikacji | 100% na wszystkich zbiorach |
| Wartości referencyjne obecne w odczytanym tekście | 99,0% (2026 z 2046) |
| Czas odczytu dokumentu | 0,4 s (cyfrowy), 3,4 s (skan), tylko CPU |
| Projekcja dla 150 PDF-ów | 1–9 min przy limicie 45 min; szczyt pamięci ok. 4,8 GB |

## Zgodność z wymaganiami

Python 3.13, instalacja `pip install -r requirements.txt`, start `python -m src.run`. Wyłącznie komponenty open source (Docling, RapidOCR, Pydantic, Bielik). Działa lokalnie bez GPU, LLM przez API w UE. Foldery `input/` i `output/` z zachowaniem struktury spraw i nazw plików.

Odwołania2json to fundament uniwersalnego narzędzia UZP do pozyskiwania danych z dokumentów PDF: nowe dokumenty dodaje się konfiguracją, jakość mierzy ewaluatorem, a każdą wartość można wyjaśnić.
