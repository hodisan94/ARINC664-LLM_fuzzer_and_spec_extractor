# Evaluation Metrics Checklist

## Status Overview

| # | Metric | Stage | Implemented? | Tier | Effort |
|---|--------|-------|:------------:|:----:|:------:|
| 1 | Rule Coverage (cumulative) | Fuzzing | [x] | 1 | Low |
| 2 | Time to Coverage (80% / 100%) | Fuzzing | [x] | 1 | Low |
| 3 | Redundancy Ratio | Test Cases | [x] | 1 | Low |
| 4 | Violation Diversity (Entropy) | Fuzzing | [x] | 1 | Low |
| 5 | Unique Findings (Venn) | Fuzzing | [x] | 1 | Low |
| 6 | Reward Convergence (Moving Avg) | Fuzzing | [x] | 1 | Low |
| 7 | Rule Correctness | Extraction | [ ] | 2 | Medium |
| 8 | Ratio of Valid Messages | Fuzzing | [x] | 2 | Medium |
| 9 | Cost-Effectiveness | Fuzzing | [x] | 2 | Low |
| 10 | Per-Rule Effectiveness | Fuzzing | [ ] | 2 | Medium |
| 11 | Bug Detection Rate (BDR) | Fuzzing | [ ] | 3 | **High** |
| 12 | Mean Iterations to First Detection | Fuzzing | [ ] | 3 | Low* |
| 13 | Rule Completeness | Extraction | [ ] | 3 | High |
| 14 | Statistical Significance Tests | Evaluation | [x] | — | Done |

\* Metric 12 is low effort only if metric 11 (bug injection) is already implemented.

---

## Existing Infrastructure

### Already implemented (`evaluation/three_way_comparison.py`)
- Basic statistics (iterations, success rate)
- Reward analysis (mean, median, max, std, improvement %)
- Coverage counts (unique VLs, rules, mutations, violation types)
- Efficiency (policing rate, bugs found, bugs per iteration)
- Learning curve (LLM early vs late, by quarters)
- Violation type distribution and high-reward percentage
- Statistical tests: Mann-Whitney U (pairwise), Kruskal-Wallis (all three)

### Data sources
- `llm_fuzzer/data/iteration_history.jsonl` — LLM fuzzer results
- `random_baseline/data/iteration_history.jsonl` — Random baseline results
- `boofuzz_baseline/data/iteration_history.jsonl` — Boofuzz baseline results
- `configs/spec_rules_filtered.json` — 236 simulator-relevant rules
- `configs/test_cases.json` — 1,491 violation test cases

---

## Tier 1 — Must Have, Low Effort

These metrics require only post-processing of existing `iteration_history.jsonl` data
and `test_cases.json`. No changes to the fuzzers or simulator needed.

---

### 1. Rule Coverage (Cumulative)

**Paper formula:**
```
RuleCov = #rules triggered by fuzzer / #total extracted rules
```

**What it measures:**
The fraction of extracted rules for which the fuzzer generated at least one frame that
triggered a violation detected by the simulator. Plotted as a cumulative curve over
iterations — the key graph showing how quickly each fuzzer explores the rule space.

**How to compute:**
For each iteration in `iteration_history.jsonl`, track the `protocol_rule` field.
A rule counts as "triggered" if the iteration had `policing_rate > 0` or `bugs_found > 0`.
Plot cumulative unique triggered rules / 236 (total filtered rules) over iterations.

**Output:** Graph (x = iteration, y = cumulative rule coverage %). One line per fuzzer.

**Worth it?** Absolutely. This is the single most important graph for the paper.
It directly shows whether the LLM fuzzer covers rules faster than baselines.

---

### 2. Time to Coverage

**Paper formula:**
```
Iterations to reach coverage level q ∈ {80%, 100%}
```

**What it measures:**
How many iterations each fuzzer needs to first reach 80% and 100% of rule coverage.
Lower = more sample-efficient.

