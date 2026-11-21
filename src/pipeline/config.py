"""Pipeline configuration: everything that defines one experiment, saved with its evaluation report."""

from pydantic import BaseModel, ConfigDict, Field

from src.classification.keyword_classifier import KeywordClassifierSettings
from src.inference.llm_client import LlmSettings
from src.text_extraction.models import ConversionSettings


class PipelineConfig(BaseModel):
    """Settings of one pipeline variant. Each stage owns its settings model; this one composes them."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]*$")  # used in run and report file names
    description: str = ""  # what this variant tests
    conversion: ConversionSettings = ConversionSettings()
    classification: KeywordClassifierSettings = KeywordClassifierSettings()
    llm: LlmSettings | None = None  # None = rules only
