#!/usr/bin/env python3
"""
Test script to demonstrate the NEW SMART SEQUENCES vs OLD REPETITIVE approach
"""

import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from llm_fuzzer.core.test_generator import TestGenerator

print("=" * 80)
print("SMART SEQUENCE TEST - Demonstrating Improved Test Generation")
print("=" * 80)
print()

# Initialize generator
generator = TestGenerator(
    seed_frames_path="llm_fuzzer/data/seed_frames.json",
    test_cases_path="configs/test_cases.json"
)

# Test 1: BAG violation testing
print("TEST 1: BAG Violation (TC0 - BAG=0)")
print("-" * 80)

strategy_bag = {
    'target_vl': 1001,
    'protocol_rule': 'bag',
    'test_mode': 'predefined',
    'test_cases': ['TC0'],  # BAG=0
    'custom_mutation': None,
    'strategy': 'edge-case'
}

test_inputs = generator.generate_test_inputs(strategy_bag)
frames = test_inputs['frames']

print(f"Generated {len(frames)} frames")
print()
print("Frame Distribution Analysis:")
print(f"  Total frames: {len(frames)}")

# Analyze BAG values
bag_values = [f['bag_ms'] for f in frames]
unique_bags = set(bag_values)
print(f"  Unique BAG values: {sorted(unique_bags)}")
print(f"  BAG value distribution:")
for bag in sorted(unique_bags):
    count = bag_values.count(bag)
    print(f"    BAG={bag}ms: {count} frames")

print()
print("Sequence Analysis:")
print("  First 5 frames:")
for i in range(min(5, len(frames))):
    f = frames[i]
    print(f"    Frame {i}: time={f['time']:.4f}s, seq={f['seq']}, bag={f['bag_ms']}ms")

print()
print("  Middle 5 frames:")
mid = len(frames) // 2
for i in range(mid, min(mid+5, len(frames))):
    f = frames[i]
    print(f"    Frame {i}: time={f['time']:.4f}s, seq={f['seq']}, bag={f['bag_ms']}ms")

print()
print("  Last 5 frames:")
for i in range(max(0, len(frames)-5), len(frames)):
    f = frames[i]
    print(f"    Frame {i}: time={f['time']:.4f}s, seq={f['seq']}, bag={f['bag_ms']}ms")

print()
print("=" * 80)
print()

# Test 2: Sequence number testing
print("TEST 2: Sequence Number Testing")
print("-" * 80)

strategy_seq = {
    'target_vl': 1001,
    'protocol_rule': 'sequence_number_field',
    'test_mode': 'predefined',
    'test_cases': ['TC0'],
    'custom_mutation': None,
    'strategy': 'edge-case'
}

test_inputs_seq = generator.generate_test_inputs(strategy_seq)
frames_seq = test_inputs_seq['frames']

print(f"Generated {len(frames_seq)} frames")
print()

# Analyze sequence numbers
seq_numbers = [f['seq'] for f in frames_seq]
print(f"Sequence numbers used: {seq_numbers[:10]}...")
print(f"  Range: {min(seq_numbers)} - {max(seq_numbers)}")
print(f"  Unique values: {len(set(seq_numbers))}")
print(f"  Duplicates: {len(seq_numbers) - len(set(seq_numbers))}")

# Check for interesting patterns
print()
print("Interesting patterns detected:")
for i in range(1, len(seq_numbers)):
    if seq_numbers[i] == seq_numbers[i-1]:
        print(f"  - Duplicate: seq={seq_numbers[i]} at frames {i-1},{i}")
    elif seq_numbers[i] < seq_numbers[i-1]:
        print(f"  - Out-of-order: seq={seq_numbers[i-1]}→{seq_numbers[i]} at frame {i}")
    elif seq_numbers[i] > seq_numbers[i-1] + 1:
        print(f"  - Skip: seq={seq_numbers[i-1]}→{seq_numbers[i]} (gap={seq_numbers[i] - seq_numbers[i-1] - 1}) at frame {i}")

print()
print("=" * 80)
print()

# Test 3: Multiple test cases (smart combination)
print("TEST 3: Multiple Test Cases (TC0 + TC1)")
print("-" * 80)

strategy_multi = {
    'target_vl': 1001,
    'protocol_rule': 'bag',
    'test_mode': 'predefined',
    'test_cases': ['TC0', 'TC1'],  # Multiple test cases!
    'custom_mutation': None,
    'strategy': 'adversarial'
}

test_inputs_multi = generator.generate_test_inputs(strategy_multi)
frames_multi = test_inputs_multi['frames']

print(f"Generated {len(frames_multi)} frames from 2 test cases")
print()

# Analyze BAG values
bag_values_multi = [f['bag_ms'] for f in frames_multi]
unique_bags_multi = set(bag_values_multi)
print(f"  Unique BAG values: {sorted(unique_bags_multi)}")
print(f"  BAG distribution:")
for bag in sorted(unique_bags_multi):
    count = bag_values_multi.count(bag)
    print(f"    BAG={bag}ms: {count} frames")

print()
print("First 10 frames from combined test:")
for i in range(min(10, len(frames_multi))):
    f = frames_multi[i]
    print(f"  Frame {i}: time={f['time']:.4f}s, seq={f['seq']}, bag={f['bag_ms']}ms")

print()
print("=" * 80)
print()

# Summary
print("SUMMARY: Why Smart Sequences Are Better")
print("=" * 80)
print()
print("OLD APPROACH (20 identical frames):")
print("  ❌ BAG=0, BAG=0, BAG=0, BAG=0, ... (x20)")
print("  ❌ No variation, no state transitions")
print("  ❌ Wastes simulation time")
print("  ❌ Limited bug discovery")
print()
print("NEW APPROACH (smart sequences):")
print("  ✅ Valid→Invalid→Valid transitions")
print("  ✅ Multiple violation patterns tested")
print("  ✅ Boundary testing (min, max, invalid)")
print("  ✅ Interleaved valid/invalid for race conditions")
print("  ✅ Better coverage, more bugs found")
print()
print("Example for BAG testing:")
print(f"  - {bag_values.count(8)} frames with valid BAG (baseline & recovery)")
print(f"  - {bag_values.count(0)} frames with invalid BAG=0 (violation)")
print(f"  - Tests both steady-state violation AND transitions")
print()
print("=" * 80)

