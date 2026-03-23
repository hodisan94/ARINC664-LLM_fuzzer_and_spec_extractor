#!/usr/bin/env python3
"""
Feedback Analyzer

Combines SimulatorLogParser and RewardCalculator to provide complete
feedback analysis for fuzzing iterations.

This is Component 1 of the LLM-Guided Iterative Fuzzing Process:
    Input:  Simulator log file, test strategy, iteration history
    Output: Complete feedback with metrics, reward, and analysis

The feedback is used by the LLM-Based Strategy Planner to decide
what to test next.
"""

import pandas as pd
from typing import Dict, Any, Optional
from pathlib import Path

# Import sibling modules
import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from llm_fuzzer.utils.log_parser import SimulatorLogParser
from llm_fuzzer.core.reward_calculator import RewardCalculator


class FeedbackAnalyzer:
    """
    Analyzes feedback from simulator runs.
    
    This is the first component in the fuzzing loop that processes
    the results of a test execution.
    """
    
    def __init__(
        self,
        reward_calculator: Optional[RewardCalculator] = None
    ):
        """
        Initialize feedback analyzer.
        
        Args:
            reward_calculator: RewardCalculator instance (creates default if None)
        """
        self.reward_calculator = reward_calculator or RewardCalculator()
    
    def analyze(
        self,
        log_file: Optional[str] = None,
        log_content: Optional[str] = None,
        csv_content: Optional[str] = None,
        strategy: Optional[Dict[str, Any]] = None,
        history: Optional[pd.DataFrame] = None
    ) -> Dict[str, Any]:
        """
        Analyze feedback from a simulator run.
        
        Args:
            log_file: Path to simulator log file (optional)
            log_content: Simulator stdout text (contains ExportMIB data)
            csv_content: CSV text from AFDX-LOG-OUTPUT.csv (optional)
            strategy: Test strategy that was executed (optional)
            history: DataFrame of previous iterations (optional)
        """
        try:
            if log_file:
                log_parser = SimulatorLogParser(log_file=log_file, csv_content=csv_content)
            elif log_content:
                log_parser = SimulatorLogParser(log_content=log_content, csv_content=csv_content)
            else:
                raise ValueError("Either log_file or log_content must be provided")
            
            metrics = log_parser.parse()
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "metrics": {},
                "reward": 0.0
            }
        
        # Calculate reward
        strategy = strategy or {}
        reward_result = self.reward_calculator.calculate(
            metrics=metrics,
            strategy=strategy,
            history=history
        )
        
        # Perform analysis (pass history for coverage-aware recommendations)
        analysis = self._analyze_results(metrics, strategy, reward_result, history)
        
        return {
            "success": True,
            "metrics": metrics,
            "reward": reward_result["reward"],
            "reward_components": reward_result["components"],
            "reward_breakdown": reward_result["breakdown"],
            "analysis": analysis
        }
    
    def _analyze_results(
        self,
        metrics: Dict[str, Any],
        strategy: Dict[str, Any],
        reward_result: Dict[str, Any],
        history: Optional[pd.DataFrame] = None
    ) -> Dict[str, Any]:
        """
        Perform high-level analysis of results.
        
        Args:
            metrics: Performance metrics
            strategy: Test strategy
            reward_result: Reward calculation result
            history: DataFrame of previous iterations
            
        Returns:
            Analysis dictionary with recommendations
        """
        policing_rate = metrics.get("policing_rate", 0.0)
        forward_rate = metrics.get("forward_rate", 0.0)
        malformed_accepted = metrics.get("malformed_accepted", 0)
        
        if policing_rate >= 0.8:
            policing_effectiveness = "Excellent - System correctly rejects most invalid frames"
        elif policing_rate >= 0.5:
            policing_effectiveness = "Good - System polices moderately well"
        elif policing_rate >= 0.2:
            policing_effectiveness = "Fair - System could be stricter"
        else:
            policing_effectiveness = "Poor - System is too permissive"
        
        bugs_found = malformed_accepted > 0
        strategy_type = strategy.get("strategy", "normal")
        edge_case_tested = strategy_type in ["edge-case", "attack", "adversarial"]
        
        recommendation = self._generate_recommendation(
            policing_rate, forward_rate, bugs_found, edge_case_tested,
            reward_result, strategy, history
        )
        
        return {
            "policing_effectiveness": policing_effectiveness,
            "bugs_found": bugs_found,
            "edge_case_tested": edge_case_tested,
            "recommendation": recommendation
        }
    
    def _generate_recommendation(
        self,
        policing_rate: float,
        forward_rate: float,
        bugs_found: bool,
        edge_case_tested: bool,
        reward_result: Dict[str, Any],
        strategy: Dict[str, Any] = None,
        history: Optional[pd.DataFrame] = None
    ) -> str:
        """
        Generate coverage-aware testing recommendation.
        """
        strategy = strategy or {}
        reward = reward_result["reward"]
        
        if bugs_found:
            return "BUG FOUND! Continue testing this area to identify root cause."
        
        parts = []
        
        mutation_type = strategy.get("mutation_type", "")
        if history is not None and len(history) > 0 and "mutation_type" in history.columns:
            times_used = int((history["mutation_type"] == mutation_type).sum())
            if times_used >= 3:
                parts.append(
                    f"WARNING: mutation_type '{mutation_type}' used {times_used} times already. "
                    f"Switch to a DIFFERENT rule to improve coverage."
                )

            seen_rules = set(history["protocol_rule"].dropna().unique()) if "protocol_rule" in history.columns else set()
            n_seen = len(seen_rules)
            parts.append(f"Coverage so far: {n_seen} unique rules tested.")
            
            if n_seen < 20:
                parts.append("Coverage is LOW. Prioritize untested rules.")
            
            if not strategy.get("test_cases"):
                parts.append("TIP: Try using predefined test_cases for broader rule coverage.")
        
        if reward > 1.5:
            parts.append("High reward, but ensure you are not repeating the same mutation.")
        elif reward > 0.8:
            parts.append("Good reward. Try a different protocol rule next.")
        elif reward > 0.4:
            parts.append("Moderate reward. Consider edge-case or adversarial strategies.")
        else:
            if not edge_case_tested:
                parts.append("Try edge-case testing to find boundary violations.")
            else:
                parts.append("Low reward. Try a completely different approach.")
        
        return " ".join(parts) if parts else "Continue systematic exploration of protocol rules."
    
    def analyze_batch(
        self,
        results: list,
        history: Optional[pd.DataFrame] = None
    ) -> pd.DataFrame:
        """
        Analyze multiple test results in batch.
        
        Args:
            results: List of (log_file/content, strategy) tuples
            history: DataFrame of previous iterations
            
        Returns:
            DataFrame with all analyses
        """
        analyses = []
        
        for i, (log_data, strategy) in enumerate(results):
            # Check if it's a file path (short string, no newlines)
            if isinstance(log_data, str) and '\n' not in log_data and len(log_data) < 300:
                try:
                    if Path(log_data).exists():
                        feedback = self.analyze(log_file=log_data, strategy=strategy, history=history)
                    else:
                        feedback = self.analyze(log_content=log_data, strategy=strategy, history=history)
                except (OSError, ValueError):
                    feedback = self.analyze(log_content=log_data, strategy=strategy, history=history)
            else:
                feedback = self.analyze(log_content=log_data, strategy=strategy, history=history)
            
            # Flatten for DataFrame
            flat_result = {
                "iteration": i,
                "success": feedback.get("success", False),
                "reward": feedback.get("reward", 0.0),
                "frames_received": feedback.get("metrics", {}).get("frames_received", 0),
                "policing_rate": feedback.get("metrics", {}).get("policing_rate", 0.0),
                "forward_rate": feedback.get("metrics", {}).get("forward_rate", 0.0),
                "bugs_found": feedback.get("analysis", {}).get("bugs_found", False),
                "target_vl": strategy.get("target_vl"),
                "protocol_rule": strategy.get("protocol_rule"),
            }
            
            analyses.append(flat_result)
        
        return pd.DataFrame(analyses)
    
    def summary(self, feedback: Dict[str, Any]) -> str:
        """
        Generate human-readable summary of feedback.
        
        Args:
            feedback: Feedback dictionary from analyze()
            
        Returns:
            Formatted summary string
        """
        if not feedback.get("success", False):
            return f"❌ Analysis failed: {feedback.get('error', 'Unknown error')}"
        
        metrics = feedback["metrics"]
        analysis = feedback["analysis"]
        
        lines = [
            "=" * 70,
            "FEEDBACK ANALYSIS SUMMARY",
            "=" * 70,
            "",
            "Performance Metrics:",
            f"  Frames received:          {metrics.get('frames_received', 0)}",
            f"  Frames forwarded:         {metrics.get('frames_forwarded', 0)} ({metrics.get('forward_rate', 0):.1%})",
            f"  Frames dropped (policing): {metrics.get('frames_dropped_policing', 0)} ({metrics.get('policing_rate', 0):.1%})",
            f"  Frames dropped (invalid VL): {metrics.get('frames_dropped_invalid_vl', 0)}",
            f"  Malformed accepted:       {metrics.get('malformed_accepted', 0)} {'[BUG]' if metrics.get('malformed_accepted', 0) > 0 else '[OK]'}",
            "",
            f"Reward Score: {feedback['reward']:.3f}",
            "",
            "Analysis:",
            f"  Policing: {analysis['policing_effectiveness']}",
            f"  Bugs found: {'Yes [BUG]' if analysis['bugs_found'] else 'No'}",
            f"  Edge case tested: {'Yes' if analysis['edge_case_tested'] else 'No'}",
            "",
            f"Recommendation: {analysis['recommendation']}",
            "",
            "=" * 70
        ]
        
        return "\n".join(lines)


if __name__ == "__main__":
    # Quick test
    print("=" * 70)
    print("FEEDBACK ANALYZER TEST")
    print("=" * 70)
    
    # Mock log
    mock_log = """
    [INFO] Frames received: 1000
    [INFO] Frames forwarded: 100
    [INFO] Frames dropped (policing): 850
    [INFO] Frames dropped (invalid VL): 50
    [INFO] Malformed frames accepted: 0
    [INFO] Simulation time: 10.5s
    """
    
    # Mock strategy
    strategy = {
        "target_vl": 2001,
        "protocol_rule": "bag",
        "test_cases": ["below_min", "negative"],
        "strategy": "edge-case"
    }
    
    # Analyze
    analyzer = FeedbackAnalyzer()
    feedback = analyzer.analyze(log_content=mock_log, strategy=strategy)
    
    # Display summary
    print(analyzer.summary(feedback))
    
    print("\nDetailed Reward Breakdown:")
    print(feedback['reward_breakdown'])

