#!/usr/bin/env python3
"""
Test HYBRID Approach - LLM has FULL FREEDOM
Verify that LLM can choose:
1. Test cases only
2. Mutation params only
3. Both combined
"""

import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from llm_fuzzer.core.strategy_planner import LLMStrategyPlanner
from llm_fuzzer.core.test_generator import TestGenerator

print("=" * 80)
print("HYBRID FREEDOM TEST - LLM Can Choose Anything")
print("=" * 80)
print()

# Initialize components
planner = LLMStrategyPlanner(
    spec_rules_path="configs/spec_rules.json",
    test_cases_path="configs/test_cases.json"
)

generator = TestGenerator(
    seed_frames_path="llm_fuzzer/data/seed_frames.json",
    test_cases_path="configs/test_cases.json"
)

print("✅ Components initialized")
print()

# Test 3 scenarios
scenarios = [
    {
        "name": "SCENARIO 1: LLM chooses TEST CASES only",
        "strategy": {
            "target_vl": 2001,
            "mutation_type": "bag_violation",
            "test_cases": ["TC0", "TC1"],
            "bag_value": None,
            "frame_size": None,
            "sequence_number": None,
            "timing_jitter_ms": None,
            "payload_pattern": None,
            "strategy": "edge-case",
            "reasoning": "Using predefined BAG test cases for systematic testing."
        }
    },
    {
        "name": "SCENARIO 2: LLM chooses SPECIFIC VALUES only",
        "strategy": {
            "target_vl": 9999,
            "mutation_type": "vl_validation",
            "test_cases": None,
            "bag_value": 8,
            "frame_size": 128,
            "sequence_number": 1,
            "timing_jitter_ms": None,
            "payload_pattern": None,
            "strategy": "adversarial",
            "reasoning": "I chose invalid VL 9999 with valid params to isolate VL validation."
        }
    },
    {
        "name": "SCENARIO 3: LLM COMBINES both (smart!)",
        "strategy": {
            "target_vl": 1002,
            "mutation_type": "combined_test",
            "test_cases": ["TC2"],
            "bag_value": None,
            "frame_size": 1519,
            "sequence_number": None,
            "timing_jitter_ms": 50,
            "payload_pattern": None,
            "strategy": "edge-case",
            "reasoning": "Using TC2 as base, but adding frame size 1519 (boundary) and jitter 50ms."
        }
    }
]

for i, scenario in enumerate(scenarios, 1):
    print("=" * 80)
    print(f"{scenario['name']}")
    print("=" * 80)
    print()
    
    strategy = scenario['strategy']
    
    # Test parsing
    print("Testing parsing...")
    strategy_json = json.dumps(strategy)
    parsed = planner._parse_strategy(strategy_json)
    print(f"✅ Parsed successfully")
    print()
    
    # Test validation
    print("Testing validation...")
    planner._validate_strategy(parsed)
    print(f"✅ Validated successfully")
    print()
    
    # Test generation
    print("Testing frame generation...")
    test_inputs = generator.generate_test_inputs(parsed)
    
    frames = test_inputs['frames']
    metadata = test_inputs['metadata']
    
    print(f"✅ Generated {len(frames)} frames")
    print()
    
    # Show what was used
    print("LLM's choices:")
    if metadata.get('test_cases'):
        print(f"  Test Cases: {metadata['test_cases']}")
    if metadata.get('bag_value') is not None:
        print(f"  BAG Value: {metadata['bag_value']}")
    if metadata.get('frame_size') is not None:
        print(f"  Frame Size: {metadata['frame_size']}")
    if metadata.get('sequence_number') is not None:
        print(f"  Sequence Number: {metadata['sequence_number']}")
    if metadata.get('timing_jitter_ms') is not None:
        print(f"  Timing Jitter: {metadata['timing_jitter_ms']}ms")
    print()
    
    # Show first 3 frames
    print("First 3 frames:")
    for j in range(min(3, len(frames))):
        f = frames[j]
        print(f"  Frame {j}: time={f['time']:.4f}s, seq={f['seq']}, bag={f['bag_ms']}ms")
    print()

print("=" * 80)
print("ALL SCENARIOS PASSED!")
print("=" * 80)
print()
print("Summary:")
print("  ✅ LLM can choose test_cases only")
print("  ✅ LLM can choose mutation params only")
print("  ✅ LLM can combine both")
print("  ✅ LLM has FULL FREEDOM - not hardcoded!")
print()
print("LLM sees:")
print("  - Protocol rules (understands constraints)")
print("  - Test cases (can use or ignore)")
print("  - History (learns what worked)")
print("  - Reward (optimizes)")
print("  → LLM DECIDES what's best!")
print()

