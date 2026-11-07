# Revision Status and Work Plan (TAES-2026-2779)

**Written:** 2026-11-07, for the advisors' meeting of 2026-11-08. **Deadline:** 13 Nov 2026
(6 days from today).

**Sources.** Reviewer text: the editor's decision email of 14 Oct 2026, quoted verbatim.
"Draft" means the student's revised manuscript of 2026-10-24 (the "_Clean" PDF). It already
answers some comments, but it was written before we found the simulator and baseline bugs, so
its numbers are no longer valid. Details: `context/PAPER_CHANGES.md` (every text change),
`context/FIX_PLAN.md` (fixes and Stage 7 runs), `context/EVALUATION_METRICS.md` (new metrics),
`context/BOOFUZZ_MODEL_PLAN.md` and `context/RANDOM_MODEL_PLAN.md` (new baselines),
`context/REVISION_FINDINGS.md` (all bugs found).

**What the editor requires at submission:** the revised manuscript (2-column, clean), a version
with every change highlighted, and a point-by-point response file. A submission missing the
highlighted version or the response file is returned.

---

## 0. Where we stand, in one table

Final comparison on the corrected simulator, 200 tests per run (Stage 7 and the new baselines):

| Fuzzer | Bugs found (of 8 reachable) | Boundary points (of 79) | Boundary ranges (of 51) | Code lines covered (of 2,213) | Tests with no change |
|---|---|---|---|---|---|
| LLM-guided (5 runs) | 8, 8, 8, 8, 8 | 31–34 | 45–47 | 1,467–1,473 | 2–4 |
| Random, Peach rule (5 seeds) | 7, 7, 7, 7, 7 | 9–12 | 34–37 | 1,469–1,473 | 0 |
| boofuzz 0.4.2 as is (1 run, deterministic) | 7 | 13 | 39 | 1,468 | 0 |
| Ablation A0 / A1 / A2 (1 run each) | 7 / 8 / 8 | 17 / 22 / 30 | 23 / 27 / 47 | 1,440 / 1,462 / 1,473 | — |

LLM vs. random: Mann–Whitney p = 0.008 for bugs, boundary points and ranges; code coverage
p = 0.21 (no difference). Normal traffic alone covers 1,322 lines. The bug that separates the
fuzzers is `max_frame_off_by_one` (needs a frame of exactly MaxFrame + 1).

**Status labels below:** **Done** (work finished, text to write), **Partly**, **To run**
(experiment still needed), **Decision** (advisors must decide), **Text only**.

---

## 1. Reviewer 1

### R1-1. Figure 6, Table IV and Equation (7) are inconsistent

> Equation (7) defines unique findings as a set difference, U_f = R_f \ union of R_f', so unique
> findings are by construction a subset of the rules a fuzzer exercises and cannot exceed them.
> Table IV nonetheless reports the random baseline as covering 54/185 categories while recording
> 92 unique findings. Summing the regions of Figure 6 gives 172 (LLM), 176 (BOOFUZZ) and 169
> (Random), with a union of 388, each exceeding the 185-category denominator; the LLM total of
> 172 matches neither the 158/185 of Table IV nor the 94.6% rule-label coverage quoted in Section
> VII-C. Section VII-C does distinguish raw rule-label coverage from normalized specification
> coverage, but the Table IV caption places both rows in normalized units and the Figure 6
> caption refers to "canonical protocol rules". Please state the units of every coverage and
> uniqueness figure and reconcile the three presentations.

**Status: Done (by removal); Text only.**
- The submitted numbers mixed units: raw labels and normalized categories. We also found that a
  single label could count for several categories (REVISION_FINDINGS Bug 17).
- **Our response:** Rule Coverage and Unique Findings are removed as evaluation metrics (see
  §3), so Table IV's coverage rows, Figure 6 and Eq. (7) go. The letter explains what was wrong
  in the submitted numbers (mixed units, Bug 17) and what replaces them.
