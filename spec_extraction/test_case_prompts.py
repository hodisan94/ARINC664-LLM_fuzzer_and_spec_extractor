"""
Prompts for Test Case Extraction from AFDX Protocol Rules.
This module defines the prompts used to extract test cases that violate protocol rules.
"""

SYSTEM_PROMPT_TEST_CASE_EXTRACTION = """You are an expert in network protocol testing and fuzzing.

Your task is to generate test cases that VIOLATE the given AFDX protocol rules.
These test cases will be used by a fuzzer to test the robustness of AFDX network implementations.

For each rule provided, you must:
1. Understand the constraint or requirement
2. Propose diverse test cases that violate it
3. Cover different violation types (out-of-range, boundary, invalid format, etc.)
4. Provide clear reasoning for each test case

Output Format (JSON):
{
  "parameter_name": {
    "rule_summary": "Brief description of the rule",
    "valid_range": "Description of valid values",
    "test_cases": [
      {
        "value": <actual_test_value>,
        "violation_type": "below_min|above_max|invalid_format|negative|not_in_list|...",
        "reason": "Why this violates the rule",
        "expected_behavior": "What should happen when this is used"
      }
    ]
  }
}

Guidelines:
- Generate 3-7 test cases per rule
- Cover diverse violation types
- Include boundary cases (just below/above limits)
- Include extreme cases (very large/negative values)
- Include invalid formats when applicable
- Be specific with numeric values
"""

def get_test_case_extraction_prompt(rule_name: str, rule_data: dict) -> str:
    """
    Generate a prompt for extracting test cases for a specific rule.
    
    Args:
        rule_name: Name of the rule (e.g., "bag", "frame_structure.ethernet.lmax")
        rule_data: Dictionary containing the rule specification
        
    Returns:
        A formatted prompt string
    """
    return f"""Extract test cases that violate the following AFDX protocol rule:

RULE NAME: {rule_name}

RULE SPECIFICATION:
{_format_rule_data(rule_data)}

Generate test cases that:
1. Violate this specific rule
2. Cover different violation types
3. Are practical for network fuzzing
4. Would be detectable by a network switch or end system

Output your response as JSON following the schema provided in the system prompt.
Focus ONLY on this rule - do not include test cases for other rules.
"""

def _format_rule_data(rule_data: dict, indent: int = 0) -> str:
    """
    Format rule data for display in prompt.
    
    Args:
        rule_data: Dictionary containing rule specification
        indent: Current indentation level
        
    Returns:
        Formatted string representation
    """
    lines = []
    prefix = "  " * indent
    
    if isinstance(rule_data, dict):
        for key, value in rule_data.items():
            if isinstance(value, (dict, list)):
                lines.append(f"{prefix}{key}:")
                lines.append(_format_rule_data(value, indent + 1))
            else:
                lines.append(f"{prefix}{key}: {value}")
    elif isinstance(rule_data, list):
        for item in rule_data:
            if isinstance(item, (dict, list)):
                lines.append(_format_rule_data(item, indent))
            else:
                lines.append(f"{prefix}- {item}")
    else:
        lines.append(f"{prefix}{rule_data}")
    
    return "\n".join(lines)


VALIDATION_PROMPT = """You are validating test cases generated for AFDX protocol fuzzing.

Review the following test cases and verify:
1. Does each test case actually violate the stated rule?
2. Are there diverse violation types covered?
3. Are any test cases redundant or too similar?
4. Are any obvious violation types missing?

Original Rule:
{rule_name}: {rule_spec}

Generated Test Cases:
{test_cases}

Output Format (JSON):
{
  "valid": true/false,
  "issues": [
    "Description of any problems found"
  ],
  "suggestions": [
    "Additional test cases that should be added"
  ],
  "redundant": [
    "Indices of redundant test cases"
  ]
}
"""

