# Stage 5: Initial Zoom Out Report

- **Target:** `C:\rov-sim\rov_sim_review_plan.md` (21 lines, whole file)
- **Split:** FeatureRange 1..9, DetailedRange 10..21
- **Goldfish context:** none (user declined). Reviewers saw only the plan.
- **Reviewers:** `egm-zoom-out` (judged against the zoom-out standard), `egm-inventive-catalyst` (no standard; review mode, so its ratings are advisory)
- **Date:** 2026-11-16

## Combined summary (findings from both reviewers, duplicates merged)

| # | Severity | Finding | Lines | Source |
|---|----------|---------|-------|--------|
| S1 | 🔴 Blocker | No stated objective, consumers or success criterion. The document hands its context to `concepts_brief.md` / `zoom_out_report.md`, and "named consumers", "mapping replay", "frame-bundle" and "intended runs" are never defined. | 1-3, 15, 16 | Zoom-out B1 |
| S2 | 🔴 Blocker | This is a task tracker, not a design. Where the writer runs, the data path, and how it relates to the existing recorder are never described, so architecture can't be reviewed. | whole file | Zoom-out B2 |
| S3 | 🟡 Major | The "decision" to use `mcap` depends on validation that hasn't happened (and installing it already failed once), and there is no fallback. | 7, 12, 13 | Zoom-out M1, Catalyst M1 |
| S4 | 🟡 Major | Items 3-6 are planned in detail before the go/no-go gate (items 1-2) that could make them unnecessary. | 12-17 | Zoom-out M2 |
| S5 | 🟡 Major | Possible reinvention: raw `mcap` writer plus WSL `ros2 bag reindex` brings in rename and recovery complexity. rosbag2-native options (MCAP storage plugin, recording outside Isaac Sim through the bridge, writing `metadata.yaml` directly) aren't recorded as considered. | 7, 13, 14, 21 | Zoom-out M3, Catalyst M3 |
| S6 | 🟡 Major | Coupling to Isaac Sim's bundled Python and `rclpy`. Proposals: vendor the pinned `mcap` package, check in the `.msg` schemas and serialize with a pure-Python CDR encoder, or move writing to a separate process. | 7, 12, 13 | Catalyst M1, M2 |
| S7 | 🟡 Major | Reindex/rename ordering: write `*.mcap.partial` with chunking, finalize the summary, then rename atomically. A leftover `.partial` file is then the failure marker. | 14 | Catalyst M3 |
| S8 | 🟡 Major | Disk-full handling is only something to measure. Proposals: check free space before the run, split output into size/time segments, close cleanly at a low-water mark. | 16 | Catalyst M4 (Zoom-out N3 argues the opposite: possibly YAGNI) |
| S9 | 🟡 Major | The "Review status" section contradicts the list ("first four major fixes" against six work items) and points at a WSL report path that differs from `C:\rov-sim\goldfish_review_report.md`. | 21 | Zoom-out M4, Catalyst N3 |
| S10 | 🟢 Nit | The writer should record per-topic counts and bundle IDs while it writes, so the after-the-fact check only compares. | 15 | Catalyst N1 |
| S11 | 🟢 Nit | The documentation requirement appears twice. Keep the documented commands in one tested script. | 8, 17 | Zoom-out N2, Catalyst N2 |
| S12 | 🟢 Nit | Install troubleshooting (WSL mount-point error) doesn't belong at plan level. | 12 | Zoom-out N1 |
| S13 | 🟢 Nit | The title doesn't name the system or the goal. | 1 | Zoom-out N4 |

**Tension between reviewers:** On disk-full handling (S8), the catalyst wants active mitigation (segmenting, low-water close), while zoom-out says this may be YAGNI until run sizes are known. Either way, the answer depends on S1: without stated run sizes, neither position can be judged.

**Unverified reviewer claims:** The catalyst says `mcap` is pure Python, that `mcap-ros2-support` / `rosbags` can serialize CDR without `rclpy`, and that rosbag2 handles multi-file bags through `metadata.yaml`. Nobody checked these during this stage. Verify them before relying on them.

**Caveat:** Both blockers reflect that reviewers had no context. The plan says its context lives in other files, and you chose not to supply them. If this plan is only meant as a checklist next to `concepts_brief.md`, S1 and S2 come down to "say so and link the brief". The other findings still apply.

---

## Reviewer report: egm-zoom-out

**Verdict: FAIL (Context Sufficiency, Standard section 0).** Review mode.

### Blocker

**B1. The document never says what it is for or why (lines 1-3, 15, 16).** A new reader can't tell what is being recorded to MCAP, by which component, for which consumer, or why MCAP is needed instead of the current output. Line 3 hands all of that context to `concepts_brief.md` and `zoom_out_report.md`. Line 15 mentions "the other named consumers", but none are named. "Mapping replay" and "frame-bundle" are never defined. "Intended runs" (line 16) has no stated size, so "acceptable limits" can't be judged. *Fix:* add a 3-5 line objective covering the problem, the consumers and the success criterion.