- **Paper:** remove Eq. (5) and Eq. (7), the coverage rows of the results table, Fig. 5 and
  Fig. 6. Every remaining number gets its unit in the caption.

### R1-2. The primary metric is defined by the method under evaluation

> Normalized rule coverage is computed over the 185 SUT-relevant categories, which are
> themselves the output of the extraction pipeline being evaluated. The baselines are therefore
> graded against an artifact the proposed method produced, which structurally favours it, and
> this underpins the headline 85.4% / 47.0% / 29.2% comparison. Please repeat the comparison
> against an independent ground truth -- the 122 validation criteria of Villegas et al. are
> already used elsewhere in the paper -- or argue explicitly why the shared denominator does not
> bias the outcome.

**Status: Done (experiments); Text only; one open question for the student.**
- We agree with the reviewer. Rule Coverage is dropped. The comparison is now made on three
  metrics that do not depend on our pipeline:
  1. **Bug detection (primary):** ground truth, replayed on the simulator. Klees et al., CCS 2018,
     recommend this.
  2. **Boundary-value coverage:** the classes come from the VL configuration and the standard,
     by standard boundary-value analysis (79 points, 51 ranges).
  3. **Code coverage of the simulator:** gcov/gcovr. It was checked against a known answer and
     against a second tool (EVALUATION_METRICS §3.6b).
- The baselines were also rebuilt so that they no longer use our extracted rules or test cases.
  This was a second way they depended on our pipeline:
  - boofuzz 0.4.2's own values over the simulator's input fields;
  - random fuzzing following Peach's random-mutation rule.
- **"122 validation criteria of Villegas et al.":** we checked the Villegas et al. paper (IEEE
  Access 2022) and found no list of 122 criteria. The draft's checklist is the 142 "shall /
  should / must" statements taken from the standard itself. **Ask the student where "122" comes
  from.** If there is no source, the letter must say that the earlier citation was wrong.
- **Paper:** new Section VII-A (metrics), new Experiment 2 results, new baselines description.

### R1-3. Single-run results, no variance or significance testing

> All headline figures appear to derive from one run per configuration; Please repeat the main
> comparison and the ablation several times per configuration, report mean and dispersion, and
> test the primary coverage claim for significance.

**Status: Main comparison done; ablation still to run.**
- Main comparison: LLM 5 runs, random 5 seeds, exact Mann–Whitney (smallest attainable
  p = 0.008). boofuzz is deterministic, so one run represents it; the letter must say so.
- **To run: ablation A0, A1, A2, 4 more runs each,** so that each has 5. About $100 of OpenAI
  calls and 1–2 days of wall-clock time. **Needs approval.**

### R1-4a. Reward weights not given, no tuning procedure

> Equation (1) introduces lambda_imp, lambda_viol, lambda_nov and lambda_rep, but no values are
> given in the paper or the appendix, and no tuning procedure is described. Since the reward is
> presented as central to the method's advantage, these must be reported, ideally with a brief
> sensitivity check.

**Status: Partly (text exists); Decision on a sensitivity check.**
- The draft already has Table X (weights) and says they were chosen by hand and fixed.
- Two corrections: the impact term was constant in the submitted campaigns (Bug 6, now fixed),
  and the letter must say so.
- Sensitivity argument: the ablation variant without feedback (A1) never sees the reward. Its
  results (8 bugs, 22 boundary points) still need repeats (R1-3) before we can lean on them.
- **Decision:** argue from the ablation only (free), or also run the full fuzzer with one
  changed weight set (about $20 per run).

### R1-4b. No repository URL or archival DOI

> The simulator is described as open source in the abstract, in Section IV-E and in the
> conclusion, but I was unable to locate a repository URL or archival DOI in the manuscript.
> Given that the simulator is offered as a reusable benchmark, please include one.

