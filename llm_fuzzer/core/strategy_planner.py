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
import os
import re
import time
import pandas as pd
from typing import Dict, List, Any, Optional
from pathlib import Path

# Import sibling modules
import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from llm_fuzzer.utils.spec_loader import SpecificationLoader
from llm_fuzzer.utils.test_case_loader import TestCaseLoader
from llm_fuzzer.prompts.fuzzing_agent import build_fuzzing_prompt, format_vl_statistics

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

    MUTATION_FIELDS = [
        "test_cases",
        "bag_value",
        "frame_size",
        "sequence_number",
        "timing_jitter_ms",
        "payload_pattern",
        "mac_mutation_type",
        "prob",
        "sequence_number_override",
        "dest_mac_mutation",
    ]
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "gpt-5",
        spec_rules_path: str = "configs/spec_rules.json",
        test_cases_path: str = "configs/test_cases.json",
        feedback_enabled: bool = True,
        steering_enabled: bool = True,
        redirect_mode: str = "replan",
        vl_config_path: str = "examples/AFDX_V3/config/virtual_links.csv",
    ):
        """
        Initialize LLM Strategy Planner.
        
        Args:
            api_key: OpenAI API key (reads from env if not provided)
            model: LLM model to use (default: gpt-5)
            spec_rules_path: Path to spec_rules.json
            test_cases_path: Path to test_cases.json
            feedback_enabled: Show prior outcomes, VL statistics and coverage state
                in the prompt
            steering_enabled: Apply the controller's coverage-driven redirection and
                scheduled mechanism tests
            redirect_mode: "replan" asks the LLM to plan a test for an untested rule
                (label and parameters refer to the same rule); "clear" keeps the earlier
                behavior that relabels the iteration and clears its parameters
            vl_config_path: VL table shown to the LLM when it re-plans
            
        Raises:
            ImportError: If the requested LLM provider package is not installed
            ValueError: If API key not provided and not in environment
        """
        # Primary: OpenAI; fallback: Claude/Anthropic.
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.model = model
        if self.api_key and not OPENAI_AVAILABLE:
            raise ImportError("openai package required for OpenAI backend. Install with: pip install openai")
        self.client = OpenAI(api_key=self.api_key) if self.api_key else None

        claude_key = os.getenv("ANTHROPIC_API_KEY") or os.getenv("CLAUDE_API_KEY")
        if claude_key and not ANTHROPIC_AVAILABLE:
            raise ImportError("anthropic package required for Claude backend. Install with: pip install anthropic")
        if claude_key and ANTHROPIC_AVAILABLE:
            self.claude_client = anthropic.Anthropic(api_key=claude_key)
            self.claude_model = "claude-sonnet-4-20250514"
        else:
            self.claude_client = None
            self.claude_model = None

        if not self.client and not self.claude_client:
            raise ValueError("Set OPENAI_API_KEY, ANTHROPIC_API_KEY, or CLAUDE_API_KEY.")
        
        # Load spec rules and test cases
        self.spec_loader = SpecificationLoader(spec_rules_path)
        self.test_case_loader = TestCaseLoader(test_cases_path)
        
        self.spec_rules = self.spec_loader.get_all_rules()
        self.test_cases = self.test_case_loader.get_all_test_cases()

        # Build rule -> spec-category lookup for category-aware coverage
        self._rule_to_cat, self._cat_to_rules = self._build_category_maps(spec_rules_path)
        self._all_known_rules = sorted(set(self.spec_rules.keys()) | set(self.test_cases.keys()))

        if redirect_mode not in ("replan", "clear"):
            raise ValueError(f"redirect_mode must be 'replan' or 'clear', got {redirect_mode!r}")
        self.feedback_enabled = feedback_enabled
        self.steering_enabled = steering_enabled
        self.redirect_mode = redirect_mode
        self.vl_table = self._load_vl_table(vl_config_path)
        self._usage: List[Dict[str, Any]] = []

    @staticmethod
    def _load_vl_table(csv_path: str) -> Dict[int, Dict[str, int]]:
        """VL id -> BAG and frame-size limits, read from virtual_links.csv."""
        table: Dict[int, Dict[str, int]] = {}
        path = Path(csv_path)
        if not path.exists():
            return table
        for line in path.read_text().splitlines():
            parts = [p.strip() for p in line.split(',')]
            if len(parts) < 9 or not parts[0].isdigit():
                continue
            table[int(parts[0])] = {"bag_ms": int(parts[6]), "max_frame": int(parts[7]),
                                    "min_frame": int(parts[8])}
        return table
    
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

    def _clear_mutation_fields(self, strategy: Dict[str, Any]) -> None:
        """Clear executable mutation fields before replacing the selected rule."""
        for field in self.MUTATION_FIELDS:
            strategy[field] = None

    @staticmethod
    def _append_planner_action(strategy: Dict[str, Any], action: Dict[str, Any]) -> None:
        """Record deterministic planner post-processing for auditability."""
        actions = strategy.setdefault("planner_actions", [])
        actions.append(action)

    def _make_standalone_mechanism_strategy(
        self,
        strategy: Dict[str, Any],
        *,
        protocol_rule: str,
        field: str,
        value: Any,
        mechanism: str,
        iteration: int,
        extra_fields: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Replace the LLM choice with a standalone scheduled mechanism test."""
        original_rule = strategy.get("protocol_rule") or strategy.get("mutation_type")
        self._clear_mutation_fields(strategy)
        strategy["protocol_rule"] = protocol_rule
        strategy["mutation_type"] = protocol_rule
        strategy["primary_rule"] = protocol_rule
        strategy["compound_test"] = False
        strategy["injected_mechanism"] = mechanism
        strategy[field] = value
        if extra_fields:
            strategy.update(extra_fields)
        strategy["reasoning"] = (
            f"Scheduled standalone mechanism coverage for {mechanism}. "
            f"Original LLM-selected rule was {original_rule}."
        )
        self._append_planner_action(strategy, {
            "type": "scheduled_standalone",
            "iteration": iteration,
            "original_rule": original_rule,
            "protocol_rule": protocol_rule,
            "field": field,
            "value": value,
            "mechanism": mechanism,
            "reason": "scheduled mechanism coverage",
        })
        return strategy

    # ------------------------------------------------------------------
    def plan_next_iteration(
        self,
        history: Optional[pd.DataFrame] = None,
        iteration: int = 1,
        system_config: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Plan the next iteration and record the LLM usage and the planner variant."""
        self._usage = []
        strategy = self._plan_next_iteration(history, iteration, system_config)
        strategy["llm_usage"] = list(self._usage)
        strategy["planner_variant"] = {
            "model": self.model,
            "feedback_enabled": self.feedback_enabled,
            "steering_enabled": self.steering_enabled,
            "redirect_mode": self.redirect_mode,
        }
        return strategy

    def _plan_next_iteration(
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
        coverage_stats = self._compute_coverage_stats(history)
        if self.feedback_enabled:
            vl_stats = format_vl_statistics(history) if history is not None else {}
            recent_results = self._prepare_recent_results(history, n=10)
            prompt_coverage = coverage_stats
        else:
            vl_stats, recent_results, prompt_coverage = {}, [], None
        
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
            coverage_stats=prompt_coverage
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
        strategy.setdefault("primary_rule", normalized)
        has_test_cases = bool(strategy.get("test_cases"))
        has_direct_params = any(
            strategy.get(field) not in (None, "none")
            for field in self.MUTATION_FIELDS
            if field != "test_cases"
        )
        strategy["compound_test"] = has_test_cases and has_direct_params
        strategy.setdefault("planner_actions", [])
        if not self.steering_enabled:
            return strategy

        # Scheduled mechanism coverage should be standalone, not stacked on
        # whatever strategy the LLM happened to choose for this iteration.
        used_mechs = coverage_stats.get("used_mutation_mechanisms", set())
        mech_schedule = [
            (21, "mac_address", "mac_mutation_type", "spoof_src",
             "mac_mutation_type:spoof_src", None),
            (26, "mac_address", "dest_mac_mutation", "corrupt_prefix",
             "dest_mac_mutation:corrupt_prefix", None),
            (31, "frame_structure.ethernet", "frame_size", 2000,
             "frame_size>1518", None),
            (36, "bag", "timing_jitter_ms", -5,
             "timing_jitter_ms<0", None),
            (41, "sequence_numbers", "sequence_number_override", 255,
             "sequence_number_override>0", None),
        ]
        for trigger_iter, rule, param, value, mech_key, extra_fields in mech_schedule:
            if iteration == trigger_iter and mech_key not in used_mechs:
                print(f"  [MECH-STANDALONE] iter {iteration}: setting {param}={value}")
                return self._make_standalone_mechanism_strategy(
                    strategy,
                    protocol_rule=rule,
                    field=param,
                    value=value,
                    mechanism=mech_key,
                    iteration=iteration,
                    extra_fields=extra_fields,
                )

        # Token bucket stress: large frames at NORMAL BAG timing.
        if iteration == 46 and "token_bucket_stress" not in used_mechs:
            print(f"  [MECH-STANDALONE] iter {iteration}: token bucket stress "
                  "(frame_size=1500, default BAG)")
            return self._make_standalone_mechanism_strategy(
                strategy,
                protocol_rule="token_bucket_stress",
                field="frame_size",
                value=1500,
                mechanism="token_bucket_stress",
                iteration=iteration,
                extra_fields={"bag_value": None},
            )

        # Dedup: redirect if the rule was already tested OR its category
        # is already covered for the same VL (when uncovered categories still remain)
        tested_rules = set()
        tested_rule_vl_pairs = set()
        covered_cats = set()
        covered_cats_for_vl = set()
        target_vl = strategy.get("target_vl")
        if history is not None and not history.empty and "protocol_rule" in history.columns:
            tested_rules = set(history["protocol_rule"].dropna().unique())
            for _, row in history.iterrows():
                rule = row.get("protocol_rule")
                if pd.isna(rule):
                    continue
                rule = str(rule)
                row_vl = row.get("target_vl")
                tested_rule_vl_pairs.add((rule, row_vl))
                for c in self._all_categories_for_rule(rule):
                    covered_cats.add(c)
                    if row_vl == target_vl:
                        covered_cats_for_vl.add(c)

        uncovered_cats_raw = coverage_stats.get("uncovered_categories", [])
        uncovered_cats = [c for c in uncovered_cats_raw if self._norm(c) not in covered_cats]
        rule_cats = self._all_categories_for_rule(normalized)
        rule_already_tested = (normalized, target_vl) in tested_rule_vl_pairs
        category_already_covered = bool(rule_cats & covered_cats_for_vl) if rule_cats else False
        category_unmapped = len(rule_cats) == 0 and normalized not in self._all_known_rules

        needs_redirect = (rule_already_tested or category_already_covered or category_unmapped) and uncovered_cats
        if needs_redirect:
            redirect = self._pick_untested_rule_from_category(
                uncovered_cats, tested_rule_vl_pairs, target_vl, strategy, system_config)
            if redirect:
                if rule_already_tested:
                    reason = f"rule tested on VL {target_vl}"
                elif category_unmapped:
                    reason = "unmapped category"
                else:
                    reason = f"category '{rule_cats}' covered on VL {target_vl}"
                if self.redirect_mode == "replan":
                    candidates = self._redirect_candidates(
                        uncovered_cats, tested_rule_vl_pairs, target_vl, strategy, system_config,
                        exclude=self._inexpressible_rules(history))
                    if not candidates:
                        return strategy
                    return self._replan_redirect(strategy, normalized, reason, candidates, system_config)
                print(f"  [DEDUP] '{normalized}' ({reason}) -> '{redirect}'")
                self._clear_mutation_fields(strategy)
                strategy["redirected_from_rule"] = normalized
                strategy["protocol_rule"] = redirect
                strategy["mutation_type"] = redirect
                strategy["primary_rule"] = redirect
                strategy["compound_test"] = False
                tc_data = self.test_cases.get(redirect, {})
                cases = tc_data.get("test_cases", [])
                if cases:
                    strategy["test_cases"] = ["TC0"]
                    strategy["test_mode"] = "predefined"
                self._append_planner_action(strategy, {
                    "type": "redirect",
                    "from_rule": normalized,
                    "to_rule": redirect,
                    "target_vl": target_vl,
                    "reason": reason,
                })

        return strategy

    REPLAN_FIELDS = ("bag_value", "frame_size", "timing_jitter_ms", "mac_mutation_type",
                     "prob", "sequence_number_override", "dest_mac_mutation")
    SRC_MAC_MUTATIONS = ("spoof_src", "spoof_dst", "broadcast", "invalid_src", "zero_mac")
    DEST_MAC_MUTATIONS = ("corrupt_prefix", "wrong_vl", "zero")

    @staticmethod
    def _inexpressible_rules(history: Optional[pd.DataFrame]) -> set:
        """Candidates that the LLM reported as not violable through the simulator interface."""
        rules: set = set()
        if history is None or history.empty or "planner_actions" not in history.columns:
            return rules
        for actions in history["planner_actions"]:
            for action in actions if isinstance(actions, list) else []:
                if action.get("type") == "redirect_skipped" and action.get("reason") == "not expressible":
                    rules.update(action.get("candidates", []))
        return rules

    def _redirect_candidates(self, uncovered_cats, tested_rule_vl_pairs, target_vl,
                             strategy, system_config, exclude: set = frozenset(),
                             limit: int = 5) -> List[str]:
        """First untested rule of each of the first uncovered categories."""
        candidates: List[str] = []
        for cat in uncovered_cats:
            rule = self._pick_untested_rule_from_category(
                [cat], tested_rule_vl_pairs, target_vl, strategy, system_config)
            if (rule and rule not in candidates and rule not in exclude
                    and self._norm(cat) in self._all_categories_for_rule(rule)):
                candidates.append(rule)
            if len(candidates) == limit:
                break
        return candidates

    def _rule_text(self, rule: str) -> List[str]:
        """Rule description for the re-plan prompt, from the test cases or the specification."""
        tc = self.test_cases.get(rule, {})
        lines = []
        if tc.get("rule_summary"):
            lines.append(f"   Rule: {str(tc['rule_summary'])[:400]}")
        if tc.get("valid_range"):
            lines.append(f"   Valid range: {str(tc['valid_range'])[:200]}")
        for case in tc.get("test_cases", [])[:4]:
            lines.append(f"   Example violation: {case.get('value')!r} ({case.get('violation_type')}): "
                         f"{str(case.get('reason', ''))[:160]}")
        spec = self.spec_rules.get(rule)
        if not lines and isinstance(spec, dict):
            for name, text in list(spec.items())[:4]:
                lines.append(f"   Requirement {name}: {json.dumps(text)[:200]}")
        return lines

    def _build_replan_prompt(self, candidates: List[str], system_config: Dict[str, Any]) -> str:
        lines = [
            "You are planning ONE fuzzing iteration against an ns-3 AFDX (ARINC 664 Part 7) simulator.",
            "The coverage controller asks you to test one of the untested protocol rules below.",
            "Choose the rule that the simulator interface can violate most directly and set the",
            "mutation parameters for that rule only. If none of the rules can be violated with these",
            "parameters, choose the first rule, set every parameter to null, and set \"expressible\": false.",
            "",
            "Candidate rules:",
        ]
        for i, rule in enumerate(candidates, 1):
            lines.append(f"{i}. {rule} (category: {self.rule_category(rule) or 'unmapped'})")
            lines += self._rule_text(rule)
        lines += ["", "Virtual links (id: BAG ms, min frame bytes, max frame bytes):"]
        for vl in system_config.get("available_vls", []):
            cfg = self.vl_table.get(vl)
            if cfg:
                lines.append(f"  {vl}: BAG {cfg['bag_ms']}, min {cfg['min_frame']}, max {cfg['max_frame']}")
        lines += [
            "",
            "Simulator mutation interface (no other field reaches the simulator):",
            "  frame_size: total frame size in bytes; sizes outside the VL limits or above 1518 are dropped by the switch",
            "  bag_value: send interval in ms; a value below the VL BAG sends frames too fast",
            "  timing_jitter_ms: offset added to the send interval (negative = faster, positive = slower)",
            "  mac_mutation_type: 'spoof_src'|'spoof_dst'|'broadcast'|'invalid_src'|'zero_mac' (source MAC)",
            "  dest_mac_mutation: 'corrupt_prefix'|'wrong_vl'|'zero' (destination MAC)",
            "  sequence_number_override: 1-255 forces this sequence number on every frame (0 or null = no override)",
            "  prob: 0.0-1.0 probability of dropping a frame at the sender",
            "",
            "Respond ONLY with JSON:",
            '{"protocol_rule": "<one candidate name>", "expressible": <true|false>, "target_vl": <int>,',
            ' "frame_size": <int or null>, "bag_value": <int or null>, "timing_jitter_ms": <int or null>,',
            ' "mac_mutation_type": <string or null>, "dest_mac_mutation": <string or null>,',
            ' "sequence_number_override": <int or null>, "prob": <float or null>,',
            ' "strategy": "<conformance|edge-case|adversarial>", "reasoning": "<one sentence>"}',
        ]
        return "\n".join(lines)

    def _sanitize_replan(self, plan: Dict[str, Any]) -> Dict[str, Any]:
        def as_int(v):
            return int(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None
        prob = plan.get("prob")
        seq = as_int(plan.get("sequence_number_override"))
        return {
            "bag_value": as_int(plan.get("bag_value")),
            "frame_size": as_int(plan.get("frame_size")),
            "timing_jitter_ms": as_int(plan.get("timing_jitter_ms")),
            "sequence_number_override": seq if seq is not None and 1 <= seq <= 255 else None,
            "prob": float(prob) if isinstance(prob, (int, float)) and 0 < prob <= 1 else None,
            "mac_mutation_type": plan.get("mac_mutation_type")
            if plan.get("mac_mutation_type") in self.SRC_MAC_MUTATIONS else None,
            "dest_mac_mutation": plan.get("dest_mac_mutation")
            if plan.get("dest_mac_mutation") in self.DEST_MAC_MUTATIONS else None,
        }

    def _replan_redirect(self, strategy: Dict[str, Any], from_rule: str, reason: str,
                         candidates: List[str], system_config: Dict[str, Any]) -> Dict[str, Any]:
        """Re-plan the iteration for an untested rule so that label and parameters agree."""
        try:
            plan = json.loads(self._query_llm(self._build_replan_prompt(candidates, system_config)))
        except Exception as e:
            print(f"  [REDIRECT] re-plan failed ({e}); keeping the LLM's strategy")
            self._append_planner_action(strategy, {
                "type": "redirect_skipped", "from_rule": from_rule, "candidates": candidates,
                "reason": reason, "error": str(e)})
            return strategy
        if plan.get("expressible") is False:
            print(f"  [REDIRECT] none of {candidates} is expressible; keeping the LLM's strategy")
            self._append_planner_action(strategy, {
                "type": "redirect_skipped", "from_rule": from_rule, "candidates": candidates,
                "reason": "not expressible", "redirect_trigger": reason})
            return strategy
        chosen = plan.get("protocol_rule") if plan.get("protocol_rule") in candidates else candidates[0]
        print(f"  [REDIRECT] '{from_rule}' ({reason}) -> re-planned for '{chosen}'")
        self._clear_mutation_fields(strategy)
        strategy.update(self._sanitize_replan(plan))
        if plan.get("target_vl") in system_config.get("available_vls", []):
            strategy["target_vl"] = plan["target_vl"]
        strategy["redirected_from_rule"] = from_rule
        strategy["protocol_rule"] = chosen
        strategy["mutation_type"] = chosen
        strategy["primary_rule"] = chosen
        strategy["compound_test"] = False
        strategy["test_mode"] = "custom"
        if plan.get("strategy") in ("conformance", "edge-case", "adversarial"):
            strategy["strategy"] = plan["strategy"]
        strategy["reasoning"] = f"[re-planned for {chosen}] {plan.get('reasoning', '')}"
        self._append_planner_action(strategy, {
            "type": "redirect", "mode": "replan", "from_rule": from_rule, "to_rule": chosen,
            "candidates": candidates, "expressible": bool(plan.get("expressible")),
            "reason": reason})
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
        self,
        uncovered_cats,
        tested_rule_vl_pairs,
        target_vl,
        strategy,
        system_config
    ) -> Optional[str]:
        """Pick a rule not yet tested for this VL from the first uncovered category."""
        for cat in uncovered_cats:
            sub_rules = self._cat_to_rules.get(cat, [])
            # Try exact sub-rule name
            for sub in sub_rules:
                if sub in self.test_cases and (sub, target_vl) not in tested_rule_vl_pairs:
                    return sub
            # Try dotted format: category.sub_rule (common in test_cases.json)
            norm_cat = self._norm(cat)
            for sub in sub_rules:
                dotted = f"{cat}.{sub}"
                if dotted in self.test_cases and (dotted, target_vl) not in tested_rule_vl_pairs:
                    return dotted
            # Try any test_case key containing the category name
            for rule_name in self._all_known_rules:
                if (rule_name, target_vl) in tested_rule_vl_pairs:
                    continue
                rn = self._norm(rule_name)
                if rn == norm_cat or rn.startswith(norm_cat + '_') or norm_cat in rn.split('_'):
                    return rule_name
        # Fallback: any untested known rule
        for rule_name in self._all_known_rules:
            if (rule_name, target_vl) not in tested_rule_vl_pairs:
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
                # Failed iterations leave NaN in these columns.
                field = {k: None if isinstance(v := row.get(k), float) and v != v else v
                         for k in ("mac_mutation_type", "dest_mac_mutation", "frame_size",
                                   "timing_jitter_ms", "sequence_number_override", "bag_value")}
                mt = field["mac_mutation_type"] or ""
                if mt and mt not in ("none", ""):
                    used_mechs.add(f"mac_mutation_type:{mt}")
                dm = field["dest_mac_mutation"] or ""
                if dm and dm not in ("none", ""):
                    used_mechs.add(f"dest_mac_mutation:{dm}")
                fs = field["frame_size"]
                if fs and int(fs or 0) > 1518:
                    used_mechs.add("frame_size>1518")
                tj = field["timing_jitter_ms"]
                if tj and int(tj or 0) < 0:
                    used_mechs.add("timing_jitter_ms<0")
                so = field["sequence_number_override"]
                if so and int(so or 0) > 0:
                    used_mechs.add("sequence_number_override>0")
                fs_val = int(field["frame_size"] or 0)
                bag_val = field["bag_value"]
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
    
    def _record_usage(self, backend: str, model: str, usage: Any) -> None:
        if usage is None:
            return

        def field(obj, *path):
            for name in path:
                obj = getattr(obj, name, None) if obj is not None else None
            return obj

        self._usage.append({
            "backend": backend,
            "model": model,
            "prompt_tokens": field(usage, "prompt_tokens"),
            "cached_tokens": field(usage, "prompt_tokens_details", "cached_tokens"),
            "completion_tokens": field(usage, "completion_tokens"),
            "reasoning_tokens": field(usage, "completion_tokens_details", "reasoning_tokens"),
        })

    def _query_llm(self, prompt: str) -> str:
        """Query LLM with prompt, trying OpenAI first and Claude as fallback."""
        sys_msg = "You are an expert protocol fuzzing agent. Respond ONLY with valid JSON."
        messages = [
            {"role": "system", "content": sys_msg},
            {"role": "user", "content": prompt}
        ]

        # Try OpenAI-compatible backends first
        openai_backends = []
        if self.client:
            openai_backends.append(("OpenAI", self.client, self.model, {
                "max_completion_tokens": 8000,
                "response_format": {"type": "json_object"}
            }))
        last_err = None
        for name, client, model, extra_kwargs in openai_backends:
            for wait_s in (0, 10, 30, 90):
                if wait_s:
                    time.sleep(wait_s)
                try:
                    response = client.chat.completions.create(
                        model=model,
                        messages=messages,
                        **extra_kwargs
                    )
                except Exception as e:
                    last_err = e
                    print(f"[{name}] failed: {e}")
                    continue
                self._record_usage(name, model, getattr(response, "usage", None))
                content = response.choices[0].message.content
                print(f"[{name}] {model} -> {len(content) if content else 0} chars")
                if content:
                    return content
                last_err = ValueError(f"{name} returned an empty response "
                                      f"(finish_reason={response.choices[0].finish_reason})")
                break

        # Try Claude as last resort
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
        unwrapped_from = None
        if not (isinstance(strategy, dict) and all(f in strategy for f in required_fields)):
            # The LLM sometimes nests the plan or returns several; use the first complete one.
            nested = list(strategy.items()) if isinstance(strategy, dict) else list(enumerate(strategy))
            for key, value in nested:
                candidates = value if isinstance(value, list) else [value]
                complete = [c for c in candidates
                            if isinstance(c, dict) and all(f in c for f in required_fields)]
                if complete:
                    strategy, unwrapped_from = complete[0], str(key)
                    break
        if not isinstance(strategy, dict):
            raise ValueError(f"LLM response is a {type(strategy).__name__}, not a JSON object")
        missing = [f for f in required_fields if f not in strategy]
        if missing:
            raise ValueError(f"LLM response missing required fields: {missing} "
                             f"(top-level keys: {list(strategy)[:8]})")
        if unwrapped_from is not None:
            self._append_planner_action(strategy, {"type": "response_unwrapped", "key": unwrapped_from})
        
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

