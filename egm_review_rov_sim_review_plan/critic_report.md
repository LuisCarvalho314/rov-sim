# Stage 7: Critic Review Report (round 1)

- **Target:** `C:\rov-sim\rov_sim_review_plan.md`, FeatureRange lines 1-9 (title, source line, "Decisions")
- **Reviewers:** `egm-design` (feature-spec standard), `egm-structural` (feature-spec standard), `egm-style` (no standard). All three **completed**; none failed.
- **Goldfish context:** `C:\rov-sim\concepts_brief.md`, `C:\rov-sim\zoom_out_report.md`
- **Date:** 2026-11-16
- **Round result:** not clean. There are open Blocker and Major findings.

## Verdict

Design and structural both **fail** lines 1-9 against the feature-spec standard. Style finds no blockers. Three issues are behind most of the findings:

1. **The plan never says how it relates to the brief.** Lines 1-9 are a decision log that hands off to the brief, but they don't say the brief is still the governing spec. As a result, every section the standard requires (problem, goals, architecture, alternatives, risks) counts as missing, and nobody can tell whether the brief's seven carried-forward decisions still stand.
2. **The one real new decision, `mcap`, has no rationale and no failure branch.**
3. **The documentation decision sounds settled but leaves open which repository's docs are in scope.**

Stating at line 3 that the brief remains the governing spec and lines 5-8 amend it would turn F3 and F4 from failures into one-line fixes. Design F8 makes this point explicitly.

## Fact check done during this stage

Reviewers disagreed about whether `mcap` is "pure Python" (the brief says it is; design flagged it as unverified). Checked against the PyPI wheel metadata for **`mcap` 1.6.0**: the package itself is a pure-Python wheel (`py3-none-any`, Python ≥3.7), but it **requires `lz4` and `zstandard`**, which ship as native wheels. So:

- Installing into Kit needs wheels of those two packages for Kit's Python version on Windows.
- The Stage 5 "vendor a pure-Python wheel" proposal (re-audit S4) would also have to vendor those two native wheels, or find a way to avoid importing them when writing uncompressed chunks. Whether `mcap` imports them lazily was **not checked**.
- The brief's phrase "pure-Python package" (brief line 105) is inaccurate as written.

## Consolidated findings

