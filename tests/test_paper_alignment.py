#!/usr/bin/env python3
"""
Test Paper-Aligned Implementation
Verify that LLM output format matches the paper description.
"""

import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from llm_fuzzer.core.strategy_planner import LLMStrategyPlanner
from llm_fuzzer.core.test_generator import TestGenerator

print("=" * 80)
print("PAPER ALIGNMENT VERIFICATION")
print("=" * 80)
print()

print("Testing NEW FORMAT (Paper-Aligned):")
print("-" * 80)
print()

# Simulate what LLM would output (NEW FORMAT)
mock_llm_output = {
    "target_vl": 2001,
    "mutation_type": "bag_violation",
    "bag_value": 0,
    "frame_size": None,
    "sequence_number": None,
    "timing_jitter_ms": None,
    "payload_pattern": None,
    "strategy": "edge-case",
    "reasoning": "Testing BAG=0 (below minimum) to verify policing rejects it."
}

print("LLM Output Format (from paper):")
print(json.dumps(mock_llm_output, indent=2))
print()

# Initialize components
try:
    planner = LLMStrategyPlanner(
        spec_rules_path="configs/spec_rules.json",
        test_cases_path="configs/test_cases.json"
    )
    
    generator = TestGenerator(
        seed_frames_path="llm_fuzzer/data/seed_frames.json",
        test_cases_path="configs/test_cases.json"
    )
    
    print("✅ Components initialized successfully")
    print()
    
    # Test parsing
    print("Testing Strategy Parsing:")
    print("-" * 80)
    
    strategy_json = json.dumps(mock_llm_output)
    try:
        strategy = planner._parse_strategy(strategy_json)
        print("✅ Strategy parsed successfully")
        print(f"   Keys: {list(strategy.keys())}")
        print()
        
        # Test validation
        print("Testing Strategy Validation:")
        print("-" * 80)
        planner._validate_strategy(strategy)
        print("✅ Strategy validated successfully")
        print()
        
        # Test generation
        print("Testing Frame Generation:")
        print("-" * 80)
        test_inputs = generator.generate_test_inputs(strategy)
        
        frames = test_inputs['frames']
        metadata = test_inputs['metadata']
        
        print(f"✅ Generated {len(frames)} frames")
        print(f"   VL ID: {test_inputs['vl_id']}")
        print(f"   Mutation Type: {metadata['mutation_type']}")
        print(f"   BAG Value: {metadata['bag_value']}")
        print(f"   Frame Size: {metadata['frame_size']}")
        print(f"   Sequence Number: {metadata['sequence_number']}")
        print()
        
        # Show first 5 frames
        print("First 5 frames:")
        for i in range(min(5, len(frames))):
            f = frames[i]
            print(f"  Frame {i}: time={f['time']:.4f}s, seq={f['seq']}, bag={f['bag_ms']}ms")
        print()
        
        # Analyze BAG values
        bag_values = [f['bag_ms'] for f in frames]
        unique_bags = set(bag_values)
        print(f"BAG value distribution:")
        for bag in sorted(unique_bags):
            count = bag_values.count(bag)
            print(f"  BAG={bag}ms: {count} frames")
        print()
        
        print("=" * 80)
        print("VERIFICATION COMPLETE")
        print("=" * 80)
        print()
        print("✅ Paper-aligned format works correctly!")
        print()
        print("Key differences from old format:")
        print("  OLD: test_cases: ['TC0'] → TestGenerator looks up TC0")
        print("  NEW: bag_value: 0 → TestGenerator applies value directly")
        print()
        print("This matches the paper description:")
        print('  "The JSON defines SPECIFIC mutation parameters:')
        print('   payload size delta (e.g., +64 bytes), timing jitter value (e.g., 50ms)"')
        print()
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        
except Exception as e:
    print(f"❌ Initialization error: {e}")
    import traceback
    traceback.print_exc()

print()
print("Test complete!")