**How to compute:**
Derived directly from the cumulative coverage curve (metric 1). Find the first
iteration where coverage crosses 80% and 100%.

**Output:** Table with one row per fuzzer, columns for iter@80% and iter@100%.

**Worth it?** Yes. Gives a single number to compare fuzzers. Easy to compute once
metric 1 exists. If no fuzzer reaches 100%, report the maximum coverage achieved.

---

### 3. Redundancy Ratio

**Paper formula:**
```
Redundancy = #duplicate test cases / #total test cases
```

**What it measures:**
The fraction of generated test cases that are semantically equivalent to another
test case targeting the same rule. Low = the LLM produces diverse, non-redundant inputs.

**How to compute:**
For each parameter in `test_cases.json`, compare all test cases pairwise:
- **Exact duplicates:** same `value` and `violation_type` → definite duplicate.
- **Near duplicates:** same `violation_type` with values within 5% of each other.
Count duplicates and divide by total test cases (1,491).

**Output:** Single number (e.g., "Redundancy = 8.3%").

**Worth it?** Yes. Quick computation, and it validates that the LLM test case
generation is producing diverse inputs, not repeating itself.

---

### 4. Violation Diversity (Shannon Entropy)

**What it measures:**
How evenly distributed the violation types are across iterations. A fuzzer that
concentrates on one violation type has low entropy; one that spreads evenly has high
entropy. Higher = better diversity.

**How to compute:**
From `iteration_history.jsonl`, count occurrences of each `protocol_rule` (or
`violation_type` if available). Compute Shannon entropy:
```
H = -Σ p_i · log2(p_i)
```
where p_i is the fraction of iterations targeting rule i.

**Output:** One number per fuzzer. Optionally: bar chart of violation type distribution.

**Worth it?** Yes. Single number that captures diversity. Complements Rule Coverage
(metric 1) — a fuzzer could have high coverage but low diversity if it visits most
rules once then hammers the same one repeatedly.

---

### 5. Unique Findings (Venn Diagram)

**What it measures:**
Which rule-violation combinations were found by only one fuzzer, by two, or by all
three. Highlights the LLM fuzzer's ability to find violations that baselines miss.

**How to compute:**
For each fuzzer, build a set of (protocol_rule, violation_type) pairs from successful
iterations (policing_rate > 0). Compute set intersections and differences.

**Output:** Venn diagram figure + table showing:
- LLM-only findings
- Random-only findings
- Boofuzz-only findings
- Shared findings (pairwise and all three)

**Worth it?** Very. The Venn diagram is a powerful visual for the paper. If LLM
has many unique findings, that's strong evidence for the approach.

---

### 6. Reward Convergence (Moving Average)

**What it measures:**
The trend of reward over time. For the LLM fuzzer, reward should increase as it
learns from feedback. For Random/Boofuzz, it should stay flat.

**How to compute:**
Compute a rolling average of the `reward` field with window size 5-10 iterations.
Plot for all three fuzzers on the same graph.

**Output:** Graph (x = iteration, y = rolling average reward). One line per fuzzer.

**Worth it?** Yes. The learning curve is the core claim of the paper — that the LLM
improves over time. This graph is the proof. Already partially captured in
`three_way_comparison.py` (learning curve analysis) but only as early/late split,
not as a continuous rolling curve.

---

## Tier 2 — Important, Medium Effort

These require either manual work, a new validation component, or additional data collection.

---

### 7. Rule Correctness

**Paper formula:**
```
Correctness = #correctly extracted rules / #total extracted rules
```

**What it measures:**
Of the 236 filtered rules (or 434 total), how many have constraints that are
fully accurate with respect to the ARINC 664 Part 7 specification.

**How to compute:**
Requires manual review. Recommended approach:
1. Randomly sample 50 rules from `spec_rules_filtered.json`.
2. For each rule, verify against the PDF spec: is the constraint correct?
3. Mark as correct/incorrect/partially correct.
4. Compute correctness rate with 95% confidence interval.

