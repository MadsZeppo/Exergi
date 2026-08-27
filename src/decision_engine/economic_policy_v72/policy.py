"""Cost-aware multi-arm policy with support, uncertainty and governance gates."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

import numpy as np

from .contracts import ActionDisposition, EconomicPolicyDataset, FloatArray, PolicyDecision
from .models import CrossFittedOutcomeModel


@dataclass
class EconomicPolicyEngine:
    model: CrossFittedOutcomeModel
    materiality: float = 0.0
    minimum_arm_rows: int = 40
    confidence_z: float = 1.6448536269514722
    residual_se_: FloatArray | None = None
    arm_rows_: FloatArray | None = None
    bau_action_: int | None = None

    def fit(self, data: EconomicPolicyDataset) -> FloatArray:
        oof_gross = self.model.fit_predict_oof(
            data.features, data.action, data.monetary_outcome, data.arms
        )
        residual_se = np.zeros(data.arms, dtype=float)
        rows = np.zeros(data.arms, dtype=float)
        for arm in range(data.arms):
            mask = data.action == arm
            rows[arm] = mask.sum()
            residual = data.monetary_outcome[mask] - oof_gross[mask, arm]
            residual_se[arm] = (
                float(np.std(residual, ddof=1) / np.sqrt(max(mask.sum(), 1)))
                if mask.sum() > 1
                else float("inf")
            )
        self.residual_se_, self.arm_rows_, self.bau_action_ = residual_se, rows, data.bau_action
        return oof_gross

    def decide(
        self, features: FloatArray, costs: FloatArray, allowed: np.ndarray
    ) -> PolicyDecision:
        if self.residual_se_ is None or self.arm_rows_ is None or self.bau_action_ is None:
            raise RuntimeError("engine is not fitted")
        gross = self.model.predict_actions(features)
        if gross.shape != costs.shape or allowed.shape != costs.shape:
            raise ValueError("features, costs and allowed action matrices do not align")
        net = gross - costs
        net = np.where(allowed, net, -np.inf)
        chosen = np.argmax(net, axis=1).astype(np.int64)
        bau = self.bau_action_
        point = net[np.arange(len(net)), chosen] - net[:, bau]
        uncertainty = self.confidence_z * np.sqrt(
            self.residual_se_[chosen] ** 2 + self.residual_se_[bau] ** 2
        )
        lower = point - uncertainty
        supported = self.arm_rows_[chosen] >= self.minimum_arm_rows
        disposition = np.full(len(net), ActionDisposition.BAU.value, dtype="U8")
        reason = np.full(len(net), "BAU_BEST_OR_NO_GAIN", dtype="U40")
        non_bau = chosen != bau
        test = non_bau & supported & (point > self.materiality) & (lower <= self.materiality)
        act = non_bau & supported & (lower > self.materiality)
        unsupported = non_bau & ~supported
        disposition[test] = ActionDisposition.TEST.value
        reason[test] = "POSITIVE_BUT_UNCERTAIN"
        disposition[act] = ActionDisposition.ACT.value
        reason[act] = "SUPPORTED_LOWER_BOUND_POSITIVE"
        disposition[unsupported] = ActionDisposition.AVOID.value
        reason[unsupported] = "INSUFFICIENT_ARM_SUPPORT"
        chosen[unsupported | (non_bau & ~(test | act))] = bau
        payload = {
            "model": self.model.name,
            "materiality": self.materiality,
            "minimum_arm_rows": self.minimum_arm_rows,
            "confidence_z": self.confidence_z,
        }
        policy_hash = hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        return PolicyDecision(
            chosen, disposition, net, point, lower, supported, reason, policy_hash
        )
