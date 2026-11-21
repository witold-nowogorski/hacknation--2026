# Odwołania2json

**Od dokumentów do danych. Inteligentna transformacja odwołań KIO do modelu JSON**

# Krótki opis wyzwania

Każdego roku do systemu zamówień publicznych trafiają tysiące dokumentów zawierających kluczowe informacje o postępowaniach, wykonawcach, pełnomocnikach i czynnościach zamawiających. Najczęściej są to dokumenty tekstowe z kluczowymi, jednak ułożonymi w przeróżny sposób, informacjami z reguły na pierwszych trzech stronach. Celem wyzwania jest stworzenie rozwiązania, które automatycznie zamieni wielodokumentową sprawę administracyjną w spójny, ustrukturyzowany model danych JSON gotowy do dalszego wykorzystania przez systemy informatyczne administracji publicznej.

# 1. Wprowadzenie

Urząd Zamówień Publicznych odpowiada za funkcjonowanie systemu zamówień publicznych w Polsce oraz wspiera uczestników rynku w prawidłowym stosowaniu przepisów prawa. Jednym z elementów tego systemu są postępowania odwoławcze prowadzone przed Krajową Izbą Odwoławczą.

Sprawa odwoławcza nie jest pojedynczym dokumentem. Stanowi zbiór wielu powiązanych ze sobą dokumentów zawierających informacje o wykonawcach, zamawiających, pełnomocnikach, postępowaniach, płatnościach, czynnościach procesowych i innych elementach wymagających dalszego przetwarzania.

Obecnie większość takich dokumentów występuje w postaci plików PDF o zróżnicowanej strukturze. Część z nich powstaje elektronicznie, część jest wynikiem skanowania dokumentów papierowych. Informacje niezbędne do dalszej obsługi sprawy są rozproszone pomiędzy wieloma dokumentami i często zapisane w różny sposób.

Dla człowieka zrozumienie takiej dokumentacji jest stosunkowo proste. Dla systemów informatycznych stanowi jednak duże wyzwanie. Aby możliwa była automatyzacja dalszych procesów, dane muszą zostać najpierw przekształcone do postaci ustrukturyzowanej.

W praktyce oznacza to konieczność przejścia od modelu:

**wiele dokumentów PDF → analiza treści → identyfikacja informacji → model danych JSON**

Wyzwanie dotyczy zatem budowy rozwiązania, które pozwoli automatycznie przekształcać wielodokumentowe sprawy administracyjne w kanoniczny model danych możliwy do dalszego wykorzystania przez systemy administracji publicznej.

Najciekawsze rozwiązania mają szansę stać się podstawą pilotażowych wdrożeń realizowanych przez Urząd Zamówień Publicznych.

# 2. Wyzwanie

Zaprojektuj i zaimplementuj rozwiązanie, które:

1.  przyjmie dokument PDF składający się na odwołanie: dokument z treścią odwołania, pełnomocnictwo, dokument potwierdzenia przelewu
2.  rozpozna rodzaj dokumentu
3.  wyodrębni informacje biznesowe istotne dla danego typu dokumentu,
4.  wygeneruje JSON dla każdego dokumentu zgodny z https://github.com/Urzad-Zamowien-Publicznych/hacknation-2026/blob/main/oczekiwane-json

Szczegółowa struktura danych:
https://github.com/Urzad-Zamowien-Publicznych/hacknation-2026/blob/main/oczekiwane-json/odwolanie.json

zestawy treningowe:
https://github.com/Urzad-Zamowien-Publicznych/hacknation-2026/blob/main/dane

# 3. Oczekiwany rezultat

Oczekiwanym rezultatem jest działająca aplikacja ładująca plik PDF i zwracająca pliki JSON w ustalonym formacie i strukturze.

Rozwiązanie powinno zawierać:

### Moduł przetwarzania dokumentów

Odpowiedzialny za:

- analizę dokumentów,

- klasyfikację dokumentów na podstawie ich zawartości (uwaga! nazwa pliku może być różna - nie sugerujcie się nazwą pliku),

- ekstrakcję informacji,

- budowę modelu danych.

### Interfejs wykonawczy

Interfejs umożliwiający uruchomienie działania aplikacji poprzez CLI, wrapper script (np. plik ```start.bat```), lub inne analogiczne rozwiązanie.

Dodanie do aplikacji GUI będzie dodatkowo punktowane, ale nie jest wymagane. Istotniejsza jest skuteczność identyfikacji informacji.

### Foldery input/output

Foldery o nazwie ```input``` oraz ```output```, znajdujące się w folderze głównym aplikacji. Folder ```input``` użyty zostanie do przekazywania analizowanych plików do aplikacji, podczas gdy folder ```output``` zawierać będzie wynikowe pliki JSON.

