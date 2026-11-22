"""Value coverage: which reference values the extracted text contains at all.

Coverage is the ceiling for extraction from that text, and a check of the conversion: a value
split across table cells or garbled by OCR is missing. A value counts as present if one of its
usual written forms occurs in the text, ignoring whitespace and case. The value type of each
field comes from the document type's schema.json.
"""

import re
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from typing import Any, Self

from src.value_types import MONTHS_GENITIVE, VALUE_TYPES

# Identifiers written with varying separators ("PL 61 1090 ...", "NIP: 123-456-78-90"): compared as digits.
DIGIT_TYPES = frozenset({"nip", "regon", "krs", "pesel", "account"})
ISO_DATE = re.compile(r"(\d{4})-(\d{2})-(\d{2})")
TED_NUMBER = re.compile(r"(\d+)-(\d{4})")
WHITESPACE = re.compile(r"\s+")
NON_DIGITS = re.compile(r"\D")


@dataclass(frozen=True, slots=True)
class ValueCheck:
    """One reference value and whether the text contains it."""

    path: str  # e.g. "Odwolujacy[].nip", as in the F1 breakdown
    present: bool


@dataclass(frozen=True, slots=True)
class CoverageCounts:
    """How many of the checked reference values the text contains."""

    present: int = 0
    total: int = 0

    @classmethod
    def of(cls, checks: Iterable[ValueCheck]) -> Self:
        outcomes = [check.present for check in checks]
        return cls(present=sum(outcomes), total=len(outcomes))

    def __add__(self, other: "CoverageCounts") -> "CoverageCounts":
        return CoverageCounts(self.present + other.present, self.total + other.total)

    @property
    def share(self) -> float:
        return self.present / self.total if self.total else 0.0


def check_values(data: dict[str, Any], schema: dict[str, Any], text: str) -> list[ValueCheck]:
    """A check for every non-null reference value of a type that documents write out."""
    compact_text = _compact(text)
    digits = NON_DIGITS.sub("", text)
    return [ValueCheck(path, _is_present(value, value_type, compact_text, digits))
            for path, value_type, value in _typed_leaves(data, schema, path="")
            if value is not None and VALUE_TYPES[value_type].written]


def _typed_leaves(data: Any, template: Any, path: str) -> Iterator[tuple[str, str, Any]]:
    """(path, value type from the schema, value) for every scalar of a reference JSON."""
    match data:
        case dict():
            for key, value in data.items():
                yield from _typed_leaves(value, template[key], f"{path}.{key}" if path else key)
        case list():
            for item in data:
                yield from _typed_leaves(item, template[0], f"{path}[]")
        case _:
            yield path, template, data


def _is_present(value: Any, value_type: str, compact_text: str, digits: str) -> bool:
    match value_type:
        case _ if value_type in DIGIT_TYPES:
            return NON_DIGITS.sub("", str(value)) in digits
        case "date" if ISO_DATE.fullmatch(str(value)):
            return any(_compact(form) in compact_text for form in _date_forms(value))
        case "amount":
            return any(form in compact_text for form in _amount_forms(float(value)))
        case "ted" if (match := TED_NUMBER.fullmatch(str(value))):  # "999449-2026", or "2026/S 245-999449"
            number, year = match.groups()
            return (_compact(value) in compact_text
                    or re.search(rf"{year}/s\d{{1,3}}-0*{int(number)}(?!\d)", compact_text) is not None)
        case _:
            return _compact(str(value)) in compact_text


def _date_forms(iso_date: str) -> set[str]:
    """2026-09-24 -> 24.09.2026, 24-09-2026, 24/09/2026, 24 września 2026, also without a leading zero."""
    year, month, day = iso_date.split("-")
    month_name = MONTHS_GENITIVE[int(month) - 1]
    forms = {iso_date}
    for day_form in {day, str(int(day))}:
        forms |= {f"{day_form}{separator}{month}{separator}{year}" for separator in ".-/"}
        forms.add(f"{day_form} {month_name} {year}")
    return forms


def _amount_forms(amount: float) -> set[str]:
    """15000.0 -> 15000,00, 15.000,00 and 15000.00 (spaces are removed before matching)."""
    whole, fraction = f"{amount:.2f}".split(".")
    grouped = f"{int(whole):,}".replace(",", ".")
    return {f"{whole},{fraction}", f"{grouped},{fraction}", f"{whole}.{fraction}"}


def _compact(text: str) -> str:
    return WHITESPACE.sub("", text).casefold()
