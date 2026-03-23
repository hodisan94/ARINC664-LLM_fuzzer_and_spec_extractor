#!/usr/bin/env python3
"""
Strategy-Driven Test Input Generator

This is Component 3 of the LLM-Guided Iterative Fuzzing Process.
It transforms the LLM's strategy into concrete AFDX frames for simulator execution.

The generator does NOT make decisions - it strictly follows the LLM's strategy.
"""

import json
import os
from typing import Dict, List, Any, Optional
from pathlib import Path

# Import sibling modules
import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from llm_fuzzer.utils.test_case_loader import TestCaseLoader
from llm_fuzzer.core.mutation_parser import CustomMutationParser


class TestGenerator:
    """
    Generates AFDX test frames based on LLM's strategy.
    
    The generator operates in two modes:
    1. Predefined mode: Uses test cases from test_cases.json
    2. Custom mode: Parses LLM's custom mutation description
    
    In both cases, the generator ONLY executes what the LLM decided.
    """
    
    def __init__(
        self,
        seed_frames_path: str = "llm_fuzzer/data/seed_frames.json",
        test_cases_path: str = "configs/test_cases.json",
        num_frames_per_test: int = 20
    ):
        """
        Initialize test generator.
        
        Args:
            seed_frames_path: Path to seed frames JSON
            test_cases_path: Path to test cases JSON
            num_frames_per_test: Number of frames to generate per test
        """
        self.seed_frames_path = Path(seed_frames_path)
        self.num_frames_per_test = num_frames_per_test
        
        # Load seed frames
        if not self.seed_frames_path.exists():
            raise FileNotFoundError(f"Seed frames not found: {seed_frames_path}")
        
        with open(self.seed_frames_path, 'r') as f:
            self.seed_frames = json.load(f)
        
        # Load test cases
        self.test_case_loader = TestCaseLoader(test_cases_path)
        
        # Initialize mutation parser
        self.mutation_parser = CustomMutationParser()
    
    def generate_test_inputs(self, strategy: Dict[str, Any]) -> Dict[str, Any]:
        """
        Generate test inputs based on LLM's strategy (PAPER-ALIGNED).
        
        LLM provides SPECIFIC MUTATION PARAMETERS, not test case IDs.
        
        Args:
            strategy: Strategy dictionary from LLM with keys:
                - target_vl: int
                - mutation_type: str
                - bag_value: int or None
                - frame_size: int or None
                - sequence_number: int or None
                - timing_jitter_ms: int or None
                - payload_pattern: str or None
                - strategy: str (conformance/edge-case/adversarial)
                
        Returns:
            Dictionary with:
                - vl_id: int
                - frames: List[Dict] with time, seq, bag_ms, payload_hex
                - metadata: Dict with test info
        """
        # Load base seed frame
        seed_frame = self._load_seed_frame(strategy['target_vl'])
        
        # Generate frames based on mutation parameters
        frames = self._generate_mutation_frames(seed_frame, strategy)
        
        # Create output structure (HYBRID - includes both test_cases and params)
        output = {
            'vl_id': strategy['target_vl'],
            'frames': frames,
            'metadata': {
                'mutation_type': strategy['mutation_type'],
                'test_cases': strategy.get('test_cases'),
                'bag_value': strategy.get('bag_value'),
                'frame_size': strategy.get('frame_size'),
                'sequence_number': strategy.get('sequence_number'),
                'timing_jitter_ms': strategy.get('timing_jitter_ms'),
                'payload_pattern': strategy.get('payload_pattern'),
                'mac_mutation_type': strategy.get('mac_mutation_type'),
                'prob': strategy.get('prob'),
                'sequence_number_override': strategy.get('sequence_number_override'),
                'dest_mac_mutation': strategy.get('dest_mac_mutation'),
                'strategy_type': strategy.get('strategy', 'unknown'),
                'num_frames': len(frames)
            }
        }
        
        return output
    
    def _load_seed_frame(self, vl_id: int) -> Dict[str, Any]:
        """
        Load seed frame for a specific VL.
        
        Args:
            vl_id: Virtual Link ID
            
        Returns:
            Seed frame dictionary
        """
        # Try to find specific VL
        vl_key = f"vl_{vl_id}"
        
        if vl_key in self.seed_frames:
            return self.seed_frames[vl_key].copy()
        
        # Use default seed and override VL ID
        if 'vl_default' in self.seed_frames:
            seed = self.seed_frames['vl_default'].copy()
            seed['vl_id'] = vl_id
            return seed
        
        # Fallback: create minimal seed
        return {
            'vl_id': vl_id,
            'default_bag_ms': 8,
            'default_frame_size_bytes': 128,
            'default_sequence_start': 1,
            'default_payload_hex': '00' * 64
        }
    
    def _generate_mutation_frames(
        self,
        seed_frame: Dict[str, Any],
        strategy: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        Generate frames using HYBRID approach - LLM has FULL FREEDOM.
        
        LLM can choose:
        1. test_cases only (use predefined test cases)
        2. mutation params only (specify exact values)
        3. BOTH (combine test cases with additional mutations)
        
        Args:
            seed_frame: Base seed frame
            strategy: Full strategy with all parameters
            
        Returns:
            List of frame dictionaries
        """
        frames = []
        
        # Check what LLM provided
        has_test_cases = strategy.get('test_cases') and len(strategy.get('test_cases', [])) > 0
        has_mutation_params = any([
            strategy.get('bag_value') is not None,
            strategy.get('frame_size') is not None,
            strategy.get('sequence_number') is not None,
            strategy.get('timing_jitter_ms') is not None,
            strategy.get('payload_pattern') is not None
        ])
        
        # SCENARIO 1: LLM chose test_cases (predefined)
        if has_test_cases and not has_mutation_params:
            frames = self._apply_test_cases(seed_frame, strategy)
        
        # SCENARIO 2: LLM chose specific mutation values
        elif has_mutation_params and not has_test_cases:
            frames = self._apply_mutation_params(seed_frame, strategy)
        
        # SCENARIO 3: LLM combined both (smart!)
        elif has_test_cases and has_mutation_params:
            # First apply test cases
            frames_from_tc = self._apply_test_cases(seed_frame, strategy)
            # Then add frames with mutation params
            frames_from_params = self._apply_mutation_params(seed_frame, strategy)
            # Combine (test cases first, then mutations)
            frames = frames_from_tc + frames_from_params
        
        else:
            # Fallback: shouldn't happen due to validation
            frames = self._create_generic_varied_sequence(seed_frame, {})
        
        return frames
    
    def _apply_test_cases(
        self,
        seed_frame: Dict[str, Any],
        strategy: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        Apply test cases chosen by LLM.
        
        Args:
            seed_frame: Base seed frame
            strategy: Strategy with test_cases
            
        Returns:
            List of frames based on test cases
        """
        test_case_ids = strategy.get('test_cases', [])
        mutation_type = strategy.get('mutation_type', 'generic')
        
        frames = []
        
        # Get all test cases for this mutation type
        # Try to match mutation_type to a rule name
        rule_candidates = [
            'bag', 'sequence_numbers', 'sequence_number_field',
            'virtual_link.id_range', 'frame_structure.ethernet'
        ]
        
        # Try to find matching rule
        protocol_rule = None
        for rule in rule_candidates:
            if rule.lower() in mutation_type.lower():
                protocol_rule = rule
                break
        
        # If no match, use first word of mutation_type
        if not protocol_rule:
            protocol_rule = mutation_type.split('_')[0]
        
        # Get test cases for this rule
        all_test_cases = self.test_case_loader.get_test_cases_for_rule(protocol_rule)
        
        if not all_test_cases:
            # No test cases found - use direct values if available
            return []
        
        # Apply each test case
        for tc_id in test_case_ids:
            try:
                idx = int(tc_id.replace('TC', ''))
                if idx < len(all_test_cases):
                    test_case = all_test_cases[idx]
                    tc_frames = self._apply_test_case_mutation(
                        seed_frame, protocol_rule, test_case
                    )
                    frames.extend(tc_frames)
            except (ValueError, IndexError):
                continue
        
        return frames
    
    def _apply_mutation_params(
        self,
        seed_frame: Dict[str, Any],
        strategy: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        Apply specific mutation parameters chosen by LLM.
        
        Args:
            seed_frame: Base seed frame
            strategy: Strategy with mutation parameters
            
        Returns:
            List of frames with mutations applied
        """
        # Extract mutation parameters
        target_bag = strategy.get('bag_value')
        target_size = strategy.get('frame_size')
        target_seq = strategy.get('sequence_number')
        jitter = strategy.get('timing_jitter_ms')
        payload_pattern = strategy.get('payload_pattern')
        
        # Use seed frame defaults if parameters not specified
        valid_bag = seed_frame['default_bag_ms']
        valid_size = seed_frame['default_frame_size_bytes']
        valid_seq_start = seed_frame['default_sequence_start']
        
        # Determine which type of smart sequence to generate
        mutation_type = strategy.get('mutation_type', 'generic')
        
        if 'bag' in mutation_type.lower() and target_bag is not None:
            # BAG-focused mutation
            frames = self._create_smart_bag_sequence(
                seed_frame=seed_frame,
                invalid_bag=target_bag,
                valid_bag=valid_bag
            )
        elif 'frame' in mutation_type.lower() or 'size' in mutation_type.lower():
            # Frame size mutation
            size_to_use = target_size if target_size is not None else valid_size
            frames = self._create_smart_frame_size_sequence(
                seed_frame=seed_frame,
                invalid_size=size_to_use,
                valid_size=valid_size
            )
        elif 'seq' in mutation_type.lower() or 'sequence' in mutation_type.lower():
            # Sequence number mutation
            frames = self._create_smart_sequence_test_direct(
                seed_frame=seed_frame,
                target_sequence=target_seq
            )
        else:
            # Generic mutation: apply all specified parameters
            frames = self._create_direct_mutation_sequence(
                seed_frame=seed_frame,
                bag=target_bag if target_bag is not None else valid_bag,
                size=target_size if target_size is not None else valid_size,
                seq_start=target_seq if target_seq is not None else valid_seq_start,
                jitter_ms=jitter,
                payload_pattern=payload_pattern
            )
        
        return frames
    
    def _apply_test_case_mutation(
        self,
        seed_frame: Dict[str, Any],
        protocol_rule: str,
        test_case: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        Apply a specific test case mutation to generate SMART SEQUENCES.
        
        Instead of 20 identical frames, create varied sequences that:
        1. Test the violation multiple times with variations
        2. Include valid→invalid→valid transitions
        3. Test edge cases and boundaries
        
        Args:
            seed_frame: Base seed frame
            protocol_rule: Rule being tested
            test_case: Test case dictionary with 'value', 'violation_type', etc.
            
        Returns:
            List of mutated frames (smart sequence, NOT identical frames)
        """
        frames = []
        
        # Determine what to mutate based on protocol rule
        if protocol_rule == 'bag':
            # BAG testing: create VARIED sequence
            mutation_value = test_case.get('value', seed_frame['default_bag_ms'])
            valid_bag = seed_frame['default_bag_ms']
            
            # Smart sequence for BAG testing
            frames = self._create_smart_bag_sequence(
                seed_frame=seed_frame,
                invalid_bag=mutation_value if isinstance(mutation_value, int) else valid_bag,
                valid_bag=valid_bag
            )
        
        elif 'sequence' in protocol_rule.lower():
            # Sequence number testing
            frames = self._create_smart_sequence_number_test(
                seed_frame=seed_frame,
                test_case=test_case
            )
        
        elif 'frame' in protocol_rule or 'ethernet' in protocol_rule:
            # Frame size testing: create VARIED sequence
            mutation_value = test_case.get('value', seed_frame['default_frame_size_bytes'])
            valid_size = seed_frame['default_frame_size_bytes']
            
            frames = self._create_smart_frame_size_sequence(
                seed_frame=seed_frame,
                invalid_size=mutation_value if isinstance(mutation_value, int) else valid_size,
                valid_size=valid_size
            )
        
        else:
            # Generic: at least add some variation
            frames = self._create_generic_varied_sequence(
                seed_frame=seed_frame,
                test_case=test_case
            )
        
        return frames
    
    def _generate_custom_frames(
        self,
        seed_frame: Dict[str, Any],
        custom_mutation: str
    ) -> List[Dict[str, Any]]:
        """
        Generate frames using LLM's custom mutation description.
        
        Args:
            seed_frame: Base seed frame
            custom_mutation: Natural language mutation description
            
        Returns:
            List of mutated frames
        """
        # Parse the custom mutation
        mutations = self.mutation_parser.parse(custom_mutation)
        
        # Apply mutations
        vl_id = mutations.get('vl_id', seed_frame['vl_id'])
        bag_ms = mutations.get('bag_ms', seed_frame['default_bag_ms'])
        frame_size = mutations.get('frame_size', seed_frame['default_frame_size_bytes'])
        sequence_start = mutations.get('sequence_number', seed_frame['default_sequence_start'])
        
        # Generate frame sequence
        frames = self._create_frame_sequence(
            vl_id=vl_id,
            bag_ms=bag_ms,
            frame_size=frame_size,
            sequence_start=sequence_start,
            payload_hex=seed_frame['default_payload_hex'],
            num_frames=self.num_frames_per_test
        )
        
        return frames
    
    def _create_frame_sequence(
        self,
        vl_id: int,
        bag_ms: int,
        frame_size: int,
        sequence_start: int,
        payload_hex: str,
        num_frames: int
    ) -> List[Dict[str, Any]]:
        """
        Create a sequence of frames with specified parameters.
        
        Args:
            vl_id: Virtual Link ID
            bag_ms: BAG in milliseconds
            frame_size: Frame size in bytes
            sequence_start: Starting sequence number
            payload_hex: Payload hex string
            num_frames: Number of frames to generate
            
        Returns:
            List of frame dictionaries
        """
        frames = []
        
        # Ensure payload fits frame size
        payload = self._adjust_payload(payload_hex, frame_size)
        
        # Generate frames
        for i in range(num_frames):
            # Calculate timing
            # If BAG is valid, space frames accordingly
            # If BAG is 0 or invalid, still generate frames with small intervals
            if bag_ms > 0:
                time = i * (bag_ms / 1000.0)  # Convert ms to seconds
            else:
                time = i * 0.01  # 10ms interval even for BAG=0
            
            frame = {
                'time': round(time, 4),
                'seq': sequence_start + i,
                'bag_ms': bag_ms,
                'payload_hex': payload
            }
            
            frames.append(frame)
        
        return frames
    
    def _adjust_payload(self, payload_hex: str, target_size: int) -> str:
        """
        Adjust payload to match target frame size.
        
        Args:
            payload_hex: Original payload hex string
            target_size: Target size in bytes
            
        Returns:
            Adjusted payload hex string
        """
        # Each hex pair = 1 byte
        current_bytes = len(payload_hex) // 2
        
        if current_bytes < target_size:
            # Pad with zeros
            padding = '00' * (target_size - current_bytes)
            return payload_hex + padding
        elif current_bytes > target_size:
            # Truncate
            return payload_hex[:target_size * 2]
        else:
            return payload_hex
    
    # =========================================================================
    # SMART SEQUENCE GENERATORS
    # These create VARIED, INTELLIGENT test sequences instead of repetitive ones
    # =========================================================================
    
    def _create_smart_bag_sequence(
        self,
        seed_frame: Dict[str, Any],
        invalid_bag: int,
        valid_bag: int
    ) -> List[Dict[str, Any]]:
        """
        Create smart BAG test sequence with variations.
        
        Sequence pattern:
        1. Valid frames (establish baseline)
        2. Invalid BAG (primary test)
        3. Valid frames (test recovery)
        4. Invalid BAG repeated (stress test)
        5. Transition test (valid->invalid->valid)
        
        Args:
            seed_frame: Base seed frame
            invalid_bag: Invalid BAG value to test
            valid_bag: Valid BAG value
            
        Returns:
            List of frames with varied BAG values
        """
        frames = []
        seq = seed_frame['default_sequence_start']
        time_offset = 0.0
        
        # Pattern 1: Start with valid frames (baseline)
        for i in range(3):
            frames.append({
                'time': round(time_offset, 4),
                'seq': seq,
                'bag_ms': valid_bag,
                'payload_hex': self._adjust_payload(seed_frame['default_payload_hex'], 
                                                     seed_frame['default_frame_size_bytes'])
            })
            seq += 1
            time_offset += valid_bag / 1000.0
        
        # Pattern 2: Invalid BAG (main test - 5 frames)
        invalid_interval = 0.01 if invalid_bag <= 0 else invalid_bag / 1000.0
        for i in range(5):
            frames.append({
                'time': round(time_offset, 4),
                'seq': seq,
                'bag_ms': invalid_bag,
                'payload_hex': self._adjust_payload(seed_frame['default_payload_hex'], 
                                                     seed_frame['default_frame_size_bytes'])
            })
            seq += 1
            time_offset += invalid_interval
        
        # Pattern 3: Back to valid (recovery test - 3 frames)
        for i in range(3):
            frames.append({
                'time': round(time_offset, 4),
                'seq': seq,
                'bag_ms': valid_bag,
                'payload_hex': self._adjust_payload(seed_frame['default_payload_hex'], 
                                                     seed_frame['default_frame_size_bytes'])
            })
            seq += 1
            time_offset += valid_bag / 1000.0
        
        # Pattern 4: Burst of invalid (stress test - 4 frames)
        for i in range(4):
            frames.append({
                'time': round(time_offset, 4),
                'seq': seq,
                'bag_ms': invalid_bag,
                'payload_hex': self._adjust_payload(seed_frame['default_payload_hex'], 
                                                     seed_frame['default_frame_size_bytes'])
            })
            seq += 1
            time_offset += invalid_interval
        
        # Pattern 5: Interleaved (transition test - 5 frames)
        for i in range(5):
            bag_val = valid_bag if i % 2 == 0 else invalid_bag
            interval = (valid_bag if i % 2 == 0 else invalid_bag) / 1000.0
            if interval <= 0:
                interval = 0.01
            
            frames.append({
                'time': round(time_offset, 4),
                'seq': seq,
                'bag_ms': bag_val,
                'payload_hex': self._adjust_payload(seed_frame['default_payload_hex'], 
                                                     seed_frame['default_frame_size_bytes'])
            })
            seq += 1
            time_offset += interval
        
        return frames
    
    def _create_smart_sequence_number_test(
        self,
        seed_frame: Dict[str, Any],
        test_case: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        Create smart sequence number test.
        
        Tests:
        1. Normal sequence (1,2,3,4,5)
        2. Invalid sequence value
        3. Duplicate sequence
        4. Out-of-order sequence
        5. Skip sequence
        
        Args:
            seed_frame: Base seed frame
            test_case: Test case with invalid sequence value
            
        Returns:
            List of frames with varied sequence numbers
        """
        frames = []
        time_offset = 0.0
        bag_interval = seed_frame['default_bag_ms'] / 1000.0
        invalid_seq = test_case.get('value', 0)
        
        # Normal sequence (1,2,3,4,5)
        for seq in range(1, 6):
            frames.append({
                'time': round(time_offset, 4),
                'seq': seq,
                'bag_ms': seed_frame['default_bag_ms'],
                'payload_hex': self._adjust_payload(seed_frame['default_payload_hex'], 
                                                     seed_frame['default_frame_size_bytes'])
            })
            time_offset += bag_interval
        
        # Invalid sequence value
        for i in range(3):
            frames.append({
                'time': round(time_offset, 4),
                'seq': invalid_seq if isinstance(invalid_seq, int) else 999,
                'bag_ms': seed_frame['default_bag_ms'],
                'payload_hex': self._adjust_payload(seed_frame['default_payload_hex'], 
                                                     seed_frame['default_frame_size_bytes'])
            })
            time_offset += bag_interval
        
        # Duplicate sequence (10,10,10)
        for i in range(3):
            frames.append({
                'time': round(time_offset, 4),
                'seq': 10,
                'bag_ms': seed_frame['default_bag_ms'],
                'payload_hex': self._adjust_payload(seed_frame['default_payload_hex'], 
                                                     seed_frame['default_frame_size_bytes'])
            })
            time_offset += bag_interval
        
        # Out-of-order (15,14,13)
        for seq in [15, 14, 13]:
            frames.append({
                'time': round(time_offset, 4),
                'seq': seq,
                'bag_ms': seed_frame['default_bag_ms'],
                'payload_hex': self._adjust_payload(seed_frame['default_payload_hex'], 
                                                     seed_frame['default_frame_size_bytes'])
            })
            time_offset += bag_interval
        
        # Skip sequence (20,22,24)
        for seq in [20, 22, 24]:
            frames.append({
                'time': round(time_offset, 4),
                'seq': seq,
                'bag_ms': seed_frame['default_bag_ms'],
                'payload_hex': self._adjust_payload(seed_frame['default_payload_hex'], 
                                                     seed_frame['default_frame_size_bytes'])
            })
            time_offset += bag_interval
        
        # Back to normal (25,26,27)
        for seq in [25, 26, 27]:
            frames.append({
                'time': round(time_offset, 4),
                'seq': seq,
                'bag_ms': seed_frame['default_bag_ms'],
                'payload_hex': self._adjust_payload(seed_frame['default_payload_hex'], 
                                                     seed_frame['default_frame_size_bytes'])
            })
            time_offset += bag_interval
        
        return frames
    
    def _create_smart_frame_size_sequence(
        self,
        seed_frame: Dict[str, Any],
        invalid_size: int,
        valid_size: int
    ) -> List[Dict[str, Any]]:
        """
        Create smart frame size test sequence.
        
        Tests:
        1. Valid size frames
        2. Invalid size frames
        3. Boundary sizes (min, max, invalid)
        4. Mixed sizes
        
        Args:
            seed_frame: Base seed frame
            invalid_size: Invalid frame size to test
            valid_size: Valid frame size
            
        Returns:
            List of frames with varied sizes
        """
        frames = []
        time_offset = 0.0
        bag_interval = seed_frame['default_bag_ms'] / 1000.0
        seq = seed_frame['default_sequence_start']
        
        # Valid size baseline (3 frames)
        for i in range(3):
            frames.append({
                'time': round(time_offset, 4),
                'seq': seq,
                'bag_ms': seed_frame['default_bag_ms'],
                'payload_hex': self._adjust_payload(seed_frame['default_payload_hex'], valid_size)
            })
            seq += 1
            time_offset += bag_interval
        
        # Invalid size (5 frames)
        for i in range(5):
            frames.append({
                'time': round(time_offset, 4),
                'seq': seq,
                'bag_ms': seed_frame['default_bag_ms'],
                'payload_hex': self._adjust_payload(seed_frame['default_payload_hex'], invalid_size)
            })
            seq += 1
            time_offset += bag_interval
        
        # Boundary tests: min size (64), max size (1518), invalid
        for size in [64, 1518, invalid_size]:
            frames.append({
                'time': round(time_offset, 4),
                'seq': seq,
                'bag_ms': seed_frame['default_bag_ms'],
                'payload_hex': self._adjust_payload(seed_frame['default_payload_hex'], size)
            })
            seq += 1
            time_offset += bag_interval
        
        # Back to valid (3 frames)
        for i in range(3):
            frames.append({
                'time': round(time_offset, 4),
                'seq': seq,
                'bag_ms': seed_frame['default_bag_ms'],
                'payload_hex': self._adjust_payload(seed_frame['default_payload_hex'], valid_size)
            })
            seq += 1
            time_offset += bag_interval
        
        # Interleaved valid/invalid (6 frames)
        for i in range(6):
            size = valid_size if i % 2 == 0 else invalid_size
            frames.append({
                'time': round(time_offset, 4),
                'seq': seq,
                'bag_ms': seed_frame['default_bag_ms'],
                'payload_hex': self._adjust_payload(seed_frame['default_payload_hex'], size)
            })
            seq += 1
            time_offset += bag_interval
        
        return frames
    
    def _create_generic_varied_sequence(
        self,
        seed_frame: Dict[str, Any],
        test_case: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        Create generic varied sequence when specific rule handling not available.
        
        At minimum, create some variation in timing and sequence.
        
        Args:
            seed_frame: Base seed frame
            test_case: Test case info
            
        Returns:
            List of frames with basic variation
        """
        frames = []
        time_offset = 0.0
        bag_interval = seed_frame['default_bag_ms'] / 1000.0
        seq = seed_frame['default_sequence_start']
        
        # Create 20 frames with at least some timing variation
        for i in range(20):
            # Vary interval slightly (normal, burst, slow)
            if i % 7 == 0:
                interval = bag_interval * 0.5  # Burst
            elif i % 5 == 0:
                interval = bag_interval * 1.5  # Slow
            else:
                interval = bag_interval  # Normal
            
            frames.append({
                'time': round(time_offset, 4),
                'seq': seq,
                'bag_ms': seed_frame['default_bag_ms'],
                'payload_hex': self._adjust_payload(seed_frame['default_payload_hex'], 
                                                     seed_frame['default_frame_size_bytes'])
            })
            seq += 1
            time_offset += interval
        
        return frames
    
    def _create_smart_sequence_test_direct(
        self,
        seed_frame: Dict[str, Any],
        target_sequence: Optional[int]
    ) -> List[Dict[str, Any]]:
        """
        Create smart sequence number test using SPECIFIC target value.
        
        Args:
            seed_frame: Base seed frame
            target_sequence: Target sequence number to test
            
        Returns:
            List of frames with varied sequence numbers
        """
        frames = []
        time_offset = 0.0
        bag_interval = seed_frame['default_bag_ms'] / 1000.0
        
        # Normal sequence (1-5)
        for seq in range(1, 6):
            frames.append({
                'time': round(time_offset, 4),
                'seq': seq,
                'bag_ms': seed_frame['default_bag_ms'],
                'payload_hex': self._adjust_payload(seed_frame['default_payload_hex'], 
                                                     seed_frame['default_frame_size_bytes'])
            })
            time_offset += bag_interval
        
        # Target sequence value (repeated 3 times)
        if target_sequence is not None:
            for i in range(3):
                frames.append({
                    'time': round(time_offset, 4),
                    'seq': target_sequence,
                    'bag_ms': seed_frame['default_bag_ms'],
                    'payload_hex': self._adjust_payload(seed_frame['default_payload_hex'], 
                                                         seed_frame['default_frame_size_bytes'])
                })
                time_offset += bag_interval
        
        # Duplicate test (10,10,10)
        for i in range(3):
            frames.append({
                'time': round(time_offset, 4),
                'seq': 10,
                'bag_ms': seed_frame['default_bag_ms'],
                'payload_hex': self._adjust_payload(seed_frame['default_payload_hex'], 
                                                     seed_frame['default_frame_size_bytes'])
            })
            time_offset += bag_interval
        
        # Out-of-order (15,14,13)
        for seq in [15, 14, 13]:
            frames.append({
                'time': round(time_offset, 4),
                'seq': seq,
                'bag_ms': seed_frame['default_bag_ms'],
                'payload_hex': self._adjust_payload(seed_frame['default_payload_hex'], 
                                                     seed_frame['default_frame_size_bytes'])
            })
            time_offset += bag_interval
        
        # Back to normal (20,21,22)
        for seq in [20, 21, 22]:
            frames.append({
                'time': round(time_offset, 4),
                'seq': seq,
                'bag_ms': seed_frame['default_bag_ms'],
                'payload_hex': self._adjust_payload(seed_frame['default_payload_hex'], 
                                                     seed_frame['default_frame_size_bytes'])
            })
            time_offset += bag_interval
        
        return frames
    
    def _create_direct_mutation_sequence(
        self,
        seed_frame: Dict[str, Any],
        bag: int,
        size: int,
        seq_start: int,
        jitter_ms: Optional[int],
        payload_pattern: Optional[str]
    ) -> List[Dict[str, Any]]:
        """
        Create sequence applying DIRECT mutation parameters (combined stress test).
        
        This is used when LLM specifies multiple parameters at once.
        
        Args:
            seed_frame: Base seed frame
            bag: BAG value to use
            size: Frame size to use
            seq_start: Starting sequence number
            jitter_ms: Timing jitter to apply (optional)
            payload_pattern: Payload pattern (optional)
            
        Returns:
            List of frames with specified mutations
        """
        frames = []
        time_offset = 0.0
        bag_interval = bag / 1000.0 if bag > 0 else 0.01
        seq = seq_start
        
        # Determine payload
        if payload_pattern == "malformed":
            payload = "FF" * size  # All 0xFF
        elif payload_pattern == "zeros":
            payload = "00" * size
        elif payload_pattern == "random":
            payload = "AA55" * (size // 2)  # Pattern
        else:
            payload = self._adjust_payload(seed_frame['default_payload_hex'], size)
        
        # Generate 20 frames with specified parameters
        for i in range(20):
            # Apply jitter if specified
            if jitter_ms:
                # Add variation: +/- jitter_ms/2
                jitter_variation = (i % 3 - 1) * (jitter_ms / 2000.0)  # -jitter/2, 0, +jitter/2
                interval = bag_interval + jitter_variation
            else:
                interval = bag_interval
            
            frames.append({
                'time': round(time_offset, 4),
                'seq': seq,
                'bag_ms': bag,
                'payload_hex': payload
            })
            
            seq += 1
            time_offset += interval
        
        return frames
    
    # =========================================================================
    
    def serialize_to_json(self, test_inputs: Dict[str, Any]) -> str:
        """
        Serialize test inputs to JSON format for simulator.
        
        Args:
            test_inputs: Test inputs dictionary
            
        Returns:
            JSON string
        """
        return json.dumps(test_inputs, indent=2)
    
    def save_to_file(self, test_inputs: Dict[str, Any], output_path: str) -> str:
        """
        Save test inputs to JSON file.
        
        Args:
            test_inputs: Test inputs dictionary
            output_path: Output file path
            
        Returns:
            Absolute path to saved file
        """
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_path, 'w') as f:
            f.write(self.serialize_to_json(test_inputs))
        
        return str(output_path.absolute())


if __name__ == "__main__":
    # Quick test
    print("=" * 70)
    print("TEST GENERATOR TEST")
    print("=" * 70)
    
    try:
        generator = TestGenerator()
        print("✓ Generator initialized")
        
        # Test 1: Predefined mode
        print("\nTest 1: Predefined mode (BAG violation)")
        strategy1 = {
            'target_vl': 2001,
            'protocol_rule': 'bag',
            'test_mode': 'predefined',
            'test_cases': ['TC0'],  # BAG = 0
            'custom_mutation': None,
            'strategy': 'edge-case'
        }
        
        result1 = generator.generate_test_inputs(strategy1)
        print(f"  Generated {result1['metadata']['num_frames']} frames")
        print(f"  VL: {result1['vl_id']}")
        print(f"  First frame: {result1['frames'][0]}")
        
        # Test 2: Custom mode
        print("\nTest 2: Custom mode")
        strategy2 = {
            'target_vl': 2001,
            'protocol_rule': 'bag',
            'test_mode': 'custom',
            'test_cases': None,
            'custom_mutation': 'Set BAG to 5ms AND frame size to 2000 bytes',
            'strategy': 'adversarial'
        }
        
        result2 = generator.generate_test_inputs(strategy2)
        print(f"  Generated {result2['metadata']['num_frames']} frames")
        print(f"  First frame: {result2['frames'][0]}")
        
    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()

