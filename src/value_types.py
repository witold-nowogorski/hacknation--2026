"""Value types of output fields: the leaves of each schema.json name one of these.

A value type gives the Python type of the value, its normaliser and whether documents write the
value out (codes, flags and dictionary texts are interpreted instead). A normaliser takes a raw
value - text from a document, an LLM answer, or an already normalised value - and returns the
canonical value, or None when it cannot read it; it never raises, so one bad value cannot fail a
document. Checksums are not enforced: the synthetic data has invalid NIP checksums, so checksums
only rank candidates.
"""

import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from typing import Any

MONTHS_GENITIVE = ("stycznia", "lutego", "marca", "kwietnia", "maja", "czerwca", "lipca", "sierpnia",
                   "września", "października", "listopada", "grudnia")
# OCR often drops Polish diacritics ("ODWOLANIE", "Odwołujacy") or reads "i" as a dotless "ı".
FOLD_DIACRITICS = str.maketrans("ąćęłńóśźżıĄĆĘŁŃÓŚŹŻ", "acelnoszziACELNOSZZ")
# Words before a person's name that are not part of it: titles and company roles.
NAME_PREFIXES = frozenset({"adw", "adwokat", "adwokatka", "r", "pr", "radca", "radczyni", "prawny", "prawna",
                           "mec", "dr", "hab", "prof", "mgr", "inż", "pan", "pani", "prezes", "wiceprezes",
                           "członek", "zarządu", "wspólnik", "prokurent", "pełnomocnik", "za",
                           # organisation words: "Kancelaria Prawna" is not a person
                           "kancelaria", "spółka", "biuro", "firma", "zakład", "urząd", "gmina", "bank"})
QUOTES = "\"'„”“«»"
NUMERIC_DATE = re.compile(r"(\d{1,2})\s*[./-]\s*(\d{1,2})\s*[./-]\s*(\d{4})")
ISO_DATE = re.compile(r"(\d{4})-(\d{1,2})-(\d{1,2})")
WORD_DATE = re.compile(r"(\d{1,2})\s*([a-z]+)\s+(\d{4})")
TED_S_FORM = re.compile(r"((?:19|20)\d{2})/S\s*\d{1,3}\s*-\s*(\d{5,8})", re.IGNORECASE)
TED_NUMBER = re.compile(r"(?<!\d)(\d{5,8})\s*-\s*((?:19|20)\d{2})(?!\d)")
BZP_NUMBER = re.compile(r"(\d{4})/BZP(\d{8})(/\d{2})?", re.IGNORECASE)
EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
NON_DIGITS = re.compile(r"\D")
UPPER = "A-ZĄĆĘŁŃÓŚŹŻ"
LOWER = "a-ząćęłńóśźż"
NAME_WORD = rf"(?:[{UPPER}][{LOWER}]+(?:-[{UPPER}][{LOWER}]+)?|[{UPPER}]{{2,}}(?:-[{UPPER}]{{2,}})?)"


def fold_diacritics(text: str) -> str:
    return text.translate(FOLD_DIACRITICS)


def fold(text: str) -> str:
    """Lower case without Polish diacritics, with every character at its original position."""
    return fold_diacritics("".join(char.lower()[:1] or char for char in text))


def normalize_text(raw: Any) -> str | None:
    """Whitespace collapsed, surrounding quotes removed."""
    if raw is None:
        return None
    text = " ".join(str(raw).split()).strip(QUOTES + " ")
    return text or None


def normalize_person_name(raw: Any) -> str | None:
    """"adw. JAN KOWALSKI – Prezes Zarządu" -> "Jan Kowalski": no titles or roles; capitals only as names have them."""
    text = normalize_text(raw)
    if text is None:
        return None
    name = re.split(r"\s+[–-]\s+|,", text)[0].split()
    while name and name[0].rstrip(".").casefold() in NAME_PREFIXES:
        name = name[1:]
    if len(name) < 2:  # a first name and a surname at least
        return None
    joined = " ".join(name)
    return joined.title() if joined.isupper() else joined


def normalize_email(raw: Any) -> str | None:
    match = EMAIL.search("".join(str(raw or "").split()))
    return match.group().lower() if match else None


def _digits(raw: Any) -> str:
    return NON_DIGITS.sub("", str(raw)) if raw is not None else ""


def normalize_nip(raw: Any) -> str | None:
    digits = _digits(raw)
    return digits if len(digits) == 10 else None


def normalize_regon(raw: Any) -> str | None:
    digits = _digits(raw)
    return digits if len(digits) in (9, 14) else None


def normalize_krs(raw: Any) -> str | None:
    """KRS numbers have 10 digits; leading zeros are often omitted in text."""
    digits = _digits(raw)
    return digits.zfill(10) if 0 < len(digits) <= 10 else None


def normalize_pesel(raw: Any) -> str | None:
    digits = _digits(raw)
    return digits if len(digits) == 11 else None


def normalize_account(raw: Any) -> str | None:
    """Digits only: the references drop the "PL" country prefix (138 of 140 values)."""
    digits = _digits(raw)
    return digits if 16 <= len(digits) <= 34 else None


def normalize_amount(raw: Any) -> float | None:
    """"15 000,00 zł", "15.000,00", "15000.00" -> 15000.0."""
    if isinstance(raw, bool) or raw is None:
        return None
    if isinstance(raw, int | float):
        return round(float(raw), 2)
    number = re.sub(r"[^\d,.]", "", "".join(str(raw).split()))
    if "," in number and "." in number:
        thousands = "." if number.rfind(",") > number.rfind(".") else ","
        number = number.replace(thousands, "")
    elif "." in number and re.fullmatch(r"\d{1,3}(\.\d{3})+", number):
        number = number.replace(".", "")
    try:
        return round(float(number.replace(",", ".")), 2)
    except ValueError:
        return None


