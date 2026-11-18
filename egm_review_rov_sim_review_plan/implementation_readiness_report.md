# Stage 9: Implementation Readiness Report (round 1)

- **Target:** `C:\rov-sim\rov_sim_review_plan.md`, DetailedRange lines 26-37 ("Work to complete", "Review status"); lines 1-25 read as context
- **Reviewers:** `egm-implementation-readiness` (implementation-readiness standard), `egm-codebase-details` (implementation-readiness standard), `egm-style` (no standard). All three **completed**.
- **Goldfish context:** `C:\rov-sim\concepts_brief.md`, `C:\rov-sim\zoom_out_report.md`
- **Date:** 2026-11-16
- **Round result:** not clean (Blocker and Major findings are open).

## Verdict: not ready for implementation

Both readiness reviewers fail lines 26-37 independently, for the same three reasons:
- **No build step.** No item builds the feature: no writer module, no flag, no CameraInfo, no stamps.
- **No file boundary.** No repository-relative paths are named.
- **Decisions handed to the implementer.** Items 3-5 say "Specify…", "Define…", "define limits / specify disk-full behaviour". These are the source zoom-out Majors copied over as tasks.

**A note on what kind of document this is:** lines 26-37 are a *list of remaining review actions*. They are not an implementation plan, and they never claimed to be (line 3: "implementation has not started"). The implementation-readiness standard assumes an implementation plan. So the three blockers say, in effect, "the implementation plan doesn't exist yet". That is accurate and useful, but it is not a defect in the wording of a document that is a review action list. You have two ways forward:

1. **Keep this document as a review/decision record.** Rename the section, for example "Remaining validation and decisions before planning". State that an implementation plan will be written after the spike. Fix the Majors that still apply to a decision record: M1-M5, M8-M10, M13.
2. **Turn it into the implementation plan.** Add phase 0 (the restructure commit and branch), build items with file paths, the decided answers for items 3-5, and a test plan. This is real design work. The spike results (item 2) are probably needed first, because several answers depend on them.

Option 1 matches the plan's own gate (line 21: items 3-5 start only after the spike passes).

## Verified during this stage

| Claim | Result |
|---|---|
| Baseline throughput | `docs/REPRODUCIBILITY.md:62` records **12.8005 pairs/s** (40 CameraSensor pairs). The brief says "12.6 pairs/s" (brief:111). **These don't match.** |
| Existing run-status mechanism | `rov_sim/application.py` writes `status.json` with states `running_<pass>`, `complete`, `failed` and `interrupted` (lines 74, 222-223, 380-386). Item 3 ignores it. |
| Line 37's reference | `\\wsl.localhost\Ubuntu\home\lcarv\rov_ws\goldfish_review_report.md` exists. Its header reads "**Status: resolved.**", and its target is `/mnt/c/rov-sim/zoom_out_report.md`, not this plan. So line 37's "the interactive review is not complete" is **stale**, and the "first four major fixes" are that report's items, not anything in this document. |
| Pin file location | `requirements-tools.txt:1` says "leave Isaac Sim packages unchanged", so Kit pins can't go there (matches Stage 8 M1). |

## Consolidated findings

