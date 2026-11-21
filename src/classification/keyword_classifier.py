"""Keyword classifier: weighted phrases from each type's config, searched in the first pages."""

import re
from collections.abc import Mapping

from pydantic import BaseModel, ConfigDict

from src.classification.classifier import Classification, Classifier
from src.doc_types import ClassificationRules, DocTypeConfig
from src.text_extraction.models import ExtractedDocument

WHITESPACE = re.compile(r"\s+")


class KeywordClassifierSettings(BaseModel):
    """Experiment knobs of the keyword classifier (keywords themselves are in config/doc_types)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    pages: int = 1  # titles and addressees are at the top of the first page


class KeywordClassifier(Classifier):
    """Scores every type by the summed weights of its phrases found in the text.

    The best type wins if it reaches its `min_score` and is not tied with another type.
    Matching ignores case and all whitespace, so spaced-out titles ("P E Ł N O M O C N I C T W O")
    and phrases broken across lines still match.
    """

    def __init__(self, doc_types: Mapping[str, DocTypeConfig], settings: KeywordClassifierSettings) -> None:
        self._rules = {name: doc_type.classification for name, doc_type in sorted(doc_types.items())}
        self._settings = settings

    def classify(self, document: ExtractedDocument) -> Classification:
        text = _compact("\n".join(block.render() for block in document.blocks if block.page <= self._settings.pages))
        scores = {name: _score(text, rules) for name, rules in self._rules.items()}
        best_score = max(scores.values())
        best_types = [name for name, score in scores.items() if score == best_score]
        if len(best_types) > 1 or best_score < self._rules[best_types[0]].min_score:
            return Classification(doc_type=None, scores=scores)
        return Classification(doc_type=best_types[0], scores=scores)


def _score(compact_text: str, rules: ClassificationRules) -> float:
    return sum(weight for phrase, weight in rules.keywords.items() if _compact(phrase) in compact_text)


def _compact(text: str) -> str:
    return WHITESPACE.sub("", text).casefold()
