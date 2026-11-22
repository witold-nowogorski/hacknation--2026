"""Incremental scoring of pipeline results against reference JSONs.

Documents are added one by one, so the running score is known during a run. Field-level
F1 follows `metrics.py`; classification is scored as accuracy plus a confusion matrix; value
coverage (`coverage.py`) shows how many reference values the extracted text contains at all.
Cold conversion times are collected per evaluation set, for the time budget of a full run.
"""

from collections import Counter, defaultdict
from collections.abc import Mapping
from dataclasses import dataclass, field
from statistics import fmean
from typing import Any, Self

from pydantic import BaseModel

from src.doc_types import DocTypeConfig
from src.evaluation.coverage import CoverageCounts, ValueCheck, check_values
from src.evaluation.metrics import Counts, LeafComparison, compare, normalised_equal, strict_equal, total_counts
from src.evaluation.references import Reference, ReferenceLoader
from src.pipeline.documents import DocumentResult

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


class Coverage(BaseModel):
    """Reference values present in the extracted text: the ceiling for extraction from that text."""

    share: float
    present: int
    total: int

    @classmethod
    def from_counts(cls, counts: CoverageCounts) -> Self:
        return cls(share=round(counts.share, 4), present=counts.present, total=counts.total)


class ClassificationScores(BaseModel):
    """Document type accuracy; confusion[expected][predicted] = number of documents."""

    accuracy: float
    confusion: dict[str, dict[str, int]]


class SubsetScores(BaseModel):
    """Scores of one evaluation set (e.g. scans), so a weakness of one kind of input stays visible."""

    documents: int
    classification_accuracy: float
    strict: Scores
    coverage: dict[str, Coverage] = {}  # by expected document type
    conversion_s: float | None = None  # mean cold conversion time per document; None if not measured
    max_conversion_s: float | None = None


class EvalScores(BaseModel):
    """Headline scores, and breakdowns by evaluation set, document type and field.

    Fields with defaults are missing in reports written before they were measured.
    """

    documents: int
    strict: Scores
    normalised: Scores
    coverage: Coverage | None = None
    conversion_s: float | None = None  # mean cold conversion time per document
    by_subset: dict[str, SubsetScores] = {}
    by_doc_type: dict[str, Scores]
    by_field: dict[str, Scores]
    coverage_by_field: dict[str, Coverage] = {}
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
    coverage: CoverageCounts
    errors: tuple[FieldError, ...]

    @property
    def type_correct(self) -> bool:
        return self.expected_type == self.predicted_type


@dataclass(slots=True)
class _SubsetTotals:
    """Running totals of one evaluation set."""

    documents: int = 0
    correctly_classified: int = 0
    strict: Counts = Counts()
    coverage: defaultdict[str, CoverageCounts] = field(default_factory=lambda: defaultdict(CoverageCounts))
    conversion_s: list[float] = field(default_factory=list)

    def add(self, evaluation: DocumentEvaluation, result: DocumentResult) -> None:
        self.documents += 1
        self.correctly_classified += evaluation.type_correct
        self.strict += evaluation.strict
        if evaluation.expected_type is not None:
            self.coverage[evaluation.expected_type] += evaluation.coverage
        if result.extracted is not None:
            self.conversion_s.append(result.extracted.conversion_s)

    def scores(self) -> SubsetScores:
        return SubsetScores(
            documents=self.documents,
            classification_accuracy=round(self.correctly_classified / self.documents, 4),
            strict=Scores.from_counts(self.strict),
            coverage={doc_type: Coverage.from_counts(counts) for doc_type, counts in sorted(self.coverage.items())},
            conversion_s=_mean_seconds(self.conversion_s),
            max_conversion_s=round(max(self.conversion_s), 2) if self.conversion_s else None,
        )