| ID | Severity | Finding | Lines | Raised by |
|----|----------|---------|-------|-----------|
| B1 | 🔴 Blocker | **No item builds the feature.** Not covered: the writer module, the flag (accepted only with `camera-sensor`), copying raw RGB from GPU to CPU and converting it to `bgr8`, CameraInfo from `stereo_calibration.json`, the stamp formula, pose/`/tf`/`/tf_static`, staging and rename, the manifest, the line 14 startup check, and the 30-frame first bag (brief 122-128, 157-180). | 26-33 | readiness-1-1, codebase-1-B1 |
| B2 | 🔴 Blocker | **No file boundary.** Paths that must be named include: the writer module under `rov_sim/`, `rov_sim/cli.py` (`parse_args`, 14-63), `rov_sim/application.py` (the frame hook next to `recorder.record(...)` at line 286), `rov_sim/sensors/rtx_stereo.py` (borrowing the raw buffer), `rov_sim/config.py` and `configs/*.yaml`, the pin file, the spike script, test files, `docs/REPRODUCIBILITY.md`, `README.md`, and `rov_ws/src/rov_dataset_player/README.md`. | 26-33 | readiness-1-3, codebase-1-B2 |
| B3 | 🔴 Blocker | **Items 3-6 hand design to the implementer (Zero-Decision Rule).** Also undecided: the epoch value (brief 162 "value to choose"), the flag name, the output layout, the staging suffix, `/tf` content, the format of `custom_data` values, and compression and chunk size. | 30-33 | readiness-1-2, readiness-1-5, codebase-1-B3 |
| M1 | 🟡 Major | **Line 37 is stale and can't be traced.** The WSL report it cites is *resolved* and covers `zoom_out_report.md`. "First four major fixes" are that report's items, not this document's. It repeats line 3 word for word and line 9 with a different reason. A different, resolved `C:\rov-sim\goldfish_review_report.md` (about `design_draft.md`) sits where a Windows reader would look. The path also exposes a home directory. *Fix:* replace it with a self-contained line that links this review's report (`egm_review_rov_sim_review_plan/`) and says what is still open. | 37 | style-1-M1/M2/M3/N5, readiness-1-12, codebase-1-M6 (matches Stage 8 M2) |
| M2 | 🟡 Major | **Item 2 doesn't match the line 15 pass criteria.** It leaves out the `rosbag2_py` read and the encoding check. It doesn't say where the script lives, what the sample contains, or where the verdict is recorded. "Keep the route conditional" repeats line 15. | 29 | style-1-M4, readiness-1-7, codebase-1-N1 (matches Stage 8 M3) |
| M3 | 🟡 Major | **Item 1 leaves out the line 13-14 deliverables and has no command.** Missing: the `lz4`/`zstandard` wheel check, the uncompressed test, the pin file, the startup check and its failure behaviour, and the `REPRODUCIBILITY.md` step. The interpreter is `python.bat` found by `scripts/runtime.ps1`, so the command would be e.g. `& $runtime -m pip install mcap==1.6.0`. *But* Stage 8 M1 says not to install into Kit at all; settle that first. | 28 | style-1-M5, readiness-1-6, codebase-1-M5, readiness-1-13 |
| M4 | 🟡 Major | **Item 4 leaves out the manifest decision from line 23 and doesn't name the consumers concretely.** "The other named consumers" and "that compatibility claim" point to the brief. Name `bag_to_capture`, `rov_slam` evaluation and `rov_mapping` replay, with their commands. | 31 | style-1-M6, readiness-1-10, codebase-1-N2, codebase-1-M3 |
| M5 | 🟡 Major | **Item 3 ignores the existing `status.json` run-status pattern** (verified above). Say whether the bag's staging, rename and reindex states extend it or replace it, to avoid a second completeness mechanism. | 30 | codebase-1-M1 |
| M6 | 🟡 Major | **CLI and output-layout collisions are unaddressed.** How the flag relates to `--record`, `--benchmark` (supervisor child) and `--preview-mp4`; whether `validate_config` or `parse_args` rejects non-`camera-sensor` backends; where the per-pass bag directories go inside the run directory that `--output-dir` creates. | 26-33 | readiness-1-4 |
| M7 | 🟡 Major | **No test plan.** Missing: the known-colour `bgr8` pixel test, flag-off byte-identical behaviour with freshness checks, first-bag criteria (brief 173-180), Kit-free unit tests for stamps, CameraInfo (cx = W/2 − 0.5, P[0,3] = −fx·0.38) and flag validation, and edge cases (empty pass, disk full, crash before rename, missing `.msg`, version mismatch). | 26-33 | readiness-1-8 |
| M8 | 🟡 Major | **Phase 0 is missing.** Brief staging step 1 (commit the `rov_sim/` restructure alone, tag it, create `feature/isaac-mcap`) hasn't happened: git status shows the restructure uncommitted. The `rov_ws` docs branch has no name. Without phase 0, the "reversible in git" and "flag-off byte-identical" baselines don't exist. | 26-28 | readiness-1-9, codebase-1-M4 |
| M9 | 🟡 Major | **Item 5 doesn't reuse the benchmark tooling and cites no baseline.** `--benchmark --record` already measures `recording_ms` and `iteration_total_ms` (`application.py:294-296`). Name the command, the frame count and the baseline, and settle 12.8005 vs. 12.6 (verified above). "Target setup" and "intended runs" are undefined. | 32 | codebase-1-M2, style-1-N2 |
| M10 | 🟡 Major | **Item 6 has no file list, even though the repo already answers it.** README recording command (75), output layout (195-213), module table (257), benchmark note (300), `docs/REPRODUCIBILITY.md`, `docs/VALIDATION.md`, and `rov_ws` `src/rov_dataset_player/README.md`. It doesn't mention the `rov_ws` branch from line 24. | 33 | readiness-1-11, codebase-1-M7, codebase-1-M3, style-1-N4 |
| N1 | 🟢 Nit | Interpreter name: "Isaac Sim's bundled Python" (28) vs. "Kit's bundled Python" (13, 14, 16). | 28 | style-1-N1 (carried from Stage 7 F14) |
| N2 | 🟢 Nit | Item 6 wording: "affected existing", "with implementation", "as applicable". | 33 | style-1-N3 |
| N3 | 🟢 Nit | Item 1: put the instruction before the history, e.g. "Run from native Windows (WSL install fails with an untrusted mount-point error)". | 28 | style-1-N6 (Stage 5 S11, Stage 8 N5) |

