"""Leaf-level comparison of a predicted JSON with its reference, and precision/recall/F1.

Both JSONs are walked together down to scalar leaves (`Odwolujacy[].nip`). Per leaf:
equal values -> TP, different values -> FP + FN, missing prediction -> FN, unexpected
value -> FP, null on both sides -> ignored. List elements are paired by best match, so
order in a list does not matter. A wrong document type or a false positive on a negative
document needs no special case: its leaves simply do not match.
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

Equality = Callable[[Any, Any], bool]


def strict_equal(expected: Any, predicted: Any) -> bool:
    """Exact JSON equality ("123" != 123)."""
    return expected == predicted


def normalised_equal(expected: Any, predicted: Any) -> bool:
    """Equality of text forms, case-folded and with whitespace collapsed."""
    return _text_form(expected) == _text_form(predicted)


def _text_form(value: Any) -> str:
    return " ".join(str(value).split()).casefold()


@dataclass(frozen=True, slots=True)
class Counts:
    """True positives, false positives and false negatives, with derived scores."""

    tp: int = 0
    fp: int = 0
    fn: int = 0

    def __add__(self, other: "Counts") -> "Counts":
        return Counts(self.tp + other.tp, self.fp + other.fp, self.fn + other.fn)

    @property
    def precision(self) -> float:
        return self.tp / (self.tp + self.fp) if self.tp + self.fp else 0.0

    @property
    def recall(self) -> float:
        return self.tp / (self.tp + self.fn) if self.tp + self.fn else 0.0

    @property
    def f1(self) -> float:
        total = 2 * self.tp + self.fp + self.fn
        return 2 * self.tp / total if total else 0.0


@dataclass(frozen=True, slots=True)
class LeafComparison:
    """One scalar leaf; at least one side is not null."""

    path: str
    expected: Any
    predicted: Any
    match: bool

    def counts(self) -> Counts:
        if self.match:
            return Counts(tp=1)
        return Counts(fp=int(self.predicted is not None), fn=int(self.expected is not None))


def total_counts(comparisons: list[LeafComparison]) -> Counts:
    return sum((comparison.counts() for comparison in comparisons), Counts())


def compare(expected: Any, predicted: Any, equal: Equality, path: str = "") -> list[LeafComparison]:
    """Compare two JSON values leaf by leaf."""
    if expected is not None and predicted is not None and _kind(expected) != _kind(predicted):
        return compare(expected, None, equal, path) + compare(None, predicted, equal, path)
    match _kind(expected if expected is not None else predicted):
        case "dict":
            expected_dict, predicted_dict = expected or {}, predicted or {}
            return [
                comparison
                for key in sorted(expected_dict.keys() | predicted_dict.keys())
                for comparison in compare(
                    expected_dict.get(key), predicted_dict.get(key), equal, f"{path}.{key}" if path else key
                )
            ]
        case "list":
            return _compare_lists(expected or [], predicted or [], equal, f"{path}[]")
        case _:
            if expected is None and predicted is None:
                return []
            both_present = expected is not None and predicted is not None
            return [LeafComparison(path, expected, predicted, both_present and equal(expected, predicted))]


def _kind(value: Any) -> str:
    if isinstance(value, dict):
        return "dict"
    if isinstance(value, list):
        return "list"
    return "leaf"


def _compare_lists(expected: list, predicted: list, equal: Equality, path: str) -> list[LeafComparison]:
    """Pair elements greedily by number of matching leaves; unpaired elements count fully as FN/FP."""
    candidates = sorted(
        (
            (-total_counts(compare(expected_item, predicted_item, equal, path)).tp, i, j)
            for i, expected_item in enumerate(expected)
            for j, predicted_item in enumerate(predicted)
        )
    )
    pairs: dict[int, int] = {}
    for _, i, j in candidates:
        if i not in pairs and j not in pairs.values():
            pairs[i] = j

    comparisons = []
    for i, expected_item in enumerate(expected):
        predicted_item = predicted[pairs[i]] if i in pairs else None
        comparisons += compare(expected_item, predicted_item, equal, path)
    for j, predicted_item in enumerate(predicted):
        if j not in pairs.values():
            comparisons += compare(None, predicted_item, equal, path)
    return comparisons
