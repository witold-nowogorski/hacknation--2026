# Odwolania2json

## KRÓTKI OPIS PROJEKTU

Sprawy odwoławcze KIO to zbiory PDF-ów: odwołania, pełnomocnictwa, potwierdzenia przelewu. Część jest generowana elektronicznie, część to skany, a każdy ma inny układ. Dziś dane z nich przepisuje się ręcznie. Nasz system automatycznie rozpoznaje rodzaj dokumentu i przekształca go w ustrukturyzowany JSON gotowy dla systemów UZP. Każda wyciągnięta wartość ma wskazane źródło w dokumencie. Docelowo to uniwersalne narzędzie do ekstrakcji danych z PDF, w którym nowe rodzaje dokumentów dodaje się konfiguracją, a nie programowaniem.

## PLAN ROZWIĄZANIA

Łączymy klasyczną ekstrakcję opartą na regułach z małym modelem językowym. Reguły obsługują dane o stałym formacie, a model tylko te fragmenty, które wymagają zrozumienia treści. Dzięki temu rozwiązanie jest tanie, przewidywalne i skuteczne również na nietypowych dokumentach.

- **Odczyt dokumentów:** open-source'owy Docling z OCR odczytuje zarówno PDF-y cyfrowe, jak i skany. Działa lokalnie na CPU.
- **Rozpoznanie i ekstrakcja:** reguły i walidatory (sumy kontrolne NIP/REGON/PESEL, formaty kwot, dat, rachunków) dają szybkie, powtarzalne i tanie wyniki.
- **Model językowy:** mały otwarty LLM przez API w UE/EOG dostaje tylko to, czego reguły nie rozstrzygną, np. czego dotyczy zarzut odwołania. Jego odpowiedzi sprawdzamy z tekstem źródłowym, żeby nie zmyślał danych.
- **Konfiguracja zamiast kodu:** wiedza o każdym rodzaju dokumentu (pola, słowa kluczowe, słowniki, instrukcje dla modelu) leży w plikach konfiguracyjnych. Nowy rodzaj dokumentu nie wymaga zmian w kodzie.
- **Transparentność:** przy każdej wartości zapisujemy, skąd pochodzi (reguła czy model, strona, fragment tekstu).
- **Mierzalna jakość:** każdą zmianę oceniamy własnym ewaluatorem F1 na danych referencyjnych.

## DOTYCHCZASOWE POSTĘPY

- Zaprojektowaliśmy architekturę i podział pracy między reguły a model językowy.
- Działa odczyt dokumentów, również skanów, z lokalnymi modelami OCR.
- Gotowy jest szkielet przetwarzania spraw (wejście -> JSON), odporny na uszkodzone pliki.
- Działa ewaluator F1, który pozwala porównywać kolejne warianty rozwiązania na zbiorze treningowym.
- W toku: rozpoznawanie rodzaju dokumentu i ekstrakcja pól sterowane konfiguracją.
