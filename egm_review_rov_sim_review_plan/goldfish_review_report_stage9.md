Status: resolved

**Resolution (2026-11-16, interactive breakdown):** 16 items were decided. The edits were applied to `rov_sim_review_plan.md`: lines 26-37, which are now lines 26-40, and line 14 (FeatureRange, changed as a consequence of Issue 6).

- **Issue 6 (ESCALATE):** After an Isaac Sim 6.1 docs check, the user first chose B + C with uv. The user then replaced the `--target` route with **a uv-created venv** from Kit's interpreter (`--system-site-packages`, `.kit-venv/`, hash-locked `requirements-kit.txt`), plus spike check C (Pixi/RoboStack rosbag2 MCAP on Windows). The install-target text in this report's replacement block is superseded by the applied text.
- **Issue 16 (N3):** discussed. The applied wording states NVIDIA's documented procedure and keeps the WSL failure as a short note.
- **Contests the user agreed with:** Issues 2 (build-file paths; known paths added, pin file named `requirements-kit.txt`), 9 and 10.
- **Accepted as proposed:** all other items. Item 12 was accepted with 40 pairs and no full-pass run.
- **Counts:** 13 accepted, 3 contested (agreed), 1 escalated and answered, 0 declined.
- **Not applied (outside this document):** the brief's "pure-Python" and "12.6 pairs/s" wording; Stage 8 N2-N4.
- **Not recorded:** a "use Fast DDS" remark during the session was not turned into a decision.

# Goldfish Annotated Review Report (Stage 9)

**Target:** `C:\rov-sim\rov_sim_review_plan.md` (lines 26-37, DetailedRange)
**Findings source:** `implementation_readiness_report.md` (Stage 9, round 1): B1-B3, M1-M10, N1-N3
**Summary:** 12 PROPOSE FIX, 3 CONTEST, 1 ESCALATE, 0 DECLINE

The fixes are written as **one replacement for lines 26-37**, given at the end of this report. **The item numbers 1-6 stay the same** and a new item 0 is added, so that references in lines 13-23 ("work item 2", "item 4", "items 3-5", "item 6") stay correct. A Stage 7 report already sits in this folder, so this report has its own file name.

## Prioritized Findings & AI Suggestions

