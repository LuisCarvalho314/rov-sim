# Stage 5: Initial Zoom Out Review

Target: [concepts_brief.md](/mnt/c/rov-sim/concepts_brief.md) (full document)

## Findings

### Major — Keep option C conditional on the spike

**Affected scope:** [Remaining risks for option C](/mnt/c/rov-sim/concepts_brief.md#remaining-risks-for-option-c); [Key Decisions & Staging for Next Steps](/mnt/c/rov-sim/concepts_brief.md#key-decisions--staging-for-next-steps)

The selected route still depends on unresolved basics: whether Kit’s bundled `rclpy` can serialize the messages, where the MCAP schemas come from, and whether WSL `ros2 bag reindex` accepts the output. The brief schedules a spike before implementation. Keep option C conditional on that spike; otherwise the detailed bag contract and milestones may be built around an unverified writer path. Specify whether a failed check changes the writer approach or blocks implementation. The chosen container library is the `mcap` package; validate its installation and interoperability before relying on it.

### Major — Specify output finalization and recovery

The brief proposes staging and renaming output and separately generating required metadata with WSL reindexing. Specify when reindexing occurs relative to the final rename, how incomplete or failed output is identified, and how to recover it. See [output format](/mnt/c/rov-sim/concepts_brief.md#new-practical-finding-consumers-open-a-rosbag2-directory-not-a-bare-mcap) and [remaining risks](/mnt/c/rov-sim/concepts_brief.md#remaining-risks-for-option-c).

### Major — Test consumer compatibility and frame completeness

The brief promises compatibility with mapping replay alongside other readers, while its first-bag criteria name two readers and explicitly count left images. Define per-topic and frame-bundle completeness checks and test mapping replay, or explicitly defer that compatibility claim. See [ideal final result](/mnt/c/rov-sim/concepts_brief.md#ideal-final-result) and [staging](/mnt/c/rov-sim/concepts_brief.md#key-decisions--staging-for-next-steps).

### Major — Establish performance and capacity limits

The brief estimates raw image size but has not measured writer throughput. Measure throughput and disk use on the target setup, define acceptable limits for intended runs, and specify disk-full behavior. See [remaining risks](/mnt/c/rov-sim/concepts_brief.md#remaining-risks-for-option-c).

### Major — Plan documentation updates with implementation

The brief leaves the location of documentation updates open. Identify the existing documentation affected by the capture workflow and update it in the implementation task; do not defer that work. See [staging and open questions](/mnt/c/rov-sim/concepts_brief.md#key-decisions--staging-for-next-steps).

### Nit — Explain the frame manifest’s distinct purpose

**Affected scope:** [Remaining risks for option C](/mnt/c/rov-sim/concepts_brief.md#remaining-risks-for-option-c); [Goals vs. Non-Goals](/mnt/c/rov-sim/concepts_brief.md#goals-vs-non-goals)

The design adds a frame manifest and completeness check alongside MCAP records and downstream validation, but does not state which failure the extra artifact catches. Repository search found no MCAP utility, though it found generic JSON-manifest patterns. Define what the completeness check compares and which failure it detects. Then decide whether the manifest provides value beyond the bag and downstream validation.

### Nit — Keep metadata generation outside the simulator initially

**Affected scope:** [Consumers open a rosbag2 directory](/mnt/c/rov-sim/concepts_brief.md#new-practical-finding-consumers-open-a-rosbag2-directory-not-a-bare-mcap)

Writing `metadata.yaml` in the simulator adds another format-specific responsibility. Running `ros2 bag reindex` adds a manual WSL step. The brief identifies reindex as the simpler first step. State the decision rule for adding simulator-side metadata generation if the extra WSL reindex command becomes a material obstacle.

## Evidence limits

The original reviewer read the target brief, both brainstorm synthesis reports, and the repository README. Repository search found no MCAP or rosbag writer in `rov_sim`, `tests`, or `configs`; it found general JSON-manifest patterns. The requested WSL `rov_ws` consumer files were inaccessible to the original reviewer; claims about the bag consumers’ contract were not independently verified during that stage. The `mcap` package installation attempt from WSL failed with a Windows untrusted mount-point error; installation and interoperability remain unverified.
