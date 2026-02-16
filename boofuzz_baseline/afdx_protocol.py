#!/usr/bin/env python3
"""
AFDX Protocol Definition for boofuzz

This module defines the AFDX packet structure for boofuzz, using the SAME
violation test cases as the LLM fuzzer for fair comparison.

Key difference from standard boofuzz:
- We don't use random mutations (bit flip, format strings, etc.)
- We use SEMANTIC violations from test_cases.json
- This ensures apples-to-apples comparison with LLM fuzzer
"""

import json
import sys
from pathlib import Path
from typing import Dict, List, Any, Optional

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))


class AFDXTestCaseGenerator:
    """
    Generates AFDX test cases for boofuzz using the same violations
    defined in test_cases.json.
    
    This is NOT random fuzzing - it's deterministic protocol testing
    with the same semantic violations as the LLM fuzzer.
    """
    
    def __init__(
        self,
        test_cases_path: str = "configs/test_cases.json",
        spec_rules_path: str = "configs/spec_rules.json"
    ):
        """
        Initialize AFDX test case generator.
        
        Args:
            test_cases_path: Path to test_cases.json
            spec_rules_path: Path to spec_rules.json
        """
        self.test_cases_path = Path(test_cases_path)
        self.spec_rules_path = Path(spec_rules_path)
        
        # Load test cases and spec rules
        with open(self.test_cases_path, 'r') as f:
            self.test_cases = json.load(f)
        
        with open(self.spec_rules_path, 'r') as f:
            self.spec_rules = json.load(f)
        
        # Extract all violation test cases
        self.all_violations = self._extract_all_violations()
        
        # Default AFDX parameters
        self.default_params = {
            'vl_id': 1001,
            'bag_ms': 8,  # Valid BAG
            'frame_size': 128,
            'sequence_start': 1,
            'dest_mac': '03:00:00:00:00:01',
            'src_mac': '02:00:00:00:00:01',
            'ethertype': 0x0800,
            'ip_version': 4,
            'ttl': 1,
            'src_ip': '10.0.0.1',
            'dst_ip': '10.0.0.2',
            'src_port': 5000,
            'dst_port': 5001
        }
    
    def _extract_all_violations(self) -> List[Dict[str, Any]]:
        """
        Extract all violation test cases from test_cases.json.
        
        Returns:
            List of violation test cases with rule info
        """
        violations = []
        
        for rule_id, rule_data in self.test_cases.items():
            if 'test_cases' in rule_data:
                for idx, test_case in enumerate(rule_data['test_cases']):
                    violation = {
                        'id': f"{rule_id}_TC{idx}",
                        'rule_id': rule_id,
                        'value': test_case.get('value'),
                        'violation_type': test_case.get('violation_type'),
                        'reason': test_case.get('reason'),
                        'expected_behavior': test_case.get('expected_behavior')
                    }
                    violations.append(violation)
        
        return violations
    
    def get_all_violations(self) -> List[Dict[str, Any]]:
        """Get all violation test cases."""
        return self.all_violations
    
    def get_violations_by_rule(self, rule_id: str) -> List[Dict[str, Any]]:
        """Get violations for a specific rule."""
        return [v for v in self.all_violations if v['rule_id'] == rule_id]
    
    def get_violation_count(self) -> int:
        """Get total number of violations."""
        return len(self.all_violations)
    
    def generate_afdx_frame(
        self,
        violation: Dict[str, Any],
        vl_id: int = 1001
    ) -> Dict[str, Any]:
        """
        Generate an AFDX frame with a specific violation.
        
        Args:
            violation: Violation dictionary
            vl_id: Virtual Link ID
            
        Returns:
            AFDX frame dictionary
        """
        frame = self.default_params.copy()
        frame['vl_id'] = vl_id
        frame['violation_id'] = violation['id']
        frame['violation_type'] = violation['violation_type']
        
        # Apply violation based on rule type
        rule_id = violation['rule_id']
        value = violation['value']
        
        if rule_id == 'bag':
            # BAG violation
            if isinstance(value, (int, float)):
                frame['bag_ms'] = int(value)
            else:
                frame['bag_ms'] = 0  # Invalid format -> use 0
        
        elif 'sequence' in rule_id.lower():
            # Sequence number violation
            if isinstance(value, int):
                frame['sequence_number'] = value
            elif isinstance(value, list):
                frame['sequence_pattern'] = value
            else:
                frame['sequence_number'] = 999  # Invalid
        
        elif 'frame_structure' in rule_id or 'ethernet' in rule_id:
            # Frame structure violation
            if 'size' in str(value).lower() or isinstance(value, int):
                if isinstance(value, int):
                    frame['frame_size'] = value
        
        elif 'ip_header' in rule_id:
            # IP header violation
            if isinstance(value, int):
                if 'version' in str(violation['reason']).lower():
                    frame['ip_version'] = value
                elif 'length' in str(violation['reason']).lower():
                    frame['ip_total_length'] = value
            elif isinstance(value, str):
                if '.' in value:  # IP address
                    frame['src_ip'] = value
        
        elif 'virtual_link' in rule_id:
            # Virtual link violation
            if isinstance(value, int):
                frame['vl_id'] = value
        
        elif 'priority' in rule_id:
            # Priority violation
            if isinstance(value, (int, str)):
                frame['priority'] = value
        
        elif 'filtering_policing' in rule_id or 'monitoring' in rule_id:
            # These violations affect frame characteristics
            if isinstance(value, str) and 'frame' in value.lower():
                if '63' in value:
                    frame['frame_size'] = 63
                elif '1519' in value:
                    frame['frame_size'] = 1519
        
        return frame
    
    def generate_test_sequence(
        self,
        violation: Dict[str, Any],
        vl_id: int = 1001,
        num_frames: int = 20
    ) -> List[Dict[str, Any]]:
        """
        Generate a sequence of frames for testing a violation.
        
        Uses the same smart sequence pattern as the LLM fuzzer:
        - Valid baseline frames
        - Violation frames
        - Recovery frames
        - Mixed frames
        
        Args:
            violation: Violation to test
            vl_id: Virtual Link ID
            num_frames: Number of frames to generate
            
        Returns:
            List of frame dictionaries
        """
        frames = []
        time_offset = 0.0
        seq = 1
        
        # Get valid and invalid parameters
        base_frame = self.generate_afdx_frame(violation, vl_id)
        valid_bag = self.default_params['bag_ms']
        invalid_bag = base_frame.get('bag_ms', valid_bag)
        bag_interval = valid_bag / 1000.0
        
        # Pattern 1: Valid baseline (3 frames)
        for i in range(3):
            frame = {
                'time': round(time_offset, 4),
                'seq': seq,
                'bag_ms': valid_bag,
                'frame_size': self.default_params['frame_size'],
                'is_valid': True,
                'violation_id': None
            }
            frames.append(frame)
            seq += 1
            time_offset += bag_interval
        
        # Pattern 2: Violation frames (5 frames)
        for i in range(5):
            frame = base_frame.copy()
            frame['time'] = round(time_offset, 4)
            frame['seq'] = seq
            frame['is_valid'] = False
            frames.append(frame)
            seq += 1
            time_offset += bag_interval
        
        # Pattern 3: Recovery (3 frames)
        for i in range(3):
            frame = {
                'time': round(time_offset, 4),
                'seq': seq,
                'bag_ms': valid_bag,
                'frame_size': self.default_params['frame_size'],
                'is_valid': True,
                'violation_id': None
            }
            frames.append(frame)
            seq += 1
            time_offset += bag_interval
        
        # Pattern 4: Stress test (4 frames violation)
        for i in range(4):
            frame = base_frame.copy()
            frame['time'] = round(time_offset, 4)
            frame['seq'] = seq
            frame['is_valid'] = False
            frames.append(frame)
            seq += 1
            time_offset += bag_interval
        
        # Pattern 5: Interleaved (5 frames)
        for i in range(min(5, num_frames - len(frames))):
            is_violation = (i % 2 == 1)
            if is_violation:
                frame = base_frame.copy()
                frame['is_valid'] = False
            else:
                frame = {
                    'bag_ms': valid_bag,
                    'frame_size': self.default_params['frame_size'],
                    'is_valid': True,
                    'violation_id': None
                }
            frame['time'] = round(time_offset, 4)
            frame['seq'] = seq
            frames.append(frame)
            seq += 1
            time_offset += bag_interval
        
        return frames[:num_frames]