**Status: To do (1 hour, needs the owner of the GitHub account).**
- The draft has the GitHub URL (`github.com/hodisan94/ARINC664-LLM…`).
- Still needed: merge the fix branch, tag a release and archive it on Zenodo for a DOI. Only the
  account owner (the student) can do this, or someone they give access to.

### R1 minor comments

| # | Original text | Status | Response |
|---|---|---|---|
| m1 | "Frame length numbers specified in page 6 is not consistent with Figure 2" | **To check** (30 min) | Not checked yet against the draft. |
| m2 | "Table III reports completeness as 93.9% (77/82), but Section VII-B describes the ground-truth checklist as enumerating all normative "shall"/"must" statements cross-referenced with 122 criteria. Please explain the 82-item denominator." | Partly | The draft replaces the 82 items with the 142 statements found mechanically in the standard (68.3% fully captured). Remove "122 criteria" (see R1-2). Ask the student how the 82 items were built. |
| m3 | "Rule correctness is 73.3% on a 236-rule sample, with 10.6% explicitly rejected by the judge. Please specify whether the rejected rules also populate the coverage denominator?" | Done by removal | They did. Since Rule Coverage is removed, this no longer affects any result; say so. The audit numbers themselves are in the draft (615/643). |
| m4 | "The median first detection iteration is 0.0 for two of three fuzzers (Table V), which conveys little information; consider reporting the per-bug distribution instead." | Done | Iteration 0 came from the simulator's second sender (Bug 1): normal traffic was being dropped. On the corrected simulator no bug is detected without a mutation. Report per bug: how many inputs detect it, per fuzzer. |
| m5 | "'Stateless' carries much of the novelty argument, yet Section IV describes per-VL switch state, sequence-number state, a deduplication table and token-bucket credit state. The intended claim appears to be the absence of a request/response session; Clarification on this would remove the apparent tension with Section IV without weakening the contribution." | Done in draft | The draft defines stateless as "no request/response session" (abstract and introduction). Keep. |
| m6 | "There are editing issues, e.g. Page 15- B. Experiments: Goal part must start at the begining of the line, rather than in-line with previous statement." | Text only | Fix in LaTeX during the final pass. |

---

## 2. Reviewer 2

### R2-1. Representativeness and selection of the injected bugs (also Question 1)

> Although there is evidence that the eight bugs selected for the bug detection performance
> comparison are related to the specifications, the representativeness of the bug set and the
> selection procedure were not sufficiently explained.

> The paper states that the 8 injected bugs correspond to specification checks, but it does
> not explain how they were selected from the broader set of possible faults. Because the suite
> primarily consists of omitted checks, its representativeness of real AFDX implementation
> faults is unclear, limiting the generalizability of the reported detection rates. The authors
> should clarify the rationale for their selection.

> How were the eight injected bugs selected, and what evidence supports their
> representativeness of faults in real AFDX implementations?

**Status: Partly done; one optional experiment.**
- **Done:**
  - The suite now has 10 bugs. Two new ones are not omitted checks: an off-by-one (MaxFrame + 1)
    and a threshold error (10% BAG tolerance instead of 1%).
  - `accept_oversized` is no longer a copy of `skip_frame_validation`.
  - The list was fixed before the new runs were scored, and every bug passed two acceptance
    checks (BUG_SUITE.md).
  - Two bugs are shown to be unreachable through the simulator's input interface, and why.
- **Weakness that remains:** the authors still chose the bugs, and the one bug that separates
  the fuzzers is a boundary bug.
- **Optional experiment: mutation testing.** A tool generates hundreds of faults in the
  simulator mechanically, with no human choice. Every fuzzer's logged inputs are then replayed
  against them, and we report the share each fuzzer exposes. It is free (no LLM) but takes 1–2
  days of work and compute. Recommended if time allows; otherwise state the weakness as a
  limitation.
- **Decision:** mutation testing yes or no.

### R2-2. The judge LLM is not validated (also Question 2)

> Verification of whether the Specification Knowledge Extraction Process was performed correctly
> is also carried out by an LLM. It is impossible to objectively assess how accurately this
> judge LLM generated the rules.

