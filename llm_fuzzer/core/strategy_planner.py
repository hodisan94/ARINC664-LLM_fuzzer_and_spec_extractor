#!/usr/bin/env python3
"""
LLM-Based Strategy Planner

This is Component 2 of the LLM-Guided Iterative Fuzzing Process.
It uses an LLM (GPT-5) to intelligently decide what to test next based on:
- Protocol rules and test cases
- Recent performance history
- VL statistics
- Reward scores

The LLM has freedom to choose predefined test cases OR propose custom mutations.
"""

import json
import math
import os
import re
import pandas as pd
from typing import Dict, List, Any, Optional
from pathlib import Path

# Import sibling modules
import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from llm_fuzzer.utils.spec_loader import SpecificationLoader
from llm_fuzzer.utils.test_case_loader import TestCaseLoader
from llm_fuzzer.prompts.fuzzing_agent import build_fuzzing_prompt, format_vl_statistics


def _safe_int_for_stats(val) -> int:
    """Convert value to int for coverage stats; NaN/inf/None -> 0."""
    if val is None:
        return 0
    try:
        f = float(val)
        if math.isnan(f) or math.isinf(f):
            return 0
        return int(f)
    except (ValueError, TypeError):
        return 0

try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False

try:
    import anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False


class LLMStrategyPlanner:
    """
    Uses LLM to plan next fuzzing iteration.
    
    The LLM receives complete information about:
    - Available protocol rules
    - Test cases (with freedom to propose custom mutations)
    - Recent performance
    - VL testing statistics
    
    And decides:
    - Which VL to test
    - Which protocol rule to focus on
    - Whether to use predefined test cases or custom mutation
    - What strategy to use (conformance/edge-case/adversarial)
    """
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "gpt-5",
        spec_rules_path: str = "configs/spec_rules.json",
        test_cases_path: str = "configs/test_cases.json"
    ):
        """
        Initialize LLM Strategy Planner.
        
        Args:
            api_key: OpenAI API key (reads from env if not provided)
            model: LLM model to use (default: gpt-5)
            spec_rules_path: Path to spec_rules.json
            test_cases_path: Path to test_cases.json
            
        Raises:
            ImportError: If openai package not installed
            ValueError: If API key not provided and not in environment
        """
        if not OPENAI_AVAILABLE:
            raise ImportError("openai package required. Install with: pip install openai")
        
        # Primary: OpenAI  Fallback: Gemini via OpenAI-compatible API
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.model = model
        self.client = OpenAI(api_key=self.api_key) if self.api_key else None

        gemini_key = os.getenv("GEMINI_API_KEY")
        if gemini_key:
            self.gemini_client = OpenAI(
                api_key=gemini_key,
                base_url="https://generativelanguage.googleapis.com/v1beta/openai/"
            )
            self.gemini_model = "gemini-2.0-flash"
        else:
            self.gemini_client = None
            self.gemini_model = None

        claude_key = os.getenv("CLAUDE_API_KEY") or os.getenv("ANTHROPIC_API_KEY")
        if claude_key and ANTHROPIC_AVAILABLE:
            self.claude_client = anthropic.Anthropic(api_key=claude_key)
            self.claude_model = "claude-sonnet-4-20250514"
        else:
            self.claude_client = None
            self.claude_model = None

        if not self.client and not self.gemini_client and not self.claude_client:
            raise ValueError(
                "Set OPENAI_API_KEY, GEMINI_API_KEY, or CLAUDE_API_KEY / ANTHROPIC_API_KEY."
            )
        
        # Load spec rules and test cases
        self.spec_loader = SpecificationLoader(spec_rules_path)
        self.test_case_loader = TestCaseLoader(test_cases_path)
        
        self.spec_rules = self.spec_loader.get_all_rules()
        self.test_cases = self.test_case_loader.get_all_test_cases()

        # Build rule -> spec-category lookup for category-aware coverage
        self._rule_to_cat, self._cat_to_rules = self._build_category_maps(spec_rules_path)
        self._all_known_rules = sorted(set(self.spec_rules.keys()) | set(self.test_cases.keys()))
    
    # ------------------------------------------------------------------
    # Category mapping helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _norm(s: str) -> str:
        s = s.lower().replace(' ', '_').replace('.', '_').replace('-', '_')
        s = re.sub(r'_+', '_', s)
        return s.strip('_')

    def _build_category_maps(self, spec_rules_path: str):
        """Build bidirectional rule<->category maps from spec_rules_filtered."""
        rule_to_cat: Dict[str, str] = {}
        cat_to_rules: Dict[str, List[str]] = {}
        try:
            with open(spec_rules_path) as f:
                spec = json.load(f)
        except Exception:
            return rule_to_cat, cat_to_rules

        for cat, content in spec.items():
            cat_to_rules[cat] = []
            rule_to_cat[self._norm(cat)] = cat
            if isinstance(content, dict):
                for sub in content.keys():
                    rule_to_cat[self._norm(sub)] = cat
                    cat_to_rules[cat].append(sub)
        return rule_to_cat, cat_to_rules

    def rule_category(self, rule_name: str) -> Optional[str]:
        """Map a rule name to its spec category (or None)."""
        norm = self._norm(rule_name)
        if norm in self._rule_to_cat:
            return self._rule_to_cat[norm]
        parts = rule_name.split('.')
        if len(parts) > 1:
            for part in parts:
                n = self._norm(part)
                if n in self._rule_to_cat:
                    return self._rule_to_cat[n]
        # Prefix matching against category names (mirrors external analysis)
        for cat in self._cat_to_rules:
            nc = self._norm(cat)
            if norm == nc or norm.startswith(nc + '_') or nc.startswith(norm + '_'):
                return cat
        return None

    def category_coverage_pct(self, history: Optional[pd.DataFrame]) -> float:
        """Compute spec-category coverage percentage from history."""
        if history is None or history.empty or 'protocol_rule' not in history.columns:
            return 0.0
        cats = set()
        for rule in history['protocol_rule'].dropna().unique():
            cat = self.rule_category(str(rule))
            if cat:
                cats.add(cat)
        total = len(self._cat_to_rules) if self._cat_to_rules else 1
        return len(cats) / total * 100

    def _normalize_to_known_rule(self, raw: str) -> str:
        """Find the closest known rule for a free-form LLM rule name."""
        if raw in self._all_known_rules:
            return raw
        norm = self._norm(raw)
        for known in self._all_known_rules:
            if self._norm(known) == norm:
                return known
        for known in self._all_known_rules:
            kn = self._norm(known)
            if norm.startswith(kn) or kn.startswith(norm):
                return known
        best, best_score = raw, 0
        raw_tokens = set(norm.split('_'))
        for known in self._all_known_rules:
            kn_tokens = set(self._norm(known).split('_'))
            overlap = len(raw_tokens & kn_tokens)
            if overlap > best_score:
                best_score = overlap
                best = known
        return best if best_score >= 2 else raw

    # ------------------------------------------------------------------
    def plan_next_iteration(
        self,
        history: Optional[pd.DataFrame] = None,
        iteration: int = 1,
        system_config: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Plan next fuzzing iteration using LLM.
        
        Args:
            history: DataFrame of previous iterations with columns:
                     iteration, target_vl, protocol_rule, reward, bugs_found, etc.
            iteration: Current iteration number
            system_config: System configuration (available VLs, etc.)
            
        Returns:
            Strategy dictionary (PAPER-ALIGNED FORMAT):
            {
                "target_vl": int,
                "mutation_type": str,
                "bag_value": int | None,
                "frame_size": int | None,
                "sequence_number": int | None,
                "timing_jitter_ms": int | None,
                "payload_pattern": str | None,
                "strategy": "conformance" | "edge-case" | "adversarial",
                "reasoning": str,
                "llm_raw_response": str
            }
        """
        vl_stats = format_vl_statistics(history) if history is not None else {}
        recent_results = self._prepare_recent_results(history, n=10)
        coverage_stats = self._compute_coverage_stats(history)
        
        if system_config is None:
            system_config = {
                "available_vls": [1001, 1002, 1003, 2001, 2002, 2003, 3001, 3002]
            }
        
        prompt = build_fuzzing_prompt(
            spec_rules=self.spec_rules,
            test_cases=self.test_cases,
            recent_results=recent_results,
            vl_statistics=vl_stats,
            system_config=system_config,
            iteration=iteration,
            coverage_stats=coverage_stats
        )
        
        # Retry once on LLM failure
        for attempt in range(2):
            try:
                llm_response = self._query_llm(prompt)
                strategy = self._parse_strategy(llm_response)
                strategy["llm_raw_response"] = llm_response
                self._validate_strategy(strategy, system_config)
                break
            except (ValueError, Exception) as e:
                if attempt == 0:
                    print(f"  [RETRY] LLM attempt 1 failed: {e}")
                    continue
                raise

        # Normalize protocol_rule to a known rule name
        raw_mt = strategy.get("mutation_type", "")
        normalized = self._normalize_to_known_rule(raw_mt)
        if normalized != raw_mt:
            print(f"  [NORM] '{raw_mt}' -> '{normalized}'")
        strategy["protocol_rule"] = normalized

        # Dedup: redirect if the rule was already tested OR its category
        # is already covered (when uncovered categories still remain)
        tested_rules = set()
        covered_cats = set()
        if history is not None and not history.empty and "protocol_rule" in history.columns:
            tested_rules = set(history["protocol_rule"].dropna().unique())
            for r in tested_rules:
                for c in self._all_categories_for_rule(str(r)):
                    covered_cats.add(c)

        uncovered_cats_raw = coverage_stats.get("uncovered_categories", [])
        uncovered_cats_norm = {self._norm(c) for c in uncovered_cats_raw}
        uncovered_cats = [c for c in uncovered_cats_raw if self._norm(c) not in covered_cats]
        rule_cats = self._all_categories_for_rule(normalized)
        rule_already_tested = normalized in tested_rules
        category_already_covered = bool(rule_cats & covered_cats) if rule_cats else False
        category_unmapped = len(rule_cats) == 0

        needs_redirect = (rule_already_tested or category_already_covered or category_unmapped) and uncovered_cats
        if needs_redirect:
            redirect = self._pick_untested_rule_from_category(
                uncovered_cats, tested_rules, strategy, system_config)
            if redirect:
                if rule_already_tested:
                    reason = "rule tested"
                elif category_unmapped:
                    reason = "unmapped category"
                else:
                    reason = f"category '{rule_cats}' covered"
                print(f"  [DEDUP] '{normalized}' ({reason}) -> '{redirect}'")
                strategy["protocol_rule"] = redirect
                strategy["mutation_type"] = redirect
                tc_data = self.test_cases.get(redirect, {})
                cases = tc_data.get("test_cases", [])
                if cases:
                    strategy["test_cases"] = ["TC0"]
                    strategy["test_mode"] = "predefined"

        # Mutation mechanism injection: if we're past iteration 20 and there
        # are untested mechanisms, periodically force one to be used.
        used_mechs = coverage_stats.get("used_mutation_mechanisms", set())
        mech_schedule = [
            (21, "mac_mutation_type", "spoof_src", "mac_mutation_type:spoof_src"),
            (26, "dest_mac_mutation", "corrupt_prefix", "dest_mac_mutation:corrupt_prefix"),
            (31, "frame_size", 2000, "frame_size>1518"),
            (36, "timing_jitter_ms", -5, "timing_jitter_ms<0"),
            (41, "sequence_number_override", 255, "sequence_number_override>0"),
        ]
        for trigger_iter, param, value, mech_key in mech_schedule:
            if iteration == trigger_iter and mech_key not in used_mechs:
                if strategy.get(param) is None or strategy.get(param) == "none":
                    print(f"  [MECH-INJECT] iter {iteration}: setting {param}={value}")
                    strategy[param] = value
                    if param == "mac_mutation_type":
                        strategy["prob"] = strategy.get("prob") or 1.0

        # Token bucket stress: large frames at NORMAL BAG timing
        if iteration == 46 and "token_bucket_stress" not in used_mechs:
            print(f"  [MECH-INJECT] iter {iteration}: token bucket stress (frame_size=1500, default BAG)")
            strategy["frame_size"] = 1500
            strategy["bag_value"] = None

        return strategy

    def _all_categories_for_rule(self, rule_name: str) -> set:
        """Get ALL categories a rule maps to, normalized for dedup comparison."""
        cats = set()
        norm = self._norm(rule_name)

        if norm in self._rule_to_cat:
            cats.add(self._norm(self._rule_to_cat[norm]))

        parts = rule_name.split('.')
        if len(parts) > 1:
            for part in parts:
                n = self._norm(part)
                if n in self._rule_to_cat:
                    cats.add(self._norm(self._rule_to_cat[n]))

        for cat in self._cat_to_rules:
            nc = self._norm(cat)
            if norm == nc or norm.startswith(nc + '_') or nc.startswith(norm + '_'):
                cats.add(nc)

        return cats

    def _pick_untested_rule_from_category(
        self, uncovered_cats, tested_rules, strategy, system_config
    ) -> Optional[str]:
        """Pick an untested rule from the first uncovered category that has TCs."""
        for cat in uncovered_cats:
            sub_rules = self._cat_to_rules.get(cat, [])
            # Try exact sub-rule name
            for sub in sub_rules:
                if sub in self.test_cases and sub not in tested_rules:
                    return sub
            # Try dotted format: category.sub_rule (common in test_cases.json)
            norm_cat = self._norm(cat)
            for sub in sub_rules:
                dotted = f"{cat}.{sub}"
                if dotted in self.test_cases and dotted not in tested_rules:
                    return dotted
            # Try any test_case key containing the category name
            for rule_name in self._all_known_rules:
                if rule_name in tested_rules:
                    continue
                rn = self._norm(rule_name)
                if rn == norm_cat or rn.startswith(norm_cat + '_') or norm_cat in rn.split('_'):
                    return rule_name
        # Fallback: any untested known rule
        for rule_name in self._all_known_rules:
            if rule_name not in tested_rules:
                return rule_name
        return None
    
    def _compute_coverage_stats(self, history: Optional[pd.DataFrame]) -> Dict[str, Any]:
        """Compute rule-level AND category-level coverage from history."""
        all_known = set(self.spec_rules.keys()) | set(self.test_cases.keys())
        all_categories = sorted(self._cat_to_rules.keys())
        
        if history is None or len(history) == 0:
            return {
                "covered_rules": [],
                "uncovered_rules": sorted(all_known),
                "mutation_type_counts": {},
                "total_rules": len(all_known),
                "covered_categories": [],
                "uncovered_categories": all_categories,
                "category_coverage_pct": 0.0,
                "cat_to_rules": self._cat_to_rules,
            }
        
        seen_rules = set()
        mt_counts: Dict[str, int] = {}
        
        if "protocol_rule" in history.columns:
            for val in history["protocol_rule"].dropna().unique():
                seen_rules.add(str(val))
        if "mutation_type" in history.columns:
            for val in history["mutation_type"].dropna().unique():
                seen_rules.add(str(val))
            for val in history["mutation_type"].dropna():
                mt_counts[str(val)] = mt_counts.get(str(val), 0) + 1
        
        covered = sorted(seen_rules & all_known)
        uncovered = sorted(all_known - seen_rules)

        covered_cats = set()
        for rule in seen_rules:
            cat = self.rule_category(rule)
            if cat:
                covered_cats.add(cat)
        uncovered_cats = sorted(set(all_categories) - covered_cats)
        cat_pct = len(covered_cats) / len(all_categories) * 100 if all_categories else 0.0
        
        used_mechs = set()
        if not history.empty:
            for _, row in history.iterrows():
                mt = row.get("mac_mutation_type") or ""
                if mt and mt not in ("none", ""):
                    used_mechs.add(f"mac_mutation_type:{mt}")
                dm = row.get("dest_mac_mutation") or ""
                if dm and dm not in ("none", ""):
                    used_mechs.add(f"dest_mac_mutation:{dm}")
                fs = row.get("frame_size")
                if fs and _safe_int_for_stats(fs) > 1518:
                    used_mechs.add("frame_size>1518")
                tj = row.get("timing_jitter_ms")
                if tj and _safe_int_for_stats(tj) < 0:
                    used_mechs.add("timing_jitter_ms<0")
                so = row.get("sequence_number_override")
                if so and _safe_int_for_stats(so) > 0:
                    used_mechs.add("sequence_number_override>0")
                fs_val = _safe_int_for_stats(row.get("frame_size"))
                bag_val = row.get("bag_value")
                if 1400 <= fs_val <= 1518 and bag_val is None:
                    used_mechs.add("token_bucket_stress")

        return {
            "covered_rules": covered,
            "uncovered_rules": uncovered,
            "mutation_type_counts": mt_counts,
            "total_rules": len(all_known),
            "covered_categories": sorted(covered_cats),
            "uncovered_categories": uncovered_cats,
            "category_coverage_pct": cat_pct,
            "cat_to_rules": self._cat_to_rules,
            "used_mutation_mechanisms": used_mechs,
        }
    
    def _prepare_recent_results(
        self,
        history: Optional[pd.DataFrame],
        n: int = 10
    ) -> List[Dict[str, Any]]:
        """Prepare recent results with metrics and category info for the prompt."""
        if history is None or len(history) == 0:
            return []
        
        recent = history.tail(n)
        results = []
        
        def _safe_int(val, default=0):
            try:
                return int(val)
            except (ValueError, TypeError):
                return default

        def _safe_float(val, default=0.0):
            try:
                v = float(val)
                return v if v == v else default  # NaN check
            except (ValueError, TypeError):
                return default

        for _, row in recent.iterrows():
            rule = str(row.get("protocol_rule", ""))
            cat = self.rule_category(rule)
            results.append({
                "iteration": _safe_int(row.get("iteration", 0)),
                "target_vl": _safe_int(row.get("target_vl", 0)),
                "protocol_rule": rule,
                "strategy": str(row.get("strategy", "")),
                "reward": _safe_float(row.get("reward", 0.0)),
                "bugs_found": bool(row.get("bugs_found", False)),
                "recommendation": str(row.get("recommendation", "")),
                "policing_rate": _safe_float(row.get("policing_rate", 0.0)),
                "es_rejection_rate": _safe_float(row.get("es_rejection_rate", 0.0)),
                "frames_dropped_mac_error": _safe_int(row.get("frames_dropped_mac_error", 0)),
                "spec_category": cat or "unmapped",
            })
        
        return results
    
    def _query_llm(self, prompt: str) -> str:
        """Query LLM with prompt, trying OpenAI -> Anthropic -> Gemini."""
        sys_msg = "You are an expert protocol fuzzing agent. Respond ONLY with valid JSON."
        messages = [
            {"role": "system", "content": sys_msg},
            {"role": "user", "content": prompt}
        ]

        last_err = None

        if self.client:
            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    max_completion_tokens=8000,
                    response_format={"type": "json_object"},
                )
                content = response.choices[0].message.content
                print(f"[OpenAI] {self.model} -> {len(content) if content else 0} chars")
                if content:
                    return content
            except Exception as e:
                last_err = e
                print(f"[OpenAI] failed: {e}")

        if self.claude_client:
            try:
                response = self.claude_client.messages.create(
                    model=self.claude_model,
                    max_tokens=4096,
                    system=sys_msg + " Do NOT wrap your JSON in markdown code blocks.",
                    messages=[{"role": "user", "content": prompt}]
                )
                content = response.content[0].text
                print(f"[Claude] {self.claude_model} -> {len(content) if content else 0} chars")
                if content:
                    content = self._extract_json(content)
                    return content
            except Exception as e:
                last_err = e
                print(f"[Claude] failed: {e}")

        if self.gemini_client:
            try:
                response = self.gemini_client.chat.completions.create(
                    model=self.gemini_model,
                    messages=messages,
                )
                content = response.choices[0].message.content
                print(f"[Gemini] {self.gemini_model} -> {len(content) if content else 0} chars")
                if content:
                    return content
            except Exception as e:
                last_err = e
                print(f"[Gemini] failed: {e}")

        raise Exception(f"All LLM backends failed. Last error: {last_err}")

    @staticmethod
    def _extract_json(text: str) -> str:
        """Extract JSON from text that may be wrapped in markdown code blocks."""
        text = text.strip()
        if text.startswith('{'):
            return text
        # Strip ```json ... ``` blocks
        m = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', text, re.DOTALL)
        if m:
            return m.group(1).strip()
        # Find first { ... last }
        start = text.find('{')
        end = text.rfind('}')
        if start != -1 and end != -1 and end > start:
            return text[start:end+1]
        return text
    
    def _parse_strategy(self, llm_response: str) -> Dict[str, Any]:
        """
        Parse LLM JSON response into strategy dictionary (HYBRID - FULL FREEDOM).
        
        LLM can choose:
        - test_cases (predefined)
        - specific mutation values
        - both combined
        
        Args:
            llm_response: Raw LLM response text
            
        Returns:
            Parsed strategy dictionary with all parameters
            
        Raises:
            ValueError: If response is not valid JSON or missing required fields
        """
        try:
            strategy = json.loads(llm_response)
        except json.JSONDecodeError as e:
            raise ValueError(f"LLM response is not valid JSON: {str(e)}")
        
        # Check required fields
        required_fields = ["target_vl", "mutation_type", "strategy", "reasoning"]
        missing = [f for f in required_fields if f not in strategy]
        if missing:
            raise ValueError(f"LLM response missing required fields: {missing}")
        
        # Ensure all parameter fields exist (can be null) - HYBRID SUPPORT
        all_params = ["test_cases", "bag_value", "frame_size", "sequence_number", 
                     "timing_jitter_ms", "payload_pattern", "mac_mutation_type", "prob",
                     "sequence_number_override", "dest_mac_mutation"]
        for param in all_params:
            if param not in strategy:
                strategy[param] = None
        
        return strategy
    
    def _validate_strategy(self, strategy: Dict[str, Any], system_config: Optional[Dict[str, Any]] = None) -> None:
        """
        Validate strategy components.
        
        Args:
            strategy: Parsed strategy dictionary
            system_config: System configuration with available_vls
            
        Raises:
            ValueError: If strategy contains invalid values
        """
        # Validate target_vl is an integer
        if not isinstance(strategy["target_vl"], int):
            raise ValueError(f"target_vl must be integer, got {type(strategy['target_vl'])}")
        
        # Validate target_vl exists in the simulator
        if system_config and 'available_vls' in system_config:
            valid_vls = system_config['available_vls']
            if strategy["target_vl"] not in valid_vls:
                import random
                corrected_vl = random.choice(valid_vls)
                print(f"  [WARN] LLM chose invalid VL {strategy['target_vl']}, correcting to {corrected_vl}")
                strategy["target_vl"] = corrected_vl
        
        # Validate strategy type
        valid_strategies = ["conformance", "edge-case", "adversarial"]
        if strategy["strategy"] not in valid_strategies:
            raise ValueError(f"strategy must be one of {valid_strategies}, got {strategy['strategy']}")
        
        # Validate mutation_type exists
        if not isinstance(strategy["mutation_type"], str) or not strategy["mutation_type"]:
            raise ValueError("mutation_type must be non-empty string")
        
        # Validate at least SOMETHING is set (test_cases OR mutation params)
        has_test_cases = strategy.get("test_cases") and len(strategy.get("test_cases", [])) > 0
        mutation_params = ["bag_value", "frame_size", "sequence_number", 
                          "timing_jitter_ms", "payload_pattern", "mac_mutation_type", "prob",
                          "sequence_number_override", "dest_mac_mutation"]
        has_mutation_params = any(strategy.get(p) is not None for p in mutation_params)
        
        if not has_test_cases and not has_mutation_params:
            raise ValueError("LLM must specify either test_cases OR mutation parameters (or both)")


if __name__ == "__main__":
    # Quick test (requires OPENAI_API_KEY in environment)
    print("=" * 70)
    print("STRATEGY PLANNER TEST")
    print("=" * 70)
    
    try:
        planner = LLMStrategyPlanner()
        print("✓ Planner initialized successfully")
        print(f"  Model: {planner.model}")
        print(f"  Protocol rules loaded: {len(planner.spec_rules)} rules")
        print(f"  Test cases loaded: {len(planner.test_cases)} rules")
        
        # Test with empty history (first iteration)
        print("\n→ Planning first iteration (no history)...")
        strategy = planner.plan_next_iteration(history=None, iteration=1)
        
        print("\n✓ Strategy received:")
        print(f"  Target VL: {strategy['target_vl']}")
        print(f"  Protocol Rule: {strategy['protocol_rule']}")
        print(f"  Test Mode: {strategy['test_mode']}")
        if strategy['test_mode'] == 'predefined':
            print(f"  Test Cases: {strategy['test_cases']}")
        else:
            print(f"  Custom Mutation: {strategy['custom_mutation']}")
        print(f"  Strategy: {strategy['strategy']}")
        print(f"  Reasoning: {strategy['reasoning']}")
        
    except ImportError as e:
        print(f"✗ Error: {e}")
        print("  Install openai package: pip install openai")
    except ValueError as e:
        print(f"✗ Error: {e}")
        print("  Set OPENAI_API_KEY environment variable")
    except Exception as e:
        print(f"✗ Error: {e}")