**Effort:** ~2-3 hours of manual review for a 50-rule sample.

**Worth it?** Yes. Reviewers will ask "how do you know the extracted rules are
correct?" This metric answers that question. A sample-based approach is standard
and acceptable in the literature.

---

### 8. Ratio of Valid Messages

**Paper formula:**
```
R_valid = #frames accepted by protocol validator / #frames sent
```

**What it measures:**
The fraction of fuzzer-generated frames that are syntactically valid AFDX frames.
Important because: syntactically invalid frames get dropped before reaching protocol
logic, so they're wasted effort. The ideal fuzzer produces frames that are
structurally valid but violate semantic rules.

**How to compute (two options):**

**Option A (proxy — low effort):**
Use `frames_received` from simulator logs as proxy. The ns-3 simulator already drops
malformed frames. So:
```
R_valid ≈ frames_received / frames_sent
```
This is already available in `iteration_history.jsonl`.

**Option B (independent validator — medium effort):**
Build a Python AFDX frame validator that checks: Ethernet header (EtherType, MAC),
IP header (version, length, TTL), UDP header (ports), SN field presence.
Run it on all generated mutation files.

**Worth it?** Yes for Option A (already have the data). Option B is stronger for
the paper but more work.

---

### 9. Cost-Effectiveness

**What it measures:**
API cost per unique rule violation found. The LLM fuzzer uses paid API calls
(GPT-4o); the baselines don't. This metric addresses the obvious reviewer question:
"Is the LLM approach cost-justified?"

**How to compute:**
- Count total LLM API calls in the fuzzer run (1 per iteration for strategy planning).
- Estimate cost: ~$0.01-0.03 per call (GPT-4o input+output tokens).
- Divide total cost by number of unique violations found.
- Compare with: Random (cost = $0) and Boofuzz (cost = $0).

**Output:** Table: "LLM found X unique violations at $Y total cost ($Z per violation).
Random found W violations at $0. Boofuzz found V violations at $0."

**Worth it?** Yes. Addresses a key criticism. If 50 iterations cost ~$1-2 total and
find significantly more violations, that's compelling.

---

### 10. Per-Rule Effectiveness

**What it measures:**
For rules tested by all three fuzzers, what is the average reward each achieves?
This is the fairest comparison: same rules, different strategies.

**How to compute:**
1. Find the set of `protocol_rule` values present in all three history files.
2. For each common rule, compute mean reward per fuzzer.
3. Report overall mean + per-rule breakdown.

**Output:** Table of common rules with mean reward per fuzzer. Bar chart.

**Worth it?** Moderate. Gives a "controlled experiment" feel, but only works if
there's enough overlap in rules tested by all three.

---

## Tier 3 — Strong Evidence, High Effort

These require significant infrastructure work (C++ simulator changes or manual
ground-truth creation) but produce the most convincing evidence for the paper.

---

### 11. Bug Detection Rate (BDR)

**Paper formula:**
```
BDR = #bugs detected / #bugs injected
```

**What it measures:**
Of N intentionally injected bugs in the simulator, how many does each fuzzer
detect within 200 iterations? This is the gold standard for fuzzer evaluation.

**How to implement (bug injection):**
Modify the ns-3 AFDX simulator C++ code to introduce known, toggleable bugs:

| Bug ID | Description | How to inject |
|--------|------------|---------------|
| B1 | Disable BAG enforcement | Remove BAG interval check in traffic policer |
| B2 | Allow oversized frames | Change Lmax check from 1518 to 9999 |
| B3 | Skip sequence number validation | Bypass SN continuity check |
| B4 | Accept invalid VL IDs | Disable VL lookup validation |
| B5 | Disable redundancy management | Allow duplicate frames on both paths |
| B6 | Wrong MAC filtering | Accept non-AFDX multicast MACs |
| B7 | No jitter enforcement | Remove jitter bounds checking |
| B8 | Accept sub-VL violations | Skip sub-VL scheduling validation |

