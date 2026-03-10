# Project Overview

## What is this project?

An **LLM-Guided Fuzzing Framework** for testing AFDX (Avionics Full-Duplex Switched Ethernet) protocol implementations. The project combines a high-fidelity ns-3 network simulator with Large Language Models to intelligently discover protocol violations in safety-critical avionics communication systems.

## Why?

AFDX (defined in ARINC 664 Part 7) is used in modern aircraft (Airbus A380, A350, Boeing 787) for deterministic, redundant communication between avionics subsystems. Testing these systems is critical for flight safety, but manual testing is incomplete and traditional fuzzing is inefficient. This project uses LLMs to:

1. **Understand the protocol specification** — automatically extract testable rules from the ARINC 664 Part 7 document
2. **Generate intelligent test cases** — use LLM reasoning to craft targeted violations rather than random noise
3. **Learn from results** — iteratively improve testing strategy based on feedback from previous runs

## Research Goal

Demonstrate that LLM-guided fuzzing achieves better **protocol rule coverage**, **violation discovery**, and **testing efficiency** compared to random fuzzing and systematic (boofuzz-based) fuzzing baselines.

## Two-Stage Architecture

### Stage 1: Specification Knowledge Extraction (Open Discovery)
- Parse the ARINC 664 Part 7 PDF specification
- Use multiple LLM providers (GPT + Claude) to independently extract protocol rules — each LLM freely discovers and categorizes rules without a predefined schema
- Semantically align rules across models to find agreements and disagreements
- Resolve conflicts by having a judge LLM consult the actual spec text
- Verify rules found by only one model (confirm or reject)
- Output: `configs/spec_rules.json` (434 validated rules, enriched with test hints and source quotes)

### Stage 2: LLM-Guided Iterative Fuzzing
An iterative loop with 4 components per iteration:
1. **LLM Strategy Planner** — reads all protocol rules, decides which Virtual Link to target and what mutation to apply
2. **Test Generator** — creates concrete AFDX frames from the strategy (predefined test cases or custom LLM mutations)
3. **Simulator Runner** — executes the ns-3 AFDX simulation with mutated frames
4. **Feedback Analyzer** — analyzes results and computes a reward score

The reward feeds back to the LLM in the next iteration, enabling learning over time. The LLM has full freedom to choose which rules to target, what values to use, and whether to use predefined test cases or propose its own mutations.

## Key Technologies
- **ns-3** (C++) — Network simulator framework
- **AFDX model** (C++) — Custom AFDX switch, end-system, and virtual link models
- **Python** — Fuzzing orchestration, LLM integration, evaluation
- **OpenAI GPT / Anthropic Claude** — LLM providers for extraction and fuzzing
- **boofuzz** — Systematic fuzzing baseline
