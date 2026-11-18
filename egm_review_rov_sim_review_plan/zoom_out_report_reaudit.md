# Stage 5: Initial Zoom Out Report (re-audit)

- **Target:** `C:\rov-sim\rov_sim_review_plan.md` (21 lines, whole file; unchanged since the first pass)
- **Split:** FeatureRange 1..9, DetailedRange 10..21
- **Goldfish context (added for this re-audit and used in later stages):** `C:\rov-sim\concepts_brief.md`, `C:\rov-sim\zoom_out_report.md` (the edited earlier zoom-out review of the brief)
- **Reviewers:** `egm-zoom-out` (judged against the zoom-out standard), `egm-inventive-catalyst` (no standard; review mode)
- **Re-audit cap:** Stage 5 has now used its one re-audit.
- **Superseded report:** `zoom_out_report.md` in this folder (first pass, no context). Its two blockers (no objective, no design) are resolved once the sources are read. The zoom-out reviewer now finds no blockers.

## What changed compared with the first pass

- **Gone:** B1 (no objective) and B2 (not a design). With the sources read, the plan is judged as what it is: a short follow-up to the brief, at the right altitude. Only a one-sentence purpose line is still suggested (S9).
- **Gone:** "possible reinvention / why not rosbag2-native". The brief already weighs this and chooses the route.
- **Still open:** no fallback for the conditional route, review-status traceability, duplicate items.
- **New:** two findings from the source `zoom_out_report.md` were dropped without a decision. Documentation scope conflicts with the brief's "no rov_ws branch" staging. The catalyst argues that the paused timeline turns throughput into a wall-time question, not an integrity question.

## Combined summary (findings from both reviewers, duplicates merged)

| # | Severity | Finding | Lines | Source |
|---|----------|---------|-------|--------|
| S1 | 🟡 Major | **The conditional route has no failure path.** The source finding asked "specify whether a failed check changes the writer approach or blocks implementation"; line 13 keeps only "keep the route conditional". The brief already has fallbacks for the library (hand-written or uncompressed writer, brief:104-107) and for schemas (embed as text, brief:108). Serialization failure and reindex rejection have none. Items 3-6 have no gate before them. *Fix:* add a gate ("items 3-6 start after items 1-2 pass") and a one-line consequence for each of the four spike checks. Optionally put the container behind an `open/write/close` interface so the library is swappable. | 7, 12-14 | Zoom-out M1, Catalyst M5 |
| S2 | 🟡 Major | **Two source findings were dropped without a decision.** The source `zoom_out_report.md` has two nits: (a) what the frame manifest catches that the bag doesn't, the only finding about cutting scope; the manifest stays in brief:112/128/163; (b) the decision rule for moving `metadata.yaml` generation into the simulator; item 3 quietly assumes reindexing. *Fix:* record each as accepted, deferred or rejected, or fold (a) into item 4. | 3, 14, 15, 21 | Zoom-out M2 |
| S3 | 🟡 Major | **The review status can't be traced.** "First four major fixes above" matches neither the 5 source Majors nor the 6 items. The "writer-alternatives finding" is in neither named source. `/home/lcarv/rov_ws/goldfish_review_report.md` (WSL) conflicts with the untracked `C:\rov-sim\goldfish_review_report.md`. *Fix:* map each item to its source finding, add the goldfish report to line 3, and give one canonical path. | 3, 21 | Zoom-out M3, Catalyst N7 |
| S4 | 🟡 Major | **Installing into Kit's bundled Python conflicts with the brief's own rules.** Changes must be reversible in git (brief:34), and behaviour must stay byte-identical with the flag off (brief:111). An install into Kit site-packages is unversioned. The WSL failure is a symptom. *Proposal:* vendor a hash-pinned pure-Python `mcap` wheel in the repo and add it to `sys.path` only when the flag is on. Item 1 then becomes a smoke test. *Liability:* manual updates and licence upkeep; you need a test that the vendored copy is the one imported. *Unverified:* that `mcap` has no required native dependencies. | 7, 12 | Catalyst M1 |
| S5 | 🟡 Major | **Two "done" states (rename vs. reindex).** Item 3 copies the source wording without resolving it. *Proposal:* a directory state machine: `<pass>.partial/` (being written or crashed; an MCAP file without a footer is detectably incomplete), `<pass>/` without `metadata.yaml` (closed cleanly), `<pass>/` with `metadata.yaml` (ready for consumers). Optional best-effort `wsl.exe ros2 bag reindex` at the end of a run. *Liability:* WSL coupling; recovery needs chunked output. | 13-14 | Catalyst M2 |
| S6 | 🟡 Major | **Completeness duplicates MCAP-native data.** The MCAP Statistics record already holds per-channel counts. *Proposal:* replace the separate manifest with an MCAP Metadata record (expected frame count, epoch/fps, pass name) written at close. The check compares it with Statistics, the regenerated `stamp_ns` series and the 7-topic bundles. This also answers S2(a). *Unverified:* that rosbag2 / `reindex` / `bag_to_capture` ignore unknown Metadata records. | 15 | Catalyst M3 |
| S7 | 🟡 Major | **Throughput can't lose frames.** The timeline is paused (brief:42) and stamps come from the frame index (brief:162), so a slow writer only makes the run longer. The only hard limit is disk size, about 2.2 MB/frame × frames (brief:109). *Proposal:* a pre-run free-space check that refuses to start. Optionally, a bounded queue feeding a writer thread with blocking backpressure. Measurement then only sets a wall-time budget. | 16 | Catalyst M4 |
| S8 | 🟢 Nit | **Documentation scope.** Lines 8/17 don't say whether `rov_ws` docs are included (brief open question 3, `AGENTS.md`). The brief says no `rov_ws` branch (brief:167), but its README describes a HoloOcean-specific contract (brief:56) that Isaac bags may break. *Fix:* state the scope; consider a docs-only `rov_ws` branch. | 8, 17 | Zoom-out N2, Catalyst N6 |
| S9 | 🟢 Nit | Repeated items: line 7 and item 1 (pinning); line 8 and item 6 (documentation). Item 1 is also a sub-step of item 2. | 7-8, 12, 17 | Zoom-out N1 |
| S10 | 🟢 Nit | Add one sentence of purpose (Isaac Sim stereo ground truth as MCAP for `rov_ws` consumers) so the plan makes sense without the brief. | 1-3 | Zoom-out N3 |
| S11 | 🟢 Nit | The WSL mount-point error is history; move it under "Review status". | 12 | Zoom-out N4 |

