"""Pydantic models of the output JSON, built from each document type's schema.json.

Every leaf is normalised by its value type (src/value_types.py) and is null when unknown, so any
values put into a model serialise to the organiser's exact structure and formats. Keys that are
not Python identifiers ("przez-pelnomocnika") become aliases.
"""

from typing import Annotated, Any

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, create_model

from src.doc_types import DocTypeConfig
from src.value_types import VALUE_TYPES


class OutputObject(BaseModel):
    """Base of the generated models: schema keys only, normalised also on assignment."""

    model_config = ConfigDict(extra="forbid", validate_by_name=True, validate_by_alias=True,
                              validate_assignment=True, serialize_by_alias=True)


def build_output_model(doc_type: DocTypeConfig) -> type[OutputObject]:
    """The output model of a document type."""
    return _object_model(doc_type.name, doc_type.output_schema)


def skeleton(schema: dict[str, Any]) -> dict[str, Any]:
    """The output structure with every value null and one element per list, as in the organiser's templates."""
    return _skeleton(schema)


def _object_model(name: str, schema: dict[str, Any]) -> type[OutputObject]:
    fields = {key.replace("-", "_"): _field(f"{name}_{key}", key, template) for key, template in schema.items()}
    return create_model(name.title().replace("_", ""), __base__=OutputObject, **fields)


def _field(name: str, key: str, template: Any) -> tuple[Any, Any]:
    annotation = _annotation(name, template)
    match template:
        case dict():
            return annotation, Field(default_factory=annotation, alias=key)
        case list():
            return annotation, Field(default_factory=list, alias=key)
        case _:
            return annotation, Field(default=None, alias=key)


def _annotation(name: str, template: Any) -> Any:
    match template:
        case dict():
            return _object_model(name, template)
        case [element]:
            return list[_annotation(name, element)]
        case _:
            value_type = VALUE_TYPES[template]
            return Annotated[value_type.python_type | None, BeforeValidator(value_type.normalize)]


def _skeleton(template: Any) -> Any:
    match template:
        case dict():
            return {key: _skeleton(value) for key, value in template.items()}
        case [element]:
            return [_skeleton(element)]
        case _:
            return None
