from __future__ import annotations

from enum import Enum


class StepStatus(Enum):
    OK = "ok"
    FAILED = "failed"
    INCONCLUSIVE = "inconclusive"
