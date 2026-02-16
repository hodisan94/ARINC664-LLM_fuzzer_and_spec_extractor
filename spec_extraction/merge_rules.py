!/usr/bin/env python
"""
Merge multiple protocol rule extractions into a single consolidated JSON.
"""

import json
import sys


def merge_value(current, new):
    """Merge two values, preferring non-null values."""
    if new is None:
        return current
    if current is None:
        return new
    
     If both are lists, combine and deduplicate
    if isinstance(current, list) and isinstance(new, list):
        combined = current + [item for item in new if item not in current]
        return combined
    
     If both are dicts, merge recursively
    if isinstance(current, dict) and isinstance(new, dict):
        merged = current.copy()
        for key, value in new.items():
            if key in merged:
                merged[key] = merge_value(merged[key], value)
            else:
                merged[key] = value
        return merged
    
     For other types, prefer new value if current is empty/null
    if not current:
        return new
    return current


def merge_extractions(extractions):
    """Merge multiple rule extractions into one."""
    merged = {}
    
    for extraction in extractions:
        if not isinstance(extraction, dict):
            continue
        
        for key, value in extraction.items():
            if key in merged:
                merged[key] = merge_value(merged[key], value)
            else:
                merged[key] = value
    
    return merged


def main():
    input_file = sys.argv[] if len(sys.argv) >  else "spec_extraction/protocol_rules.json"
    output_file = sys.argv[] if len(sys.argv) >  else "spec_extraction/protocol_rules_merged.json"
    
    print(f" Reading: {input_file}")
    with open(input_file, 'r') as f:
        data = json.load(f)
    
    if 'extractions' in data:
        print(f" Merging {len(data['extractions'])} extractions...")
        merged = merge_extractions(data['extractions'])
    else:
        print(" File is already in final format")
        merged = data
    
    print(f" Saving merged rules to: {output_file}")
    with open(output_file, 'w') as f:
        json.dump(merged, f, indent=)
    
    print(f" Done! Size: {len(json.dumps(merged)):,} bytes")
    
     Show summary
    print("\n Summary of extracted rules:")
    for key, value in merged.items():
        if isinstance(value, dict):
            non_null = sum( for v in value.values() if v is not None)
            print(f"   - {key}: {non_null} fields with data")
        elif isinstance(value, list):
            print(f"   - {key}: {len(value)} items")
        elif value is not None:
            print(f"   - {key}: present")


if __name__ == "__main__":
    main()