**B2. This is a status tracker, not a design (whole file).** It never describes where the writer runs (inside Isaac Sim or in post-processing), what the data path is (sim, then serialization, then writer, then rename/reindex), or how it relates to the existing recording module. *Fix:* reframe as a short design (objective, chosen pipeline, alternatives considered, open validation gates) and move task tracking to an appendix or a separate file.

### Major

**M1. The decision is conditional and has no fallback (lines 7, 13).** It is committed "subject to" validation, the route is "kept conditional", and installation has already failed once (line 12). Nothing says what happens if the spike fails. *Fix:* treat it as a hypothesis with an explicit fallback, or record the rejected alternatives.

**M2. Detailed work comes before the gate (lines 12-17).** Items 3-6 assume items 1-2 succeed. *Fix:* make items 1-2 an explicit go/no-go gate and keep items 3-6 to one line each until it passes.

**M3. Possible reinvention (lines 7, 13, 14).** The custom writer plus reindex creates the lifecycle problem described in line 14. The rosbag2 MCAP storage plugin (`ros2 bag record` / `rosbag2_py`), recording outside Isaac Sim through the bridge, and writing `metadata.yaml` directly aren't recorded as evaluated. Line 21 mentions a "writer-alternatives finding" but doesn't give its outcome. *Fix:* state the alternatives and why they were rejected.

**M4. Review status is inconsistent (line 21).** "First four major fixes" doesn't match anything in the list above. The WSL path conflicts with the `C:/rov-sim` copy, and line 3 says its sources are "in this folder". *Fix:* delete the section, or use item numbers and one canonical path.

### Nit

- **N1 (line 12):** Move the install troubleshooting to a log. The plan only needs "install and pin `mcap` (gate)".
- **N2 (lines 8, 17):** The documentation requirement is stated twice.
- **N3 (line 16):** Disk-full behaviour may be YAGNI without stated run sizes. A pre-run free-space check may be enough.
- **N4 (line 1):** The title doesn't name the system or the goal.

---

## Reviewer report: egm-inventive-catalyst

**Verdict:** The plan contains compromises it hasn't examined. Most come from one assumption: the writer has to run inside Isaac Sim's bundled Python and depend on its ROS runtime. (Review mode: advisory ratings only, so no Blockers.)

### Major

**M1. The writer is tied to bundled Python (lines 7, 12, 13).** Everything waits on a pip install that has already failed. *Resolution:* vendor a pinned `mcap` copy or wheel on `sys.path`, so the version is pinned at commit time and item 1 becomes a smoke test. *Alternative:* a separate writer process with its own virtualenv or native ROS 2. *Liabilities:* vendoring means tracking upstream fixes and keeping the license notice. A separate process adds IPC bandwidth for large stereo frames, a second process to supervise, and the risk that the writer dies while the simulation keeps running.

**M2. Serializing with bundled `rclpy` ties output to the distro (line 13).** *Resolution:* check in the needed `.msg` schemas (e.g. `sensor_msgs/Image`, `CameraInfo`, `tf2_msgs/TFMessage`) and use a pure-Python CDR encoder (`mcap-ros2-support` or `rosbags`) behind a serializer interface. The spike then shrinks to confirming that reindex and the consumers accept the file. *Liabilities:* schemas can drift from Jazzy, and the second serialization path needs round-trip tests.

**M3. Reindex after rename treats a valid file and crash safety as a trade-off (line 14).** *Resolution:* write `<name>.mcap.partial` with chunking, write the summary and index on close, then rename atomically. A leftover `.partial` file is the failure marker, and recovery only ever touches `.partial` files. Optionally write `metadata.yaml` at close so reindex only verifies. *Liabilities:* chunking uses memory, a crash can lose one chunk, and a hand-written `metadata.yaml` can drift between distros.

**M4. Disk-full handling has no active response (line 16).** *Resolution:* check free space before the run (bytes/s × duration + margin), split output into size/time segments, and optionally watch free space during the run and close at a low-water mark. *Liabilities:* consumers (including mapping replay) must handle multi-file bags, the estimate may be wrong under compression, and dropping topics adaptively hurts reproducibility.

### Nit

- **N1 (line 15):** The writer should assign bundle/sequence IDs (tied to sim ticks) and record per-topic counts in an MCAP metadata record, so the after-the-fact check only compares.
- **N2 (lines 8, 17):** Keep the documented commands in a single script under `scripts/` that a test runs, and have the docs quote it.
- **N3 (line 21):** The review-status bookkeeping is inconsistent (same as zoom-out M4).

### Ideal final result

The recorder doesn't depend on what is installed in Isaac Sim's Python. A run either produces a finalized file or leaves a recoverable `.partial`. Running out of disk loses at most one segment. The writer records its own completeness data.
