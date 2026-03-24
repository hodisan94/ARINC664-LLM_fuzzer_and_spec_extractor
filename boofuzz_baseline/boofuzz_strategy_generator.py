#!/usr/bin/env python3
"""
boofuzz Strategy Generator - Deterministic Protocol Fuzzing

This module provides a strategy generator that iterates through ALL
test cases in a deterministic order. Unlike the LLM fuzzer (intelligent)
or random fuzzer (random), boofuzz goes through every violation systematically.

Key characteristics:
1. Deterministic: Same order every time
2. Exhaustive: Tests every violation in test_cases.json
3. No learning: Does not adapt based on results
4. Industry-standard approach: This is how traditional fuzzers work
5. Round-robin: One TC per rule first, maximising rule diversity early
"""

import json
import re
import sys
from collections import OrderedDict
from pathlib import Path
from typing import Dict, Any, List, Optional
import pandas as pd

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from boofuzz_baseline.afdx_protocol import AFDXTestCaseGenerator


class BoofuzzStrategyGenerator:
    """
    Deterministic strategy generator for boofuzz baseline.
    
    Unlike LLM (intelligent selection) or Random (random selection),
    boofuzz systematically tests every violation in order.
    
    Uses a category-aware round-robin schedule: rules that map to
    different spec categories are tested first (one per category),
    maximising specification coverage in the fewest iterations.
    """
    
    def __init__(
        self,
        test_cases_path: str = "configs/test_cases.json",
        spec_rules_path: str = "configs/spec_rules_filtered.json"
    ):
        self.afdx_generator = AFDXTestCaseGenerator(test_cases_path, spec_rules_path)
        self.spec_rules_path = spec_rules_path
        
        self.all_violations = self.afdx_generator.get_all_violations()
        
        self._rule_to_cat = self._build_rule_category_lookup()
        self.round_robin_schedule = self._build_round_robin_schedule()
        
        self.current_index = 0
        self.tested_violations = set()

    # ------------------------------------------------------------------
    @staticmethod
    def _norm(s: str) -> str:
        s = s.lower().replace(' ', '_').replace('.', '_').replace('-', '_')
        s = re.sub(r'_+', '_', s)
        return s.strip('_')

    def _build_rule_category_lookup(self) -> Dict[str, str]:
        """Map normalised sub-rule names to their parent spec category."""
        try:
            with open(self.spec_rules_path) as f:
                spec = json.load(f)
        except Exception:
            return {}
        lookup: Dict[str, str] = {}
        for cat, content in spec.items():
            lookup[self._norm(cat)] = cat
            if isinstance(content, dict):
                for sub in content.keys():
                    lookup[self._norm(sub)] = cat
        return lookup

    def _rule_category(self, rule_id: str) -> Optional[str]:
        """Return the spec category for a rule, or None if unmapped."""
        norm = self._norm(rule_id)
        if norm in self._rule_to_cat:
            return self._rule_to_cat[norm]
        parts = rule_id.split('.')
        if len(parts) > 1:
            sub = self._norm(parts[-1])
            if sub in self._rule_to_cat:
                return self._rule_to_cat[sub]
            prefix = self._norm(parts[0])
            if prefix in self._rule_to_cat:
                return self._rule_to_cat[prefix]
        return None

    def _build_round_robin_schedule(self) -> List[Dict[str, Any]]:
        """Build a category-diverse round-robin ordering.

        1. Group violations by rule_id.
        2. Separate rules into *mapped* (has a spec category) and *unmapped*.
        3. Order mapped rules so successive entries come from different
           categories (greedy interleave), giving maximal category coverage
           in the fewest iterations.
        4. Append unmapped rules after all mapped ones.
        5. Within each group, apply the standard round-robin (TC0 of every
           rule first, then TC1, etc.).
        """
        by_rule: OrderedDict[str, List[Dict[str, Any]]] = OrderedDict()
        for v in self.all_violations:
            by_rule.setdefault(v['rule_id'], []).append(v)

        mapped_rules: Dict[str, List[str]] = {}   # cat -> [rule_ids]
        unmapped_rule_ids: List[str] = []

        for rule_id in by_rule:
            cat = self._rule_category(rule_id)
            if cat:
                mapped_rules.setdefault(cat, []).append(rule_id)
            else:
                unmapped_rule_ids.append(rule_id)

        ordered_rule_ids: List[str] = []
        cat_queues = {c: list(rids) for c, rids in sorted(mapped_rules.items())}
        while cat_queues:
            empty = []
            for cat in list(cat_queues.keys()):
                rids = cat_queues[cat]
                if rids:
                    ordered_rule_ids.append(rids.pop(0))
                if not rids:
                    empty.append(cat)
            for c in empty:
                del cat_queues[c]

        ordered_rule_ids.extend(unmapped_rule_ids)

        schedule: List[Dict[str, Any]] = []
        max_tcs = max(len(tcs) for tcs in by_rule.values()) if by_rule else 0
        for tc_round in range(max_tcs):
            for rule_id in ordered_rule_ids:
                tcs = by_rule[rule_id]
                if tc_round < len(tcs):
                    schedule.append(tcs[tc_round])
        return schedule
    
    def plan_next_iteration(
        self,
        history: Optional[pd.DataFrame] = None,
        iteration: int = 0,
        system_config: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Plan next iteration - deterministically select next violation
        using round-robin across rules.
        """
        if not system_config or 'available_vls' not in system_config:
            raise ValueError("system_config must contain 'available_vls'")
        
        available_vls = system_config['available_vls']
        
        if self.current_index >= len(self.round_robin_schedule):
            self.current_index = 0
        
        violation = self.round_robin_schedule[self.current_index]
        self.current_index += 1
        
        self.tested_violations.add(violation['id'])
        
        # Select VL (round-robin through available VLs)
        vl_index = (iteration) % len(available_vls)
        target_vl = available_vls[vl_index]
        
        rule_id = violation['rule_id']
        value = violation['value']

        mutation_type = self._classify_mutation(rule_id)

        bag_value = None
        frame_size = None
        sequence_number = None
        sequence_number_override = None
        dest_mac_mutation = None
        mac_mutation_type = None
        prob = None

        if mutation_type == 'bag':
            bag_value = int(value) if isinstance(value, (int, float)) else 1
        elif mutation_type == 'frame_size':
            frame_size = value if isinstance(value, int) else 63
        elif mutation_type == 'sequence_number':
            if isinstance(value, int):
                sequence_number = value
                sequence_number_override = value
            else:
                sequence_number_override = 0
        elif mutation_type == 'mac_address':
            mac_mutation_type = 'spoof_src'
            dest_mac_variants = ['corrupt_prefix', 'wrong_vl', 'zero']
            dest_mac_mutation = dest_mac_variants[iteration % len(dest_mac_variants)]
        elif mutation_type == 'ip_header':
            pass
        elif mutation_type == 'vl_id':
            pass
        elif mutation_type == 'priority':
            pass
        else:
            bag_value, frame_size, sequence_number_override, dest_mac_mutation = \
                self._generic_fallback(iteration, value)

        tc_idx = violation['id'].split('_TC')[-1] if '_TC' in violation['id'] else '0'
        strategy = {
            "target_vl": target_vl,
            "mutation_type": rule_id,
            "protocol_rule": rule_id,
            "test_mode": "predefined",
            "test_cases": [f"TC{tc_idx}"],
            "custom_mutation": None,
            "strategy": "edge-case",
            "bag_value": bag_value,
            "frame_size": frame_size,
            "sequence_number": sequence_number,
            "sequence_number_override": sequence_number_override,
            "dest_mac_mutation": dest_mac_mutation,
            "mac_mutation_type": mac_mutation_type,
            "prob": prob,
            "timing_jitter_ms": None,
            "payload_pattern": None,
            "reasoning": (
                f"boofuzz baseline: iteration {iteration}. "
                f"Systematically testing violation '{violation['id']}' "
                f"({violation['violation_type']}) on VL {target_vl}. "
                f"No learning or adaptation - exhaustive sequential testing."
            ),
            "violation_id": violation['id'],
            "violation_type": violation['violation_type'],
            "expected_behavior": violation.get('expected_behavior', 'N/A')
        }

        return strategy

    # ------------------------------------------------------------------
    @staticmethod
    def _classify_mutation(rule_id: str) -> str:
        """Map rule_id to a mutation category via keyword matching."""
        r = rule_id.lower()
        if 'bag' in r or 'bandwidth' in r or 'traffic_shaping' in r:
            return 'bag'
        if any(k in r for k in ('sequence', 'ordinal', 'integrity_check', 'duplicate',
                                'redundancy')):
            return 'sequence_number'
        if any(k in r for k in ('frame', 'ethernet', 'fragment', 'reassembly',
                                'payload', 'data_size', 'mtu', 'overhead')):
            return 'frame_size'
        if any(k in r for k in ('ip', 'ttl', 'routing', 'datagram', 'header')):
            return 'ip_header'
        if any(k in r for k in ('virtual_link', 'vl_', 'switching', 'switch',
                                'forwarding')):
            return 'vl_id'
        if 'priority' in r or 'qos' in r or 'quality' in r:
            return 'priority'
        if any(k in r for k in ('mac', 'address', 'destination', 'source_addr')):
            return 'mac_address'
        if any(k in r for k in ('latency', 'jitter', 'delay', 'timing')):
            return 'bag'
        if any(k in r for k in ('filter', 'policing', 'discard', 'reject')):
            return 'frame_size'
        return 'generic'

    @staticmethod
    def _generic_fallback(iteration: int, value):
        """Produce concrete mutation params for rules that don't match any keyword.

        Deterministically cycles through four mutation styles so that
        successive generic rules exercise different simulator paths.
        """
        cycle = iteration % 4
        bag_value = None
        frame_size = None
        seq_override = None
        dest_mac = None

        if isinstance(value, (int, float)):
            iv = int(value)
        else:
            iv = None

        if cycle == 0:
            bag_value = iv if iv is not None else 1
            frame_size = 63
        elif cycle == 1:
            frame_size = iv if iv is not None else 1519
            seq_override = 0
        elif cycle == 2:
            bag_value = iv if iv is not None else 0
            dest_mac = 'corrupt_prefix'
        else:
            frame_size = iv if iv is not None else 17
            dest_mac = 'wrong_vl'
            seq_override = 255

        return bag_value, frame_size, seq_override, dest_mac
    
    def get_progress(self) -> Dict[str, Any]:
        """
        Get testing progress.
        
        Returns:
            Progress dictionary
        """
        total = len(self.all_violations)
        tested = len(self.tested_violations)
        
        return {
            'total_violations': total,
            'tested_violations': tested,
            'coverage_percent': (tested / total * 100) if total > 0 else 0,
            'remaining': total - tested,
            'current_index': self.current_index
        }
    
    def reset(self):
        """Reset to start testing from beginning."""
        self.current_index = 0
        self.tested_violations.clear()


if __name__ == "__main__":
    print("=" * 70)
    print("BOOFUZZ STRATEGY GENERATOR TEST")
    print("=" * 70)
    
    generator = BoofuzzStrategyGenerator()
    system_config = {'available_vls': [1001, 1002, 2001, 2002]}
    
    print(f"\nTotal violations to test: {len(generator.all_violations)}")
    print("\nGenerating first 5 strategies:")
    
    for i in range(5):
        strategy = generator.plan_next_iteration(
            history=None,
            iteration=i,
            system_config=system_config
        )
        
        print(f"\nIteration {i}:")
        print(f"  VL: {strategy['target_vl']}")
        print(f"  Rule: {strategy['protocol_rule']}")
        print(f"  Violation ID: {strategy['violation_id']}")
        print(f"  Violation Type: {strategy['violation_type']}")
        print(f"  BAG value: {strategy['bag_value']}")
    
    print("\n" + "-" * 70)
    progress = generator.get_progress()
    print(f"Progress: {progress['tested_violations']}/{progress['total_violations']} "
          f"({progress['coverage_percent']:.1f}%)")

