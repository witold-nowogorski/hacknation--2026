"""Pipeline configuration: everything that defines one experiment, saved with its evaluation report."""

from pydantic import BaseModel, ConfigDict, Field

from src.text_extraction.models import ConversionSettings


class LlmSettings(BaseModel):
    """OpenAI-compatible LLM endpoint; the API key is read from the environment, never stored here."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    base_url: str
    model: str
    api_key_env: str = "LLM_API_KEY"
    temperature: float = 0.0


class PipelineConfig(BaseModel):
    """Settings of one pipeline variant. Each stage owns its settings model; this one composes them."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]*$")  # used in run and report file names
    description: str = ""  # what this variant tests
    conversion: ConversionSettings = ConversionSettings()
    llm: LlmSettings | None = None  # None = rules only