def get_all_test_cases() -> List[Dict[str, Any]]:
    """
    Get all AFDX test cases for boofuzz.
    
    Returns:
        List of all violation test cases
    """
    generator = AFDXTestCaseGenerator()
    return generator.get_all_violations()


if __name__ == "__main__":
    print("=" * 70)
    print("AFDX PROTOCOL TEST CASES FOR BOOFUZZ")
    print("=" * 70)
    
    generator = AFDXTestCaseGenerator()
    
    print(f"\nTotal violations: {generator.get_violation_count()}")
    print("\nViolations by rule:")
    
    # Group by rule
    rules = {}
    for v in generator.all_violations:
        rule = v['rule_id']
        if rule not in rules:
            rules[rule] = []
        rules[rule].append(v)
    
    for rule, violations in sorted(rules.items()):
        print(f"  {rule}: {len(violations)} violations")
    
    print("\n" + "-" * 70)
    print("Sample violation test sequence:")
    
    # Generate sample
    sample_violation = generator.all_violations[0]
    print(f"\nViolation: {sample_violation['id']}")
    print(f"Type: {sample_violation['violation_type']}")
    print(f"Value: {sample_violation['value']}")
    
    sequence = generator.generate_test_sequence(sample_violation)
    print(f"\nGenerated {len(sequence)} frames:")
    for i, frame in enumerate(sequence[:5]):
        print(f"  Frame {i}: seq={frame['seq']}, valid={frame['is_valid']}")

