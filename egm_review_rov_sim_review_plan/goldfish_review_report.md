Status: resolved

**Resolution (2026-11-16, interactive breakdown):** All 13 non-declined items were accepted and applied to `rov_sim_review_plan.md` lines 1-9. Those lines are now lines 1-25 (FeatureRange 1..25, DetailedRange 26..37).
- **Issue 1 (ESCALATE):** the user chose to use the candidate trade-offs as the rationale.
- **Issue 5 (ESCALATE):** the user chose option B (rov-sim docs plus a docs-only `rov_ws` branch).
- **Issue 2 (F2):** after discussion, a tightened version replaced the original proposal. It tries uncompressed `mcap` before blocking; on `serialize_message` failure it names the design candidates; a reindex rejection means fix and retry; only items 3-5 are gated.
- **Issue 7 (F7):** accepted with a split. The spike passes on reindex, `rosbag2_py` and encodings; consumer acceptance stays a first-bag criterion.
- **Declined:** Issues 14 and 15, carried to Stage 9.
- **Counts:** 13 accepted, 0 contested, 2 escalated and answered, 2 declined.

# Goldfish Annotated Review Report

**Target:** `C:\rov-sim\rov_sim_review_plan.md` (lines 1-9, FeatureRange)
**Findings source:** `critic_report.md` (Stage 7, round 1), findings F1-F15
**Summary:** 11 PROPOSE FIX, 2 ESCALATE, 2 DECLINE, 0 CONTEST

Most fixes touch line 7, so the fixes are written as **one replacement for lines 1-9** (at the end of this report). Each finding points to the part of that replacement that fixes it. The two ESCALATE items appear as `<<ANSWER NEEDED>>` placeholders. They need your answer before the text can be final.

## Prioritized Findings & AI Suggestions