> The paper evaluates extracted rules using a judge LLM but does not independently validate the
> reliability of its judgments. The reported Rule Correctness, therefore, reflects the
> proportion of rules the judge accepted, with insufficient evidence that these judgments
> accurately reflect the specification. The authors should assess the judge's accuracy and error
> types against a reference set of rules verified by domain experts using the specification.

> Was Judge LLM's ability to assess extracted rules independently validated against
> expert-adjudicated ground truth? How were incorrect or unverifiable judgments handled?

**Status: To do. Needs human expert time, no money.**
- The draft's answer is a second LLM judge (GPT-5) on 108 rules: 91.7% agreement, κ = 0.28.
  The reviewer explicitly asks for **domain experts**, so this is not enough.
- **Plan:**
  1. I prepare a file of about 50 rules, sampled with a fixed seed across the agreement strata,
     each with its specification passage and the judge's verdict hidden.
  2. One or two authors mark each rule correct, incorrect or unverifiable against the standard.
     This takes about 3–4 hours per person.
  3. I compute the judge's accuracy, its error types and κ against the experts.
- **Decision:** who reviews the rules, and by when (by 2026-11-10 at the latest).

### R2-3. Single small topology (also Question 4)

> Since the evaluation was conducted only on a single, small-scale topology, it remains
> unconfirmed whether the effectiveness is maintained under conditions such as competing traffic
> from multiple transmitting ESs, multi-hop switching, and timing, policing, and redundancy
> behaviors that arise with increased scale.

> The evaluation is limited to a single topology with 2 redundant switches and 3 end systems.
> It is therefore unclear whether the reported coverage and bug detection performance hold in
> more complex network configurations. The authors should evaluate configurations with varying
> numbers of transmitting end systems, hop counts, and delay differences between redundant
> paths.

> Does the approach remain effective on larger topologies?

**Status: Not done. Decision.**
- The simulator's topology is built in `afdx-demo.cc`. A second topology (for example more
  end systems and two switches in a row) means C++ work, validation, and new runs of every
  fuzzer: an estimated 2–3 days plus about $50–100 in LLM costs. That is tight for 13 Nov.
