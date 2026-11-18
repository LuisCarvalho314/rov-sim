# Stage 8: Intermediate Zoom Out Report

- **Target:** `C:\rov-sim\rov_sim_review_plan.md`, full file (37 lines). FeatureRange is lines 1-25, rewritten in Stage 7. DetailedRange is lines 26-37, unchanged.
- **Reviewer:** `egm-zoom-out` (zoom-out standard), review mode. It was given the earlier re-audit report so it would not repeat it.
- **Goldfish context:** `C:\rov-sim\concepts_brief.md`, `C:\rov-sim\zoom_out_report.md`
- **Date:** 2026-11-16

## Verdict: Revise. No blockers.

The Stage 7 rewrite closed most of the Stage 5 re-audit:

| Re-audit item | Closed by |
|---|---|
| S10 (purpose sentence) | line 5 |
| S1 (failure paths and gate) | lines 15-21 |
| S2 (dropped source findings) | lines 22-23 |
| S8 (documentation scope) | line 24 |

No new code modules are proposed, and a search for `mcap`/`lz4`/`zstandard` under `rov_sim/` still finds nothing to reuse.

Three problems remain:
1. The new pinning decision breaks a stated project rule.
2. The unchanged lines 26-37 now disagree with the rewritten lines 1-25.
3. Several new decisions have no work item that delivers them.

## Verified during this stage

The project-rule conflict in M1 was checked against the working-tree files. All four quotes are accurate:

| Source | Text |
|---|---|
| `README.md:33-34` | "Use Isaac Sim's bundled packages for simulation; do not install these tools over its runtime packages." |
| `README.md:63` | "No extension copying or modification of the Isaac Sim installation is required." |
| `README.md:231` | "No package installation is required." |
| `requirements-tools.txt:1` | "Ordinary Python analysis environment only; leave Isaac Sim packages unchanged." |

`README.md` has uncommitted changes in the working tree; these lines are from that version.

## Findings

| ID | Severity | Finding | Lines | Fix |
|----|----------|---------|-------|-----|
| M1 | 🟡 Major | **Installing into Kit's Python breaks the README rule, and the pinning fix only guards against drift.** The plan installs `mcap`, `lz4` and `zstandard` into Kit's bundled Python, against the four quotes above. Line 14 (added in Stage 7, Issue 6) adds a version file, a startup check and an install step, but leaves the Kit runtime modified. Re-audit S4 (vendoring) has no recorded decision. | 13-14, 28 | Install into a gitignored directory in the repo, not into Kit's site-packages: `<kit python> -m pip install --target <repo>/.kit_deps -r requirements-mcap.txt`, pinned with `==` like `requirements-tools.txt`. Put that directory on `sys.path` only when the flag is on. Kit stays unmodified and the pinned file is the version record, which probably makes the startup check unnecessary. Either way, the README lines must change in the same branch. *Unverified:* that `lz4`/`zstandard` installed this way load in Kit's interpreter. Add this to the spike. |
| M2 | 🟡 Major | **"Review status" (line 37) contradicts the new header.** Line 5 says the decisions came "after ... the interactive review"; line 37 says "the interactive review is not complete". "First four major fixes above" now points at six decision bullets plus six work items, so it matches nothing. It repeats line 9 with a different reason and line 3 word for word. The WSL path is still there. | 37 (vs. 3, 5, 9) | Shrink line 37 to two things: whether the review is still open, and one canonical path to the remaining findings. Delete the rest. |
| M3 | 🟡 Major | **New decisions have no work items; the work list states weaker criteria.** (a) The line 13 checks (Windows wheels, uncompressed without `lz4`/`zstandard`) aren't in item 1, line 28. (b) The line 14 version file and startup check have no item. (c) The line 15 pass criteria are three checks, but item 2 (line 29) says only "reindex accepts it", and "keep the route conditional" now repeats line 15. (d) Line 23 sends the manifest decision to item 4, but item 4 (line 31) doesn't mention it. | 13-15, 23 vs. 28-31 | Merge item 1 into item 2, pointing at line 15 for the criteria. Add the pinning or M1 deliverable to that item. Add "manifest: justify or remove" to item 4. |
| N1 | 🟢 Nit | **Documentation scope on line 24 is open-ended.** "Any docs that describe HoloOcean-only requirements" could grow without limit. "Same branch as the implementation" doesn't fit `rov_ws`, which has no implementation branch. Item 6 (line 33) doesn't mention `rov_ws`. | 24, 33 | Limit it to statements Isaac bags would break: `map` rebasing, `initial_left_camera_optical_frame`, the nominal calibration file, HoloOcean metadata keys (brief 81-84). Say the `rov_ws` docs branch merges together with the rov-sim feature branch. Mention `rov_ws` in item 6. |
| N2 | 🟢 Nit | **Rejection reason partly applies to the accepted fallback.** Option 3 is rejected partly for "about 2.2 GB per 1,000 frames", but the first fallback (uncompressed chunks, line 16) is the same size. Only the summary index and chunk recovery separate them. | 11, 16 | Drop the size argument from line 11, or note that the fallback accepts it. |
| N3 | 🟢 Nit | **Speculative design on line 18.** Naming candidates (CDR encoder, out-of-process writer) for a failure that hasn't happened is early design. An out-of-process writer may bring back the cross-process problems the brief used to reject options A and B. | 18 | Keep "block and return to design" and drop the candidates, or add that warning. |
| N4 | 🟢 Nit | **The title says "validation plan", but items 3, 5 and 6 are specification and implementation work.** | 1 | e.g. "review decisions and remaining work". |
| N5 | 🟢 Nit | **Install history still in item 1** (re-audit S11). Line 13 now owns the install question. | 28 | Move it to the status line or drop it; it disappears anyway if M3 merges items 1 and 2. |

**Counts:** 0 Blocker, 3 Major, 5 Nit.

## Notes for the author

- **M1 comes from a Stage 7 fix.** Issue 6's pinning bullet was the lighter option. The vendoring alternative was set aside partly because of the native `lz4`/`zstandard` wheels. `pip install --target` into a gitignored repo directory removes that objection, because pip fetches the native wheels for Kit's interpreter just like a normal install. It also stays inside the README rule. This is the strongest finding from this stage.
- **N3 reverses part of the tightened Issue 2** that you accepted in Stage 7, where the candidates were added after discussion. The reviewer's point is that naming them is design work done too early. The counter-point from that discussion still holds: naming them tells the reader where "return to design" leads. Your call.
- **M2, M3 and N1 fall in DetailedRange (lines 26-37), which Stage 9 audits next.** If you go straight on, Stage 9 will probably raise them again. Fixing them first would let Stage 9 focus on readiness.

## Evidence limits

The reviewer did not read `goldfish_review_report.md`, the brainstorm reports, or `rov_ws` source. The `mcap` 1.6.0 dependency claim was verified in Stage 7. The `--target` alternative has **not** been checked against Kit's interpreter.
