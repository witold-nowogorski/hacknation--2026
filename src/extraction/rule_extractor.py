"""Rule-based field extraction: the rules of config/doc_types/<type>/doc_type.toml applied to a text.

Labels, sections, cuts and classifications are matched against a folded copy of the text (lower
case, no Polish diacritics, same length), so they survive OCR losses and need no case variants.
Values are read from the original text at the same positions and normalised by their value type;
anything not found stays null. See `FieldRule` for how a field is read.
"""

import re
from collections.abc import Mapping
from typing import Any

from src.doc_types import DocTypeConfig, FieldRule, SectionRule, leaf_paths
from src.extraction.field_extractor import FieldExtractor
from src.extraction.output_model import OutputObject, build_output_model, skeleton
from src.extraction.llm_tasks import LlmTasks, Span
from src.inference.llm_client import LlmClient
from src.text_extraction.models import ExtractedDocument
from src.value_types import VALUE_TYPES, ValueType, fold, fold_diacritics

FLAGS = re.IGNORECASE | re.MULTILINE
LEADING_SEPARATORS = re.compile(r"[\s:|.\-–\"„“”]+")
TRAILING_SEPARATORS = " \t,;:|–-"



def _compile(regexes: list[str]) -> list[re.Pattern[str]]:
    return [re.compile(fold_diacritics(regex), FLAGS) for regex in regexes]


class _Section:
    def __init__(self, rule: SectionRule) -> None:
        self._start = _compile(rule.start)
        self._end = _compile(rule.end)
        self._max_chars = rule.max_chars

    def span(self, folded: str) -> Span | None:
        """From the end of the earliest start match to the earliest end match; None if it does not start."""
        begin = 0
        if self._start:
            starts = [match for regex in self._start if (match := regex.search(folded))]
            if not starts:
                return None
            begin = min(starts, key=lambda match: match.start()).end()
        ends = [match.start() for regex in self._end if (match := regex.search(folded, begin))]
        stop = min(ends, default=len(folded))
        return begin, min(stop, begin + self._max_chars) if self._max_chars else stop


class _Field:
    """One field's compiled rule."""

    def __init__(self, path: str, rule: FieldRule, value_type: ValueType) -> None:
        self.path = path
        self.rule = rule
        self.value_type = value_type
        self.labels = _compile(rule.labels)
        self.cut = _compile(rule.cut)
        self.skip = _compile(rule.skip)
        self.classify = [(value, _compile(regexes)) for value, regexes in rule.classify.items()]
        pattern = rule.pattern or value_type.pattern
        self.pattern = re.compile(pattern) if pattern else None
        self.rivals: list[_Field] = []  # typed fields of the same value type and sections; their labels end this window

    def normalise(self, raws: list[Any]) -> list[Any]:
        return [value for raw in raws if (value := self.value_type.normalize(raw)) is not None]


class DocumentRules:
    """The compiled sections and field rules of one document type."""

    def __init__(self, doc_type: DocTypeConfig) -> None:
        value_types = leaf_paths(doc_type.output_schema)
        self._sections = {name: _Section(rule) for name, rule in doc_type.sections.items()}
        self._fields = [_Field(path, rule, VALUE_TYPES[value_types[path]]) for path, rule in doc_type.fields.items()]
        for field in self._fields:  # typed values compete for candidates (two accounts); free texts do not
            if field.value_type.pattern:
                field.rivals = [other for other in self._fields if other is not field and other.labels
                                and other.value_type is field.value_type and other.rule.sections == field.rule.sections]

    def spans(self, text: str) -> dict[str, Span | None]:
        """Where each section is in the text (None: it does not start)."""
        folded = fold(text)
        return {name: section.span(folded) for name, section in self._sections.items()}

    def apply(self, text: str) -> dict[str, list[Any]]:
        """Normalised values of every field with a rule, in rule order; multi-valued fields may have several."""
        folded = fold(text)
        spans = self.spans(text)
        values: dict[str, list[Any]] = {}
        for field in self._fields:
            values[field.path] = self._field_values(field, text, folded, spans, values)
        return values

    def derive(self, values: dict[str, list[Any]]) -> None:
        """Recompute lookup fields, after their source fields changed (e.g. by an LLM task)."""
        for field in self._fields:
            if field.rule.lookup:
                values[field.path] = self._field_values(field, "", "", {}, values)

    def _field_values(self, field: _Field, text: str, folded: str, spans: dict[str, Span | None],
                      values: dict[str, list[Any]]) -> list[Any]:
        rule = field.rule
        if any(str(value) not in map(str, values[path]) for path, value in rule.only_if.items()):
            return []
        if rule.lookup:
            source = values[rule.lookup.source]
            return field.normalise([rule.lookup.table.get(str(source[0]))]) if source else []
        searched = [spans[name] for name in rule.sections] if rule.sections else [(0, len(text))]
        excluded = {value for path in rule.exclude for value in values[path]}
        for span in filter(None, searched):
            if found := self._read(field, text, folded, span, excluded):
                unique = list(dict.fromkeys(found))
                return unique if rule.multiple != "no" else unique[:1]
        if rule.nth is not None:
            for span in filter(None, searched):
                candidates = [value for value in self._values_after(field, text, folded, *span) if value not in excluded]
                if len(candidates) > rule.nth:
                    return [candidates[rule.nth]]
        return field.normalise([rule.default])

    def _read(self, field: _Field, text: str, folded: str, span: Span, excluded: set[Any]) -> list[Any]:
        start, end = span
        if field.classify:
            hits = [(match.start(), order, value) for order, (value, regexes) in enumerate(field.classify)
                    for regex in regexes if (match := regex.search(folded, start, end))]
            return field.normalise([min(hits)[2]]) if hits else []
        def values_after(position: int, stop: int) -> list[Any]:
            found = [value for value in self._values_after(field, text, folded, position, stop) if value not in excluded]
            return found if field.rule.multiple != "no" else found[:1]

        if not field.labels:
            return values_after(start, end)
        hits = [match for regex in field.labels for match in regex.finditer(folded, start, end)]
        if field.rule.multiple == "occurrences":  # each label match reads up to the next one (stacked signature lines)
            ordered = sorted(hits, key=lambda match: match.start())
            stops = [match.start() for match in ordered[1:]] + [end]
            return [value for hit, stop in zip(ordered, stops)
                    for value in values_after(hit.end(), self._limit(field, folded, hit.end(), stop))]
        for hit in hits:  # labels in their configured order, then by position
            if found := values_after(hit.end(), self._limit(field, folded, hit.end(), end)):
                return found
        return []

    @staticmethod
    def _limit(field: _Field, folded: str, position: int, end: int) -> int:
        """End of the window after a label: its size, the section end or the next label of a rival field."""
        rival_labels = [match.start() for rival in field.rivals for regex in rival.labels
                        if (match := regex.search(folded, position, end))]
        return min([end, position + field.rule.window, *rival_labels])

    @staticmethod
    def _values_after(field: _Field, text: str, folded: str, start: int, end: int) -> list[Any]:
        """All values in text[start:end] up to the first cut, normalised."""
        if field.pattern:
            end = _cut(field, folded, start, end)
            matches = field.pattern.finditer(text, start, end)
            if field.rule.pattern is None:  # a value type's pattern: the whole match is the value
                return field.normalise([match.group() for match in matches])
            return field.normalise([next((group for group in match.groups() if group is not None), match.group())
                                    for match in matches])
        return field.normalise([_free_text(field, text, folded, start, end)])


