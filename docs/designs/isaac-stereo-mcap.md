# Isaac Sim stereo ground truth to MCAP

*   **Author:** L.Carvalho
*   **Status:** Proposed. Revised 2026-11-17: the writer is `rosbag2_py.SequentialWriter`
    in-process, chosen after measured evidence.
*   **Date:** 2026-11-17
*   **Sources:**
    *   [concepts brief](../../concepts_brief.md), the governing spec;
    *   [review decisions and validation plan](../../rov_sim_review_plan.md), which amends the
        brief, including its [Spike result](../../rov_sim_review_plan.md#spike-result);
    *   [native ROS 2 recording research](../../native_ros2_recording_research.md): measured bridge,
        recorder and `SequentialWriter` results.

--------------------------------------------------------------------------------

## Overview

rov-sim renders a stereo pair from Isaac Sim 6.1 (`6.1.0-rc.26`) on Windows. The ROS 2 Jazzy
tools in `rov_ws` (WSL Ubuntu) that build maps, run SLAM evaluation and turn bags back into
capture folders all read rosbag2 MCAP directories. Today the only bags they have come from
HoloOcean, which the project is leaving.

This design adds an opt-in recording flag to the existing rov-sim capture loop. With the flag on,
after each frame the loop has already checked as fresh, rov-sim:

1.  builds seven ROS 2 messages;
2.  serializes them with ROS 2 Jazzy's `rclpy`;
3.  writes them with **ROS 2's own bag writer, `rosbag2_py.SequentialWriter`** (MCAP storage),
    inside Isaac Sim's process.

The bag library comes from NVIDIA's supported native Windows ROS 2 installation, the Pixi
workspace `isaac-sim/IsaacSim-ros_workspaces`. rosbag2 writes the MCAP file, `metadata.yaml` and
per-topic QoS itself. After each pass, rov-sim reopens the bag with rosbag2's reader, checks it,
and marks the pass complete. The `rov_ws` tools read the result from `/mnt/c/...` with no extra
step and no code changes.

The route is measured, not assumed
([research](../../native_ros2_recording_research.md)):

*   Bags written this way inside a running `SimulationApp` passed every contract check in WSL.
*   `bag_to_capture` read one unchanged.
*   The standard alternative, Isaac's ROS 2 bridge with `ros2 bag record`, failed measured
    requirements.

## The Problem

There is no way today to get rov-sim data into `rov_ws`. The existing paths fail for measured
or source-verified reasons:

*   **Isaac's ROS 2 bridge plus `ros2 bag record` gives bags the consumers reject.** Measured on
    this machine, 2026-11-17:
    *   `bag_to_capture` rejected the bag: there is no ground-truth pose or `/tf_static`
        publisher.
    *   Log time never equals the header stamp: wall-clock arrival time by default; with
        `--use-sim-time`, one to two frames late, and different for the left and right images of
        one frame.
    *   One frame was lost inside each 300-frame stream.
    *   Images are `rgb8`, and cx/cy follow the pixel-corner convention.
    *   The timeline must play, which rov-sim's validated loop does not do.
*   **rov-sim moves the ROV kinematically.** Each frame's pose is set from a scripted trajectory,
    with the timeline held still while both cameras render. That gives exact ground truth and
    identical "before" and "after" passes. Isaac's bridge needs physics stepping and a playing
    timeline to produce timestamps at all.
*   **The HoloOcean contract carries conventions that are wrong for Isaac.** The nominal
    calibration's fx = 376 against Isaac's ≈ 537.14 is not caught by consumer checks. Rebasing
    `map` per pass would separate the change-detection passes.

Writing the bag from the loop that already knows each frame's images, poses and calibration
avoids all of this. Nothing is in transit, so no frames are lost, and every timestamp is set once.

Three constraints shape the design:

*   **The validated surface must not move.** With the flag off, rov-sim behaves exactly as at tag
    `baseline/isaac-mcap`, with an identical environment. With the flag on, the existing
    freshness checks still pass.
*   **Kit stays as NVIDIA ships it.** Kit's Python and `python.bat` are not modified. The
    interpreter keeps running as `kit.exe`. Kit's NumPy 2.3.1 stays the one loaded.
*   **Every change is reversible in git.** The Pixi workspace lives outside the repository,
    pinned by tag and lock hash. `rov_ws` changes are docs only, on their own branch.

## Goals

1.  **First bag.** `--experiment change_detection` with the `camera-sensor` backend and the new
    flag, for one 30-frame "before" pass, produces one rosbag2 MCAP directory (MCAP file plus
    `metadata.yaml`). It meets every first-bag criterion in the brief's staging step 3, with no
    WSL step and the stamp check made against `status.json` and the stamp formula:
    *   `/stereo/left/image_raw` has exactly 30 messages, and all seven contract topics are
        present on every stamp.
    *   Stamps are non-zero, strictly increasing integers: `epoch + i·10⁹ // fps` for
        `i < completed_frames`.
    *   Log time = publish time = header stamp on every message.
    *   Images are `bgr8`; a known-colour pixel survives the RGB to BGR conversion. Frame ids,
        sizes and `/tf_static` follow the brief's "Keep" table.
    *   CameraInfo matches `stereo_calibration.json`: cx = W/2 − 0.5, cy = H/2 − 0.5, D = 0,
        R = I, and right P[0,3] = −fx·0.38.
    *   `/tf_static` is recorded as reliable and transient-local.
    *   `bag_to_capture` and `rov_slam` evaluation accept the bag without code changes.
2.  **Geometry cross-check.** The same pass, run with `--stereo-diagnostics`, decodes back to the
    geometry the simulator validates:
    *   the diagnostic target, reprojected with the bag's pose and K, lands on the measured
        pixel;
    *   `/tf_static` is +0.38 m along the left optical x axis, with no rotation;
    *   the sign of right P[0,3] gives the measured disparity.
3.  **Flag off is unchanged.** Against tag `baseline/isaac-mcap`, with the flag off:
    *   the deterministic outputs are byte-identical: CLI and config validation results,
        recorded poses, the output file layout, and `status.json` apart from times and
        durations;
    *   `launch.ps1` changes no environment variable;
    *   no `rosbag2_py`, Pixi or bag-writer module is imported;
    *   all existing tests and validation checks pass.
4.  **Dependencies load the decided way, and only for recording runs.**
    *   `launch.ps1` appends the Pixi environment's `Library\bin` to `PATH` and sets
        `AMENT_PREFIX_PATH`, process-local and only with the flag. `ROS_DISTRO` stays unset, so
        Kit keeps its bundled ROS 2 libraries first.
    *   A bootstrap module appends the Pixi `site-packages` to the **end** of `sys.path`. It
        verifies that NumPy is still Kit's 2.3.1, the same module object, and that `rosbag2_py`
        and `rclpy` resolve from the pinned Pixi environment.
    *   A mismatch aborts startup with a message that names what was expected and what was
        found.
    *   The bootstrap is separate from the writer.
5.  **The launcher keeps Kit's behaviour.** A targeted regression test shows that, with the
    recording overlay applied:
    *   the interpreter still runs as `kit.exe`;
    *   rendering still produces fresh, valid stereo frames;
    *   shutdown still returns the expected exit codes (success, failure, and the native crash
        code that the benchmark supervisor reports);
    *   with the flag off, the environment `python.bat` receives is identical to the baseline's.
6.  **A pass's state can be trusted.** `status.json` records each pass as `writing`, `failed`,
    `check_failed` or `complete`. A pass is `complete` only after the bag is closed, moved to its
    final name, reopened and checked. Consumers read only complete passes.
7.  **Cost is measured.** With the flag on, `--benchmark` over 40 CameraSensor pairs reports
    throughput, per-frame `recording_ms` and bytes per frame. It runs once with uncompressed MCAP
    storage and once with `zstd_fast`. The numbers are compared with the 40-pair baseline of
    12.8005 pairs/s in `docs/REPRODUCIBILITY.md`, and the default follows from them.
8.  **Docs match behaviour.** The rov-sim docs and the `rov_ws` `docs/isaac-mcap` branch describe
    the implemented command, output layout, the Pixi workspace install and pin, and the
    recording overlay.

## Non-Goals

*   **Depth.** It is the next milestone, together with planar 32FC1 and the 1 mm tank-wall check.
*   **Underwater-processed images, a live preview, lidar, labels and `/clock`.**
*   **Backends other than `camera-sensor`.** The flag is rejected with any other backend.
*   **Isaac's ROS 2 bridge, DDS or Zenoh transport, and `ros2 bag record`.** Measured and rejected.
*   **Running Kit inside the full Pixi activation (`pixi run`).** Measured: Pixi's NumPy shadowed
    Kit's, and Isaac's torch failed with `WinError 1114`. Only the minimal overlay is used.
*   **Physics or dynamics for the ROV.** The kinematic, scripted trajectory stays.
*   **A frame manifest.** Removed by the review plan. Completeness comes from `status.json`, the
    stamp formula and the bag itself.
*   **HoloOcean conventions:** map rebasing, `initial_left_camera_optical_frame`, the nominal
    calibration file and HoloOcean metadata keys.
*   **Changes to `rov_ws` code, Kit's Python, NVIDIA's `python.bat`, or the Pixi workspace's
    files.**
*   **A pass/fail threshold for throughput.** This change measures the cost (see Open Questions).

## Open Questions

*   **The acceptable throughput cost**, if a threshold is set before measuring.
*   **Default MCAP storage preset:** uncompressed (rosbag2's default) is provisional. It changes
    to `zstd_fast` only if the item 5 measurements show a worthwhile size saving at acceptable
    `recording_ms`.
*   **`rov_mapping` replay:** tested with the first bag, or recorded in the brief as deferred.

## Critical User Journeys (CUJs)

### CUJ 1: Record the first change-detection bag

*   **Given**: a checkout of `feature/isaac-mcap`; NVIDIA's `IsaacSim-ros_workspaces` at tag
    `IsaacSim-6.1.0`, installed with `pixi install --locked`; `ISAAC_SIM_PATH`,
    `OCEANSIM_ASSET_PATH` and `ROV_SIM_PIXI_ENV` set; the `camera-sensor` backend.
*   **When**: the user runs `scripts/launch.ps1` with `--experiment change_detection`,
    `--record-mcap` and a 30-frame "before" pass.
*   **Then**: `status.json` marks the pass `complete`, and `bag_to_capture` and `rov_slam`
    evaluation read `<run dir>/mcap/before/` from `/mnt/c/...` unchanged, with no WSL
    preprocessing.

### CUJ 2: Run without the flag

*   **Given**: the same checkout, with or without the Pixi workspace installed.
*   **When**: the user runs any existing command (capture, `--record`, `--benchmark`, validation
    scripts) without the flag.
*   **Then**: the deterministic outputs are byte-identical to the baseline tag, the environment
    passed to `python.bat` is unchanged, and no ROS bag code is imported.

### CUJ 3: Recover from a failed or interrupted pass

*   **Given**: a run that crashed, was interrupted, ran out of disk, or whose bag failed its check.
*   **When**: the user inspects the run directory.
*   **Then**: `status.json` and the directory layout show which passes are complete and which are
    unusable, and why. An unusable pass is re-recorded; nothing is repaired in place.

### CUJ 4: Measure the recording cost

*   **Given**: the 40-pair CameraSensor benchmark baseline.
*   **When**: the user runs `--benchmark --record-mcap` with each storage setting.
*   **Then**: the benchmark report gives pairs/s, `recording_ms` and bytes per frame, and the run
    still passes the existing freshness checks.

## Technical Plan (Architecture)

### Decisions taken in this section

| Question | Decision | Why |
| --- | --- | --- |
| Writer | **`rosbag2_py.SequentialWriter`, MCAP storage, inside Kit** (author decision, after evidence) | ROS 2's own writer; `metadata.yaml` and QoS written directly; WSL-verified; `bag_to_capture` accepts it. |
| How the writer runs | **Synchronous, in the loop** (author decision) | Errors surface on the frame that caused them; `recording_ms` measures the whole cost. |
| How a pass becomes complete | **In-process check after close** (author decision) | No WSL step; a run ends with complete bags or says why not. |
| ROS 2 libraries | NVIDIA's Pixi workspace `IsaacSim-ros_workspaces`, tag `IsaacSim-6.1.0` (commit `a9e8471`), `pixi install --locked`; the SHA-256 of `jazzy_ws/pixi.lock` is recorded. `pixi run build` is not needed. | NVIDIA's supported native Windows ROS 2; outside git, pinned. |
| Overlay | **Minimal, flag runs only:** `launch.ps1` appends `<env>\Library\bin` to `PATH` and prepends `<env>\Library` to `AMENT_PREFIX_PATH`; `ROS_DISTRO` stays unset; the bootstrap appends `<env>\Lib\site-packages` to the end of `sys.path` | The variant measured in the research (bundled ROS libraries first); full `pixi run` activation broke Kit. `site-packages` cannot go on `PYTHONPATH`, because that would put Pixi's NumPy 2.5.1 before Kit's. |
| Pixi environment location | Environment variable `ROV_SIM_PIXI_ENV` (path to `jazzy_ws\.pixi\envs\default`); `launch.ps1 -PixiEnv` overrides it | The same pattern as `ISAAC_SIM_PATH`; no machine paths in tracked files. |
| Flag | `--record-mcap`, plus `--mcap-storage {none,zstd}` (default `none`) | CLI flags only, no config keys: a config key would change the `config.json` written to every run directory. `zstd` maps to rosbag2's `zstd_fast` preset. |
| Backend rejection | In `cli.main`, after `--camera-backend` has been applied | The effective backend is known only after the override. |
| Stamp epoch | `EPOCH_NS = 1_767_225_600 · 10⁹` (2026-01-01T00:00:00Z), the same for every pass | Non-zero; shows as a plausible date in tools. |
| `/tf` | One `map → left_camera_optical_frame` transform per frame, equal to `/ground_truth/pose` | Passes the spike; follows the brief's "Drop" table. |
| QoS | All topics reliable, volatile, keep-last 10, except `/tf_static`: reliable, transient-local, keep-last 1 | Verified in WSL; `/tf_static` replays as latched. |
| `.kit-venv`, `mcap`, `lz4`, `zstandard` | Removed: commit `c279b8f` (`requirements-kit.txt`, the `.kit-venv/` ignore entry) is reverted | No longer used. |

### Components

```text
scripts/launch.ps1
  └─ only with --record-mcap:  PATH += <pixi env>\Library\bin ; AMENT_PREFIX_PATH = <pixi env>\Library;<previous>
                               ROV_SIM_PIXI_ENV = <pixi env>          (all restored after the run)
        v
python.bat (NVIDIA, unchanged; ROS_DISTRO unset → bundled ROS 2 libs first) ──> kit.exe -m rov_sim ... --record-mcap
        │
 rov_sim/cli.py        flag checks before Kit starts
        v
 rov_sim/application.py  run()
   ├─ after SimulationApp start, before scene build:
   │     rov_sim/rosbag/deps.py  load()   ── append <env>\Lib\site-packages LAST; import rosbag2_py, rclpy, msgs;
   │                                         check numpy identity, package paths and versions, kit.exe image
   ├─ per pass:  rov_sim/rosbag/writer.py  PassBagWriter
   │     open:   SequentialWriter → <run>/mcap/.staging/<pass>/ (rosbag2 creates it)
   │     frame:  raw RGBA host copy ← stereo.inputs[side][0].numpy()  (same frame step)
   │             7 messages (contract.py values) → serialize_message → write(topic, data, t, t)
   │     close:  writer.close() → rename .staging/<pass> → mcap/<pass>
   │     check:  rov_sim/rosbag/check.py  (SequentialReader over mcap/<pass>, contract.py rules)
   └─ status.json "mcap": per pass  writing → complete | check_failed | failed
        v
 bag_to_capture / rov_slam evaluation / rov_mapping read <run dir>/mcap/<pass>/ from /mnt/c/...
```

### Dependency bootstrap (`rov_sim/rosbag/deps.py`)

This module loads dependencies and writes nothing. It is imported only when `--record-mcap` is
on. It runs once, after `SimulationApp` has started and before the scene is built, so a broken
install fails within seconds.

1.  **Find the environment.** It reads `ROV_SIM_PIXI_ENV`, and requires
    `<env>\Library\bin\rosbag2_storage_mcap.dll` and `<env>\Lib\site-packages\rosbag2_py`. On
    failure it names the missing path and the fix: install the pinned workspace, set
    `ROV_SIM_PIXI_ENV`, and run through `scripts/launch.ps1`. It also requires `<env>\Library\bin`
    to be on `PATH`, which proves the launcher overlay was applied.
2.  **Record NumPy, and refuse a second `rclpy`.** It records `numpy` (module object,
    `__version__`, `__file__`). It aborts if `rclpy` or `rosbag2_py` is already in `sys.modules`
    from a path outside `<env>`, for example because Isaac's ROS 2 bridge extension loaded its
    bundled `rclpy` into the same process. Two `rclpy` builds in one process are untested.
3.  **Append `site-packages`.** It appends `<env>\Lib\site-packages` to the end of `sys.path`,
    unless already present.
4.  **Import.** It imports `rosbag2_py`, `rclpy.serialization`, and the message classes
    (`sensor_msgs.msg.Image`, `CameraInfo`, `geometry_msgs.msg.PoseStamped`,
    `TransformStamped`, `tf2_msgs.msg.TFMessage`, `builtin_interfaces.msg.Time`).
5.  **Check.** It aborts with an expected-versus-found message unless:
    *   `numpy` is the same object, version and file as before;
    *   `rosbag2_py.__file__` and `rclpy.__file__` are under `<env>`;
    *   `importlib.metadata.version("rosbag2_py") == "0.26.10"`;
    *   the process image (`QueryFullProcessImageNameW` via `ctypes`) ends in `kit.exe`.
6.  **Return.** It returns a small object holding `SequentialWriter`, `SequentialReader`,
    `StorageOptions`, `ConverterOptions`, `TopicMetadata`, the rosbag2 `QoS` class,
    `serialize_message`, `deserialize_message`, the message classes, and a report dict (paths,
    versions, process image, the `pixi.lock` SHA-256 if `<env>\..\..\..\pixi.lock` exists). The
    report goes into `status.json` under `mcap.environment`.

The writer and the check receive this object as a parameter and never import ROS modules
themselves, so the CPU tests can pass fakes in.

### Message contract (`rov_sim/rosbag/contract.py`)

This module is pure Python with no imports outside the standard library. The writer and the check
import it, so both use one definition.

*   **Topics and types:** the seven topics, their ROS types (`sensor_msgs/msg/Image`, ...), and
    the two optical frame ids.
*   **`QOS`:** a per-topic description (reliability, durability, depth). The writer turns it into
    rosbag2 `QoS` objects.
*   **`stamp_ns(index, fps)`** = `EPOCH_NS + index · 10⁹ // fps`.
*   **`camera_info_fields(calibration, side)`:**
    *   width and height from `resolution_wh`;
    *   `distortion_model = "plumb_bob"` and `d = [0]*5`;
    *   `k` from `calibration["K"][side]`, with cx and cy **shifted by −0.5**.
        `stereo_calibration.json` stores cx = W/2 (pixel corners); ROS uses pixel centres (brief
        decision 4). The shift is deliberate and tested.
    *   `r = I` and `p = [fx, 0, cx, Tx, 0, fy, cy, 0, 0, 0, 1, 0]`, with `Tx = −fx·baseline_m`
        on the right and `0` on the left.
*   **`pose_fields(T_world_leftOptical)`:** translation, plus a unit quaternion (Shepperd's
    method, w ≥ 0).
*   **`tf_static_fields(calibration)`:** one transform `left → right` from
    `T_leftOptical_rightOptical`, whose rotation must be the identity.
*   **`rgba_to_bgr8(array)`:** `[..., [2, 1, 0]]` plus a contiguous copy.
*   **`custom_data(...)`:** the bag's `custom_data` keys: `rov_sim.format`
    (`isaac-stereo-mcap`), `rov_sim.format_version` (`1`), `rov_sim.writer_commit`,
    `rov_sim.config_sha256`, `rov_sim.backend`, `rov_sim.pass`, `rov_sim.epoch_ns`,
    `rov_sim.fps`.
*   **`expected_stamps(completed_frames, fps)`** and **`bundle_problems(...)`**, used by the
    check and the tests.

### Writer (`rov_sim/rosbag/writer.py`)

`PassBagWriter(run_dir, pass_name, deps, calibration, fps, storage, status, custom_data)`:

*   **Open:**
    *   calls `SequentialWriter.open` with `StorageOptions(uri=<run>/mcap/.staging/<pass>,
        storage_id="mcap", storage_preset_profile="" or "zstd_fast", custom_data=...)` and
        `ConverterOptions("cdr", "cdr")`. rosbag2 creates the directory and names the file
        `<pass>_0.mcap`;
    *   creates the seven topics with `TopicMetadata(id, name, type, "cdr", [QoS])`;
    *   sets `status["mcap"][pass] = {"state": "writing"}`.
*   **`write_frame(index, raw_rgba_by_side, poses)`:**
    *   builds the seven messages, all stamped `stamp_ns(index, fps)`;
    *   images are `bgr8`, `step = 3·W`, `is_bigendian = 0`;
    *   serializes each and calls `writer.write(topic, data, stamp, stamp)`, in a fixed topic
        order. That sets log time and publish time.
*   **`close()`:** calls `writer.close()`, then renames `.staging/<pass>/` to `mcap/<pass>/`.
    `metadata.yaml` lists the file by relative name, so the rename keeps it valid.
*   **`abort(error)`:** best effort. It calls `writer.close()` if open, leaves
    `.staging/<pass>/` in place, sets the state to `failed` with the error, and never renames.

**Write errors and a full disk:** any exception from `write`, `close` or `rename` propagates. The
application's existing `except BaseException` marks the run `failed` or `interrupted`, and
`abort` marks the pass `failed`. Partial data stays under `.staging/` for diagnosis and is never
consumed.

### Completeness check (`rov_sim/rosbag/check.py`)

`check_pass(bag_dir, deps, calibration, completed_frames, fps)` runs right after `close()`, in
the same process, still outside any measured benchmark row. It:

*   opens `bag_dir` with `SequentialReader` (`mcap`) and `metadata.yaml`;
*   checks that the topic set and types match `contract.py`;
*   deserializes every message, and checks that:
    *   every header stamp equals the log time;
    *   the stamps equal `expected_stamps(completed_frames, fps)`;
    *   every stamp has all seven topics;
    *   images are `bgr8`, W×H, `step = 3·W`;
    *   CameraInfo equals `camera_info_fields`;
    *   `/tf_static` matches `tf_static_fields`;
    *   the recorded QoS of `/tf_static` is transient-local.

It returns a list of problems. If the list is empty the pass becomes `complete` with message
counts. Otherwise it becomes `check_failed` with the first five problems, and the run fails
after all passes have been attempted.

### Loop integration (`rov_sim/application.py`)

All changes are guarded by `args.record_mcap`. With the flag off, no code path changes and no new
module is imported.

*   **After `SimulationApp` startup:** `deps = rov_sim.rosbag.deps.load()`, and `status["mcap"] =
    {"environment": deps.report, "epoch_ns": EPOCH_NS, "fps": fps, "storage": ...}`.
*   **Per pass:**
    *   the writer opens next to the `PoseRecorder` creation;
    *   after the frame loop it closes beside `recorder.close()`, then `check_pass` runs and
        `status.json` is written.
*   **Per frame:** after the pose checks, at the existing recorder call, the raw RGBA host copy
    `stereo.inputs[side][0].numpy()` is taken for both sides, then `write_frame` runs. This sits
    in the window between `acquisition_end_ns` and `iteration_end_ns`, before the next
    `render_step()` returns the borrowed buffer.
*   **Benchmark counting:** the condition behind `recording_ms` becomes "PNG recorder or bag
    writer active". `Benchmark` gains an `mcap=None` keyword and reports
    `"mcap": {"storage": ...}` only when it is set.
*   **Failure:** the `finally` block calls `writer.abort()` before Kit cleanup.

### Flag rules (`rov_sim/cli.py`, before Kit starts)

| Combination with `--record-mcap` | Result | Reason |
| --- | --- | --- |
| Effective backend not `camera-sensor` | Rejected | Only `camera-sensor` is validated for this route. |
| `--frames 0` (interactive) | Rejected | A bag needs a bounded pass. |
| `--startup-only` | Rejected | No capture. |
| `--benchmark-mode` other than `full` | Rejected | Those modes skip readback. |
| `--photometric-diagnostics` | Rejected | Photometric runs stay separate. |
| `--benchmark` (full) | Allowed | Item 5 measures the cost. |
| `--stereo-diagnostics` | Allowed | Goal 2. |
| `--record`, `--preview-mp4` | Allowed, independent | PNG and MP4 output are unaffected. |
| `--validate-only` | Allowed | Validates the combination without Kit. |
| `--mcap-storage` without `--record-mcap` | Rejected | Avoids a silent no-op. |

### Output layout and pass states

```text
<run dir>/
  status.json            existing; gains "mcap" only with the flag
  before/ after/         existing PoseRecorder output
  mcap/
    .staging/before/     while writing, or after a failure (never consumed)
    before/              after a clean close: before_0.mcap + metadata.yaml (rosbag2)
    after/ ...
```

| `status.json` `mcap.<pass>.state` | Meaning | Recovery |
| --- | --- | --- |
| `writing` | Pass in progress. If the run died here, the pass is unusable. | Delete `.staging/<pass>/` and re-run. |
| `failed` | Write error, crash or interrupt during the pass | Same. |
| `check_failed` | Closed and moved, but the check found problems (listed) | Investigate; not consumable. |
| `complete` | Closed, moved and checked | Consumers may read it. |

### Launcher (`scripts/launch.ps1`)

New parameter: `-PixiEnv` (default `$env:ROV_SIM_PIXI_ENV`). If `$RunArguments` contains
`--record-mcap`, the launcher:

1.  requires `-PixiEnv` to name a directory containing `Library\bin\rosbag2_storage_mcap.dll`,
    and otherwise throws with the install steps;
2.  saves `$env:PATH`, `$env:AMENT_PREFIX_PATH` and `$env:ROV_SIM_PIXI_ENV`;
3.  sets `PATH = <previous>;<env>\Library\bin`, `AMENT_PREFIX_PATH = <env>\Library` (plus the
    previous value after `;` if non-empty), and `ROV_SIM_PIXI_ENV = <env>`;
4.  leaves `ROS_DISTRO` untouched, which must be unset: if it is set, the launcher throws, because
    `python.bat` would then skip Kit's bundled ROS libraries, which is untested;
5.  runs `python.bat` exactly as today, and restores the three variables in the existing
    `finally`.

The exit code is still `$LASTEXITCODE` from `python.bat`. The benchmark supervisor's child
(`sys.executable` = `kit.exe`) inherits the variables. Without the flag, `launch.ps1` behaves
exactly as at the baseline. `runtime.ps1` and the validation and photometric scripts are
unchanged.

--------------------------------------------------------------------------------

## Alternatives Considered

Sources: the brief's [Alternatives Weighed](../../concepts_brief.md#alternatives-weighed), the
[review decisions](../../rov_sim_review_plan.md#review-decisions), the
[spike result](../../rov_sim_review_plan.md#spike-result), and the
[native ROS 2 recording research](../../native_ros2_recording_research.md) with its measurements.

### A. Isaac's ROS 2 bridge plus `ros2 bag record -s mcap` on native Windows (Pixi)

*   **Pros**: NVIDIA's documented helpers and ROS 2's standard recorder; no message code in
    rov-sim; `metadata.yaml` and QoS written by rosbag2; it kept up at about 47–49 updates/s.
*   **Cons (measured 2026-11-17, 300 frames, WSL-verified)**:
    *   `bag_to_capture` rejected the bag: no ground-truth pose or `/tf_static` publisher.
    *   Log time ≠ header stamp: about 1.79·10¹² ms off (wall clock), or 33–67 ms off with
        `--use-sim-time`, differing between the left and right images of one frame.
    *   One frame lost inside each stream, about 6 at the start and 2 at the end.
    *   `rgb8`; cx/cy 376/240.
    *   Requires a playing timeline and physics stepping, which changes the validated loop.
*   **Reason for Rejection**: Rejected by author after measurement. It fails consumer
    acceptance and the timestamp contract, with no standard recorder option to fix the log time.

### B. Custom `rclpy` publishers with `ros2 bag record`

*   **Pros**: Messages under rov-sim's control.
*   **Cons**: Log time is still arrival time; frames can be lost in transport; a router or DDS
    setup is needed.
*   **Reason for Rejection**: Rejected by author: same timestamp and loss problems as A.

### C. Route C: the `mcap` Python package, bundled `rclpy` serialization, WSL `ros2 bag reindex`

*   **Pros**: Passed every consumer-facing check in the 2026-11-16 spike; needs only small pure-
    Python wheels in `.kit-venv`, no Pixi workspace and no `PATH` overlay.
*   **Cons**: rov-sim builds `ros2msg` schema text itself; `metadata.yaml` needs a WSL
    `ros2 bag reindex` step; no QoS metadata, so `/tf_static` replays as volatile; more custom code
    than calling rosbag2.
*   **Reason for Rejection**: Rejected by author in favour of ROS 2's own writer ("keep it
    simple"). **Kept as the fallback** if the Pixi overlay stops working, for example after an
    Isaac Sim or Pixi update.

### D. Full Pixi activation (`pixi run` around Kit)

*   **Pros**: NVIDIA's documented way to run Isaac with the Pixi ROS installation.
*   **Cons**: Measured: Pixi's NumPy 2.5.1 shadowed Kit's 2.3.1 (`DLL load failed`), and inside
    `SimulationApp` Isaac's torch failed with `WinError 1114` on `c10_cuda.dll`.
*   **Reason for Rejection**: Breaks Kit. The minimal overlay is used instead.

### E. Overlay with `ROS_DISTRO=jazzy` (Pixi ROS libraries first)

*   **Pros**: Matches NVIDIA's Pixi workflow, where Isaac uses the Pixi ROS libraries.
*   **Cons**: Changes which ROS libraries Kit loads first for its own bridge extension; it passed
    the same spike, but would add a second variant to validate.
*   **Reason for Rejection**: Rejected for simplicity: `ROS_DISTRO` unset keeps Kit's default
    library order, and the launcher refuses a set `ROS_DISTRO`.

### F. Pixi `site-packages` on `PYTHONPATH`

*   **Pros**: No `sys.path` handling in rov-sim code.
*   **Cons**: `PYTHONPATH` entries come before Kit's packages, so Pixi's NumPy 2.5.1 would shadow
    Kit's, the failure measured with full activation.
*   **Reason for Rejection**: Unsafe. The bootstrap appends `site-packages` at the end of
    `sys.path` and checks NumPy identity.

### G. A WSL check or finalize script

*   **Pros**: Checks the bag on the consuming side.
*   **Cons**: An extra manual step. Its main purpose was running `ros2 bag reindex`, which
    rosbag2's writer makes unnecessary.
*   **Reason for Rejection**: Rejected by author for the in-process check after close.

### H. A bounded background writer thread

*   **Pros**: Overlaps serialization and disk writes with rendering.
*   **Cons**: Thread lifecycle, deferred errors, shutdown ordering with Kit's fast exit, queue
    memory.
*   **Reason for Rejection**: Rejected by author for a synchronous writer. The writer's
    `open` / `write_frame` / `close` / `abort` interface lets a thread be added later if item 5
    justifies it.

### I. Install packages into Kit's bundled Python

*   **Pros**: No overlay.
*   **Cons**: Modifies NVIDIA's installation, against the README rule, and can't be reverted in
    git.
*   **Reason for Rejection**: Rejected by author.

### J. Physics-driven ROV motion

*   **Pros**: Would give the bridge a moving simulation clock.
*   **Cons**: No thruster or hydrodynamics model exists. Dynamics would make the "before" and
    "after" passes diverge and the ground truth no longer exact by construction. The bridge's
    other failures remain.
*   **Reason for Rejection**: Rejected by author: the kinematic, scripted trajectory stays.

### K. HoloOcean conventions: rebase `map` per pass; nominal calibration file

*   **Pros**: Matches the existing `rov_ws` contract README word for word.
*   **Cons**: Rebasing separates the "before" and "after" map frames. The nominal fx = 376 is
    wrong for Isaac, and the checks don't catch it.
*   **Reason for Rejection**: Rejected after the conventions audit.

--------------------------------------------------------------------------------

## Detailed Implementation Plan

All rov-sim changes go on branch `feature/isaac-mcap` (from tag `baseline/isaac-mcap`). The
`rov_ws` docs change goes on branch `docs/isaac-mcap`. Nothing is pushed until the plan has been
reviewed and the author approves. Paths are relative to the rov-sim repository root unless marked
`rov_ws:`.

### Order of work

1.  **Revert.** Run `git revert c279b8f`: it removes `requirements-kit.txt` and the `.kit-venv/`
    line in `.gitignore`. Delete the local untracked `.kit-venv/` directory.
2.  **Pure code first:** `rov_sim/rosbag/contract.py` with `tests/test_rosbag_contract.py`.
3.  **Bootstrap, writer and check against fakes:** `deps.py`, `writer.py`, `check.py`, with their
    CPU tests.
4.  **Flags, loop integration and benchmark keyword:** `cli.py`, `application.py` and
    `benchmark.py`, with the `tests/test_standalone.py` and `tests/test_benchmark.py` additions.
5.  **Launcher overlay:** `scripts/launch.ps1` and its PowerShell tests.
6.  **Runtime validation:** `scripts/validate_mcap.ps1`. Run it, then the WSL acceptance steps.
7.  **Docs:** rov-sim docs, then the `rov_ws` README on its docs branch, then the planning
    documents.

### Target Files to Create/Modify

#### 1. `requirements-kit.txt` (Delete, by revert)

*   **Type / Scope**: Dependency lock.
*   **Proposed Changes**: Removed by `git revert c279b8f`. `mcap`, `lz4` and `zstandard` are no
    longer used; ROS 2's own writer replaces them.

#### 2. `.gitignore` (Modify, by revert)

*   **Type / Scope**: Repository config.
*   **Proposed Changes**: The `.kit-venv/` line is removed by the same revert. Nothing is added:
    the Pixi workspace lives outside the repository.

#### 3. `rov_sim/rosbag/__init__.py` (Create)

*   **Type / Scope**: Python package marker.
*   **Proposed Changes**: Empty, like the other package initializers (the README says
    initializers are inert). Importing `rov_sim.rosbag` must import nothing else.

#### 4. `rov_sim/rosbag/contract.py` (Create)

*   **Type / Scope**: Pure Python module, standard library only.
*   **Proposed Changes**: The constants and functions in the Technical Plan's "Message contract":
    *   `TOPICS` (ordered: left image, right image, left info, right info, pose, `/tf_static`,
        `/tf`, each with its ROS type), `LEFT_FRAME`, `RIGHT_FRAME`, `MAP_FRAME`;
    *   `QOS` (per-topic reliability, durability, depth), and `EPOCH_NS = 1_767_225_600 *
        10**9`;
    *   `stamp_ns(index, fps) -> int`;
    *   `camera_info_fields(calibration, side) -> dict` (width, height, distortion_model, d, k,
        r, p; cx and cy minus 0.5; right `p[3] = -fx * baseline_m`);
    *   `pose_fields(T) -> (xyz, xyzw)`, with the quaternion by Shepperd's method and w ≥ 0;
    *   `tf_static_fields(calibration) -> dict`, raising `ValueError` if the rotation isn't
        within 1e-9 of the identity;
    *   `rgba_to_bgr8(array) -> array` (channel order `[2, 1, 0]`, contiguous; takes any
        object supporting NumPy-style indexing);
    *   `custom_data(commit, config_sha256, backend, pass_name, fps) -> dict[str, str]`, with the
        keys listed in the Technical Plan;
    *   `expected_stamps(completed_frames, fps) -> list[int]`;
    *   `bundle_problems(stamps_by_topic, expected) -> list[str]`, which reports missing,
        duplicate and unexpected stamps and any stamp lacking one of the seven topics.

#### 5. `rov_sim/rosbag/deps.py` (Create)

*   **Type / Scope**: Kit-side dependency bootstrap. Imported only with `--record-mcap`.
*   **Proposed Changes**: `load() -> RosbagDeps`, performing steps 1–6 of the Technical Plan's
    "Dependency bootstrap", in that order. `RosbagDeps` is a frozen dataclass of the classes and
    functions listed there plus `report: dict`. Constants: `ROSBAG2_PY_VERSION = "0.26.10"`, and
    the environment variable name `ROV_SIM_PIXI_ENV`. Each failure raises `RuntimeError` with
    what was expected, what was found, and the fix. The `pixi.lock` SHA-256 is computed only if
    `<env>/../../../pixi.lock` exists; otherwise the report records `null`.

#### 6. `rov_sim/rosbag/writer.py` (Create)

*   **Type / Scope**: Kit-side bag writer.
*   **Proposed Changes**: `PassBagWriter` as specified in the Technical Plan's "Writer":
    `__init__(run_dir, pass_name, deps, calibration, fps, storage, status, custom_data)`,
    `write_frame(index, raw_rgba_by_side, poses)`, `close()`, `abort(error)`. Storage `none`
    maps to preset `""` and `zstd` to `"zstd_fast"`. The `poses` argument is the existing loop's
    `poses` dict; the writer uses `poses["T_world_optical"]["left"]`. The writer counts messages
    per topic for the status entry. It imports nothing from ROS: everything comes from `deps`.

#### 7. `rov_sim/rosbag/check.py` (Create)

*   **Type / Scope**: Kit-side completeness check.
*   **Proposed Changes**: `check_pass(bag_dir, deps, calibration, completed_frames, fps) ->
    list[str]`, with exactly the checks in the Technical Plan's "Completeness check". It reads
    `metadata.yaml` with the standard library only (a line scan for the `/tf_static` topic's
    `durability:` value; no PyYAML dependency) and opens messages with `deps.SequentialReader`.
    It returns problems; it never raises for a content problem, only for I/O errors.

#### 8. `rov_sim/cli.py` (Modify)

*   **Type / Scope**: CLI parsing and validation, no Kit.
*   **Proposed Changes**:
    *   **New arguments:** `--record-mcap` (store_true, help "Write one rosbag2 MCAP bag per pass
        with ROS 2 rosbag2 (camera-sensor only)"), and `--mcap-storage` (choices `none`, `zstd`;
        default `None`, meaning `none` when `--record-mcap` is set).
    *   **`parse_args`:** add the rejections from the "Flag rules" table that depend only on
        arguments (`--frames 0`, `--startup-only`, a non-`full` `--benchmark-mode`,
        `--photometric-diagnostics`, `--mcap-storage` without `--record-mcap`), each with a
        one-line `parser.error` message.
    *   **`main`:** after `--camera-backend` is applied, raise `ValueError("--record-mcap
        requires the camera-sensor backend; effective backend is <x>")` when the backend isn't
        `camera-sensor`. This runs before `--validate-only` returns, so validation reports it.
    *   **Config:** no config keys are added.

#### 9. `rov_sim/application.py` (Modify)

*   **Type / Scope**: Capture loop.
*   **Proposed Changes**: The four guarded insertions described in the Technical Plan's "Loop
    integration":
    *   **Bootstrap**, after `status` is first written and before `build_scene`. It computes
        `config_sha256` from the `config.json` bytes and the writer commit with `git rev-parse
        HEAD` (via `subprocess`, cwd `ROOT`, `"unknown"` on failure).
    *   **Writer open**, beside `PoseRecorder` creation.
    *   **Raw copy and `write_frame`**, after `recorder.record`, inside the timed window.
    *   **Close, check and status write** after the frame loop.
    *   **Failure:** `writer.abort()` in the `finally` block, before `rep.orchestrator.stop()`.
    *   **Benchmark:** the `recording_ms` expression's `if recorder` becomes `if recorder or
        writer`, and `Benchmark(...)` receives `mcap={"storage": ...}` when the flag is on.
    *   **Run result:** if any pass ends `check_failed`, raise `RuntimeError` after all passes, so
        the run ends `failed` with the per-pass details in `status.json`.

#### 10. `rov_sim/benchmark.py` (Modify)

*   **Type / Scope**: Benchmark report.
*   **Proposed Changes**: `Benchmark.__init__` gains the keyword `mcap=None`, stored. `write()`
    adds `"mcap": self.mcap` to the report only when it isn't `None`, so reports without the flag
    are unchanged.

#### 11. `scripts/launch.ps1` (Modify)

*   **Type / Scope**: PowerShell launcher.
*   **Proposed Changes**: Add `[string]$PixiEnv = $env:ROV_SIM_PIXI_ENV` to `param` and the
    overlay steps 1–5 from the Technical Plan's "Launcher", only when `$RunArguments -contains
    '--record-mcap'`. The saved values are restored in the existing `finally`, including
    "variable was unset". Error messages name the missing file and the install commands.

#### 12. `scripts/validate_mcap.ps1` (Create)

*   **Type / Scope**: Windows runtime validation (needs Isaac Sim, OceanSim assets and the Pixi
    environment). Same parameter style as `validate_6_1.ps1`: `-SimRoot`, `-PixiEnv`,
    `-EvidenceRoot`.
*   **Proposed Changes**: It runs `launch.ps1`, writes each run's console to the evidence root,
    and fails on the first unmet check:
    1.  **First bag:** `--headless --experiment change_detection --frames 30 --record-mcap`.
        It requires exit code 0, `status.json` `state == "complete"`, both passes' `mcap` state
        `complete`, `mcap.environment.process_image` ending in `kit.exe`, and NumPy version
        `2.3.1`.
    2.  **Stereo diagnostics:** the same run with `--stereo-diagnostics`. It requires exit 0 and
        both the diagnostics summary `PASS` and the bag passes `complete`.
    3.  **Failure exit path:** `--record-mcap` with `-PixiEnv` pointing at a scratch directory
        that contains only an empty `Library\bin\rosbag2_storage_mcap.dll`, so the launcher
        check passes and the bootstrap fails inside Kit. It requires a non-zero exit code and
        `status.json` `state == "failed"`, with the bootstrap error recorded.
    4.  **Benchmark:** `--benchmark --frames 40 --record-mcap --mcap-storage none`, then the same
        with `zstd`. It requires supervisor `process_exit_code == 0` and `benchmark.json`
        present, and prints pairs/s, mean and p95 `recording_ms`, and bytes per frame from
        `status.json`. These numbers decide the default storage (Goal 7).
    5.  **Flag-off environment:** run `launch.ps1 --validate-only` with and without the flag
        through a temporary `python.bat` stub that dumps its environment (as in the existing
        launcher tests). Require the environments to be identical apart from the three overlay
        variables, and identical to the pre-launch environment without the flag.

#### 13. `tests/test_rosbag_contract.py` (Create)

*   **Type / Scope**: CPU unit tests (ordinary Python, NumPy from `requirements-tools.txt`).
*   **Proposed Changes**:
    *   `stamp_ns` against hand values, including integer exactness for fps 30 over 10,000
        frames.
    *   `camera_info_fields`: cx = 375.5 and cy = 239.5 for 752×480; right `p[3] = -fx * 0.38`;
        left `p[3] = 0`; D = 0 and R = I.
    *   `pose_fields`: identity, 90° rotations about each axis, and a w < 0 input normalized to
        w ≥ 0.
    *   `tf_static_fields`: rejects a rotated rig.
    *   `rgba_to_bgr8`: the known-colour pixel (RGB 200, 30, 90 → BGR 90, 30, 200), with the
        result contiguous.
    *   `custom_data` keys.
    *   `expected_stamps` and `bundle_problems`: complete, missing, duplicate, extra and
        incomplete-bundle cases.

#### 14. `tests/test_rosbag_writer.py` (Create)

*   **Type / Scope**: CPU unit tests with fake `deps`.
*   **Proposed Changes**: A fake `SequentialWriter` records `open`, `create_topic`, `write` and
    `close` calls, and creates the URI directory and file as rosbag2 does. Tests:
    *   the staging URI and preset mapping;
    *   seven topics with the `/tf_static` QoS transient-local and depth 1;
    *   seven writes per frame in fixed order, with log time = publish time = `stamp_ns`;
    *   `close` renames `.staging/<pass>` to `mcap/<pass>`;
    *   `abort` leaves staging in place, sets `failed` and never renames;
    *   an exception in `write` propagates.

    A fake `SequentialReader` feeds `check_pass` complete, missing-frame, wrong-encoding,
    wrong-stamp and volatile-`/tf_static` bags, and the test asserts the problem lists.

#### 15. `tests/test_rosbag_deps.py` (Create)

*   **Type / Scope**: CPU unit tests of the bootstrap's failure paths.
*   **Proposed Changes**: With a temporary fake Pixi directory and patched `os.environ` and
    `sys.modules`:
    *   a missing `ROV_SIM_PIXI_ENV`, a missing DLL, `Library\bin` absent from `PATH`, and a
        pre-loaded foreign `rclpy` each raise with the documented message;
    *   the NumPy identity check fails when a different module object is substituted;
    *   `sys.path` gains `site-packages` only at the end, and only once.

#### 16. `tests/test_standalone.py` (Modify)

*   **Type / Scope**: Existing CPU and PowerShell test module.
*   **Proposed Changes**:
    *   In `test_fresh_process_imports_and_cpu_cli_do_not_load_runtime`, add `"rov_sim.rosbag"`,
        `"rosbag2_py"` and `"rclpy"` to the forbidden-module prefixes.
    *   New `test_record_mcap_flag_rules`, covering each row of the "Flag rules" table through
        `cli.parse_args` and `cli.main([... "--validate-only"])`, including the backend rule via
        `--camera-backend legacy`.
    *   In the PowerShell launcher class, new
        `test_launcher_applies_pixi_overlay_only_with_record_mcap`. A fake `python.bat` (the
        existing fixture pattern) writes its `PATH`, `AMENT_PREFIX_PATH`, `ROV_SIM_PIXI_ENV` and
        `ROS_DISTRO` to a file. It asserts:
        *   the appended `Library\bin` and the variables appear only with `--record-mcap`;
        *   the caller's values are restored afterwards;
        *   a set `ROS_DISTRO` or a missing DLL makes the launcher fail before running
            `python.bat`;
        *   the fake's exit code (0 and 3) is propagated with the overlay applied.
    *   Confirm the existing script-scan test still passes with the new `validate_mcap.ps1`.

#### 17. `tests/test_benchmark.py` (Modify)

*   **Type / Scope**: CPU unit tests.
*   **Proposed Changes**: `Benchmark(mcap={"storage": "none"})` writes `"mcap"` into the
    report; the default writes no `"mcap"` key, which keeps the existing report byte layout.

#### 18. `README.md` (Modify)

*   **Type / Scope**: User documentation.
*   **Proposed Changes**:
    *   **"Prerequisites and validated build":** add the optional Pixi workspace for MCAP
        recording (tag, `pixi install --locked`, `ROV_SIM_PIXI_ENV`). State that nothing is
        installed into Isaac Sim.
    *   **"Launch and reproduce change detection":** add the `--record-mcap` command.
    *   **"Experiments and output":** add the `mcap/` layout, the pass states and the consumer
        rule (read only `complete`).
    *   **"Architecture and extension points":** qualify "No package installation is required"
        to "except the optional Pixi workspace for MCAP recording", and add the four
        `rov_sim/rosbag/*` modules to the module table.
    *   **"Checks and troubleshooting":** add rows for the bootstrap errors (environment not set,
        overlay missing, NumPy changed, foreign `rclpy`).

#### 19. `docs/REPRODUCIBILITY.md` (Modify)

*   **Type / Scope**: Reproduction documentation.
*   **Proposed Changes**:
    *   **"Validation using the pinned checkout":** a new subsection with the Pixi workspace
        install. That means `winget install prefix-dev.pixi`, cloning `IsaacSim-ros_workspaces`
        with `--branch IsaacSim-6.1.0 --recurse-submodules` to a short path, and
        `pixi install --locked` in `jazzy_ws`, without `pixi run build`. It records commit
        `a9e8471` and the `pixi.lock` SHA-256, and explains `ROV_SIM_PIXI_ENV`.
    *   **"Reproduce":** `scripts/validate_mcap.ps1`, and the item 5 results table as produced
        by step 4 of that script, compared with the 12.8005 pairs/s baseline.

#### 20. `docs/VALIDATION.md` (Modify)

*   **Type / Scope**: Validation documentation.
*   **Proposed Changes**:
    *   **"Completed checks":** the new CPU tests.
    *   **"Required Windows runtime checks":** `validate_mcap.ps1`, plus the manual WSL first-bag
        acceptance steps (`source /opt/ros/jazzy/setup.bash`):
        *   `ros2 run rov_reconstruction bag_to_capture <run>/mcap/before <new output dir>`,
            which must exit 0 and extract 30 pairs;
        *   `python3 -c "from rov_evaluation.inputs import read_pose_topic;
            read_pose_topic('<bag>')"` from `rov_ws/src/rov_slam/scripts`, which must return 30
            poses without error;
        *   the decision on `rov_mapping` replay, or its recorded deferral.

#### 21. `rov_ws: src/rov_dataset_player/README.md` (Modify, branch `docs/isaac-mcap`)

*   **Type / Scope**: Consumer contract documentation.
*   **Proposed Changes**: A section "Isaac Sim (rov-sim) bags", limited to the statements Isaac
    bags change:
    *   `map` is the Isaac tank world frame, not rebased;
    *   there is no `initial_left_camera_optical_frame`;
    *   CameraInfo comes from rov-sim's calibration (fx ≈ 537.14), not
        `nominal_752x480.yaml`;
    *   HoloOcean metadata keys are absent; the bag's `custom_data` keys are listed;
    *   `metadata.yaml` and QoS are written by rosbag2, so no reindex is needed.

#### 22. `rov_sim_review_plan.md` and `native_ros2_recording_research.md` (Modify, planning documents, untracked)

*   **Type / Scope**: Planning records.
*   **Proposed Changes**:
    *   **Review plan:** add a "Route change (2026-11-17)" decision. Route C becomes the fallback,
        replaced by in-process `rosbag2_py.SequentialWriter` through the Pixi overlay, linking
        the research report. Mark the `.kit-venv` launcher decision and work items 1, 3, 4 and 6
        as amended by this design. Work item 5 keeps its benchmark, with storage `none`/`zstd`.
    *   **Research report:** no change beyond what it already records.
    *   Both are copied back from the worktree to `C:\rov-sim`, where the originals live.

### Verification Plan

*   **Compilation/Build**: None (Python and PowerShell). `python -m compileall rov_sim` must pass.
*   **Unit Tests**: `python -m unittest discover -s tests -q` with ordinary Python and
    `requirements-tools.txt`. All existing tests (51 at the baseline) plus the new ones must
    pass.
*   **Static Analysis & Linting**: None is configured in the repository; none is added.
*   **Test Coverage Requirement**: Every row of the "Flag rules" table, every pass state, and
    every bootstrap failure message has a CPU test (items 13–17). No percentage target is
    configured.
*   **E2E/Integration**:
    *   `scripts/validate_mcap.ps1 -SimRoot C:\isaacsim -PixiEnv
        C:\IsaacSim-ros_workspaces\jazzy_ws\.pixi\envs\default -EvidenceRoot <new dir>` passes
        all five steps.
    *   The WSL acceptance steps in `docs/VALIDATION.md` pass on the first bag.
    *   The existing `scripts/validate_6_1.ps1` passes unchanged with the flag off, against tag
        `baseline/isaac-mcap` (Goal 3).

--------------------------------------------------------------------------------

*Drafted with EGM*