**Reuse check (zoom-out):** a search for `mcap` under `C:\rov-sim\rov_sim` found nothing. No existing writer to reuse, which fits the choice of the external package plus `ros2 bag reindex`.

**Unverified claims to check in the spike (line 13):** MCAP Statistics/Metadata records and footer-based incompleteness detection; chunk-level recovery with the MCAP CLI; rosbag2 ignoring unknown Metadata records; `mcap` having no required native dependencies. All of these come from reviewers' general knowledge, not from checks against this repo or the installed versions.

**Evidence limits:** Neither reviewer read the goldfish report named on line 21, the brainstorm synthesis reports, or `rov_ws` source. Claims that the plan faithfully carries forward its sources cover only `concepts_brief.md` and `zoom_out_report.md`.

---

## Reviewer report: egm-zoom-out (re-audit)

**Verdict: Revise. No blockers.** The plan is short, stays at the right level, and adds no new code. It carries forward all five Major source findings (lines 7-8, 12-17). The gaps are: what happens if the conditions fail, how findings trace back to their sources, and two source findings dropped without saying so.

- **M1. "Conditional" route with no failure path (lines 7, 12-13).** Line 13 keeps only half of the source finding. The brief already lists fallbacks (lines 104-107). Items 3-6 depend on the spike and have no gate. *Fix:* add the gate line and a fallback-or-block for each spike check.
- **M2. Two source findings dropped without a decision (line 21).** The frame-manifest purpose (the only finding about cutting scope; the manifest is still in brief:112/128/163) and the decision rule for simulator-side `metadata.yaml` (brief open question 2; item 3 assumes reindex). *Fix:* record a decision for each, or fold the manifest question into item 4.
- **M3. The review-status line can't be traced (line 21).** "First four major fixes above" has nothing to point to. The "writer-alternatives finding" is not in the named sources. The WSL path conflicts with `C:/rov-sim/goldfish_review_report.md`. *Fix:* map items to findings, add the goldfish report to the sources, and fix the path.
- **N1.** Repeated items: 7/12 and 8/17.
- **N2.** Which repo's docs is not stated (brief open question 3: `rov_ws` docs required by its `AGENTS.md`).
- **N3.** Add one sentence of purpose.
- **N4.** Install history in item 1 belongs under "Review status".

## Reviewer report: egm-inventive-catalyst (re-audit)

**Verdict:** The plan accepts several trade-offs that patterns from the catalog can remove. Where the brief already resolves something, the reviewer did not re-raise it.

- **M1. Kit install conflicts with git-reversible, byte-identical runtime (lines 7, 12).** Vendor a hash-pinned wheel and add it to `sys.path` only when the flag is on.
- **M2. Two "done" states (lines 13-14).** Use a three-state directory machine (`.partial` / closed / indexed). Optional best-effort reindex at the end of a run.
- **M3. Completeness duplicates MCAP data (line 15).** Fold the manifest into an MCAP Metadata record and check it against Statistics, regenerated stamps and the 7-topic bundles.
- **M4. A paused timeline means throughput can't lose frames (line 16).** Pre-run free-space refusal; optional bounded writer queue with blocking backpressure.
- **M5. No fallback for two of the four spike checks (line 13).** Serialization: hand-written CDR for the four message families, with a byte-match test against WSL `rclpy`. Reindex: simulator-written `metadata.yaml` (brief:98). Put the container behind an `open/write/close` interface.
- **N6.** Same-task doc updates conflict with "no rov_ws branch". Split the `rov_ws` README into a checked contract and a HoloOcean producer profile; add a docs-only branch.
- **N7.** Review-status traceability (same as zoom-out M3).
