"""An experiment: a pipeline class with the config it is built from."""

from collections.abc import Sequence
from dataclasses import dataclass

from src.pipeline.config import PipelineConfig
from src.pipeline.pipeline import Pipeline
from src.workspace import Workspace


@dataclass(frozen=True, slots=True)
class Experiment:
    """One pipeline variant; its config is saved with every evaluation report."""

    pipeline_class: type[Pipeline]
    config: PipelineConfig

    @property
    def name(self) -> str:
        return self.config.name

    def build_pipeline(self, workspace: Workspace) -> Pipeline:
        return self.pipeline_class.from_config(self.config, workspace)


def select_experiments(experiments: Sequence[Experiment], names: Sequence[str]) -> list[Experiment]:
    """Experiments with the given names, in that order; names must be unique and defined."""
    by_name: dict[str, Experiment] = {}
    for experiment in experiments:
        if experiment.name in by_name:
            raise ValueError(f"Duplicate experiment name: {experiment.name!r}")
        by_name[experiment.name] = experiment

    unknown = [name for name in names if name not in by_name]
    if unknown:
        raise ValueError(f"Unknown experiments {unknown}; defined: {sorted(by_name)}")
    return [by_name[name] for name in names]