| ID | Severity | Finding | Lines | Raised by |
|----|----------|---------|-------|-----------|
| F1 | 🔴 Blocker | **No evaluation of alternatives for `mcap`.** The brief (104-107, Open Question 1) lists three options: the `mcap` package, a hand-written writer of about 200 lines, and uncompressed unchunked MCAP. Lines 1-9 record none of them and give no reason for rejecting options 2 and 3. Line 21 credits the choice to "the user" with no link, which the Alternatives Rule forbids. *Fix:* add a short alternatives entry with a concrete trade-off for each option (a dependency outside git plus native deps, versus about 200 lines of CRC, chunk and summary code to maintain, versus larger files and no index), and replace the attribution with the reason or a link. | 7, (21) | design-1-1, structural-1-B1 |
| F2 | 🟡 Major | **No failure branch for the conditional decision.** "Subject to ... validation" has no consequence attached, though one install has already failed. The source zoom-out (line 11) asked for exactly this. *Fix:* give a fallback order (for example `mcap`, then the hand-written writer, then block), the check that triggers each step, and record "route C is conditional on the spike" as a Decision rather than only in item 2. | 7, (13) | design-1-2, structural-1-M3, style-1-2 |
| F3 | 🟡 Major | **How "Decisions" relates to the brief is not stated.** The brief's seven carried-forward decisions (157-163) aren't confirmed, superseded or reopened. Open Question 2 (reindex vs. simulator `metadata.yaml`) is undecided while item 3 assumes reindexing. The zoom-out nit on the manifest isn't decided. *Fix:* one line saying "brief decisions 1-7 still stand", plus explicit decisions on the conditional route, `metadata.yaml`, and the manifest. | 3, 5-8 | design-1-6, design-1-11, structural-1-M2, style-1-7 |
| F4 | 🟡 Major | **None of the spec's required structure is present (problem, goals and non-goals, architecture, risks).** *Fix:* either declare the brief the governing spec and these lines amendments to it, with section-level links, or add short subsections. | 1-9 | design-1-8, structural-1-M1 |
| F5 | 🟡 Major | **Documentation scope is unresolved and conflicts with staging.** Brief Open Question 3 concerns `rov_ws` docs, which its `AGENTS.md` requires, but the brief says no `rov_ws` branch (167) and lists `rov_ws` code changes as a non-goal. "Same task" means nothing for a repo that gets no implementation task. *Fix:* name the repositories; if `rov_ws` is included, allow a docs-only branch and update staging. | 8 | design-1-7, structural-1-M4, style-1-3 |
| F6 | 🟡 Major | **The pin lives outside git, which is a reproducibility risk.** Installing into Kit's Python conflicts with "every change reversible in git" (brief 34), and the brief used the same argument to reject option B (144). A Kit reinstall silently drops the package. *Fix:* say where the pin is recorded, how a missing or mismatched package is detected at startup, and add it to `docs/REPRODUCIBILITY.md`. | 7 | design-1-4 (matches Stage 5 re-audit S4) |
| F7 | 🟡 Major | **"Interoperability" is undefined.** *Fix:* give pass criteria in the decision, e.g. WSL `ros2 bag reindex <dir> -s mcap` succeeds, `rosbag2_py` reads every topic, encodings are `cdr` / `ros2msg`, and the named consumers accept the output unchanged. | 7 | design-1-3, style-1-5 |
| F8 | 🟡 Major | **The dependency assumption is unverified.** Now **confirmed** (see fact check): `mcap` requires the native `lz4` and `zstandard`. *Fix:* record the resolved dependency set and the chosen chunk compression; note uncompressed chunks as the mitigation. | 7 | design-1-5 |
| F9 | 🟡 Major | **The status caveat suggests partial implementation.** "Does not claim implementation is complete" reads as partly done; the brief says none has run (brief 5). *Fix:* "Implementation has not started; installation and interoperability are unverified." | 3 | style-1-1, structural-1-N3 |
| F10 | 🟢 Nit | The title names the document type, not the feature. Suggestion: "Isaac Sim stereo ground truth to MCAP: review decisions and validation plan". | 1 | design-1-9, structural-1-N1 |
| F11 | 🟢 Nit | Source references are code spans with "in this folder"; line 21 uses a WSL path in another repo; the source reports are untracked. Use relative markdown links with section anchors and one path convention, and state where the reports are kept. | 3, (21) | design-1-10, structural-1-N2 |
| F12 | 🟢 Nit | "For the writer" is ambiguous: `mcap` writes only the container, and serialization stays with `rclpy`. Also, "the writer" is undefined in lines 1-9. | 7 | structural-1-N4, style-1-5 |
| F13 | 🟢 Nit | Line 7 states the same condition twice ("subject to ..." / "after validating"). | 7 | style-1-4 |
| F14 | 🟢 Nit | The name for the target environment varies: "Isaac Sim runtime" / "Isaac Sim's bundled Python" / "Kit's Python". Pick one. | 7, (12) | style-1-6 |
| F15 | 🟢 Nit | Line 8 wording: "all affected existing" stacks qualifiers, "task" is undefined, and it repeats item 6 (line 17). Rename the heading to "Review decisions" and add the interactive review as a source. | 5, 8 | style-1-7, style-1-8 |

**Counts:** 1 Blocker, 8 Major, 6 Nit (31 raw findings from three reviewers, merged).

## Traceability matrix

| Raw finding | Consolidated |
|---|---|
| design-1-1 | F1 |
| design-1-2 | F2 |
| design-1-3 | F7 |
| design-1-4 | F6 |
| design-1-5 | F8 |
| design-1-6 | F3 |
| design-1-7 | F5 |
| design-1-8 | F4 |
| design-1-9 | F10 |
| design-1-10 | F11 |
| design-1-11 | F3 |
| structural-1-B1 | F1 |
| structural-1-M1 | F4 |
| structural-1-M2 | F3 |
| structural-1-M3 | F2 |
| structural-1-M4 | F5 |
| structural-1-N1 | F10 |
| structural-1-N2 | F11 |
| structural-1-N3 | F9 |
| structural-1-N4 | F12 |
| style-1-1 | F9 |
| style-1-2 | F2 |
| style-1-3 | F5 |
| style-1-4 | F13 |
| style-1-5 | F7, F12 |
| style-1-6 | F14 |
| style-1-7 | F3, F15 |
| style-1-8 | F15 |

## Cross-stage links

- F2 matches Stage 5 re-audit S1 and Stage 6 finding 3.
- F3 matches Stage 5 re-audit S2.
- F4 matches Stage 6 finding 1 and the first-pass Stage 5 B1/B2.
- F5 matches Stage 5 re-audit S8.
- F6 and F8 match Stage 5 re-audit S4.
- F11 matches Stage 5 re-audit S3 and Stage 6 finding 8.

## Out of scope (passed on to Stage 9)

- Line 21 points to `/home/lcarv/rov_ws/goldfish_review_report.md`, while an untracked `C:\rov-sim\goldfish_review_report.md` exists. Decide which copy is authoritative.
