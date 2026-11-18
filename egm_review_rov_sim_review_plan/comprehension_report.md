# Stage 6: Comprehension Test Report

- **Target:** `C:\rov-sim\rov_sim_review_plan.md`. FeatureRange is lines 1-9; DetailedRange is lines 10-21.
- **Reviewer:** `egm-comprehension`, review mode. The reviewer read the document alone, with no Goldfish context and no standard, as Stage 6 requires.
- **Date:** 2026-11-16

> **Note for the author:** This test checks whether the plan makes sense on its own. The Stage 5 re-audit found the plan coherent when read *with* `concepts_brief.md`. The Blocker below means that a reader without the brief cannot rebuild what the feature is. If you intend the plan only as a companion to the brief, a short purpose paragraph and a short glossary (frame bundle, mapping replay, the named consumers, the route, why reindexing is needed) would resolve most of findings 1 and 3-6.

## FeatureRange (lines 1-9)

### What this proposes
The plan seems to add an MCAP writer to the project. MCAP is a robotics log file format. It would write the output using the `mcap` Python package, running inside Isaac Sim's bundled Python. The package version gets pinned only after it is proven to work in that runtime. Existing documentation must be updated in the same task as the implementation. The document says it is a record of review decisions and open validation work, not a claim that anything is built.

### How the existing system works, per this document
I cannot paraphrase this. Lines 1-9 never say what is being recorded, what the current output format or recording path is, or why MCAP is wanted. From the setting I can only infer that there is a simulator (Isaac Sim with its own Python) that produces some output.

## DetailedRange (lines 10-21)

### What this proposes
- Install `mcap` from native Windows, because a WSL attempt failed.
- Run a "spike":
  - check ROS 2 Jazzy `rclpy` serialization in the bundled runtime
  - find ROS message schemas
  - write a sample MCAP file
  - confirm that `ros2 bag reindex` in WSL accepts it
- Specify crash and recovery semantics around reindexing and a "final output rename".
- Define completeness checks and consumer compatibility tests.
- Measure throughput and disk use, and define disk-full behaviour.
- Update the docs.

The review status section says some fixes were accepted and the user chose `mcap`. Installation and interoperability are still unverified, and the review is unfinished.

### How the existing system works, per this document
From hints only: Isaac Sim runs on native Windows, and a ROS 2 Jazzy toolchain is available under WSL. Some recording workflow already exists, and it ends with an output rename step. Output is organized in "frame bundles", and several downstream "consumers" read it, including "mapping replay". I cannot say how any of these work or connect from this document alone.

## Findings

**1. Blocker: the feature and the existing system are never stated (whole document, especially lines 1-9).**
No line says what data is recorded, from where, for whom, or why MCAP replaces or adds to the current output. The existing recording system is not described, so the reviewer could not write a paraphrase of the existing system. All context is left to `concepts_brief.md` and `zoom_out_report.md` (line 3).

**2. Major: "the first four major fixes above" can't be traced (line 21).**
The only list above is "Work to complete". If the phrase means items 1-4, line 21 conflicts with those items still being listed as unfinished. If it means review findings, those findings aren't listed here.

**3. Major: "the planned spike" and "the route" are undefined (line 13).**
The document doesn't say which route this is, what the alternative is, or what result triggers a fallback.

**4. Major: why reindexing is needed and what the "final output rename" is are not explained (line 14).**
The document doesn't say whether the writer leaves out the index or summary, or whether reindexing is for crash recovery. It also doesn't say what gets renamed, from what temporary name, or why. Without both, the ordering question in item 3 can't be understood.

**5. Major: project-specific terms are undefined (line 15).**
- "Frame bundle": which frames, from which sensors.
- "Mapping replay": a tool or workflow, but which one is not stated.
- "The other named consumers": named somewhere else, not here.

So the scope of the compatibility claim is unknown.

**6. Major: "target setup" and "intended runs" are undefined (line 16).**
Hardware, OS, run duration, sensor set and rates are not stated, so the throughput and disk measurements have no baseline.

**7. Nit: the install context is assumed (line 12).**
The document doesn't explain why the install was attempted from WSL, or how to locate the bundled interpreter on Windows.

**8. Nit: "this folder" vs. the WSL path (lines 3, 21).**
Line 3 says the sources are "in this folder", but line 21 points to `/home/lcarv/rov_ws/...`. A Windows reader can't open that path, and "this folder" is never identified.

**9. Nit: "all affected existing documentation" is vague and repeated (lines 8, 17).**
No documents are named, so a reader can't tell when this work is done.

**10. Nit: the "writer-alternatives finding" is not summarized (line 21).**
The alternatives that were rejected aren't stated, so the reason for choosing `mcap` can't be followed from this document.

## Overlap with Stage 5 (for the resolver)

| Stage 6 finding | Stage 5 re-audit item |
|---|---|
| 1 (feature not stated) | S10 (add a purpose sentence), and first-pass B1 |
| 2, 8, 10 (traceability of the review status) | S3 |
| 3 (route / fallback undefined) | S1 |
| 4 (reindex / rename) | S5, S2(b) |
| 5 (frame bundle / consumers) | S6, S2(a) |
| 6 (target setup / runs) | S7 |
| 9 (documentation scope) | S8, S9 |