**Counts:** 3 Blocker, 10 Major, 3 Nit (34 raw findings across three reviewers, merged).

## Traceability matrix

| Raw finding | Consolidated |
|---|---|
| readiness-1-1 | B1 |
| readiness-1-2 | B3 |
| readiness-1-3 | B2 |
| readiness-1-4 | M6 |
| readiness-1-5 | B3 |
| readiness-1-6 | M3 |
| readiness-1-7 | M2 |
| readiness-1-8 | M7 |
| readiness-1-9 | M8 |
| readiness-1-10 | M4 |
| readiness-1-11 | M10 |
| readiness-1-12 | M1 |
| readiness-1-13 | M3 |
| codebase-1-B1 | B1 |
| codebase-1-B2 | B2 |
| codebase-1-B3 | B3 |
| codebase-1-M1 | M5 |
| codebase-1-M2 | M9 |
| codebase-1-M3 | M4, M10 |
| codebase-1-M4 | M8 |
| codebase-1-M5 | M3 |
| codebase-1-M6 | M1 |
| codebase-1-M7 | M10 |
| codebase-1-N1 | M2 |
| codebase-1-N2 | M4 |
| style-1-M1 | M1 |
| style-1-M2 | M1 |
| style-1-M3 | M1 |
| style-1-M4 | M2 |
| style-1-M5 | M3 |
| style-1-M6 | M4 |
| style-1-N1 | N1 |
| style-1-N2 | M9 |
| style-1-N3 | N2 |
| style-1-N4 | M10 |
| style-1-N5 | M1 |
| style-1-N6 | N3 |

## Carried in from earlier stages

| Earlier finding | Where it lands here |
|---|---|
| Stage 8 M1 (do not install into Kit; use `pip --target` into a gitignored repo directory) | Affects M3 directly; still undecided |
| Stage 8 M2 | M1 |
| Stage 8 M3 | M2, M3, M4 |
| Stage 8 N1 (`rov_ws` docs scope) | M10 |
| Stage 8 N4 (title says "validation plan") | Relevant to the document-type note above |
| Stage 7 F14 | N1 |
| Brief "pure-Python" wording (brief 105) | Still uncorrected; outside this document |
| Brief "12.6 pairs/s" (brief 111) | Contradicts `REPRODUCIBILITY.md` (M9); outside this document |
