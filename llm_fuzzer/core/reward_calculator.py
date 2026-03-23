#!/usr/bin/env python3
"""
Reward Calculator (v2 — Impact-Based)

Reward = A1·r_impact + A2·r_new_violations + A3·r_novelty
       - A4·r_repeat + bonus_edge + bonus_mutation_applied

Where:
- r_impact: how much the mutation changed simulator output vs baseline
- r_new_violations: bonus for triggering FrameError, MACError, InvalidVL (beyond policing)
- r_novelty: reward for exploring new (VL, rule, parameter) combinations
- r_repeat: penalty for repeating recent tests
- bonus_edge: bonus for edge-case strategies
- bonus_mutation_applied: bonus when mutation wasn't clamped/ignored
"""

import pandas as pd
from typing import Dict, Any, Optional


BASELINE_RECEIVED = 3559
BASELINE_FORWARDED = 1757
BASELINE_POLICING = 1802
BASELINE_ES_REJECTED = 130
BASELINE_ES_DUPLICATES = 1644


class RewardCalculator:

    def __init__(
        self,
        lambda_impact: float = 0.5,
        lambda_new_violations: float = 0.6,
        lambda_novelty: float = 0.3,
        lambda_repeat: float = 0.2,
        bonus_edge_max: float = 0.5,
        bonus_mutation_applied: float = 0.2,
        penalty_overuse: float = 0.5,
        bonus_new_rule: float = 1.0,
        overuse_threshold: int = 3
    ):
        self.lambda_impact = lambda_impact
        self.lambda_new_violations = lambda_new_violations
        self.lambda_novelty = lambda_novelty
        self.lambda_repeat = lambda_repeat
        self.bonus_edge_max = bonus_edge_max
        self.bonus_mutation_applied = bonus_mutation_applied
        self.penalty_overuse = penalty_overuse
        self.bonus_new_rule = bonus_new_rule
        self.overuse_threshold = overuse_threshold

    def calculate(
        self,
        metrics: Dict[str, Any],
        strategy: Dict[str, Any],
        history: Optional[pd.DataFrame] = None,
        coverage_pct: float = 0.0
    ) -> Dict[str, Any]:
        r_impact = self._compute_impact_score(metrics)
        r_new_violations = self._compute_new_violations_score(metrics)
        r_novelty = self._compute_novelty_score(strategy, history)
        r_repeat = self._compute_repeat_penalty(strategy, history)
        bonus_edge = self._compute_edge_bonus(strategy, metrics)
        bonus_mutation = self._compute_mutation_bonus(metrics)
        penalty_overuse = self._compute_overuse_penalty(strategy, history, coverage_pct)
        bonus_new_rule = self._compute_new_rule_bonus(strategy, history)

        reward = (
            self.lambda_impact * r_impact
            + self.lambda_new_violations * r_new_violations
            + self.lambda_novelty * r_novelty
            - self.lambda_repeat * r_repeat
            + bonus_edge
            + bonus_mutation
            - penalty_overuse
            + bonus_new_rule
        )

        breakdown = self._build_breakdown(
            reward, r_impact, r_new_violations, r_novelty,
            r_repeat, bonus_edge, bonus_mutation,
            penalty_overuse, bonus_new_rule
        )

        return {
            "reward": reward,
            "components": {
                "r_impact": r_impact,
                "r_new_violations": r_new_violations,
                "r_novelty": r_novelty,
                "r_repeat": r_repeat,
                "bonus_edge": bonus_edge,
                "bonus_mutation": bonus_mutation,
                "penalty_overuse": penalty_overuse,
                "bonus_new_rule": bonus_new_rule,
            },
            "breakdown": breakdown
        }

    def _compute_impact_score(self, metrics: Dict[str, Any]) -> float:
        """How much did the mutation change simulator output vs baseline?"""
        recv = metrics.get("frames_received", 0)
        fwd = metrics.get("frames_forwarded", 0)
        pol = metrics.get("frames_dropped_policing", 0)
        es_rej = metrics.get("es_frames_rejected", 0)
        es_dup = metrics.get("es_duplicates_discarded", 0)

        if recv == 0:
            return 0.0

        delta_recv = abs(recv - BASELINE_RECEIVED) / max(BASELINE_RECEIVED, 1)
        delta_fwd = abs(fwd - BASELINE_FORWARDED) / max(BASELINE_FORWARDED, 1)
        delta_pol = abs(pol - BASELINE_POLICING) / max(BASELINE_POLICING, 1)
        delta_es_rej = abs(es_rej - BASELINE_ES_REJECTED) / max(BASELINE_ES_REJECTED, 1)
        delta_es_dup = abs(es_dup - BASELINE_ES_DUPLICATES) / max(BASELINE_ES_DUPLICATES, 1)

        all_deltas = [delta_recv, delta_fwd, delta_pol, delta_es_rej, delta_es_dup]
        return min(1.0, sum(all_deltas) / len(all_deltas) * 5.0)

    def _compute_new_violations_score(self, metrics: Dict[str, Any]) -> float:
        """Bonus for triggering non-baseline drop categories (switch + ES)."""
        score = 0.0
        fe = metrics.get("frames_dropped_frame_error", 0)
        mac = metrics.get("frames_dropped_mac_error", 0)
        inv = metrics.get("frames_dropped_invalid_vl", 0)
        es_rej = metrics.get("es_frames_rejected", 0)

        if fe > 0:
            score += 0.3
        if mac > 0:
            score += 0.3
        if inv > 0:
            score += 0.1
        if es_rej > BASELINE_ES_REJECTED:
            score += 0.3
        return min(1.0, score)

    def _compute_novelty_score(
        self, strategy: Dict[str, Any], history: Optional[pd.DataFrame]
    ) -> float:
        if history is None or len(history) == 0:
            return 1.0

        target_vl = strategy.get("target_vl")
        protocol_rule = strategy.get("protocol_rule")
        mutation_type = strategy.get("mutation_type", "")
        bag_value = strategy.get("bag_value")
        frame_size = strategy.get("frame_size")

        key = (target_vl, protocol_rule, mutation_type, bag_value, frame_size)

        match_count = 0
        for _, row in history.iterrows():
            row_key = (
                row.get("target_vl"),
                row.get("protocol_rule"),
                row.get("mutation_type", ""),
                row.get("bag_value"),
                row.get("frame_size"),
            )
            if row_key == key:
                match_count += 1

        return max(0.0, 1.0 - match_count / 5.0)

    def _compute_repeat_penalty(
        self, strategy: Dict[str, Any], history: Optional[pd.DataFrame]
    ) -> float:
        if history is None or len(history) == 0:
            return 0.0

        recent = history.tail(5)
        target_vl = strategy.get("target_vl")
        protocol_rule = strategy.get("protocol_rule")

        matches = 0
        for _, row in recent.iterrows():
            if (row.get("target_vl") == target_vl
                    and row.get("protocol_rule") == protocol_rule):
                matches += 1

        return min(1.0, matches / 3.0)

    def _compute_edge_bonus(
        self, strategy: Dict[str, Any], metrics: Dict[str, Any]
    ) -> float:
        bonus = 0.0
        strategy_type = strategy.get("strategy", "normal")
        if strategy_type in ("edge-case", "attack", "adversarial"):
            bonus += 0.2

        if metrics.get("frames_dropped_invalid_vl", 0) > 0:
            bonus += 0.15
        if metrics.get("frames_dropped_frame_error", 0) > 0:
            bonus += 0.15

        return min(bonus, self.bonus_edge_max)

    def _compute_mutation_bonus(self, metrics: Dict[str, Any]) -> float:
        """Reward when the mutation was actually applied (not clamped/ignored)."""
        clamp = metrics.get("mutation_clamp_count", 0)
        payload_applied = abs(metrics.get("mutation_payload_applied", 0))
        mac_spoof = metrics.get("mutation_mac_spoof_count", 0)
        tx_drops = metrics.get("mutation_tx_prob_drops", 0)

        if clamp > 0:
            return -0.1

        if payload_applied > 0 or mac_spoof > 0 or tx_drops > 0:
            return self.bonus_mutation_applied

        return 0.0

    def _compute_overuse_penalty(
        self, strategy: Dict[str, Any], history: Optional[pd.DataFrame],
        coverage_pct: float = 0.0
    ) -> float:
        """Penalty for reusing the same mutation_type, reduced when coverage is high.

        When coverage > 90%, most rules are explored so re-testing with different
        parameters is expected.  The penalty scales down to let the LLM deepen
        its investigation instead of being punished for having no new rules left.
        """
        if history is None or len(history) == 0:
            return 0.0

        mutation_type = strategy.get("mutation_type", "")
        if "mutation_type" not in history.columns:
            return 0.0

        times_used = int((history["mutation_type"] == mutation_type).sum())
        if times_used < self.overuse_threshold:
            return 0.0

        excess = times_used - self.overuse_threshold + 1
        raw_penalty = min(self.penalty_overuse * excess, 2.0)

        if coverage_pct >= 90:
            raw_penalty *= 0.2
        elif coverage_pct >= 70:
            raw_penalty *= 0.5

        return raw_penalty

    def _compute_new_rule_bonus(
        self, strategy: Dict[str, Any], history: Optional[pd.DataFrame]
    ) -> float:
        """Large bonus for testing a protocol_rule never seen before in history."""
        if history is None or len(history) == 0:
            return self.bonus_new_rule

        protocol_rule = strategy.get("protocol_rule", strategy.get("mutation_type", ""))
        if "protocol_rule" not in history.columns:
            return self.bonus_new_rule

        seen_rules = set(history["protocol_rule"].dropna().unique())
        if protocol_rule not in seen_rules:
            return self.bonus_new_rule
        return 0.0

    def _build_breakdown(
        self, reward, r_impact, r_new_violations, r_novelty,
        r_repeat, bonus_edge, bonus_mutation,
        penalty_overuse=0.0, bonus_new_rule=0.0
    ) -> str:
        lines = [
            "Reward Breakdown:",
            f"  Total: {reward:.3f}",
            "",
            "Components:",
            f"  + {self.lambda_impact:.1f} x impact ({r_impact:.2f}) = {self.lambda_impact * r_impact:.3f}",
            f"  + {self.lambda_new_violations:.1f} x new_violations ({r_new_violations:.2f}) = {self.lambda_new_violations * r_new_violations:.3f}",
            f"  + {self.lambda_novelty:.1f} x novelty ({r_novelty:.2f}) = {self.lambda_novelty * r_novelty:.3f}",
            f"  - {self.lambda_repeat:.1f} x repeat ({r_repeat:.2f}) = {-self.lambda_repeat * r_repeat:.3f}",
            f"  + edge bonus = {bonus_edge:.3f}",
            f"  + mutation bonus = {bonus_mutation:.3f}",
            f"  - overuse penalty = {-penalty_overuse:.3f}",
            f"  + new rule bonus = {bonus_new_rule:.3f}",
        ]
        return "\n".join(lines)