### Wynik działania

Pliki JSON w folderze ```./output```, ułożone w strukturze drzewa, gdzie każdy wynikowy **JSON nazwany jest tak samo jak plik z katalogu input któremu odpowiada**:

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

# 4. Wymagania formalne

Projekt przesyłany do oceny powinien zawierać:

- tytuł projektu,

- Link do GitHub działającego prototypu umożliwiający wgranie dokumentów i odczytanie rezultatów ekstrakcji informacji.

Dodatkowo uczestnicy mogą dostarczyć:

- repozytorium projektu,

- dokumentację techniczną w tym opis wykorzystanego LLM,

- wyniki własnych testów jakości.

# 5. Wymagania techniczne

Rozwiązanie musi:

- być opracowane w języku **Python 3.13+**
  
- zawierać plik ```requirements.txt``` pozwalający na szybkie zainstalowanie pozostałych zależności projektu (np. poprzez ```pip install```)

- wykorzystywać wyłącznie komponenty open source (w tym otwarto-źródłowe modele językowe),

- umożliwiać uruchomienie w środowisku lokalnym (on-premise) bez GPU (LLM po API).

Szczególnie premiowane będą rozwiązania:

- umożliwiające konfigurację nowych klas dokumentów bez modyfikacji kodu źródłowego (jedynie przez pliki konfiguracyjne),

- wspierające transparentność procesu ekstrakcji danych.

# 6. Sposób testowania i walidacji

Ocena zostanie przeprowadzona na dwóch zbiorach danych:

### Zbiór treningowy

Udostępniony uczestnikom podczas realizacji wyzwania dostępny w katalogu dane. Zbiór danych zawiera też kategorie dokumentów, które NIE powinny być zidentyfikowane (zwrócić pusty plik `.json`).

dane negatywne (które nie powinny zostać sklasyfikowane) umieszczone zostały w wybranych przykładach oraz w katalogu https://github.com/Urzad-Zamowien-Publicznych/hacknation-2026/tree/main/dane/negatywne.

### Zbiór testowy

Nieudostępniany uczestnikom.

Zbiór testowy będzie zawierał kompletne sprawy administracyjne przygotowane przez organizatora.

Wyniki wygenerowane przez rozwiązanie zostaną porównane z zestawem danych referencyjnych przygotowanym przez ekspertów merytorycznych.

Podstawową miarą jakości będzie [wskaźnik F1](https://en.wikipedia.org/wiki/F-score).

## Parametry maszyny na której będą testowane rozwiązania
Jest ok. 30 zespołów zainteresowanych. Musimy zmienić planowany sposób oceny. Stay tuned.

Dostarczone rozwiązanie, jeśli korzysta z LLM to powinno korzystać z API i być dostarczone z kluczem API. Obiecujemy nie wykorzystywać w innym celu niż proces testowy. API musi być świadczone przez firmę która posiada określony zakres i miejsce przetwarzania danych w swojej Polityce Prywatności, i z serwerów znajdujących się w EU/EOG.

# 7. Kryteria oceny

Etap 1 - preselekcja:

### 1. Jakość ekstrakcji danych (F1 Score) – 100%

Ocena zgodności wyników z danymi referencyjnymi na nieznanym zbiorze testowym.

Etap 2 - wybór finalny:

### 1. Jakość ekstrakcji danych (F1 Score) – 50%

Ocena zgodności wyników z danymi referencyjnymi na nieznanym zbiorze testowym.

### 2. Elastyczność i możliwość rozbudowy rozwiązania – 50%

Ocena uwzględniać będzie:
* 1-20 pkt za moc modelu LLM. Im mocniejszy model liczony w miliardach parametrów, tym mniejsza ilość punktów. Innymi słowy, zależy nam na znalezieniu równowagi między skutecznością ekstrakcji, a kosztami. Poniżej więcej info.
* 1-20 Łatwość dodawania nowych typów dokumentów i nowych klas danych bez konieczności przebudowy całego systemu.
* 1-10 Inne ciekawe funkcje dodane do aplikacji (np. GUI)

#### Sposób punktacji LLM
W wyniku dyskusji z uczestnikami i zgłoszeń o potencjalnych sposobach manipulacji, pracujemy nad nowymi wytycznymi. stay tuned. 

# Wyjątki

## OCR po API
Możecie wykorzystać OCR lokalny lub przez API. Jeśli przez API -> jego parametry będą liczone jak dla LLM i brane pod uwagę w procesie oceny.

## Maksymalny czas przetwarzania
Wasze rozwiązanie będzie testowane na 150 plikach PDF. Maksymalny czas przetwarzania całego tego zbioru to 45 minut.
