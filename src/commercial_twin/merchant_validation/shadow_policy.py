"""Non-acting policy recorder used before any real merchant assignment."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class ShadowDecision(BaseModel):
    model_config = ConfigDict(frozen=True)

    merchant_id: UUID
    decision_id: UUID
    decided_at: datetime
    action_family: str
    proposed_arm: str
    observable_inputs: dict[str, Any]
    reason_codes: tuple[str, ...]
    assignment_created: bool = False


class ShadowPolicy:
    """Records proposals and is structurally incapable of assigning treatment."""

    def __init__(self) -> None:
        self._records: list[ShadowDecision] = []

    def record(self, decision: ShadowDecision) -> None:
        if decision.decided_at.tzinfo is None:
            raise ValueError("decided_at must be timezone-aware")
        if decision.assignment_created:
            raise ValueError("shadow mode cannot create assignments")
        self._records.append(decision)

    @property
    def records(self) -> tuple[ShadowDecision, ...]:
        return tuple(self._records)

