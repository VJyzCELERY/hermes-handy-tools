"""Small public value objects used by integrations."""

from dataclasses import dataclass
from enum import StrEnum


class Phase(StrEnum):
    """Semantic workflow phases."""

    ISSUE = "issue"
    PLAN = "plan"
    IMPLEMENT = "implement"
    IMPLEMENTATION_REVIEW = "implementation_review"
    REMEDIATION = "remediation"
    MERGE_READY = "merge_ready"


@dataclass(frozen=True, slots=True)
class ReviewBinding:
    """Review evidence identity that becomes stale on any drift."""

    head: str
    base: str
    diff: str


@dataclass(frozen=True, slots=True)
class Checkpoint:
    """Exact resumable action for a phase run."""

    phase: Phase
    next_action: str