- Options:
  - **(a)** one extra topology with a reduced run set (LLM 3 runs, baselines);
  - **(b)** a clearly argued limitation, plus the note that all three end systems already
    transmit (the draft's caption says only ES1 transmits; this must be corrected anyway);
  - **(c)** ask the editor for an extension and do (a).
- **Recommendation:** (c) if the editor agrees, otherwise (b).

### R2-4. Coverage of boundary values and combinations, depth vs. detection

> Rule Coverage counts a category as covered once a corresponding violation signal is observed,
> without distinguishing a single tested input from thorough testing across boundary values and
> conditions. High coverage does not establish that each rule has been adequately tested. The
> authors should report coverage of boundary values and combinations of conditions within each
> rule category, and assess how testing depth affects bug detection.

**Status: Done (boundary values); combinations optional.**
- Boundary-value coverage is implemented (`boundary_coverage.py`, 12 tests) and computed for
  all runs: LLM 31–34 of 79 points, random 9–12, boofuzz 13 (p = 0.008).
- **Depth vs. detection:** every input that detects `max_frame_off_by_one` hits a MaxFrame + 1
  class, and no baseline input reaches any MaxFrame ± 1 class. That bug is what separates the
  fuzzers. We report per bug which classes expose it.
- **Not done:** combinations of conditions (pairs of classes in one test). Free to compute from
  the logs, about half a day. Optional.

### R2-5. Table IV vs. Figure 6 counts

> The per-fuzzer coverage counts in Table IV do not match the totals obtained by summing the
> corresponding regions in Figure 6. In particular, Random is reported to cover 54 categories
> but to have 92 unique findings, which is impossible under the same counting scheme. The
> authors should clarify the counting units and normalization criteria, and recompute the
> results using a consistent set of rules and execution logs.

**Status: Done (by removal).** Same as R1-1.

### R2-6. The ablation mixes feedback and redirection

> The no-feedback ablation removes both feedback information, such as previous execution
> outcomes, and coverage-driven redirection toward untested rules, making it difficult to
> isolate the cause of the performance decline. The results do not distinguish the contribution
> of the LLM's use of feedback from that of the controller's prevention of redundant
> exploration. The authors should separately evaluate feedback removal with the controller
> retained and redirection removal with feedback retained.

**Status: Design done; repeats to run.**
- The 2 × 2 ablation asked for exists:
  - **A1:** steering without feedback;
  - **A2:** feedback without steering;
  - **A0:** neither.
- It was re-run in Stage 7 on the corrected simulator, one run each:
  - bugs: A0 7, A1 8, A2 8;
  - boundary points: 17, 22, 30.
- **To run:** the repeats of R1-3 (same $100).
- **Text:** the draft's conclusion ("coverage comes mainly from steering") was based on Rule
  Coverage and must be rewritten with the new metrics. The steering's re-plan step is itself an
  LLM call (PAPER_CHANGES 7.3), so do not claim that it isolates the controller.

---

## 3. What to remove from the paper, keep, and add

**Short answer:**
- **Remove 9 metrics, 2 figures and the label-based sensitivity analysis.**
- **Add 2 metrics:** boundary-value coverage and code coverage. Bug detection, already in the
  paper, becomes the primary metric. Mutation score is a possible third addition (optional, see
  R2-1).
- **Keep all experiments,** but Experiment 2 and the ablation get new metrics and new
  baselines.
- **The NAV case study needs a decision.**

### 3.1 Metrics (Section VII-A of the draft)

| Metric (draft) | Decision | Why |
|---|---|---|
| a) Rule Correctness | **Keep** | Experiment 1; add the expert validation (R2-2). |
| b) Rule Completeness (142 statements) | **Keep** | Experiment 1; independent denominator (the standard's text). Remove "122 criteria". |
| c) Redundancy Ratio | **Keep, recompute** | The test cases were regenerated (3,989 for 626 rules); the 0.4% is from the old file. |
| Inter-model agreement | **Keep** | Experiment 1, unaffected. |
| d) Rule Coverage (labels, 185 categories) | **Remove** | Depends on our pipeline (R1-2); labels are not tests. |
| Executed Rule Coverage | **Remove** | The same, plus "any mutation counts". |
| Distinct rule labels | **Remove** | A label count, not a test count. |
| e) Time to Coverage | **Remove** | Defined on Rule Coverage; N/A for every fuzzer anyway. |
| g) Unique Findings, Eq. (7), executed variant | **Remove** | Defined on Rule Coverage; the source of R1-1 and R2-5. |
| Checklist coverage through labels, looser Jaccard mapping | **Remove** | Both still go through labels (PAPER_CHANGES 4.10). |
| Distinct simulator settings | **Remove** | Weak; boundary coverage measures variety better. |
| f) Ratio of Valid Messages | **Keep as one sentence** | Sanity check only (all runs at or near 100%). |
| Tests without any mutation | **Keep as one row** | Shows that every test does something (LLM 2–4, baselines 0). |
| h) Bug Detection Rate | **Keep, make primary** | 10-bug suite, reported of 10 and of 8 reachable. |
| i) First Detection Iteration | **Replace** | By per-bug detection counts (R1 m4). |
| Targeted-pattern bugs | **Remove** | Superseded by per-bug results. |
| **New: boundary-value coverage** | **Add** | R2-4; independent of the method. |
| **New: code coverage (lines, branches)** | **Add, secondary** | Independent; shows no difference, report as is. |
| **New: mutation score** | **Optional** | Only if mutation testing is run (R2-1). |

### 3.2 Experiments, tables and figures