def _cut(field: _Field, folded: str, start: int, end: int) -> int:
    return min([end, *(match.start() for regex in field.cut if (match := regex.search(folded, start, end)))])


def _free_text(field: _Field, text: str, folded: str, start: int, end: int) -> str:
    """Text after a label: separators and `skip` prefixes dropped, up to the line end or a cut; wrapped lines joined."""
    position = start
    while prefix := LEADING_SEPARATORS.match(folded, position, end) or next(
            (match for regex in field.skip if (match := regex.match(folded, position, end))), None):
        if prefix.end() == position:
            break
        position = prefix.end()
    lines = text[position:_cut(field, folded, position, end)].split("\n")
    kept = [lines[0]]
    for line in lines[1:]:
        if not line[:1].islower():
            break
        kept.append(line)
    return " ".join(kept).rstrip(TRAILING_SEPARATORS)


def place_values(data: dict[str, Any], schema: dict[str, Any], path: str, values: list[Any]) -> None:
    """Write a field's values into the output structure; values of a multi-valued field fill its innermost list."""
    keys = path.split(".")
    innermost_list = max((index for index, key in enumerate(keys) if key.endswith("[]")), default=None)
    for value_index, value in enumerate(values):
        node, template = data, schema
        for index, key in enumerate(keys):
            name = key.removesuffix("[]")
            if index == len(keys) - 1 and not key.endswith("[]"):
                node[name] = value
                break
            if key.endswith("[]"):
                items, element = node[name], template[name][0]
                position = value_index if index == innermost_list else 0
                while len(items) <= position:
                    items.append(skeleton(element))
                node, template = items[position], element
            else:
                node, template = node[name], template[name]


class RuleExtractor(FieldExtractor):
    """Fills the output structure of a document type with the values its rules find in the text,
    then, if an LLM is given, lets the type's LLM tasks refine them.

    Models and rules are built for all types up front, so an invalid config fails when the
    pipeline is built. A type without field rules yields the complete structure with null values.
    """

    def __init__(self, doc_types: Mapping[str, DocTypeConfig], llm: LlmClient | None = None) -> None:
        self._models: dict[str, type[OutputObject]] = {
            name: build_output_model(doc_type) for name, doc_type in doc_types.items()}
        self._rules = {name: DocumentRules(doc_type) for name, doc_type in doc_types.items()}
        self._tasks = {name: LlmTasks(doc_type, llm) for name, doc_type in doc_types.items()} if llm else {}

    def extract(self, document: ExtractedDocument, doc_type: DocTypeConfig) -> dict[str, Any]:
        rules = self._rules[doc_type.name]
        values = rules.apply(document.text)
        if tasks := self._tasks.get(doc_type.name):
            tasks.apply(document.text, rules.spans(document.text), values)
            rules.derive(values)
        data = skeleton(doc_type.output_schema)
        for path, field_values in values.items():
            place_values(data, doc_type.output_schema, path, field_values)
        return self._models[doc_type.name].model_validate(data).model_dump()
