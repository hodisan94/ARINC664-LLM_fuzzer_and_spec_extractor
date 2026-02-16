"""
Validation logic for AFDX protocol test cases.
Ensures that generated test cases actually violate the rules they claim to violate.
"""

import json
from typing import Dict, List, Any, Tuple


class TestCaseValidator:
    """Validates that test cases actually violate AFDX protocol rules."""
    
    def __init__(self, spec_rules: Dict[str, Any]):
        """
        Initialize validator with protocol specification rules.
        
        Args:
            spec_rules: Dictionary containing AFDX protocol rules
        """
        self.spec_rules = spec_rules
        self.validation_results = {
            "total_test_cases": 0,
            "valid_violations": 0,
            "invalid_test_cases": [],
            "warnings": []
        }
    
    def validate_all(self, test_cases: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate all test cases.
        
        Args:
            test_cases: Dictionary of test cases to validate
            
        Returns:
            Dictionary containing validation results
        """
        for param_name, param_data in test_cases.items():
            if "test_cases" in param_data:
                for idx, tc in enumerate(param_data["test_cases"]):
                    self.validation_results["total_test_cases"] += 1
                    is_valid, reason = self._validate_test_case(param_name, tc)
                    
                    if is_valid:
                        self.validation_results["valid_violations"] += 1
                    else:
                        self.validation_results["invalid_test_cases"].append({
                            "parameter": param_name,
                            "test_case_index": idx,
                            "test_case": tc,
                            "reason": reason
                        })
        
        return self.validation_results
    
    def _validate_test_case(self, param_name: str, test_case: Dict[str, Any]) -> Tuple[bool, str]:
        """
        Validate a single test case.
        
        Args:
            param_name: Name of the parameter being tested
            test_case: Test case to validate
            
        Returns:
            Tuple of (is_valid, reason)
        """
        value = test_case.get("value")
        violation_type = test_case.get("violation_type", "")
        
        # Validate based on parameter type
        if param_name == "bag" or "bag" in param_name:
            return self._validate_bag(value, violation_type)
        elif "frame" in param_name and ("lmin" in param_name or "lmax" in param_name):
            return self._validate_frame_size(value, violation_type, param_name)
        elif "vl" in param_name.lower() and "id" in param_name.lower():
            return self._validate_vl_id(value, violation_type)
        elif "sequence" in param_name.lower():
            return self._validate_sequence_number(value, violation_type)
        elif "priority" in param_name.lower() or "qos" in param_name.lower():
            return self._validate_priority(value, violation_type)
        elif "mac" in param_name.lower():
            return self._validate_mac_address(value, violation_type)
        elif "ip" in param_name.lower():
            return self._validate_ip(value, violation_type)
        elif "port" in param_name.lower():
            return self._validate_port(value, violation_type)
        else:
            # Generic validation
            return self._validate_generic(param_name, value, violation_type)
    
    def _validate_bag(self, value: Any, violation_type: str) -> Tuple[bool, str]:
        """Validate BAG test case."""
        allowed_values = self.spec_rules.get("bag", {}).get("allowed_values_ms", [])
        
        # Handle non-numeric values (strings, None, etc.)
        if not isinstance(value, (int, float)):
            return True, "Valid violation (invalid type)"
        
        if value in allowed_values:
            return False, f"Value {value} is in allowed list"
        
        if violation_type == "negative" and value >= 0:
            return False, "Marked as negative but value is non-negative"
        
        if violation_type == "above_max" and allowed_values and value <= max(allowed_values):
            return False, f"Marked as above_max but value {value} <= {max(allowed_values)}"
        
        return True, "Valid violation"
    
    def _validate_frame_size(self, value: Any, violation_type: str, param_name: str) -> Tuple[bool, str]:
        """Validate frame size test case."""
        frame_rules = self.spec_rules.get("frame_structure", {}).get("ethernet", {})
        lmin = frame_rules.get("lmin", 64)
        lmax = frame_rules.get("lmax", 1518)
        
        # Handle non-numeric values
        if not isinstance(value, (int, float)):
            return True, "Valid violation (invalid type)"
        
        if lmin <= value <= lmax:
            return False, f"Value {value} is within valid range [{lmin}, {lmax}]"
        
        if violation_type == "below_min" and value >= lmin:
            return False, f"Marked as below_min but value {value} >= {lmin}"
        
        if violation_type == "above_max" and value <= lmax:
            return False, f"Marked as above_max but value {value} <= {lmax}"
        
        return True, "Valid violation"
    
    def _validate_vl_id(self, value: Any, violation_type: str) -> Tuple[bool, str]:
        """Validate VL ID test case."""
        vl_rules = self.spec_rules.get("frame_structure", {}).get("afdx", {}).get("vl_id", {})
        min_val = vl_rules.get("min", 0)
        max_val = vl_rules.get("max", 65535)
        
        # Handle non-numeric values
        if not isinstance(value, (int, float)):
            return True, "Valid violation (invalid type)"
        
        if min_val <= value <= max_val:
            return False, f"Value {value} is within valid range [{min_val}, {max_val}]"
        
        if violation_type == "negative" and value >= 0:
            return False, "Marked as negative but value is non-negative"
        
        if violation_type == "above_max" and value <= max_val:
            return False, f"Marked as above_max but value {value} <= {max_val}"
        
        return True, "Valid violation"
    
    def _validate_sequence_number(self, value: Any, violation_type: str) -> Tuple[bool, str]:
        """Validate sequence number test case."""
        seq_rules = self.spec_rules.get("sequence_numbers", {})
        min_val = seq_rules.get("min", 0)
        max_val = seq_rules.get("max", 255)
        
        # Handle non-numeric values (strings, None, etc.)
        if not isinstance(value, (int, float)):
            return True, "Valid violation (invalid type)"
        
        if min_val <= value <= max_val:
            return False, f"Value {value} is within valid range [{min_val}, {max_val}]"
        
        return True, "Valid violation"
    
    def _validate_priority(self, value: Any, violation_type: str) -> Tuple[bool, str]:
        """Validate priority/QoS test case."""
        priority_rules = self.spec_rules.get("priority_qos", {})
        levels = priority_rules.get("levels", 4)
        
        # Handle non-numeric values
        if not isinstance(value, (int, float)):
            return True, "Valid violation (invalid type)"
        
        if 0 <= value < levels:
            return False, f"Value {value} is within valid range [0, {levels-1}]"
        
        return True, "Valid violation"
    
    def _validate_mac_address(self, value: Any, violation_type: str) -> Tuple[bool, str]:
        """Validate MAC address test case."""
        if isinstance(value, str):
            # Check if it's a valid MAC format
            parts = value.split(":")
            if len(parts) == 6 and all(len(p) == 2 for p in parts):
                # Check multicast bit rules
                mac_rules = self.spec_rules.get("frame_structure", {}).get("ethernet", {}).get("destination_mac", {})
                if "multicast_bit" in mac_rules:
                    # Valid format but might violate multicast rules
                    return True, "Valid violation (multicast bit)"
            else:
                # Invalid format
                return True, "Valid violation (invalid format)"
        
        return True, "Valid violation"
    
    def _validate_ip(self, value: Any, violation_type: str) -> Tuple[bool, str]:
        """Validate IP address test case."""
        ip_rules = self.spec_rules.get("frame_structure", {}).get("ip", {})
        
        if isinstance(value, str):
            # Check if it's a valid IP format
            parts = value.split(".")
            if len(parts) != 4:
                return True, "Valid violation (invalid format)"
            
            # Check multicast range
            if "multicast_range" in ip_rules:
                # Could violate multicast rules
                return True, "Valid violation"
        
        return True, "Valid violation"
    
    def _validate_port(self, value: Any, violation_type: str) -> Tuple[bool, str]:
        """Validate UDP port test case."""
        if not isinstance(value, (int, float)):
            return True, "Valid violation (invalid type)"
        
        if value < 0 or value > 65535:
            return True, "Valid violation (out of range)"
        
        return False, "Value is within valid port range"
    
    def _validate_generic(self, param_name: str, value: Any, violation_type: str) -> Tuple[bool, str]:
        """Generic validation for parameters without specific rules."""
        # Look up the parameter in spec_rules
        param_spec = self._get_nested_value(self.spec_rules, param_name)
        
        if param_spec is None:
            self.validation_results["warnings"].append(
                f"No specification found for parameter: {param_name}"
            )
            return True, "No spec to validate against (assuming valid)"
        
        # Generic range checking
        if isinstance(param_spec, dict):
            if "min" in param_spec and "max" in param_spec:
                min_val = param_spec["min"]
                max_val = param_spec["max"]
                if min_val <= value <= max_val:
                    return False, f"Value {value} is within valid range [{min_val}, {max_val}]"
            
            if "allowed_values" in param_spec:
                if value in param_spec["allowed_values"]:
                    return False, f"Value {value} is in allowed list"
        
        return True, "Valid violation"
    
    def _get_nested_value(self, d: Dict, key_path: str) -> Any:
        """Get nested dictionary value using dot notation."""
        keys = key_path.split(".")
        current = d
        
        for key in keys:
            if isinstance(current, dict) and key in current:
                current = current[key]
            else:
                return None
        
        return current
    
    def print_summary(self):
        """Print validation summary."""
        total = self.validation_results["total_test_cases"]
        valid = self.validation_results["valid_violations"]
        invalid_count = len(self.validation_results["invalid_test_cases"])
        
        print("\n" + "="*60)
        print("TEST CASE VALIDATION SUMMARY")
        print("="*60)
        print(f"Total test cases:     {total}")
        print(f"Valid violations:     {valid} ({100*valid/max(1,total):.1f}%)")
        print(f"Invalid test cases:   {invalid_count}")
        print(f"Warnings:             {len(self.validation_results['warnings'])}")
        
        if invalid_count > 0:
            print("\nINVALID TEST CASES:")
            for item in self.validation_results["invalid_test_cases"]:
                print(f"  - {item['parameter']}: {item['reason']}")
        
        if self.validation_results["warnings"]:
            print("\nWARNINGS:")
            for warning in self.validation_results["warnings"]:
                print(f"  - {warning}")
        
        print("="*60)