| Item | Decision |
|---|---|
| Experiment 1 (rule extraction), Table IV extraction rows | Keep; add the expert-validation result; recompute redundancy. |
| Experiment 2 (comparison with baselines), Table V | Keep the experiment, **replace the table**: new baselines (boofuzz as is, Peach-rule random), metrics = bugs, boundary points and ranges, code lines and branches, tests without mutation. |
| Old "BOOFUZZ-style" and old random baselines | **Remove** from the results; describe in the letter why they were replaced (they walked our own test-case list; 27% of rules got no mutation, and other faults, REVISION_FINDINGS Part C). |
| Fig. 5 (Rule Coverage curves) | **Replace** with curves of bugs found and boundary classes over the 200 tests (free, from the logs). |
| Fig. 6 (Venn of Unique Findings) | **Remove.** |
| Ablation, Table VI, Fig. 7 | Keep the 2 × 2 design; new metrics; 5 runs per variant after the repeats. |
| Experiment 3 (bug detection), Tables III, VII, VIII | Keep; 10 bugs, Stage 7 numbers, per-bug counts; correct the "two bugs at iteration 0" paragraph. |
| Section IV simulator | Keep; add the list of simulator corrections (second sender, timing, frame size, BAG tolerance and others). |
| NAV case study, Table IX | **Decision.** Its metrics are labels and rewards ("distinct rule/mutation labels", "reward ≥ 2.2"), and it ran before the simulator fixes. **(a)** Shorten it to "the pipeline extracts 8 NAV rules and the loop runs 200 iterations", no effectiveness claim. **(b)** Remove it and free about a page. Recommended: (a). |

---

## 4. Work plan to 13 Nov

| # | Task | Who | Cost | Days | Status |
|---|---|---|---|---|---|
| 1 | Ask the editor for an extension (2–3 weeks), citing the corrected simulator and the new experiments | Advisor or Noa | — | today | **Urgent** |
| 2 | Ablation repeats, 4 × A0/A1/A2 | Claude, after approval | ≈ $100 | 1–2 | Waiting for approval |
| 3 | Expert validation of the judge: sample file → authors mark it → analysis | Claude + 1–2 authors | free | 2 (3–4 h of expert time) | Waiting for reviewer names |
| 4 | Curves over the 200 tests (bugs, boundary classes) | Claude | free | 0.5 | Ready to start |
| 5 | Recompute the redundancy ratio on the new test cases | Claude | check whether it needs LLM calls | 0.5 | To do |
| 6 | Mutation testing (optional, R2-1) | Claude | free | 1–2 | Decision |
| 7 | Second topology (R2-3) | Claude | ≈ $50–100 | 2–3 | Decision; likely only with extension |
| 8 | Questions to the student: "122 criteria", the 82-item checklist, the second sender, GitHub release and Zenodo DOI | Noa | — | — | To send |
| 9 | Check the page 6 frame lengths against Fig. 2 (R1 m1) | Claude | free | 0.1 | To do |
| 10 | Rewrite the paper: Sections IV (corrections), V-B, VII (metrics, Exp. 2, ablation, Exp. 3), VIII, abstract, conclusion; highlighted version | Noa + Claude | — | 3 | Not started |
| 11 | Response letter, point by point (this file is its skeleton) | Noa + Claude | — | 1 | Not started |
| 12 | Final checks: every number in the paper traced to a result file | Claude | free | 0.5 | Not started |

Without an extension, the minimum to submit by 13 Nov is tasks 2, 3, 4, 8 (DOI), 9, 10, 11 and
12. The second topology becomes a limitation, and mutation testing is dropped.

## 5. Decisions for the meeting

1. Approve the ablation repeats (≈ $100).
2. Who validates the judge's rules, and by when.
3. Ask the editor for an extension: yes or no, and who writes to them.
4. Second topology: run it (needs the extension) or state it as a limitation.
5. Mutation testing: yes or no.
6. NAV case study: shorten or remove.
7. Confirm dropping Rule Coverage completely (not even as a secondary metric).