Each bug is enabled via a compile flag or config parameter. Run each fuzzer
(LLM, Random, Boofuzz) for 200 iterations per bug. Record whether and when
each bug is detected.

**Effort:** High — requires C++ modifications to the simulator. Estimated 1-2 days
for an experienced developer.

**Worth it?** Extremely. This is the strongest possible evidence. It transforms
the evaluation from "our fuzzer gets higher rewards" (somewhat abstract) to
"our fuzzer finds real bugs faster" (concrete and compelling). Reviewers love
mutation testing experiments.

---

### 12. Mean Iterations to First Detection

**Paper formula:**
```
Ī_det = Σ I(b) / |B_det|
```

**What it measures:**
Average number of iterations before each injected bug is first detected.
Lower = faster convergence to fault-revealing inputs.

**How to compute:**
For each bug b from metric 11, record the iteration number where the fuzzer
first detects it. Average across all detected bugs.

**Dependency:** Requires metric 11 (bug injection) to be implemented first.

**Effort:** Low once metric 11 exists — pure post-processing.

**Worth it?** Yes, if metric 11 is done. Gives a single, powerful number:
"LLM detects bugs in 12 iterations on average vs. 47 for Random."

---

### 13. Rule Completeness

**Paper formula:**
```
Completeness = #spec requirements covered by extracted rules / #total spec requirements
```

**What it measures:**
What fraction of all normative requirements ("shall" statements) in ARINC 664
Part 7 are covered by at least one extracted rule.

**How to compute:**
1. Extract all "shall" statements from the PDF spec (manually or LLM-assisted).
2. For each requirement, check if any of the 434 extracted rules covers it.
3. Compute coverage fraction.

**Effort:** High. The ARINC 664 Part 7 spec has hundreds of "shall" statements.
Manual extraction takes significant time. LLM-assisted extraction is faster but
needs validation.

**Worth it?** Important for completeness of the paper, but can be approximated.
A reasonable alternative: focus on a specific chapter (e.g., Chapter 5 on AFDX)
and compute completeness for that chapter only.

---

## Implementation Plan

All Tier 1 metrics are implemented in:
`evaluation/compute_metrics.py`

### How to run
```bash
cd ns-3/
python3 evaluation/compute_metrics.py
```

### Output files
- `evaluation/results/metrics_report.json` — full JSON report
- `evaluation/results/figures/rule_coverage.png` — cumulative rule coverage graph
- `evaluation/results/figures/violation_diversity.png` — entropy bar chart
- `evaluation/results/figures/unique_findings_venn.png` — Venn diagram
- `evaluation/results/figures/reward_convergence.png` — learning curve graph

### CLI options
```bash
python3 evaluation/compute_metrics.py \
  --llm-history llm_fuzzer/data/iteration_history.jsonl \
  --random-history random_baseline/data/iteration_history.jsonl \
  --boofuzz-history boofuzz_baseline/data/iteration_history.jsonl \
  --test-cases configs/test_cases.json \
  --spec-rules configs/spec_rules_filtered.json \
  --window 5
```

### Dependencies
```
pandas, numpy          — data processing (already installed)
matplotlib             — graphs (already installed)
matplotlib_venn        — Venn diagram (installed)
scipy                  — statistical tests (already installed)
```

### Execution Order
1. Run all three fuzzers (50+ iterations each)
2. Run `python3 evaluation/compute_metrics.py`
3. Review outputs in `evaluation/results/`

---

## Notes for Paper

- All metrics are computed on the **same rule set** (`spec_rules_filtered.json`,
  236 rules) for fair comparison.
- All three fuzzers use the **same infrastructure** (TestGenerator, SimulatorRunner,
  FeedbackAnalyzer, RewardCalculator) — only the strategy selection differs.
- Statistical significance is tested with Mann-Whitney U (non-parametric, no
  normality assumption) at α = 0.05.
- For metrics requiring manual validation (7, 13), random sampling with confidence
  intervals is used to keep effort manageable.
