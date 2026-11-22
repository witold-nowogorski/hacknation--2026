"""Incremental scoring of pipeline results against reference JSONs.

Documents are added one by one, so the running score is known during a run. Field-level
F1 follows `metrics.py`; classification is scored as accuracy plus a confusion matrix.
"""

from collections import Counter, defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Self

from pydantic import BaseModel

from src.evaluation.metrics import Counts, LeafComparison, compare, normalised_equal, strict_equal, total_counts
from src.evaluation.references import Reference
from src.pipeline.documents import DocumentResult, InputDocument

NO_TYPE = "none"
WORST_FIELDS_SHOWN = 10


class Scores(BaseModel):
    """Precision, recall and F1 with the counts behind them."""

    precision: float
    recall: float
    f1: float
    tp: int
    fp: int
    fn: int

    @classmethod
    def from_counts(cls, counts: Counts) -> Self:
        return cls(
            precision=round(counts.precision, 4), recall=round(counts.recall, 4), f1=round(counts.f1, 4),
            tp=counts.tp, fp=counts.fp, fn=counts.fn,
        )


class ClassificationScores(BaseModel):
    """Document type accuracy; confusion[expected][predicted] = number of documents."""

    accuracy: float
    confusion: dict[str, dict[str, int]]


class SubsetScores(BaseModel):
    """Scores of one evaluation set (e.g. scans), so a weakness of one kind of input stays visible."""

    documents: int
    classification_accuracy: float
    strict: Scores


class EvalScores(BaseModel):
    """Headline scores (strict and normalised) and strict breakdowns by evaluation set, document type and field."""

    documents: int
    strict: Scores
    normalised: Scores
    by_subset: dict[str, SubsetScores] = {}  # empty in reports written before evaluation sets existed
    by_doc_type: dict[str, Scores]
    by_field: dict[str, Scores]
    classification: ClassificationScores


@dataclass(frozen=True, slots=True)
class FieldError:
    """One strict mismatch, for error analysis."""

    document: str
    path: str
    expected: Any
    predicted: Any


@dataclass(frozen=True, slots=True)
class DocumentEvaluation:
    """Scores of a single document."""

    expected_type: str | None
    predicted_type: str | None
    strict: Counts
    normalised: Counts
    errors: tuple[FieldError, ...]

    @property
    def type_correct(self) -> bool:
        return self.expected_type == self.predicted_type


@dataclass(slots=True)
class _SubsetTotals:
    documents: int = 0
    correctly_classified: int = 0
    strict: Counts = Counts()


class Evaluator:
    """Accumulates field-level counts and classification outcomes document by document."""

    def __init__(self, reference_loader: Callable[[InputDocument], Reference]) -> None:
        self._load_reference = reference_loader
        self._documents = 0
        self._strict = Counts()
        self._normalised = Counts()
        self._by_subset: dict[str, _SubsetTotals] = defaultdict(_SubsetTotals)
        self._by_doc_type: dict[str, Counts] = defaultdict(Counts)
        self._by_field: dict[str, Counts] = defaultdict(Counts)
        self._confusion: dict[str, Counter[str]] = defaultdict(Counter)

    def add(self, result: DocumentResult, subset: str) -> DocumentEvaluation:
        """Score one result of evaluation set `subset` against its reference and add it to the totals."""
        reference = self._load_reference(result.document)
        comparisons = compare(reference.data, result.data, strict_equal)
        evaluation = DocumentEvaluation(
            expected_type=reference.doc_type,
            predicted_type=result.doc_type,
            strict=total_counts(comparisons),
            normalised=total_counts(compare(reference.data, result.data, normalised_equal)),
            errors=tuple(_field_error(result, comparison) for comparison in comparisons if not comparison.match),
        )
        self._accumulate(evaluation, comparisons, subset)
        return evaluation

    @property
    def running(self) -> Counts:
        """Strict counts of all documents added so far."""
        return self._strict

    @property
    def classification_accuracy(self) -> float:
        correct = sum(row[label] for label, row in self._confusion.items())
        return correct / self._documents if self._documents else 0.0

    def scores(self) -> EvalScores:
        """Final scores of all documents added so far."""
        return EvalScores(
            documents=self._documents,
            strict=Scores.from_counts(self._strict),
            normalised=Scores.from_counts(self._normalised),
            by_subset={name: SubsetScores(
                documents=totals.documents,
                classification_accuracy=round(totals.correctly_classified / totals.documents, 4),
                strict=Scores.from_counts(totals.strict),
            ) for name, totals in self._by_subset.items()},
            by_doc_type={label: Scores.from_counts(counts) for label, counts in sorted(self._by_doc_type.items())},
            by_field={path: Scores.from_counts(counts) for path, counts in sorted(self._by_field.items())},
            classification=ClassificationScores(
                accuracy=round(self.classification_accuracy, 4),
                confusion={label: dict(sorted(row.items())) for label, row in sorted(self._confusion.items())},
            ),
        )

    def _accumulate(self, evaluation: DocumentEvaluation, comparisons: list[LeafComparison], subset: str) -> None:
        expected_type = evaluation.expected_type or NO_TYPE
        self._documents += 1
        self._strict += evaluation.strict
        self._normalised += evaluation.normalised
        subset_totals = self._by_subset[subset]
        subset_totals.documents += 1
        subset_totals.correctly_classified += evaluation.type_correct
        subset_totals.strict += evaluation.strict
        self._by_doc_type[expected_type] += evaluation.strict
        self._confusion[expected_type][evaluation.predicted_type or NO_TYPE] += 1
        for comparison in comparisons:
            self._by_field[comparison.path] += comparison.counts()


def _field_error(result: DocumentResult, comparison: LeafComparison) -> FieldError:
    return FieldError(
        document=result.document.label, path=comparison.path,
        expected=comparison.expected, predicted=comparison.predicted,
    )


def format_scores(scores: EvalScores) -> str:
    """Multi-line plain-text summary of the scores."""
    worst_fields = sorted(scores.by_field.items(), key=lambda item: (item[1].f1, -item[1].fn))[:WORST_FIELDS_SHOWN]
    return "\n".join([
        f"Documents: {scores.documents}   classification accuracy: {scores.classification.accuracy:.3f}",
        f"F1 strict: {scores.strict.f1:.3f} (P {scores.strict.precision:.3f}, R {scores.strict.recall:.3f})"
        f"   normalised: {scores.normalised.f1:.3f}",
        "By evaluation set (strict; FP on negatives = invented values):",
        *(f"  {name:16s} documents {s.documents:4d}  class. {s.classification_accuracy:.3f}  F1 {s.strict.f1:.3f}"
          f"  FP {s.strict.fp:4d}  FN {s.strict.fn:4d}" for name, s in scores.by_subset.items()),
        "By document type (strict):",
        *(f"  {label:16s} F1 {s.f1:.3f}  TP {s.tp:4d}  FP {s.fp:4d}  FN {s.fn:4d}"
          for label, s in scores.by_doc_type.items()),
        f"Worst {WORST_FIELDS_SHOWN} fields (strict):",
        *(f"  {path:50s} F1 {s.f1:.3f}  FP {s.fp:4d}  FN {s.fn:4d}" for path, s in worst_fields),
    ])
