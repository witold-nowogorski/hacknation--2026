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
from src.extraction.provenance import SNIPPET_MARGIN, Extraction, Found, Source, ValueSource
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
        self.classify = [(value, regexes, _compile(regexes)) for value, regexes in rule.classify.items()]
        pattern = rule.pattern or value_type.pattern
        self.pattern = re.compile(pattern) if pattern else None
        self.rivals: list[_Field] = []  # typed fields of the same value type and sections; their labels end this window

    def found(self, raw: Any, source: Source, detail: str, span: Span | None = None) -> Found | None:
        """The normalised value as a Found, or None if it cannot be read."""
        value = self.value_type.normalize(raw)
        return Found(value, source, detail, span) if value is not None else None


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

    def apply(self, text: str) -> dict[str, list[Found]]:
        """Values of every field with a rule, in rule order; multi-valued fields may have several."""
        folded = fold(text)
        spans = self.spans(text)
        values: dict[str, list[Found]] = {}
        for field in self._fields:
            values[field.path] = self._field_values(field, text, folded, spans, values)
        return values

    def derive(self, values: dict[str, list[Found]]) -> None:
        """Recompute lookup fields, after their source fields changed (e.g. by an LLM task)."""
        for field in self._fields:
            if field.rule.lookup:
                values[field.path] = self._field_values(field, "", "", {}, values)

    def _field_values(self, field: _Field, text: str, folded: str, spans: dict[str, Span | None],
                      values: dict[str, list[Found]]) -> list[Found]:
        rule = field.rule
        if any(str(value) not in {str(found.value) for found in values[path]} for path, value in rule.only_if.items()):
            return []
        if rule.lookup:
            source = values[rule.lookup.source]
            looked_up = source and field.found(rule.lookup.table.get(str(source[0].value)), "derived",
                                               f"lookup by {rule.lookup.source}", source[0].span)
            return [looked_up] if looked_up else []
        searched = [spans[name] for name in rule.sections] if rule.sections else [(0, len(text))]
        excluded = {found.value for path in rule.exclude for found in values[path]}
        for span in filter(None, searched):
            if found := self._read(field, text, folded, span, excluded):
                unique = _first_of_each_value(found)
                return unique if rule.multiple != "no" else unique[:1]
        if rule.nth is not None:
            for span in filter(None, searched):
                candidates = [item for item in self._values_after(field, text, folded, *span, f"candidate {rule.nth}")
                              if item.value not in excluded]
                if len(candidates) > rule.nth:
                    return [candidates[rule.nth]]
        default = field.found(rule.default, "default", "default")
        return [default] if default else []

    def _read(self, field: _Field, text: str, folded: str, span: Span, excluded: set[Any]) -> list[Found]:
        start, end = span
        if field.classify:
            hits = [(match.start(), order, value, regex, match.span())
                    for order, (value, sources, compiled) in enumerate(field.classify)
                    for regex, pattern in zip(sources, compiled) if (match := pattern.search(folded, start, end))]
            if not hits:
                return []
            _, _, value, regex, match_span = min(hits)
            found = field.found(value, "rule", f"classify {value}: {regex}", match_span)
            return [found] if found else []

        def values_after(position: int, stop: int, detail: str) -> list[Found]:
            found = [item for item in self._values_after(field, text, folded, position, stop, detail)
                     if item.value not in excluded]
            return found if field.rule.multiple != "no" else found[:1]

        if not field.labels:
            where = "section" if field.rule.sections else "document"
            return values_after(start, end, f"pattern in {where}" if field.rule.pattern else f"first in {where}")
        hits = [(match, label) for label, regex in zip(field.rule.labels, field.labels)
                for match in regex.finditer(folded, start, end)]
        if field.rule.multiple == "occurrences":  # each label match reads up to the next one (stacked signature lines)
            ordered = sorted(hits, key=lambda hit: hit[0].start())
            stops = [match.start() for match, _ in ordered[1:]] + [end]
            return [item for (match, label), stop in zip(ordered, stops)
                    for item in values_after(match.end(), self._limit(field, folded, match.end(), stop), f"label {label}")]
        for match, label in hits:  # labels in their configured order, then by position
            if found := values_after(match.end(), self._limit(field, folded, match.end(), end), f"label {label}"):
                return found
        return []

    @staticmethod
    def _limit(field: _Field, folded: str, position: int, end: int) -> int:
        """End of the window after a label: its size, the section end or the next label of a rival field."""
        rival_labels = [match.start() for rival in field.rivals for regex in rival.labels
                        if (match := regex.search(folded, position, end))]
        return min([end, position + field.rule.window, *rival_labels])

    @staticmethod
    def _values_after(field: _Field, text: str, folded: str, start: int, end: int, detail: str) -> list[Found]:
        """All values in text[start:end] up to the first cut."""
        if field.pattern:
            end = _cut(field, folded, start, end)
            found = []
            for match in field.pattern.finditer(text, start, end):
                if field.rule.pattern is None:  # a value type's pattern: the whole match is the value
                    raw, span = match.group(), match.span()
                else:
                    group = next((index for index, group in enumerate(match.groups(), 1) if group is not None), 0)
                    raw, span = match.group(group), match.span(group)
                if item := field.found(raw, "rule", detail, span):
                    found.append(item)
            return found
        raw, span = _free_text(field, text, folded, start, end)
        item = field.found(raw, "rule", detail, span)
        return [item] if item else []