class Evaluator:
    """Accumulates F1 counts, classification outcomes, value coverage and conversion times per document."""

    def __init__(self, doc_types: Mapping[str, DocTypeConfig]) -> None:
        self._doc_types = doc_types
        self._references = ReferenceLoader(doc_types)
        self._documents = 0
        self._strict = Counts()
        self._normalised = Counts()
        self._coverage = CoverageCounts()
        self._by_subset: dict[str, _SubsetTotals] = defaultdict(_SubsetTotals)
        self._by_doc_type: dict[str, Counts] = defaultdict(Counts)
        self._by_field: dict[str, Counts] = defaultdict(Counts)
        self._coverage_by_field: dict[str, CoverageCounts] = defaultdict(CoverageCounts)
        self._confusion: dict[str, Counter[str]] = defaultdict(Counter)

    def add(self, result: DocumentResult, subset: str) -> DocumentEvaluation:
        """Score one result of evaluation set `subset` against its reference and add it to the totals."""
        reference = self._references.load(result.document)
        comparisons = compare(reference.data, result.data, strict_equal)
        checks = self._check_values(reference, result)
        evaluation = DocumentEvaluation(
            expected_type=reference.doc_type,
            predicted_type=result.doc_type,
            strict=total_counts(comparisons),
            normalised=total_counts(compare(reference.data, result.data, normalised_equal)),
            coverage=CoverageCounts.of(checks),
            errors=tuple(_field_error(result, comparison) for comparison in comparisons if not comparison.match),
        )
        self._accumulate(evaluation, comparisons, checks)
        self._by_subset[subset].add(evaluation, result)
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
            coverage=Coverage.from_counts(self._coverage),
            conversion_s=_mean_seconds([seconds for totals in self._by_subset.values() for seconds in totals.conversion_s]),
            by_subset={name: totals.scores() for name, totals in self._by_subset.items()},
            by_doc_type={label: Scores.from_counts(counts) for label, counts in sorted(self._by_doc_type.items())},
            by_field={path: Scores.from_counts(counts) for path, counts in sorted(self._by_field.items())},
            coverage_by_field={path: Coverage.from_counts(counts)
                               for path, counts in sorted(self._coverage_by_field.items())},
            classification=ClassificationScores(
                accuracy=round(self.classification_accuracy, 4),
                confusion={label: dict(sorted(row.items())) for label, row in sorted(self._confusion.items())},
            ),
        )

    def _check_values(self, reference: Reference, result: DocumentResult) -> list[ValueCheck]:
        """Coverage checks of the reference values; without extracted text, every value is missing."""
        if reference.doc_type is None:
            return []
        text = result.extracted.text if result.extracted is not None else ""
        return check_values(reference.data, self._doc_types[reference.doc_type].output_schema, text)

    def _accumulate(self, evaluation: DocumentEvaluation, comparisons: list[LeafComparison],
                    checks: list[ValueCheck]) -> None:
        expected_type = evaluation.expected_type or NO_TYPE
        self._documents += 1
        self._strict += evaluation.strict
        self._normalised += evaluation.normalised
        self._coverage += evaluation.coverage
        self._by_doc_type[expected_type] += evaluation.strict
        self._confusion[expected_type][evaluation.predicted_type or NO_TYPE] += 1
        for comparison in comparisons:
            self._by_field[comparison.path] += comparison.counts()
        for check in checks:
            self._coverage_by_field[check.path] += CoverageCounts.of([check])


def _field_error(result: DocumentResult, comparison: LeafComparison) -> FieldError:
    return FieldError(
        document=result.document.label, path=comparison.path,
        expected=comparison.expected, predicted=comparison.predicted,
    )


def _mean_seconds(seconds: list[float]) -> float | None:
    return round(fmean(seconds), 2) if seconds else None


def format_scores(scores: EvalScores) -> str:
    """Multi-line plain-text summary of the scores."""
    worst_fields = sorted(scores.by_field.items(), key=lambda item: (item[1].f1, -item[1].fn))[:WORST_FIELDS_SHOWN]
    least_present = sorted(((path, coverage) for path, coverage in scores.coverage_by_field.items()
                            if coverage.present < coverage.total),
                           key=lambda item: (item[1].share, -item[1].total))[:WORST_FIELDS_SHOWN]
    return "\n".join([
        f"Documents: {scores.documents}   classification accuracy: {scores.classification.accuracy:.3f}",
        f"F1 strict: {scores.strict.f1:.3f} (P {scores.strict.precision:.3f}, R {scores.strict.recall:.3f})"
        f"   normalised: {scores.normalised.f1:.3f}",
        "By evaluation set (strict; FP on negatives = invented values; conversion = cold seconds per document):",
        *(_format_subset(name, subset) for name, subset in scores.by_subset.items()),
        "Reference values present in the extracted text (ceiling for extraction):",
        *(f"  {name:16s} " + "  ".join(f"{doc_type} {coverage.share:.3f} ({coverage.present}/{coverage.total})"
                                       for doc_type, coverage in subset.coverage.items())
          for name, subset in scores.by_subset.items() if subset.coverage),
        "By document type (strict):",
        *(f"  {label:16s} F1 {s.f1:.3f}  TP {s.tp:4d}  FP {s.fp:4d}  FN {s.fn:4d}"
          for label, s in scores.by_doc_type.items()),
        f"Worst {WORST_FIELDS_SHOWN} fields (strict):",
        *(f"  {path:50s} F1 {s.f1:.3f}  FP {s.fp:4d}  FN {s.fn:4d}" for path, s in worst_fields),
        "Fields least present in the text:",
        *(f"  {path:50s} {coverage.share:.3f} ({coverage.present}/{coverage.total})" for path, coverage in least_present),
    ])


def _format_subset(name: str, subset: SubsetScores) -> str:
    conversion = (f"  conversion {subset.conversion_s:5.2f} s (max {subset.max_conversion_s:.1f})"
                  if subset.conversion_s is not None else "")
    return (f"  {name:16s} documents {subset.documents:4d}  class. {subset.classification_accuracy:.3f}"
            f"  F1 {subset.strict.f1:.3f}  FP {subset.strict.fp:4d}  FN {subset.strict.fn:4d}{conversion}")
