#!/usr/bin/env python3
"""
Custom Mutation Parser

Parses LLM's natural language mutation descriptions into concrete mutation parameters.
The LLM has freedom to describe mutations in natural language, and this parser
extracts the specific parameters to apply.

Examples of LLM descriptions:
- "Set BAG to 5ms"
- "Frame size to 2000 bytes"
- "Use VL ID 9999"
- "Set BAG to 5ms AND frame size to 2000 bytes"
- "Invalid sequence numbers starting from 100"
"""

import re
from typing import Dict, Any, Optional, List


class CustomMutationParser:
    """
    Parses LLM's custom mutation descriptions into actionable parameters.
    
    This class does NOT make decisions - it only extracts what the LLM specified.
    """
    
    def __init__(self):
        """Initialize the parser with regex patterns."""
        self.patterns = {
            # BAG patterns
            'bag_ms': [
                r'BAG\s+(?:to\s+|=\s*)?(\d+)\s*ms',
                r'set\s+BAG\s+(?:to\s+)?(\d+)',
                r'BAG\s*[:=]\s*(\d+)',
            ],
            
            # Frame size patterns
            'frame_size': [
                r'frame\s+size\s+(?:to\s+|=\s*)?(\d+)\s*bytes?',
                r'size\s+(?:to\s+|=\s*)?(\d+)\s*bytes?',
                r'(\d+)\s*bytes?\s+frame',
            ],
            
            # VL ID patterns
            'vl_id': [
                r'VL\s+(?:ID\s+)?(\d+)',
                r'Virtual\s+Link\s+(\d+)',
                r'use\s+VL\s+(\d+)',
            ],
            
            # Sequence number patterns
            'sequence_number': [
                r'sequence\s+(?:number\s+)?(?:to\s+|=\s*)?(\d+)',
                r'seq\s+(?:=\s*)?(\d+)',
                r'sequence\s+starting\s+(?:from\s+|at\s+)?(\d+)',
            ],
            
            # Timing jitter patterns
            'timing_jitter_ms': [
                r'jitter\s+(?:of\s+)?(\d+)\s*ms',
                r'timing\s+jitter\s+(\d+)',
            ],
        }
        
        # Pattern for boolean flags (e.g., "invalid sequence")
        self.flag_patterns = {
            'invalid_sequence': r'invalid\s+sequence',
            'malformed_frame': r'malformed\s+frame',
            'out_of_order': r'out\s+of\s+order',
        }
    
    def parse(self, description: str) -> Dict[str, Any]:
        """
        Parse LLM's custom mutation description.
        
        Args:
            description: Natural language description from LLM
            
        Returns:
            Dictionary with extracted mutation parameters
            
        Example:
            >>> parser = CustomMutationParser()
            >>> parser.parse("Set BAG to 5ms AND frame size to 2000 bytes")
            {'bag_ms': 5, 'frame_size': 2000}
        """
        if not description:
            return {}
        
        mutations = {}
        description_lower = description.lower()
        
        # Extract numeric parameters
        for param_name, patterns in self.patterns.items():
            value = self._extract_numeric_parameter(description_lower, patterns)
            if value is not None:
                mutations[param_name] = value
        
        # Extract boolean flags
        for flag_name, pattern in self.flag_patterns.items():
            if re.search(pattern, description_lower):
                mutations[flag_name] = True
        
        # Special case: detect "above max" or "below min" hints
        if 'above' in description_lower and ('max' in description_lower or 'lmax' in description_lower):
            mutations['intent'] = 'above_max'
        elif 'below' in description_lower and ('min' in description_lower or 'lmin' in description_lower):
            mutations['intent'] = 'below_min'
        
        return mutations
    
    def _extract_numeric_parameter(self, text: str, patterns: List[str]) -> Optional[int]:
        """
        Try to extract a numeric parameter using multiple regex patterns.
        
        Args:
            text: Text to search
            patterns: List of regex patterns to try
            
        Returns:
            Extracted integer value or None
        """
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                try:
                    return int(match.group(1))
                except (ValueError, IndexError):
                    continue
        return None
    
    def validate_mutations(self, mutations: Dict[str, Any], spec_rules: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate extracted mutations against specification rules.
        
        This is NOT for enforcement - it's to provide warnings if the LLM
        specified something that might not be testable.
        
        Args:
            mutations: Extracted mutations
            spec_rules: Protocol specification rules
            
        Returns:
            Validation result with warnings
        """
        warnings = []
        
        # Check BAG
        if 'bag_ms' in mutations:
            allowed_bags = spec_rules.get('bag', {}).get('allowed_values_ms', [])
            if allowed_bags and mutations['bag_ms'] not in allowed_bags:
                warnings.append(f"BAG {mutations['bag_ms']}ms not in allowed list {allowed_bags}")
        
        # Check frame size
        if 'frame_size' in mutations:
            frame_rules = spec_rules.get('frame_structure', {}).get('ethernet', {})
            lmin = frame_rules.get('lmin', 64)
            lmax = frame_rules.get('lmax', 1518)
            
            if mutations['frame_size'] < lmin:
                warnings.append(f"Frame size {mutations['frame_size']} below lmin {lmin}")
            elif mutations['frame_size'] > lmax:
                warnings.append(f"Frame size {mutations['frame_size']} above lmax {lmax}")
        
        return {
            'valid': len(warnings) == 0,
            'warnings': warnings,
            'mutations': mutations
        }
    
    def to_string(self, mutations: Dict[str, Any]) -> str:
        """
        Convert mutations back to human-readable description.
        
        Useful for logging and debugging.
        
        Args:
            mutations: Mutations dictionary
            
        Returns:
            Human-readable description
        """
        if not mutations:
            return "No mutations"
        
        parts = []
        
        if 'bag_ms' in mutations:
            parts.append(f"BAG={mutations['bag_ms']}ms")
        
        if 'frame_size' in mutations:
            parts.append(f"frame_size={mutations['frame_size']} bytes")
        
        if 'vl_id' in mutations:
            parts.append(f"VL_ID={mutations['vl_id']}")
        
        if 'sequence_number' in mutations:
            parts.append(f"seq={mutations['sequence_number']}")
        
        if 'timing_jitter_ms' in mutations:
            parts.append(f"jitter={mutations['timing_jitter_ms']}ms")
        
        for flag in ['invalid_sequence', 'malformed_frame', 'out_of_order']:
            if mutations.get(flag):
                parts.append(flag.replace('_', ' '))
        
        if 'intent' in mutations:
            parts.append(f"intent:{mutations['intent']}")
        
        return ", ".join(parts)


if __name__ == "__main__":
    # Quick test
    parser = CustomMutationParser()
    
    print("=" * 70)
    print("MUTATION PARSER TEST")
    print("=" * 70)
    
    test_cases = [
        "Set BAG to 5ms",
        "Frame size to 2000 bytes",
        "Use VL ID 9999",
        "Set BAG to 5ms AND frame size to 2000 bytes",
        "Invalid sequence numbers starting from 100",
        "VL 2001 with BAG 3ms (not in list) and frame size 1519 bytes",
    ]
    
    for description in test_cases:
        print(f"\n Input: '{description}'")
        mutations = parser.parse(description)
        print(f"Output: {mutations}")
        print(f"String: {parser.to_string(mutations)}")