### [Issue 1] [`egm-implementation-readiness`, `egm-codebase-details`] - Severity: Blocker (B1)
*   **Affected Scope:** [Lines 26-33](../rov_sim_review_plan.md#L26-L33) (Work to complete)
*   **Discrepancy Description:** No item builds the feature (writer module, flag, RGB copy and conversion, CameraInfo, stamps, pose and TF, staging, manifest, startup check, first bag).
*   **Rationale:** Someone who follows the list finishes without a writer.
*   ***AI Suggestion:*** PROPOSE FIX
*   ***Justification:*** The finding is valid, but its cause is that the document never says where the build work lives. Line 3 says "implementation has not started". Line 21 says items 3-5 start only after the spike passes. So implementation planning is meant to come after the spike, but the document never says so. Adding build items now would mean designing around results the spike doesn't have yet (for example, which writer path survives lines 16-19). The fix states the boundary instead: an implementation plan follows the spike, and it must cover brief decisions 1-7 and the first-bag criteria.
*   ***Proposed Edit:*** The new section heading and intro paragraph in the replacement block.

### [Issue 2] [`egm-implementation-readiness`, `egm-codebase-details`] - Severity: Blocker (B2)
*   **Affected Scope:** [Lines 26-33](../rov_sim_review_plan.md#L26-L33)
*   **Discrepancy Description:** No repository-relative file paths are given.
*   **Rationale:** Without them, writes can't be limited to an allowlist.
*   ***AI Suggestion:*** CONTEST, partly. A fix covers the paths that are known now.
*   ***Justification:*** The file boundary for *build* work belongs to the implementation plan that Issue 1 defers. The evidence is line 21 (the gate) plus the Issue 1 intro. For the remaining *pre-implementation* items, the paths that are already known are added: `rov_sim/application.py` (`status.json`), `scripts/runtime.ps1` (interpreter), `docs/REPRODUCIBILITY.md`, the README sections and `rov_ws` `src/rov_dataset_player/README.md`. Only the build paths are contested.
*   ***Proposed Edit:*** Paths written inline into items 1-6 in the replacement block.

### [Issue 3] [`egm-implementation-readiness`, `egm-codebase-details`] - Severity: Blocker (B3)
*   **Affected Scope:** [Lines 30-33](../rov_sim_review_plan.md#L30-L33)
*   **Discrepancy Description:** Items 3-6 hand design to the implementer. The epoch, flag name, layout, `/tf`, compression and chunk size are also undecided.
*   **Rationale:** Zero-Decision Rule.
*   ***AI Suggestion:*** PROPOSE FIX
*   ***Justification:*** This is valid as written. "Specify…" puts no owner and no deadline on the decision. The fix does two things:
    1. It decides what can be decided now with evidence the reviewers could read. Item 3 extends the existing `status.json` (verified at `application.py:74, 222, 380-386`). Item 4 defines a frame bundle as the seven contract topics sharing one stamp (brief decision 6). Item 5 names the benchmark command and baseline.
    2. It marks the rest as "decide in the implementation plan", tied to the post-spike gate.

    The epoch, flag name, `/tf` content and compression are listed as decisions the implementation plan must make. Compression depends on the spike's `lz4`/`zstandard` result, so it can't be chosen today.
*   ***Proposed Edit:*** Items 3-5 and the "must decide" list in the intro.

### [Issue 4] [`egm-style`, `egm-implementation-readiness`, `egm-codebase-details`] - Severity: Major (M1)
*   **Affected Scope:** [Line 37](../rov_sim_review_plan.md#L37) (Review status)
*   **Discrepancy Description:** The line is stale: the WSL report it cites is *resolved* and covers `zoom_out_report.md`. "First four major fixes" can't be traced. It repeats lines 3 and 9. It exposes a home directory.
*   ***AI Suggestion:*** PROPOSE FIX
*   ***Justification:*** Verified. Replace it with a self-contained line that links this review's folder by a repo-relative path. That also removes the personal path from a document meant for the repo.
*   ***Proposed Edit:*** The new "Review status" paragraph.

### [Issue 5] [all three] - Severity: Major (M2)
*   **Affected Scope:** [Line 29](../rov_sim_review_plan.md#L29)
*   **Discrepancy Description:** Item 2 lists only one of the three pass criteria. It gives no script location, no sample definition and no place to record the result.
*   ***AI Suggestion:*** PROPOSE FIX
*   ***Justification:*** The finding is valid. The item now cites lines 15-19 instead of paraphrasing them. It follows the brief ("scratch script inside Kit", not committed), defines a minimal sample, and records the result in a new section of this document.
*   ***Proposed Edit:*** Item 2 in the replacement block.

### [Issue 6] [all three] - Severity: Major (M3)
*   **Affected Scope:** [Line 28](../rov_sim_review_plan.md#L28), and lines 13-14 (FeatureRange)
*   **Discrepancy Description:** Item 1 leaves out the `lz4`/`zstandard` check, the uncompressed test, the pin file, the startup check and its failure behaviour, and gives no command.
*   ***AI Suggestion:*** ESCALATE (the install target), with a fix for the rest.
*   ***Justification:*** The command and deliverables can be fixed. Stage 8 M1 is still undecided, though: *where* to install. Kit's site-packages is what line 14 says now, and it breaks `README.md:33-34, 63, 231` (verified). The alternative is `pip install --target` into a gitignored repo directory, put on `sys.path` only when the flag is on. That is your call, and it also changes line 14, which is outside this range. The failure behaviour of the startup check is proposed as "abort with a message naming the expected and found versions", because a silent version mismatch would produce bags that look valid.
*   ***Proposed Edit:*** Item 1 in the replacement block, with `<<ANSWER NEEDED>>` for the target. If you choose `--target`, line 14 also changes (shown under the block).

### [Issue 7] [all three] - Severity: Major (M4)
*   **Affected Scope:** [Line 31](../rov_sim_review_plan.md#L31)
*   **Discrepancy Description:** Item 4 leaves out the manifest decision from line 23. The consumers are vague.
*   ***AI Suggestion:*** PROPOSE FIX
*   ***Justification:*** The finding is valid. The item now names `bag_to_capture`, `rov_slam` evaluation and `rov_mapping` replay, and carries the manifest decision. Consumer *commands* aren't added: no reviewer could read the `rov_ws` consumer source, and I haven't either.
*   ***Proposed Edit:*** Item 4 in the replacement block.

### [Issue 8] [`egm-codebase-details`] - Severity: Major (M5)
*   **Affected Scope:** [Line 30](../rov_sim_review_plan.md#L30)
*   **Discrepancy Description:** Item 3 ignores the existing `status.json` pattern.
*   ***AI Suggestion:*** PROPOSE FIX
*   ***Justification:*** Verified. Extending the existing mechanism avoids a second parallel one.
*   ***Proposed Edit:*** Item 3 in the replacement block.

### [Issue 9] [`egm-implementation-readiness`] - Severity: Major (M6)
*   **Affected Scope:** [Lines 26-33](../rov_sim_review_plan.md#L26-L33)
*   **Discrepancy Description:** Collisions with `--record`, `--benchmark` and `--preview-mp4`, the validation location, and the per-pass directory layout are not addressed.
*   ***AI Suggestion:*** CONTEST
*   ***Justification:*** These are build-design questions for the deferred implementation plan (Issue 1; line 21). They are added to the intro's "must decide" list so they aren't lost. They are not answered here.
*   ***Proposed Edit:*** Covered by the intro list.

### [Issue 10] [`egm-implementation-readiness`] - Severity: Major (M7)
*   **Affected Scope:** [Lines 26-33](../rov_sim_review_plan.md#L26-L33)
*   **Discrepancy Description:** No test plan.
*   ***AI Suggestion:*** CONTEST
*   ***Justification:*** Same reason as Issue 9. The test plan belongs to the implementation plan, and the intro requires it to include the brief's tests (the known-colour pixel, flag-off byte-identical behaviour, first-bag criteria) and the reviewer's edge cases.
*   ***Proposed Edit:*** Covered by the intro list.

### [Issue 11] [`egm-implementation-readiness`, `egm-codebase-details`] - Severity: Major (M8)
*   **Affected Scope:** [Lines 26-28](../rov_sim_review_plan.md#L26-L28)
*   **Discrepancy Description:** Phase 0 is missing (commit the restructure, tag it, create the branches).
*   ***AI Suggestion:*** PROPOSE FIX
*   ***Justification:*** Valid. Git status shows the restructure uncommitted. Without that commit there's no baseline for "reversible in git" or for checking that behaviour with the flag off is byte-identical. The branch name `docs/isaac-mcap` for `rov_ws` is a proposal; change it if you like.
*   ***Proposed Edit:*** Item 0 in the replacement block.

### [Issue 12] [`egm-codebase-details`, `egm-style`] - Severity: Major (M9)
*   **Affected Scope:** [Line 32](../rov_sim_review_plan.md#L32)
*   **Discrepancy Description:** No benchmark command and no baseline. The two throughput figures disagree (12.8005 vs. 12.6). "Target setup" and "intended runs" are undefined.
*   ***AI Suggestion:*** PROPOSE FIX
*   ***Justification:*** Verified. `docs/REPRODUCIBILITY.md:62` is the recorded, validated figure, so it becomes the baseline. The brief's 12.6 is noted as out of date, but the brief itself isn't edited because it's outside this document.
*   ***Proposed Edit:*** Item 5 in the replacement block.

### [Issue 13] [all three] - Severity: Major (M10)
*   **Affected Scope:** [Line 33](../rov_sim_review_plan.md#L33)
*   **Discrepancy Description:** No file list. The `rov_ws` branch from line 24 isn't mentioned.
*   ***AI Suggestion:*** PROPOSE FIX
*   ***Justification:*** The reviewers already listed the README sections and doc files. The fix also takes Stage 8 N1's limit on the `rov_ws` scope.
*   ***Proposed Edit:*** Item 6 in the replacement block.

### [Issue 14] [`egm-style`] - Severity: Nit (N1)
*   **Affected Scope:** [Line 28](../rov_sim_review_plan.md#L28)
*   ***AI Suggestion:*** PROPOSE FIX. Use "Kit's bundled Python", matching lines 13-16.

### [Issue 15] [`egm-style`] - Severity: Nit (N2)
*   **Affected Scope:** [Line 33](../rov_sim_review_plan.md#L33)
*   ***AI Suggestion:*** PROPOSE FIX. Fixed by the item 6 rewrite.

### [Issue 16] [`egm-style`] - Severity: Nit (N3)
*   **Affected Scope:** [Line 28](../rov_sim_review_plan.md#L28)
*   ***AI Suggestion:*** PROPOSE FIX. The instruction now comes before the history.

---

## Proposed replacement for lines 26-37

```markdown
## Remaining work before implementation planning

These items settle what the spike and measurements must decide. They are not the implementation plan. That plan, with build items, exact file paths and a test plan, is written after item 2 passes, because several of its answers depend on the spike (see the gate above). It must cover brief decisions 1-7 and the first-bag criteria (brief staging step 3), and decide: the flag name and its interaction with `--record`, `--benchmark` and `--preview-mp4`; where non-`camera-sensor` backends are rejected; the per-pass directory layout inside the run directory; the stamp epoch; `/tf` content; chunk compression and size; and the tests, including the brief's known-colour pixel check, flag-off byte-identical behaviour, and edge cases (empty pass, disk full, crash before rename, missing `.msg`, version mismatch).

0. **Baseline.** Commit the pending `rov_sim/` restructure alone on `main`, excluding the report `.md` files and `.idea/`, and tag it. Create `feature/isaac-mcap` in rov-sim and `docs/isaac-mcap` in `rov_ws` (brief staging step 1). Git reversibility and flag-off byte-identical behaviour are measured against this tag.
1. **Install.** Run from native Windows with Kit's bundled Python (`python.bat`, found by `scripts/runtime.ps1`); installing from WSL fails with an untrusted mount-point error. Install `mcap` with its `lz4` and `zstandard` dependencies <<ANSWER NEEDED: into Kit's site-packages, or with `pip install --target` into a gitignored repo directory>>, and check whether uncompressed writing works without `lz4` and `zstandard`. Record the resolved versions in the pin file from the pinning decision above. The startup check aborts with a message naming the expected and found versions.
2. **Spike.** In a scratch script run with Kit's bundled Python (not committed): check `rclpy.serialization.serialize_message`, check whether Jazzy `share/` contains the `.msg` files, and write a sample containing at least one message on each of the seven contract topics at full image size. Apply the pass criteria and failure branches in the route decision above. Record the outcome, the branch taken and the resolved versions in a "Spike result" section of this document.
3. **Output finalization.** Extend the existing run status in `rov_sim/application.py` (`status.json`: `running_<pass>`, `complete`, `failed`, `interrupted`) rather than adding a second mechanism. The implementation plan decides the staging directory name, whether `reindex` runs before or after the rename, and the recovery steps for a failed pass.
4. **Completeness and consumers.** A frame bundle is the seven contract topics sharing one stamp (brief decision 6). The implementation plan sets the expected per-topic counts for N frames, and settles the manifest as decided above: justify it against the bag's own message counts, or remove it. `bag_to_capture` and `rov_slam` evaluation acceptance are first-bag criteria. Also test `rov_mapping` replay, or record in the brief that the compatibility claim for it is deferred.
5. **Throughput and disk.** Run `--benchmark` with the MCAP flag on over 40 CameraSensor pairs and compare with `docs/REPRODUCIBILITY.md` (12.8005 pairs/s; the brief's 12.6 figure is out of date). The benchmark already reports per-frame `recording_ms` and `iteration_total_ms`. Record bytes per frame. The implementation plan decides disk-full behaviour.
6. **Documentation** (scope as decided above). In rov-sim: `README.md` (recording command, output layout, module table, benchmark-recording note), `docs/REPRODUCIBILITY.md` (install step) and `docs/VALIDATION.md`. In the `rov_ws` docs branch: `src/rov_dataset_player/README.md`, limited to statements Isaac bags break (map rebasing, `initial_left_camera_optical_frame`, the nominal calibration file, HoloOcean metadata keys). Identifying the sections can start now; the updates land with the implementation, and documented commands are checked against the implemented behaviour.

## Review status

Reviewed with the EGM review pipeline on 2026-11-16. Reports and resolutions are in [egm_review_rov_sim_review_plan/](egm_review_rov_sim_review_plan/). Still open: the spike (item 2) and the implementation plan that follows it.
```

**If you choose `--target` for Issue 6,** line 14 (FeatureRange, outside this range) also changes to:

```markdown
- **Pinning:** Kit's bundled Python stays unmodified (README rule). Install `mcap`, `lz4` and `zstandard` with `pip install --target` into a gitignored repo directory from a pinned requirements file in this repo, put that directory on `sys.path` only when the MCAP flag is on, check versions at startup, update the README lines that say no packages are installed, and add the install step to `docs/REPRODUCIBILITY.md`.
```

The spike would also check that `lz4` and `zstandard` load from that directory in Kit's interpreter.

## Not addressed (outside this document)

- The brief's "pure-Python" wording (brief 105) and the "12.6 pairs/s" figure (brief 111).
- Stage 8 N2-N4 (line 11 size argument, line 18 candidates, title wording): lines 1-25 are outside this range.