def normalize_date(raw: Any) -> str | None:
    """The first date in the text as ISO: 2026-09-24, 24.09.2026, 24/09/2026, "24 września 2026 r."."""
    text = fold_diacritics(" ".join(str(raw or "").split()).casefold())
    months = [fold_diacritics(month) for month in MONTHS_GENITIVE]
    candidates = []
    if match := ISO_DATE.search(text):
        candidates.append((match.start(), int(match[1]), int(match[2]), int(match[3])))
    if match := NUMERIC_DATE.search(text):
        candidates.append((match.start(), int(match[3]), int(match[2]), int(match[1])))
    for match in WORD_DATE.finditer(text):
        if match[2] in months:
            candidates.append((match.start(), int(match[3]), months.index(match[2]) + 1, int(match[1])))
            break
    for _, year, month, day in sorted(candidates):
        try:
            return date(year, month, day).isoformat()
        except ValueError:
            continue
    return None


def normalize_ted(raw: Any) -> str | None:
    """"2026/S 245-999449" or "999449-2026" -> "999449-2026"."""
    text = str(raw or "")
    if match := TED_S_FORM.search(text):
        return f"{match[2]}-{match[1]}"
    if match := TED_NUMBER.search(text):
        return f"{match[1]}-{match[2]}"
    return None


def normalize_bzp(raw: Any) -> str | None:
    """"2026/BZP 00999778/03" -> "2026/BZP00999778/03"."""
    match = BZP_NUMBER.search("".join(str(raw or "").split()))
    return f"{match[1]}/BZP{match[2]}{match[3] or ''}" if match else None


def normalize_flag(raw: Any) -> int | None:
    answers = {"1": 1, "true": 1, "tak": 1, "0": 0, "false": 0, "nie": 0}
    return answers.get(str(raw).strip().casefold()) if raw is not None else None


def normalize_reason_id(raw: Any) -> int | None:
    """Contested action code 1-12 (the organiser's dictionary)."""
    digits = _digits(raw)
    return int(digits) if digits and 1 <= int(digits) <= 12 else None


def normalize_party_type(raw: Any) -> str | None:
    text = fold_diacritics(str(raw or "").casefold())
    if "prawn" in text:
        return "osoba_prawna"
    if "fizyczn" in text:
        return "osoba_fizyczna"
    return None


@dataclass(frozen=True, slots=True)
class ValueType:
    """How values of one kind are typed, normalised and found."""

    python_type: type
    normalize: Callable[[Any], Any]
    written: bool = True  # False: interpreted (codes, flags, dictionary texts), never verbatim in documents
    pattern: str | None = None  # finds candidate values in text; None = free text, read up to the line end
    choices: tuple[Any, ...] = ()  # the only allowed values (constrains LLM answers); empty = any


VALUE_TYPES: dict[str, ValueType] = {
    "text": ValueType(str, normalize_text),
    "person_name": ValueType(str, normalize_person_name, pattern=rf"(?<![\w-]){NAME_WORD}[ \t]+{NAME_WORD}(?!\w|-\w)"),
    "email": ValueType(str, normalize_email, pattern=EMAIL.pattern),
    "nip": ValueType(str, normalize_nip, pattern=r"(?<!\d)(?:PL\s?)?\d{3}[- ]?\d{2,3}[- ]?\d{2,3}[- ]?\d{2,3}(?!\d)"),
    "regon": ValueType(str, normalize_regon, pattern=r"(?<!\d)\d{9}(?:\d{5})?(?!\d)"),
    "krs": ValueType(str, normalize_krs, pattern=r"(?<!\d)\d{1,10}(?!\d)"),
    "pesel": ValueType(str, normalize_pesel, pattern=r"(?<!\d)\d{11}(?!\d)"),
    "account": ValueType(str, normalize_account, pattern=r"(?<![\dA-Z])(?:PL)?\s?\d{2}(?:\s?\d{4}){6}(?!\d)"),
    "amount": ValueType(float, normalize_amount, pattern=r"(?<![\d,.])-?\d{1,3}(?:[ \u00a0.]?\d{3})*(?:,\d{2}(?!\d)|(?=\s*(?:PLN|zł|zl)\b))|(?<![\d,.])\d+\.\d{2}(?=\s*(?:PLN|zł|zl)\b)"),
    "date": ValueType(str, normalize_date, pattern=r"(?<!\d)(?:\d{4}-\d{1,2}-\d{1,2}|\d{1,2}\s*[./-]\s*\d{1,2}\s*[./-]\s*\d{4}|\d{1,2}\s*[" + LOWER + r"]+\s+\d{4})"),
    "ted": ValueType(str, normalize_ted, pattern=rf"{TED_S_FORM.pattern}|{TED_NUMBER.pattern}"),
    "bzp": ValueType(str, normalize_bzp, pattern=r"\d{4}\s*/\s*BZP\s*\d{8}(?:\s*/\s*\d{2})?"),
    "flag": ValueType(int, normalize_flag, written=False, choices=(0, 1)),
    "reason_id": ValueType(int, normalize_reason_id, written=False, choices=tuple(range(1, 13))),
    "reason_description": ValueType(str, normalize_text, written=False),
    "party_type": ValueType(str, normalize_party_type, written=False, choices=("osoba_prawna", "osoba_fizyczna")),
}
