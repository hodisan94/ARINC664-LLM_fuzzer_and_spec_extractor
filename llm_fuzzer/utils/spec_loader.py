#!/usr/bin/env python3
"""
Specification Rules Loader

Loads and provides access to protocol rules from spec_rules.json.
This module does NOT impose any restrictions on the LLM - it simply
provides clean access to all available rules.
"""

import json
from pathlib import Path
from typing import Dict, List, Any, Optional


class SpecificationLoader:
    """
    Loads AFDX specification rules from JSON file.
    
    This class provides read-only access to protocol rules without
    imposing any predetermined choices on the LLM.
    """
    
    def __init__(self, spec_path: str):
        """
        Initialize the specification loader.
        
        Args:
            spec_path: Path to spec_rules.json file
            
        Raises:
            FileNotFoundError: If spec file doesn't exist
            json.JSONDecodeError: If spec file is invalid JSON
        """
        self.spec_path = Path(spec_path)
        
        if not self.spec_path.exists():
            raise FileNotFoundError(f"Specification file not found: {spec_path}")
        
        with open(self.spec_path, 'r', encoding='utf-8') as f:
            self.spec_rules = json.load(f)
        
        # Build flat index of all rule names for quick access
        self._rule_index = self._build_rule_index()
    
    def _build_rule_index(self) -> Dict[str, Any]:
        """
        Build a flat index mapping rule names to their data.
        
        Indexes every dict node that contains non-dict leaf values
        (i.e., actual rule data rather than just nesting structure).
        
        Returns:
            Dictionary mapping rule names to rule data
        """
        index = {}

        def _flatten(obj: Any, prefix: str = ""):
            if isinstance(obj, dict):
                has_leaf_values = any(
                    not isinstance(v, dict) for v in obj.values()
                )

                if has_leaf_values and prefix:
                    index[prefix] = obj

                for key, value in obj.items():
                    new_prefix = f"{prefix}.{key}" if prefix else key
                    _flatten(value, new_prefix)

        _flatten(self.spec_rules)
        return index
    
    def get_all_rules(self) -> Dict[str, Any]:
        """
        Get all protocol rules as a dictionary.
        
        Returns:
            Complete specification rules dictionary
        """
        return self.spec_rules
    
    def get_rule(self, rule_name: str) -> Optional[Dict]:
        """
        Get a specific rule by name.
        
        Args:
            rule_name: Name of the rule (e.g., "bag", "frame_structure.ethernet")
            
        Returns:
            Rule data dictionary, or None if not found
        """
        return self._rule_index.get(rule_name)
    
    def get_rule_names(self) -> List[str]:
        """
        Get list of all available rule names.
        
        Returns:
            List of rule names (e.g., ["bag", "frame_structure.ethernet", ...])
        """
        return sorted(self._rule_index.keys())
    
    def search_rules(self, keyword: str) -> Dict[str, Any]:
        """
        Search for rules containing a keyword (case-insensitive).
        
        Args:
            keyword: Search term
            
        Returns:
            Dictionary of matching rules
        """
        keyword_lower = keyword.lower()
        return {
            name: rule
            for name, rule in self._rule_index.items()
            if keyword_lower in name.lower()
        }
    
    def get_rule_summary(self, rule_name: str) -> str:
        """
        Get a human-readable summary of a rule.
        
        Args:
            rule_name: Name of the rule
            
        Returns:
            Summary string, or "Rule not found" if rule doesn't exist
        """
        rule = self.get_rule(rule_name)
        if not rule:
            return f"Rule '{rule_name}' not found"
        
        summary_parts = [f"Rule: {rule_name}"]
        
        # Add key-value pairs
        for key, value in rule.items():
            if key == "constraints":
                summary_parts.append(f"  Constraints: {value}")
            elif isinstance(value, list):
                summary_parts.append(f"  {key}: {value}")
            elif isinstance(value, dict):
                summary_parts.append(f"  {key}: [nested object]")
            else:
                summary_parts.append(f"  {key}: {value}")
        
        return "\n".join(summary_parts)
    
    def to_llm_format(self) -> str:
        """
        Convert specification rules to LLM-friendly text format.
        
        This format is designed to be included in prompts without
        imposing structure - just presenting the available rules.
        
        Returns:
            Formatted string suitable for LLM prompts
        """
        lines = ["AVAILABLE PROTOCOL RULES:"]
        lines.append("=" * 70)
        
        for idx, (rule_name, rule_data) in enumerate(sorted(self._rule_index.items()), 1):
            lines.append(f"\n{idx}. {rule_name}:")
            
            # Format the rule data
            for key, value in rule_data.items():
                if isinstance(value, list) and len(value) <= 10:
                    lines.append(f"   - {key}: {value}")
                elif isinstance(value, str) and len(value) < 100:
                    lines.append(f"   - {key}: {value}")
                elif isinstance(value, (int, float, bool)):
                    lines.append(f"   - {key}: {value}")
                else:
                    lines.append(f"   - {key}: [complex value]")
        
        lines.append("\n" + "=" * 70)
        return "\n".join(lines)


if __name__ == "__main__":
    # Quick test
    loader = SpecificationLoader("../../configs/spec_rules.json")
    print(f"Loaded {len(loader.get_rule_names())} rules:")
    for name in loader.get_rule_names()[:5]:
        print(f"  - {name}")
    
    print("\n" + loader.get_rule_summary("bag"))