def _first_of_each_value(found: list[Found]) -> list[Found]:
    seen, unique = set(), []
    for item in found:
        if item.value not in seen:
            seen.add(item.value)
            unique.append(item)
    return unique


def _cut(field: _Field, folded: str, start: int, end: int) -> int:
    return min([end, *(match.start() for regex in field.cut if (match := regex.search(folded, start, end)))])


def _free_text(field: _Field, text: str, folded: str, start: int, end: int) -> tuple[str, Span]:
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
    value = " ".join(kept).rstrip(TRAILING_SEPARATORS)
    return value, (position, position + sum(len(line) + 1 for line in kept) - 1)


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
    then, if an LLM is given, lets the type's LLM tasks refine them. Every value keeps its source.

    Models and rules are built for all types up front, so an invalid config fails when the
    pipeline is built. A type without field rules yields the complete structure with null values.
    """

    def __init__(self, doc_types: Mapping[str, DocTypeConfig], llm: LlmClient | None = None) -> None:
        self._models: dict[str, type[OutputObject]] = {
            name: build_output_model(doc_type) for name, doc_type in doc_types.items()}
        self._rules = {name: DocumentRules(doc_type) for name, doc_type in doc_types.items()}
        self._tasks = {name: LlmTasks(doc_type, llm) for name, doc_type in doc_types.items()} if llm else {}

    def extract(self, document: ExtractedDocument, doc_type: DocTypeConfig) -> Extraction:
        text = document.text
        rules = self._rules[doc_type.name]
        values = rules.apply(text)
        if tasks := self._tasks.get(doc_type.name):
            tasks.apply(text, rules.spans(text), values)
            rules.derive(values)
        data = skeleton(doc_type.output_schema)
        for path, found in values.items():
            place_values(data, doc_type.output_schema, path, [item.value for item in found])
        data = self._models[doc_type.name].model_validate(data).model_dump()
        pages = _page_starts(document)
        sources = tuple(_value_source(_indexed_path(path, index), item, text, pages)
                        for path, found in values.items() for index, item in enumerate(found))
        return Extraction(data, sources)


def _page_starts(document: ExtractedDocument) -> list[tuple[int, int]]:
    """(offset in document.text, page) of every block, in text order."""
    starts, offset = [], 0
    for block in document.blocks:
        starts.append((offset, block.page))
        offset += len(block.render()) + 1  # blocks are joined by newlines
    return starts


def _indexed_path(path: str, index: int) -> str:
    """Field path with list positions: the innermost list gets `index`, outer lists 0."""
    keys = path.split(".")
    innermost = max((position for position, key in enumerate(keys) if key.endswith("[]")), default=None)
    return ".".join(key.replace("[]", f"[{index if position == innermost else 0}]") for position, key in enumerate(keys))


def _value_source(path: str, found: Found, text: str, pages: list[tuple[int, int]]) -> ValueSource:
    if found.span is None:
        return ValueSource(path, found.value, found.source, found.detail, page=None, snippet=None)
    start, end = found.span
    page = next((page for offset, page in reversed(pages) if offset <= start), None)
    snippet = " ".join(text[max(0, start - SNIPPET_MARGIN):end + SNIPPET_MARGIN].split())
    return ValueSource(path, found.value, found.source, found.detail, page, snippet)