### [Issue 1] [`egm-design`, `egm-structural`] - Severity: Blocker (F1)
*   **Affected Scope:** [Lines 7](../rov_sim_review_plan.md#L7) (Decisions), and line 21 for context
*   **Discrepancy Description:** The `mcap` decision records no alternatives and no reasons for rejecting the hand-written writer or uncompressed MCAP (brief lines 104-107). Line 21 credits the choice to "the user" with no link.
*   **Rationale:** Feature-spec Alternatives Rule.
*   ***AI Suggestion:*** ESCALATE
*   ***Justification:*** The finding is valid, but the reason for the choice isn't in any file the reviewers or I can read. The brief leaves it open (Open Question 1). `zoom_out_report.md` only names the choice. `C:\rov-sim\goldfish_review_report.md` covers a different document (`design_draft.md`). The WSL report on line 21 can't be reached from here. Writing a rationale myself would invent a reason the decision wasn't actually based on. Only you know why `mcap` was picked.
*   ***Proposed Edit:*** The "Alternatives" sentence in the replacement block, completed with your reason. Candidate trade-offs to confirm or correct: the hand-written writer costs about 200 lines of CRC, chunk and summary-index code to maintain and test; uncompressed, unchunked MCAP gives larger files, no index, and loses chunk-level crash recovery. Against that, `mcap` is a dependency outside git with two native transitive dependencies.

### [Issue 2] [`egm-design`, `egm-structural`, `egm-style`] - Severity: Major (F2)
*   **Affected Scope:** [Line 7](../rov_sim_review_plan.md#L7); line 13 for context
*   **Discrepancy Description:** "Subject to validation" has no consequence attached, and the conditional-route decision appears only in work item 2.
*   **Rationale:** Risks & Limits requires failure modes and mitigations. The source zoom-out asked for this directly.
*   ***AI Suggestion:*** PROPOSE FIX
*   ***Justification:*** The finding is valid. The brief already supplies fallbacks for two of the four checks (library: brief 104-107; schemas: brief 108). For serialization failure and reindex rejection, the brief has no fallback. I propose "block and return to design" rather than inventing a new route. The catalyst's hand-written CDR encoder and simulator-written `metadata.yaml` (Stage 5 re-audit S1/S6) are larger design changes and should go back to design, not into a plan.
*   ***Proposed Edit:*** The "Route C stays conditional" bullet in the replacement block.

### [Issue 3] [`egm-design`, `egm-structural`, `egm-style`] - Severity: Major (F3)
*   **Affected Scope:** [Lines 3, 5-8](../rov_sim_review_plan.md#L3-L8)
*   **Discrepancy Description:** The status of the brief's seven decisions, of Open Question 2 (`metadata.yaml`), and of the manifest nit is not stated.
*   **Rationale:** A reader can't tell which design is in force.
*   ***AI Suggestion:*** PROPOSE FIX
*   ***Justification:*** The finding is valid and cheap to fix. Work item 3 already assumes reindexing, so recording that as the decision matches the plan's current direction. For the manifest, the plan should say it is kept per brief decision 7, pending a justification in item 4. That records the zoom-out nit without deciding it early.
*   ***Proposed Edit:*** The "brief decisions 1-7 still stand" sentence, plus the `metadata.yaml` and manifest bullets in the replacement block.

### [Issue 4] [`egm-design`, `egm-structural`] - Severity: Major (F4)
*   **Affected Scope:** [Lines 1-9](../rov_sim_review_plan.md#L1-L9)
*   **Discrepancy Description:** No problem statement, goals, architecture, alternatives or risks.
*   **Rationale:** Feature-spec core principle.
*   ***AI Suggestion:*** PROPOSE FIX
*   ***Justification:*** Repeating the brief here would duplicate 189 lines that already pass a separate review. The design critic's first option fits: declare the brief the governing spec, link its sections, and treat these lines as amendments. This also addresses Stage 6 finding 1 for a human reader, because the purpose sentence and links tell them where to look.
*   ***Proposed Edit:*** The new paragraph after the status line in the replacement block.

### [Issue 5] [`egm-design`, `egm-structural`, `egm-style`] - Severity: Major (F5)
*   **Affected Scope:** [Line 8](../rov_sim_review_plan.md#L8)
*   **Discrepancy Description:** It is unclear whether `rov_ws` documentation is in scope. "Same task" conflicts with "no `rov_ws` branch" (brief 167) and the non-goal "changes to `rov_ws` code" (brief 139).
*   **Rationale:** The decision looks settled, but brief Open Question 3 is still open.
*   ***AI Suggestion:*** ESCALATE
*   ***Justification:*** The finding is valid, but the answer is a scope decision only you can make: rov-sim docs only, or rov-sim plus a docs-only `rov_ws` branch. Nothing in the readable files settles it. The catalyst (Stage 5 re-audit S8) notes that the `rov_ws` MCAP contract README describes HoloOcean (brief 56), so Isaac bags may break its documented contract. That points toward including `rov_ws`, but it doesn't decide it.
*   ***Proposed Edit:*** The "Documentation" bullet in the replacement block, with your choice filled in.

### [Issue 6] [`egm-design`] - Severity: Major (F6)
*   **Affected Scope:** [Line 7](../rov_sim_review_plan.md#L7)
*   **Discrepancy Description:** The pin lives outside git, which conflicts with "every change reversible in git" (brief 34).
*   **Rationale:** Reproducibility; a Kit reinstall silently drops the package.
*   ***AI Suggestion:*** PROPOSE FIX
*   ***Justification:*** The finding is valid. The repo already documents fresh-checkout reproduction (`docs/REPRODUCIBILITY.md`, modified in the working tree). The fix records the pin in the repo and adds a startup check. The heavier alternative, vendoring, is a design change to raise separately (Stage 5 re-audit S4). It is also harder than that report suggested, because of the native dependencies (F8).
*   ***Proposed Edit:*** The "Pinning" bullet in the replacement block.

### [Issue 7] [`egm-design`, `egm-style`] - Severity: Major (F7)
*   **Affected Scope:** [Line 7](../rov_sim_review_plan.md#L7)
*   **Discrepancy Description:** "Interoperability" is undefined.
*   **Rationale:** Without pass criteria, the spike can't fail.
*   ***AI Suggestion:*** PROPOSE FIX
*   ***Justification:*** The finding is valid. The criteria come from the brief itself: lines 95-97 (rosbag2 directory, reindex command), line 108 (`ros2msg`), and line 179 (consumers named in the first-bag criteria). Mapping replay is left out on purpose. The brief's first-bag criteria name only `bag_to_capture` and `rov_slam` evaluation, and work item 4 already says to test it or defer the claim.
*   ***Proposed Edit:*** The "Pass criteria" sentence in the route bullet.

### [Issue 8] [`egm-design`] - Severity: Major (F8)
*   **Affected Scope:** [Line 7](../rov_sim_review_plan.md#L7)
*   **Discrepancy Description:** The "pure-Python" assumption is unverified.
*   **Rationale:** Missing native wheels are a likely reason installation fails.
*   ***AI Suggestion:*** PROPOSE FIX
*   ***Justification:*** Verified during Stage 7. The `mcap` 1.6.0 wheel is `py3-none-any`, but its metadata declares `Requires-Dist: lz4` and `Requires-Dist: zstandard`, both native. The brief's "pure-Python" wording (line 105) is inaccurate. Fixing the brief is outside this range, so it is noted here only.
*   ***Proposed Edit:*** The dependency sentence in the `mcap` bullet.

### [Issue 9] [`egm-style`, `egm-structural`] - Severity: Major (F9)
*   **Affected Scope:** [Line 3](../rov_sim_review_plan.md#L3)
*   **Discrepancy Description:** "Does not claim implementation is complete" suggests partial implementation.
*   **Rationale:** The brief says no implementation has run (brief line 5).
*   ***AI Suggestion:*** PROPOSE FIX
*   ***Justification:*** The finding is valid. A search for `mcap` under `rov_sim/` found nothing (Stage 5 re-audit reuse check).
*   ***Proposed Edit:*** The "Status:" line in the replacement block.

### [Issue 10] [`egm-design`, `egm-structural`] - Severity: Nit (F10)
*   **Affected Scope:** [Line 1](../rov_sim_review_plan.md#L1)
*   **Discrepancy Description:** The title names the document type, not the feature.
*   ***AI Suggestion:*** PROPOSE FIX
*   ***Justification:*** A one-line change. It also helps Stage 6 finding 1.
*   ***Proposed Edit:*** New H1 in the replacement block.

### [Issue 11] [`egm-design`, `egm-structural`] - Severity: Nit (F11)
*   **Affected Scope:** [Line 3](../rov_sim_review_plan.md#L3); line 21 for context
*   **Discrepancy Description:** Sources are code spans; path conventions differ.
*   ***AI Suggestion:*** PROPOSE FIX (lines 1-9 only)
*   ***Justification:*** Relative links to files in the same folder cost nothing. The WSL path on line 21 is outside this range and is passed on to Stage 9.
*   ***Proposed Edit:*** Relative markdown links in the replacement block.

### [Issue 12] [`egm-structural`, `egm-style`] - Severity: Nit (F12)
*   **Affected Scope:** [Line 7](../rov_sim_review_plan.md#L7)
*   **Discrepancy Description:** "For the writer" is ambiguous; serialization stays with `rclpy`.
*   ***AI Suggestion:*** PROPOSE FIX
*   ***Justification:*** Prevents misreading, and costs one clause.
*   ***Proposed Edit:*** "It writes only the container; serialization stays with ..." in the `mcap` bullet.

### [Issue 13] [`egm-style`] - Severity: Nit (F13)
*   **Affected Scope:** [Line 7](../rov_sim_review_plan.md#L7)
*   **Discrepancy Description:** The condition is stated twice.
*   ***AI Suggestion:*** PROPOSE FIX
*   ***Justification:*** Fixed as a side effect of the line 7 rewrite.
*   ***Proposed Edit:*** Covered by the replacement block.

### [Issue 14] [`egm-style`] - Severity: Nit (F14)
*   **Affected Scope:** [Line 7](../rov_sim_review_plan.md#L7); line 12 for context
*   **Discrepancy Description:** The name for the environment varies.
*   ***AI Suggestion:*** DECLINE
*   ***Justification:*** The replacement block uses "Kit's bundled Python" throughout lines 1-9. Making line 12 and the brief match is outside this range. Recorded for Stage 9.
*   ***Proposed Edit:*** None beyond the block.

### [Issue 15] [`egm-style`] - Severity: Nit (F15)
*   **Affected Scope:** [Lines 5, 8](../rov_sim_review_plan.md#L5-L8)
*   **Discrepancy Description:** The heading could be read as replacing the brief's decisions; line 8 wording repeats line 17.
*   ***AI Suggestion:*** DECLINE (heading rename applied anyway as part of F3; the overlap between line 8 and line 17 is left for Stage 9, where line 17 is in scope)
*   ***Justification:*** The heading becomes "Review decisions" in the block. Removing the line 8 / line 17 duplicate needs an edit to line 17.
*   ***Proposed Edit:*** None beyond the block.

---

## Proposed replacement for lines 1-9

Placeholders marked `<<ANSWER NEEDED>>` correspond to Issues 1 and 5.

```markdown
# Isaac Sim stereo ground truth to MCAP: review decisions and validation plan

Status: implementation has not started; installation and interoperability are unverified.

This plan amends [concepts_brief.md](concepts_brief.md), which remains the governing feature spec: problem and overview, [goals and non-goals](concepts_brief.md#goals-vs-non-goals), [alternatives](concepts_brief.md#alternatives-weighed) and [risks](concepts_brief.md#remaining-risks-for-option-c). It records the decisions taken after the brief's [zoom-out review](zoom_out_report.md) and the interactive review that followed. The brief's [carried-forward decisions 1-7](concepts_brief.md#key-decisions--staging-for-next-steps) still stand unless amended below.

## Review decisions

- **MCAP container library: the `mcap` Python package** (resolves brief open question 1). It writes only the container; serialization stays with the bundled `rclpy.serialization`. Alternatives rejected: a hand-written writer (brief option 2) because <<ANSWER NEEDED>>; uncompressed, unchunked MCAP (option 3) because <<ANSWER NEEDED>>. `mcap` 1.6.0 is a pure-Python wheel but requires the native `lz4` and `zstandard` packages, so wheels for Kit's bundled Python on Windows must be available.
- **Pinning:** Kit's bundled Python is outside git. Record the validated `mcap`, `lz4` and `zstandard` versions in a file in this repo, check them at startup when the MCAP flag is on, and add the install step to `docs/REPRODUCIBILITY.md`.
- **Route C stays conditional on the spike (work item 2).** Pass criteria: WSL `ros2 bag reindex <dir> -s mcap` succeeds; `rosbag2_py` reads every topic; message and schema encodings are `cdr` and `ros2msg`; `bag_to_capture` and `rov_slam` evaluation accept the bag unchanged. If a check fails:
  - `mcap` cannot be installed in Kit's bundled Python: use the hand-written writer, then uncompressed, unchunked MCAP.
  - The `.msg` files are missing from Jazzy `share/`: embed the schema text (brief risks).
  - `serialize_message` fails in Kit: block implementation and return to design.
  - `reindex` rejects the file: block implementation and return to design.

  Work items 3-6 start only after item 2 passes.
- **`metadata.yaml`: produced by WSL `ros2 bag reindex`** for the first bag (resolves brief open question 2). Revisit writing it from the simulator if the extra WSL step blocks a consumer workflow.
- **Frame manifest:** kept per brief decision 7. Work item 4 must state which failure it catches that the bag's own message counts do not, or remove it.
- **Documentation** (resolves brief open question 3): <<ANSWER NEEDED: rov-sim only, or rov-sim plus a docs-only `rov_ws` branch>>. Update it in the same branch as the implementation; see work item 6.
```

## Handoff to the next stage

- Issue 1 and Issue 5 must be answered before the block can be applied without placeholders.
- Passed on to Stage 9: the WSL path on line 21, the environment-name consistency on line 12, the line 8 / line 17 overlap, and the brief's inaccurate "pure-Python" wording (brief line 105; outside this document).
