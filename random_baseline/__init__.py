"""
Random Baseline Fuzzer

This module implements a purely random fuzzer for comparison with the LLM-guided fuzzer.
It uses the SAME infrastructure (FeedbackAnalyzer, TestGenerator, SimulatorRunner)
but makes RANDOM decisions instead of LLM-guided ones.

This ensures a fair comparison - same tools, same data, only the decision-making differs.
"""

__version__ = "1.0.0"

