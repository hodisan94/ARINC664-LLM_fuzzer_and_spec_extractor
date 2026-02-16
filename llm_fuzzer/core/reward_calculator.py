#!/usr/bin/env python3
"""
Reward Calculator

Calculates reward scores for fuzzing iterations based on the paper's formula:

    Reward = A1·r_policing - A2·r_forward + A3·r_novelty - A4·r_repeat
           + bonus_edge + bonus_safety

Where:
- r_policing: proportion of frames dropped due to legitimate AFDX policing
- r_forward: fraction of frames successfully forwarded
- r_novelty: reward for testing strategies that differ from previous ones
- r_repeat: penalty for tests that closely resemble recently executed tests
- bonus_edge: additional reward for edge-case testing
- bonus_safety: bonus when system doesn't crash under malformed inputs

This module does NOT impose constraints - it evaluates based on observed results.
"""

import pandas as pd
from typing import Dict, Any, Optional


class RewardCalculator:
    """
    Calculates reward scores for fuzzing iterations.
    
    The reward function guides the LLM toward effective testing strategies
    by rewarding behaviors that expose vulnerabilities and penalizing
    redundant or ineffective tests.
    """
    
    def __init__(
        self,
        lambda_policing: float = 0.6,
        lambda_forward: float = 0.2,
        lambda_novelty: float = 0.4,
        lambda_repeat: float = 0.2,
        bonus_edge_max: float = 1.0,
        bonus_safety: float = 0.3
    ):
        """
        Initialize reward calculator with weights.
        
        Args:
            lambda_policing: Weight for policing rate (default: 0.6)
            lambda_forward: Weight for forward rate penalty (default: 0.2)
            lambda_novelty: Weight for novelty bonus (default: 0.4)
            lambda_repeat: Weight for repeat penalty (default: 0.2)
            bonus_edge_max: Maximum edge-case bonus (default: 1.0)
            bonus_safety: Safety bonus value (default: 0.3)
        """
        self.lambda_policing = lambda_policing
        self.lambda_forward = lambda_forward
        self.lambda_novelty = lambda_novelty
        self.lambda_repeat = lambda_repeat
        self.bonus_edge_max = bonus_edge_max
        self.bonus_safety = bonus_safety
    
    def calculate(
        self,
        metrics: Dict[str, Any],
        strategy: Dict[str, Any],
        history: Optional[pd.DataFrame] = None
    ) -> Dict[str, Any]:
        """
        Calculate complete reward score.
        
        Args:
            metrics: Performance metrics from SimulatorLogParser
            strategy: Test strategy that was executed
            history: DataFrame of previous iterations (optional)
            
        Returns:
            Dictionary containing:
            {
                "reward": float,  # Total reward score
                "components": {
                    "r_policing": float,
                    "r_forward": float,
                    "r_novelty": float,
                    "r_repeat": float,
                    "bonus_edge": float,
                    "bonus_safety": float
                },
                "breakdown": str  # Human-readable explanation
            }
        """
        # Calculate individual components
        r_policing = self._compute_policing_score(metrics)
        r_forward = self._compute_forward_score(metrics)
        r_novelty = self._compute_novelty_score(strategy, history)
        r_repeat = self._compute_repeat_penalty(strategy, history)
        bonus_edge = self._compute_edge_bonus(strategy, metrics)
        bonus_safety = self._compute_safety_bonus(metrics)
        
        # Calculate total reward
        reward = (
            self.lambda_policing * r_policing
            - self.lambda_forward * r_forward
            + self.lambda_novelty * r_novelty
            - self.lambda_repeat * r_repeat
            + bonus_edge
            + bonus_safety
        )
        
        # Build breakdown
        breakdown = self._build_breakdown(
            reward, r_policing, r_forward, r_novelty, 
            r_repeat, bonus_edge, bonus_safety
        )
        
        return {
            "reward": reward,
            "components": {
                "r_policing": r_policing,
                "r_forward": r_forward,
                "r_novelty": r_novelty,
                "r_repeat": r_repeat,
                "bonus_edge": bonus_edge,
                "bonus_safety": bonus_safety
            },
            "breakdown": breakdown
        }
    
    def _compute_policing_score(self, metrics: Dict[str, Any]) -> float:
        """
        Calculate policing score (proportion of frames dropped by policing).
        
        High policing rate is good - it means the system correctly rejects
        invalid frames according to AFDX rules.
        
        Args:
            metrics: Performance metrics
            
        Returns:
            Policing score in range [0.0, 1.0]
        """
        frames_received = metrics.get("frames_received", 0)
        if frames_received == 0:
            return 0.0
        
        frames_dropped_policing = metrics.get("frames_dropped_policing", 0)
        return frames_dropped_policing / frames_received
    
    def _compute_forward_score(self, metrics: Dict[str, Any]) -> float:
        """
        Calculate forward score (fraction of frames successfully forwarded).
        
        High forwarding under malformed conditions is BAD - it indicates
        overly permissive behavior that should be penalized.
        
        Args:
            metrics: Performance metrics
            
        Returns:
            Forward score in range [0.0, 1.0]
        """
        frames_received = metrics.get("frames_received", 0)
        if frames_received == 0:
            return 0.0
        
        frames_forwarded = metrics.get("frames_forwarded", 0)
        return frames_forwarded / frames_received
    
    def _compute_novelty_score(
        self,
        strategy: Dict[str, Any],
        history: Optional[pd.DataFrame]
    ) -> float:
        """
        Calculate novelty score (how different is this test from previous ones).
        
        Rewards testing strategies that explore new areas.
        
        Args:
            strategy: Current test strategy
            history: DataFrame of previous iterations
            
        Returns:
            Novelty score in range [0.0, 1.0]
        """
        if history is None or len(history) == 0:
            # First test is always novel
            return 1.0
        
        # Extract key strategy components
        target_vl = strategy.get("target_vl")
        protocol_rule = strategy.get("protocol_rule")
        test_cases = strategy.get("test_cases", [])
        
        # Check how many times this VL was tested
        if "target_vl" in history.columns:
            vl_count = len(history[history["target_vl"] == target_vl])
            vl_novelty = max(0.0, 1.0 - (vl_count / 10.0))  # Decreases as VL is tested more
        else:
            vl_novelty = 1.0
        
        # Check how many times this rule was tested
        if "protocol_rule" in history.columns:
            rule_count = len(history[history["protocol_rule"] == protocol_rule])
            rule_novelty = max(0.0, 1.0 - (rule_count / 10.0))
        else:
            rule_novelty = 1.0
        
        # Combined novelty
        novelty = (vl_novelty + rule_novelty) / 2.0
        
        return novelty
    
    def _compute_repeat_penalty(
        self,
        strategy: Dict[str, Any],
        history: Optional[pd.DataFrame]
    ) -> float:
        """
        Calculate repeat penalty (penalize tests similar to recent ones).
        
        Discourages repetitive testing in the last N iterations.
        
        Args:
            strategy: Current test strategy
            history: DataFrame of previous iterations
            
        Returns:
            Repeat penalty in range [0.0, 1.0]
        """
        if history is None or len(history) == 0:
            return 0.0
        
        # Look at last 5 iterations
        recent_history = history.tail(5)
        
        target_vl = strategy.get("target_vl")
        protocol_rule = strategy.get("protocol_rule")
        
        # Count exact matches in recent history
        matches = 0
        for _, row in recent_history.iterrows():
            if (row.get("target_vl") == target_vl and 
                row.get("protocol_rule") == protocol_rule):
                matches += 1
        
        # Penalty increases with number of recent matches
        penalty = min(1.0, matches / 3.0)
        
        return penalty
    
    def _compute_edge_bonus(
        self,
        strategy: Dict[str, Any],
        metrics: Dict[str, Any]
    ) -> float:
        """
        Calculate edge-case bonus.
        
        Rewards testing edge cases like:
        - Invalid VL IDs
        - Boundary values
        - Malformed MAC addresses
        - Extreme parameter values
        
        Args:
            strategy: Test strategy
            metrics: Performance metrics
            
        Returns:
            Edge-case bonus in range [0.0, bonus_edge_max]
        """
        bonus = 0.0
        
        # Check if strategy is marked as edge-case or attack
        strategy_type = strategy.get("strategy", "normal")
        if strategy_type in ["edge-case", "attack"]:
            bonus += 0.5
        
        # Check if invalid VL was tested
        frames_dropped_invalid_vl = metrics.get("frames_dropped_invalid_vl", 0)
        if frames_dropped_invalid_vl > 0:
            bonus += 0.3
        
        # Check if test cases include boundary/extreme violations
        test_cases = strategy.get("test_cases", [])
        if test_cases:
            # Assume test_cases is a list of test case IDs or objects
            bonus += 0.2
        
        return min(bonus, self.bonus_edge_max)
    
    def _compute_safety_bonus(self, metrics: Dict[str, Any]) -> float:
        """
        Calculate safety bonus.
        
        Rewards system robustness - bonus if system didn't crash or
        incorrectly accept malformed frames.
        
        Args:
            metrics: Performance metrics
            
        Returns:
            Safety bonus (0.0 or bonus_safety)
        """
        # Check if system accepted malformed frames (BUG!)
        malformed_accepted = metrics.get("malformed_accepted", 0)
        if malformed_accepted > 0:
            # System accepted invalid frames - no safety bonus
            return 0.0
        
        # Check if simulation completed successfully
        parsing_success = metrics.get("parsing_success", False)
        if parsing_success:
            return self.bonus_safety
        
        return 0.0
    
    def _build_breakdown(
        self,
        reward: float,
        r_policing: float,
        r_forward: float,
        r_novelty: float,
        r_repeat: float,
        bonus_edge: float,
        bonus_safety: float
    ) -> str:
        """
        Build human-readable reward breakdown.
        
        Args:
            reward: Total reward
            r_policing: Policing component
            r_forward: Forward component
            r_novelty: Novelty component
            r_repeat: Repeat component
            bonus_edge: Edge bonus
            bonus_safety: Safety bonus
            
        Returns:
            Formatted breakdown string
        """
        lines = [
            "Reward Breakdown:",
            f"  Total: {reward:.3f}",
            "",
            "Components:",
            f"  + {self.lambda_policing:.1f} × policing ({r_policing:.2f}) = {self.lambda_policing * r_policing:.3f}",
            f"  - {self.lambda_forward:.1f} × forward ({r_forward:.2f}) = {-self.lambda_forward * r_forward:.3f}",
            f"  + {self.lambda_novelty:.1f} × novelty ({r_novelty:.2f}) = {self.lambda_novelty * r_novelty:.3f}",
            f"  - {self.lambda_repeat:.1f} × repeat ({r_repeat:.2f}) = {-self.lambda_repeat * r_repeat:.3f}",
            f"  + edge bonus = {bonus_edge:.3f}",
            f"  + safety bonus = {bonus_safety:.3f}"
        ]
        
        return "\n".join(lines)


if __name__ == "__main__":
    # Quick test
    calculator = RewardCalculator()
    
    # Mock metrics
    metrics = {
        "frames_received": 1000,
        "frames_forwarded": 100,
        "frames_dropped_policing": 800,
        "frames_dropped_invalid_vl": 50,
        "malformed_accepted": 0,
        "parsing_success": True
    }
    
    # Mock strategy
    strategy = {
        "target_vl": 2001,
        "protocol_rule": "bag",
        "test_cases": ["tc1", "tc2"],
        "strategy": "edge-case"
    }
    
    result = calculator.calculate(metrics, strategy, history=None)
    
    print("=" * 70)
    print("REWARD CALCULATOR TEST")
    print("=" * 70)
    print(f"\nReward: {result['reward']:.3f}")
    print(f"\nComponents:")
    for key, value in result['components'].items():
        print(f"  {key}: {value:.3f}")
    print(f"\n{result['breakdown']}")

