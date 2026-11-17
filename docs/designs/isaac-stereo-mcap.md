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
*   **Supersedes** these earlier decisions: the review plan's rule that no Pixi installation or
    `rosbag2_py` dependency is authorised, and its closure of the `SequentialWriter` side check;
    route C as the writer, with `metadata.yaml` produced by WSL `ros2 bag reindex`; and the
    brief's rejection of "rosbag2 on Windows". The author's decision is recorded in the
    [research](../../native_ros2_recording_research.md#verified-in-wsl-afterwards-author-chose-sequentialwriter-2026-11-17).

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
and marks the pass complete. `bag_to_capture` and `rov_slam` evaluation are to read the result
from `/mnt/c/...` with no extra step and no code changes; `rov_mapping` replay is an open
question.

The route is measured, not assumed
([research](../../native_ros2_recording_research.md)):

*   A 3-frame bag with synthetic images, written this way inside a running `SimulationApp`,
    passed the spike's WSL checks, and `bag_to_capture` read it unchanged. The real capture loop
    and `rov_slam` evaluation are first tested by the first bag (Goal 1).
*   The standard alternative, Isaac's ROS 2 bridge with `ros2 bag record`, failed measured
    requirements.

## The Problem

There is no way today to get rov-sim data into `rov_ws`. The existing paths fail, or conflict
with how rov-sim works, for measured or source-verified reasons:

*   **Isaac's ROS 2 bridge plus `ros2 bag record` gives bags `bag_to_capture` rejects.** Measured on
    this machine, 2026-11-17:
    *   `bag_to_capture` rejected the bag: there is no ground-truth pose or `/tf_static`
        publisher.
    *   Log time never equals the header stamp: wall-clock arrival time by default; with
        `--use-sim-time`, one to two frames late, and different for the left and right images of
        one frame.
    *   Frames were lost in each 300-frame stream: one inside it, about 6 at the start and 2 at
        the end.
    *   Images are `rgb8`, and cx/cy follow the pixel-corner convention.
    *   The timeline must play, which rov-sim's validated loop does not do.
*   **rov-sim moves the ROV kinematically.** Each frame's pose is set from a scripted trajectory,
    with the timeline held still while both cameras render. That gives exact ground truth and
    identical "before" and "after" passes. Isaac's bridge publishes only while the timeline plays,
    and its simulation-time stamps advance only with physics steps.
*   **The HoloOcean contract carries conventions that are wrong for Isaac.** The nominal
    calibration's fx = 376 against Isaac's ≈ 537.14 is not caught by consumer checks. Rebasing
    `map` per pass would put the "before" and "after" passes in different `map` frames when their
    start poses differ.

Writing the bag from the loop that already knows each frame's images, poses and calibration
avoids the transport and timestamp problems. Nothing is in transit, so no frames are lost in
transport, and every timestamp is set once.

Three constraints shape the design:

*   **The validated surface must not move.** With the flag off, rov-sim's deterministic outputs
    and environment match tag `baseline/isaac-mcap`, as Goal 3 defines. With the flag on, the existing
    freshness checks still pass.
*   **Kit stays as NVIDIA ships it.** Kit's Python and `python.bat` are not modified. The
    interpreter keeps running as `kit.exe`. Kit's NumPy 2.3.1 stays the one loaded.
*   **Every repository change is reversible in git.** The Pixi workspace lives outside the
    repository. It is installed from a pinned tag with `pixi install --locked`, and its lock
    file's SHA-256 is recorded in each run's `status.json` (recorded, not enforced). `rov_ws`
    changes are docs only, on their own branch.

## Goals

1.  **First bag.** `--experiment change_detection` with the `camera-sensor` backend and the new
    flag, for one 30-frame "before" pass, produces one rosbag2 MCAP directory (MCAP file plus
    `metadata.yaml`). It meets these first-bag criteria, which are the brief's staging step 3
    without its manifest check (removed by the review plan). No WSL step is needed, and the
    stamp check is made against `status.json` and the stamp formula:
    *   `/stereo/left/image_raw` has exactly 30 messages, and all seven contract topics are
        present on every stamp.
    *   Stamps are non-zero, strictly increasing integers: `epoch + i·10⁹ // fps` for
        `i < completed_frames`.
    *   Log time = publish time = header stamp on every message (publish time confirmed in WSL
        with the first bag).
    *   Images are `bgr8`; a known-colour pixel survives the RGB to BGR conversion.
    *   The seven topics are `/stereo/{left,right}/{image_raw,camera_info}`,
        `/ground_truth/pose` (PoseStamped, `frame_id = map`, the left optical camera),
        `/tf_static` and `/tf`. Image and CameraInfo frame ids are `left_camera_optical_frame` /
        `right_camera_optical_frame`, and their sizes match the calibration (752×480 in the
        default config).
    *   CameraInfo matches `stereo_calibration.json`: cx = W/2 − 0.5, cy = H/2 − 0.5, D = 0,
        R = I, and right P[0,3] = −fx·0.38.
    *   `/tf_static` is recorded as reliable and transient-local.
    *   `bag_to_capture` and `rov_slam` evaluation accept the bag without code changes.
2.  **Geometry cross-check.** A change-detection run with `--stereo-diagnostics` and the flag
    passes the simulator's stereo diagnostics (`<run>/diagnostics/summary.json` `status ==
    "PASS"`), and both bag passes are `complete`. The bag's geometry is covered by
    `check_pass` and the `contract.py` tests: `/tf_static` is +0.38 m along the left optical x
    axis with no rotation, and right P[0,3] = −fx·0.38. Reprojecting the diagnostic target with
    the bag's pose and K is not part of this change.
3.  **Flag off is unchanged.** Against tag `baseline/isaac-mcap`, with the flag off:
    *   the deterministic outputs are byte-identical: CLI and config validation results,
        recorded poses, the output file layout, and `status.json` apart from times and
        durations;
    *   `launch.ps1` changes no environment variable;
    *   no `rosbag2_py`, Pixi or bag-writer module is imported;
    *   all existing tests and validation checks pass.
4.  **Recording-only dependency overlay.**
    *   `launch.ps1` appends the Pixi environment's `Library\bin` to `PATH` and prepends
        `<env>\Library` to `AMENT_PREFIX_PATH`, process-local and only with the flag. `ROS_DISTRO` stays unset, so
        Kit keeps its bundled ROS 2 libraries first.
    *   A bootstrap module appends the Pixi `site-packages` to the **end** of `sys.path`. It
        verifies that NumPy is still Kit's 2.3.1, the same module object, and that `rosbag2_py`
        and `rclpy` resolve from the pinned Pixi environment.
    *   A mismatch aborts startup with a message that names what was expected and what was
        found.
    *   The bootstrap is separate from the writer.
5.  **Launcher regression test.** A targeted regression test shows that, with the
    recording overlay applied:
    *   the interpreter still runs as `kit.exe`;
    *   rendering still produces fresh, valid stereo frames;
    *   shutdown still returns the expected exit codes (success, failure, and the native crash
        code that the benchmark supervisor reports);
    *   with the flag off, the environment `python.bat` receives is identical to the baseline's.
6.  **Pass states match the bag on disk.** `status.json` records each pass as `writing`,
    `failed`, `check_failed` or `complete`. A pass is `complete` only after the bag is closed,
    reopened and checked in `mcap/.staging/<pass>/`, and then renamed to `mcap/<pass>/`. Any
    folder at `mcap/<pass>/` therefore holds a checked bag, so consumers do not need to read
    `status.json`.
7.  **Cost is measured.** With the flag on, `--benchmark` over 40 CameraSensor pairs reports
    throughput, per-frame `recording_ms` and bytes per frame (the bag file's size divided by the
    frame count, which the writer records in `status.json` at close). It runs once with
    uncompressed MCAP storage and once with `zstd_fast`. The numbers are compared with the
    40-pair baseline of 12.8005 pairs/s in `docs/REPRODUCIBILITY.md`. The author picks the
    default from them; no threshold is set in advance.
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

*   **Default MCAP storage preset:** uncompressed (rosbag2's default) is provisional until Goal 7
    reports. The author then picks the default, and removes `--mcap-storage` if one option is
    clearly better.
*   **Overlay variant:** the minimal overlay (no `CONDA_PREFIX`, `AMENT_PREFIX_PATH` prepended)
    has not been measured on its own. Either the first bag measures it, or the launcher sets
    `CONDA_PREFIX` as in the research. Moving the whole overlay into `deps.py` is the alternative
    to measure, and it would leave `launch.ps1` unchanged.
*   **`rov_mapping` replay:** tested with the first bag, or recorded in the brief as deferred.

## Critical User Journeys (CUJs)

### CUJ 1: Record the first change-detection bag

*   **Given**: a checkout of `feature/isaac-mcap`; NVIDIA's `IsaacSim-ros_workspaces` at tag
    `IsaacSim-6.1.0`, installed with `pixi install --locked`; `ISAAC_SIM_PATH`,
    `OCEANSIM_ASSET_PATH` and `ROV_SIM_PIXI_ENV` set; the `camera-sensor` backend.
*   **When**: the user runs `scripts/launch.ps1` with `--config configs/tank_photometric.yaml
    --camera-backend camera-sensor --headless --experiment change_detection --frames 30
    --record-mcap`.
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
*   **Then**: the benchmark report gives pairs/s and `recording_ms`, `status.json` gives bytes per
    frame for each pass, and the run
    still passes the existing freshness checks.

## Technical Plan (Architecture)

### Decisions taken in this section

| Question | Decision | Why |
| --- | --- | --- |
| Writer | **`rosbag2_py.SequentialWriter`, MCAP storage, inside Kit** (author decision, after evidence) | ROS 2's own writer; `metadata.yaml` and QoS written directly; a 3-frame synthetic bag passed in WSL and `bag_to_capture` accepted it. |
| How the writer runs | **Synchronous, in the loop** (author decision) | Errors surface on the frame that caused them. `recording_ms` covers the per-frame RGBA copy, serialization and `write` calls; `close()`, `check_pass` and the rename run after the frame loop, outside the benchmark rows. |
| How a pass becomes complete | **In-process check after close, before the rename** (author decision) | No WSL step; only checked bags reach `mcap/<pass>/`. |
| ROS 2 libraries | NVIDIA's Pixi workspace `IsaacSim-ros_workspaces`, tag `IsaacSim-6.1.0` (commit `a9e8471`), `pixi install --locked`; the SHA-256 of `jazzy_ws/pixi.lock` is recorded. `pixi run build` is not needed. | NVIDIA's supported native Windows ROS 2; outside git, pinned. |
| Overlay | **Minimal, flag runs only:** `launch.ps1` appends `<env>\Library\bin` to `PATH` and prepends `<env>\Library` to `AMENT_PREFIX_PATH`; `ROS_DISTRO` stays unset; the bootstrap appends `<env>\Lib\site-packages` to the end of `sys.path` | Close to the variant measured in the research, which also set `CONDA_PREFIX` and set `AMENT_PREFIX_PATH` to the Pixi environment outright. This minimal form is first measured by the first bag (Open Questions). Full `pixi run` activation broke Kit. `site-packages` cannot go on `PYTHONPATH`, because that would put Pixi's NumPy 2.5.1 before Kit's. |
| Pixi environment location | Environment variable `ROV_SIM_PIXI_ENV` (path to `jazzy_ws\.pixi\envs\default`); `launch.ps1 -PixiEnv` overrides it | The same pattern as `ISAAC_SIM_PATH`; no machine paths in tracked files. |
| Flag | `--record-mcap`, plus `--mcap-storage {none,zstd}` (default `none`) | CLI flags only, no config keys: a config key would change the `config.json` written to every run directory. `zstd` maps to rosbag2's `zstd_fast` preset. |
| Backend rejection | In `cli.main`, after `--camera-backend` has been applied | The effective backend is known only after the override. |
| Stamp epoch | `EPOCH_NS = 1_767_225_600 · 10⁹` (2026-01-01T00:00:00Z), the same for every pass | Non-zero; shows as a plausible date in tools. |
| `/tf` | One `map → left_camera_optical_frame` transform per frame, equal to `/ground_truth/pose` | It passed the spike; a per-frame `map → left_camera_optical_frame` lets tools that follow `map` show the camera. |
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
   │     close:  writer.close()
   │     check:  rov_sim/rosbag/check.py  (SequentialReader over .staging/<pass>, contract.py rules)
   │     pass:   rename .staging/<pass> → mcap/<pass>
   └─ status.json "mcap": per pass  writing → complete | check_failed | failed
        v
 bag_to_capture / rov_slam evaluation (rov_mapping: open question) read <run dir>/mcap/<pass>/ from /mnt/c/...
```

### Dependency bootstrap (`rov_sim/rosbag/deps.py`)

This module loads dependencies and writes nothing. It is imported only when `--record-mcap` is
on. It runs once, after `SimulationApp` has started and before the scene is built, so a broken
install fails before the scene is built.

1.  **Find the environment.** It reads `ROV_SIM_PIXI_ENV`, and requires
    `<env>\Library\bin\rosbag2_storage_mcap.dll` and `<env>\Lib\site-packages\rosbag2_py`. On
    failure it names the missing path and the fix: install the pinned workspace, set
    `ROV_SIM_PIXI_ENV`, and run through `scripts/launch.ps1`. It also requires `<env>\Library\bin`
    to be on `PATH` (compared with `os.path.normcase(os.path.normpath(...))`), which proves the launcher overlay was applied.
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
        decision 4). The shift is deliberate and will be covered by a unit test.
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
    *   sets `status["mcap"][pass] = {"state": "writing"}` and writes `status.json` before the
        first frame.
*   **`write_frame(index, raw_rgba_by_side, poses)`:**
    *   builds the seven messages, all stamped `stamp_ns(index, fps)`;
    *   images are `bgr8`, `step = 3·W`, `is_bigendian = 0`;
    *   serializes each and calls `writer.write(topic, data, stamp, stamp)` in a fixed topic
        order. This is `rosbag2_py` 0.26.10's overload
        `write(topic, data, recv_timestamp, send_timestamp)` (`rosbag2_py/_writer.pyi` in the Pixi
        environment), which sets both log time and publish time explicitly.
*   **`close()`:** calls `writer.close()`.
*   **`commit()`:** after `check_pass` finds no problems, renames `.staging/<pass>/` to
    `mcap/<pass>/`. `metadata.yaml` lists the file by relative name, so the rename keeps it
    valid.
*   **`abort(error)`:** calls `writer.close()` if open and suppresses any error from that call,
    leaves `.staging/<pass>/` in place, sets the state to `failed` with the original error, and
    never renames.

**Write errors and a full disk:** any exception from `write`, `close` or `rename` propagates. The
application's existing `except BaseException` marks the run `failed` or `interrupted`, and
`abort` marks the pass `failed`. Partial data stays under `.staging/` for diagnosis and is never
consumed.

### Completeness check (`rov_sim/rosbag/check.py`)

`check_pass(staging_dir, deps, calibration, completed_frames, fps)` runs right after `close()`,
on `mcap/.staging/<pass>/`, in the same process, still outside any measured benchmark row. It:

*   opens `staging_dir` with `SequentialReader` (`mcap`) and `metadata.yaml`;
*   checks that the topic set and types match `contract.py`;
*   deserializes every message, and checks that:
    *   every header stamp equals the log time;
    *   the stamps equal `expected_stamps(completed_frames, fps)`;
    *   every stamp has all seven topics;
    *   images are `bgr8`, W×H, `step = 3·W`;
    *   CameraInfo equals `camera_info_fields`;
    *   `/tf_static` matches `tf_static_fields`;
    *   `/tf` equals `/ground_truth/pose` on every stamp;
    *   the frame ids follow the contract;
    *   the recorded QoS of `/tf_static` is transient-local.

Publish time cannot be read back: `SequentialReader.read_next()` returns only the log time. The
first bag's WSL acceptance confirms publish time once (Goal 1).

It returns a list of problems. If the list is empty, the writer renames the folder to
`mcap/<pass>/` and the pass becomes `complete` with message counts. Otherwise the folder stays in
`.staging/<pass>/`, the pass becomes `check_failed` with the first five problems, and the run
fails after all passes have been attempted.

### Loop integration (`rov_sim/application.py`)

All changes are guarded by `args.record_mcap`. With the flag off, existing behaviour and outputs
are unchanged (Goal 3) and no new module is imported. The new code that still runs without the
flag is the CLI parsing and rejection rules, the `recording_ms` condition and `Benchmark`'s
`mcap=None` default.

*   **After `SimulationApp` startup:** `deps = rov_sim.rosbag.deps.load()`, and `status["mcap"] =
    {"environment": deps.report, "epoch_ns": EPOCH_NS, "fps": fps, "storage": ...}`.
*   **Per pass:**
    *   the writer opens after the `PoseRecorder` block, independent of `--record` and benchmark
        mode;
    *   after the frame loop it closes beside `recorder.close()`; then `check_pass` runs, the
        folder is renamed if the check passes, and `status.json` is written.
*   **Per frame:** after the pose checks, at the existing recorder call, the raw RGBA host copy
    `stereo.inputs[side][0].numpy()` is taken for both sides, then `write_frame` runs. This sits
    in the window between `acquisition_end_ns` and `iteration_end_ns`, before the next
    `render_step()` reuses the borrowed buffer.
*   **Benchmark counting:** the condition behind `recording_ms` becomes "PNG recorder or bag
    writer active". `Benchmark` gains an `mcap=None` keyword and reports
    `"mcap": {"storage": ...}` only when it is set. Bytes per frame is reported in `status.json`.
*   **Failure:** the `except` block calls `writer.abort(error)` before it writes `status.json`. A
    native crash or
    Kit's fast exit skips `finally`. The pass then stays `writing` in `status.json` with its
    folder in `.staging/`, and both mean the pass is unusable. Nothing cleans up stale `writing`
    entries automatically; recovery is CUJ 3.

### Flag rules (`rov_sim/cli.py`, before Kit starts)

| Combination with `--record-mcap` | Result | Reason |
| --- | --- | --- |
| Effective backend not `camera-sensor` | Rejected | Only `camera-sensor` is validated for this route. |
| `--frames 0`, or the interactive default of 0 frames | Rejected | A bag needs a bounded pass. |
| `--startup-only` | Rejected | No capture. |
| `--benchmark-mode` other than `full` | Rejected | Those modes skip readback. |
| `--photometric-diagnostics` | Rejected | Photometric runs stay separate. |
| `--benchmark` (full) | Allowed | Goal 7 measures the cost. |
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
    .staging/before/     while writing, after a failure, or after a failed check (never consumed)
    before/              only after the check passed: before_0.mcap + metadata.yaml (rosbag2)
    after/ ...
```

| `status.json` `mcap.<pass>.state` | Meaning | Recovery |
| --- | --- | --- |
| `writing` | Pass in progress. If the run died here, including a native crash that skipped `finally`, the pass is unusable. | Delete `.staging/<pass>/` and re-run. |
| `failed` | Write error, crash or interrupt during the pass | Same. |
| `check_failed` | Closed, but the check found problems (listed). The bag stays in `.staging/<pass>/`. | Keep it for diagnosis; re-record the pass. |
| `complete` | Closed, checked, then renamed to `mcap/<pass>/` | Consumers may read it. |

### Launcher (`scripts/launch.ps1`)

New parameter: `-PixiEnv` (default `$env:ROV_SIM_PIXI_ENV`). If `$RunArguments` contains
`--record-mcap`, the launcher:

1.  requires `-PixiEnv` to name a directory containing `Library\bin\rosbag2_storage_mcap.dll`,
    and otherwise throws with the install steps;
2.  saves `$env:PATH`, `$env:AMENT_PREFIX_PATH` and `$env:ROV_SIM_PIXI_ENV`;
3.  sets `PATH = <previous>;<env>\Library\bin`, `AMENT_PREFIX_PATH = <env>\Library` (plus the
    previous value after `;` if non-empty), and `ROV_SIM_PIXI_ENV = <env>`;
4.  requires `ROS_DISTRO` to be unset and throws otherwise, because `python.bat` would then skip
    Kit's bundled ROS libraries, which is untested;
5.  runs `python.bat` exactly as today, and restores the three variables in the existing
    `finally`.

The exit code is still `$LASTEXITCODE` from `python.bat`. The benchmark supervisor's child
(`sys.executable` = `kit.exe`) inherits the variables. Without the flag, `launch.ps1` changes no
environment variable and calls `python.bat` as at the baseline (Goal 3); its only difference is
the unused `-PixiEnv` parameter. `runtime.ps1` and the validation and photometric scripts are
unchanged.

## Risks & Mitigations

| Risk | Impact | Mitigation |
| --- | --- | --- |
| Mixed ROS builds in one process. With `ROS_DISTRO` unset, Kit's bundled `jazzy\lib` is first on `PATH`, so Pixi's `rosbag2_*` and `rclpy` binaries can load Kit's bundled `rcutils`, `rcl`, `rmw` and typesupport DLLs. Shown to work once, for one version pair (`rclcpp` 28.1.18 on both sides), on 3 synthetic frames. | A later Isaac Sim or Pixi build could fail to load, or load with mismatched libraries, without an import error. | The bootstrap records the `rosbag2_py` and `rclpy` file paths and the `rosbag2_py` version in `mcap.environment`. The first bag (Goal 1) is the first test in the real loop. After any Isaac Sim or Pixi update, Goal 1 is repeated before bags are used. |
| Update drift (Isaac Sim, Pixi, RoboStack). | The overlay or the `rosbag2_py` binding stops working. | `pixi install --locked` at a pinned tag; the bootstrap aborts unless `rosbag2_py` is 0.26.10; the lock SHA-256 is recorded. Fallback: route C, rebuilt from commit `c279b8f` (Alternative C). |
| Python ABI. Pixi's `rosbag2_py` and `rclpy` are built for the lock's Python, which must match Kit's CPython 3.12 (research, Option 2 risks). | Import fails. | Checked after `pixi install`; an import failure aborts the bootstrap with the expected and found versions. |
| Disk use. About 2.18 MB per frame uncompressed (research), so about 2.2 GB per 1,000 frames per pass. | A full disk fails the pass partway. | Write errors propagate and the pass becomes `failed`; partial data stays in `.staging/`. Goal 7 measures `zstd_fast`. There is no free-space check before the run. |
| Check cost. `check_pass` decodes every message again. | Reads roughly double, and time grows with pass length. | It runs after the pass, outside the benchmark rows. |
| WSL reads over `/mnt/c`. | Multi-GB bags replay slowly in `rov_ws`. | Accepted. Users may copy a bag into the WSL filesystem first. |
| Native crash or Kit fast exit. | `finally` does not run, so the pass is left half-written. | The `writing` state is saved at open. A pass that is still `writing` with its folder in `.staging/` is unusable (see Output layout and pass states). |
| Code loaded from a user-set path. `ROV_SIM_PIXI_ENV` adds DLLs and Python modules to Kit's process. | Whoever can set the variable or write to that directory runs code inside Kit. | Only on `--record-mcap` runs; the same trust level as `ISAAC_SIM_PATH`; the bootstrap requires `rosbag2_py` and `rclpy` to load from under `<env>`. |
| Long paths. The `.pixi\envs\default\Library\...` paths are deep. | The Windows 260-character path limit (MAX_PATH) can break the install. | Install at a short root such as `C:\IsaacSim-ros_workspaces`, as measured; documented in `docs/REPRODUCIBILITY.md`. |
| Small evidence base. The in-process route was measured on 3 synthetic frames. | Real-loop problems (OceanSim, 30-frame readback, benchmark) are untested. | Goal 1 and Goal 7 are the first real tests; the doc claims no more than was run. |

--------------------------------------------------------------------------------

## Alternatives Considered

Sources: the brief's [Alternatives Weighed](../../concepts_brief.md#alternatives-weighed), the
[review decisions](../../rov_sim_review_plan.md#review-decisions), the
[spike result](../../rov_sim_review_plan.md#spike-result), and the
[native ROS 2 recording research](../../native_ros2_recording_research.md) with its measurements.

### A. Isaac's ROS 2 bridge plus `ros2 bag record -s mcap` on native Windows (Pixi)

*   **Pros**: NVIDIA's documented helpers and ROS 2's standard recorder; no message code in
    rov-sim; `metadata.yaml` and QoS written by rosbag2; the recorder kept up at about 65 MB/s.
*   **Cons (measured 2026-11-17, 300 frames, WSL-verified)**:
    *   `bag_to_capture` rejected the bag: no ground-truth pose or `/tf_static` publisher.
    *   Log time ≠ header stamp: about 1.79·10¹² ms off (wall clock), or 33–67 ms off with
        `--use-sim-time`, differing between the left and right images of one frame.
    *   One frame lost inside each stream, about 6 at the start and 2 at the end.
    *   `rgb8` instead of `bgr8`; cx/cy 376/240 instead of 375.5/239.5.
    *   Requires a playing timeline and physics stepping, which changes the validated loop.
*   **Reason for Rejection**: It fails consumer acceptance and the timestamp contract
    (measured), and no standard recorder option sets log time to the header stamp.

### B. Custom `rclpy` publishers with `ros2 bag record`

*   **Pros**: Messages under rov-sim's control.
*   **Cons**: Log time is still arrival time; frames can be lost in transport; a router or DDS
    setup is needed.
*   **Reason for Rejection**: It has the same arrival-time log stamps and transport loss as A,
    and also needs a router or DDS setup.

### C. The `mcap` Python package, bundled `rclpy` serialization and WSL `ros2 bag reindex` (route C)

*   **Pros**: Passed every consumer-facing check in the 2026-11-16 spike; needs only small pure-
    Python wheels in `.kit-venv`, no Pixi workspace and no `PATH` overlay.
*   **Cons**: rov-sim builds `ros2msg` schema text itself; `metadata.yaml` needs a WSL
    `ros2 bag reindex` step; no QoS metadata, so `/tf_static` replays as volatile; more custom code
    than calling rosbag2.
*   **Reason for Rejection**: It needs more custom code (the schema-text builder), a WSL reindex
    step per bag, and records no QoS, so `/tf_static` replays as volatile; rosbag2's writer does
    all three itself
    ([author's decision](../../native_ros2_recording_research.md#verified-in-wsl-afterwards-author-chose-sequentialwriter-2026-11-17)).
    **Fallback:** this change does not keep route C as working code, because commit `c279b8f` is
    reverted. If the Pixi overlay stops working, route C is rebuilt from `c279b8f` and the spike
    notes.

### D. Full Pixi activation (`pixi run` around Kit)

*   **Pros**: NVIDIA's documented way to run Isaac with the Pixi ROS installation.
*   **Cons**: Measured: Pixi's NumPy 2.5.1 shadowed Kit's 2.3.1 (`DLL load failed`), and inside
    `SimulationApp` Isaac's torch failed with `WinError 1114` on `c10_cuda.dll`.
*   **Reason for Rejection**: Breaks Kit. The minimal overlay is used instead.

### E. Overlay with `ROS_DISTRO=jazzy` (Pixi ROS libraries first)

*   **Pros**: Matches NVIDIA's Pixi workflow, where Isaac uses the Pixi ROS libraries.
*   **Cons**: Changes which ROS libraries Kit loads first for its own bridge extension; it passed
    the same spike, but would add a second variant to validate.
*   **Reason for Rejection**: It would change which ROS libraries Kit loads first for its own
    bridge extension, and that order needs its own validation. With `ROS_DISTRO` unset, Kit keeps
    the library order of every validated run, and the launcher refuses a set `ROS_DISTRO`.

### F. Pixi `site-packages` on `PYTHONPATH`

*   **Pros**: No `sys.path` handling in rov-sim code.
*   **Cons**: `PYTHONPATH` entries come before Kit's packages, so Pixi's NumPy 2.5.1 would shadow
    Kit's, the failure measured with full activation.
*   **Reason for Rejection**: Pixi's NumPy 2.5.1 would shadow Kit's 2.3.1, the failure measured
    with full activation. The bootstrap appends `site-packages` at the end of
    `sys.path` and checks NumPy identity.

### G. A WSL check or finalize script

*   **Pros**: Checks the bag on the consuming side.
*   **Cons**: An extra manual step. Its main purpose was running `ros2 bag reindex`, which
    rosbag2's writer makes unnecessary.
*   **Reason for Rejection**: It adds a manual WSL step per pass, and its main purpose (reindex)
    is gone. The in-process check covers stamps, topics and container integrity; WSL consumer
    acceptance stays a one-time first-bag step.

### H. A bounded background writer thread

*   **Pros**: Overlaps serialization and disk writes with rendering.
*   **Cons**: Thread lifecycle, deferred errors, shutdown ordering with Kit's fast exit, queue
    memory.
*   **Reason for Rejection**: It adds thread lifecycle, deferred errors and shutdown ordering
    with Kit's fast exit before the cost is known. The writer's `open` / `write_frame` /
    `close` / `commit` / `abort` interface lets a thread be added later if Goal 7 justifies it.

### I. Install packages into Kit's bundled Python

*   **Pros**: No overlay.
*   **Cons**: Modifies NVIDIA's installation, which the [README](../../README.md) rules out
    ("No extension copying or modification of the Isaac Sim installation is required"), and
    cannot be reverted in git.
*   **Reason for Rejection**: It breaks the unmodified-Kit constraint (The Problem, constraints).

### J. Physics-driven ROV motion

*   **Pros**: Would give the bridge a moving simulation clock.
*   **Cons**: No thruster or hydrodynamics model exists. Dynamics would make the "before" and
    "after" passes diverge and the ground truth no longer exact by construction. The bridge's
    other failures remain.
*   **Reason for Rejection**: No thruster or hydrodynamics model exists; dynamics would make the
    passes diverge and the ground truth inexact; and the bridge's other failures remain.

### K. HoloOcean conventions: rebase `map` per pass; nominal calibration file

*   **Pros**: Matches the existing `rov_ws` contract README exactly.
*   **Cons**: Rebasing separates the "before" and "after" map frames. The nominal fx = 376 is
    wrong for Isaac, and the checks do not catch it.
*   **Reason for Rejection**: Rebasing would put the passes in different `map` frames, and
    fx = 376 is wrong for Isaac and is not caught by consumer checks (brief, "Drop" table).

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
*   **Proposed Changes**: A one-line docstring, like the other package initializers (the README
    says initializers are inert). Importing `rov_sim.rosbag` must import nothing else.

#### 4. `rov_sim/rosbag/contract.py` (Create)

*   **Type / Scope**: Pure Python module, standard library only.
*   **Proposed Changes**: The constants and functions in the Technical Plan's "Message contract":
    *   `TOPICS` (ordered: left image, right image, left info, right info, pose, `/tf_static`,
        `/tf`, each with its ROS type), `LEFT_FRAME`, `RIGHT_FRAME`, `MAP_FRAME`;
    *   `QOS` (per-topic reliability, durability, depth), and `EPOCH_NS = 1_767_225_600 *
        10**9`;
    *   `stamp_ns(index, fps) -> int`; `fps` must be a positive `int` (`TypeError` otherwise);
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
    `<env>\..\..\..\pixi.lock` exists; otherwise the report records `null`.

#### 6. `rov_sim/rosbag/writer.py` (Create)

*   **Type / Scope**: Kit-side bag writer.
*   **Proposed Changes**: `PassBagWriter` as specified in the Technical Plan's "Writer":
    `__init__(run_dir, pass_name, deps, calibration, fps, storage, status, custom_data)`,
    `write_frame(index, raw_rgba_by_side, poses)`, `close()`, `commit()`,
    `mark_check_failed(problems)`, `abort(error)`.
    *   Opening writes `writing` to `status.json` before the first frame.
    *   `close()` closes the writer and records `bag_bytes = os.path.getsize(<staging>/<pass>_0.mcap)`
        and `bytes_per_frame = bag_bytes / frames_written`. It does not rename.
    *   `commit()` renames `.staging/<pass>/` to `mcap/<pass>/`, sets `complete` and writes
        `status.json`. `mark_check_failed(problems)` leaves staging in place, sets
        `check_failed` with the first five problems and writes `status.json`.
    *   `abort(error)` does nothing once the state is `complete` or `check_failed`.
    *   Storage `none` maps to preset `""` and `zstd` to `"zstd_fast"`. Topics are created with
        `QoS(10).keep_last(10).reliable().durability_volatile()`, and `/tf_static` with
        `QoS(1).keep_last(1).reliable().transient_local()`.
    *   The `poses` argument is the existing loop's `poses` dict; the writer uses
        `poses["T_world_optical"]["left"]`. It imports nothing from ROS: everything comes from
        `deps`.
    *   **`status.json` entry (owned by the writer):** `mcap.<pass> = {"state",
        "message_counts": {topic: int}, "problems": [≤5 str], "error": str|null, "bag_bytes":
        int, "bytes_per_frame": float}`. `mcap.environment` (set by the application from
        `deps.report`) = `{"numpy_version", "numpy_file", "rosbag2_py_file",
        "rosbag2_py_version", "rclpy_file", "process_image", "pixi_lock_sha256"}`.

#### 7. `rov_sim/rosbag/check.py` (Create)

*   **Type / Scope**: Kit-side completeness check.
*   **Proposed Changes**: `check_pass(staging_dir, deps, calibration, completed_frames, fps) ->
    list[str]`, with exactly the checks in the Technical Plan's "Completeness check". It opens
    the bag with `deps.SequentialReader`. It takes topic types and the offered QoS of
    `/tf_static` from `get_all_topics_and_types()` (`TopicMetadata.offered_qos_profiles`), and
    reads messages with `read_next()`. It closes the reader in a `finally` before returning, so
    that the rename that follows can succeed on Windows. It returns problems; it never raises
    for a content problem, only for I/O errors.

#### 8. `rov_sim/cli.py` (Modify)

*   **Type / Scope**: CLI parsing and validation, no Kit.
*   **Proposed Changes**:
    *   **New arguments:** `--record-mcap` (store_true, help "Write one rosbag2 MCAP bag per pass
        (camera-sensor only)"), and `--mcap-storage` (choices `none`, `zstd`; default `none`).
    *   **`parse_args`:** add the rejections from the "Flag rules" table that depend only on
        arguments (`--frames 0`, or no `--frames` without `--experiment` or `--headless`, which
        is the interactive default of 0 frames; `--startup-only`, a non-`full` `--benchmark-mode`,
        `--photometric-diagnostics`, `--mcap-storage` without `--record-mcap`), each with a
        one-line `parser.error` message.
    *   **`main`:** after `--camera-backend` is applied, raise `ValueError("--record-mcap
        requires the camera-sensor backend; effective backend is <x>")` when the backend isn't
        `camera-sensor`, and reject `--record-mcap` when `simulation.fps` is not a whole number.
        These run before `--validate-only` returns, so validation reports them.
    *   **Config:** no config keys are added.

#### 9. `rov_sim/application.py` (Modify)

*   **Type / Scope**: Capture loop.
*   **Proposed Changes**: The guarded insertions described in the Technical Plan's "Loop
    integration", all under `if args.record_mcap`:
    *   **Bootstrap:** immediately after `try:` (line 83), before `omni.usd.get_context()`, so
        that a bootstrap failure reaches the existing `except` and `status.json` records
        `failed`. It computes `config_sha256` from the `config.json` bytes. It reads the writer
        commit with `git rev-parse HEAD` (via `subprocess`, cwd `rov_sim.config.ROOT`,
        `"unknown"` on failure).
    *   **`writer = None`:** beside `recorder = None` (line 76).
    *   **Writer open:** after the PoseRecorder block (after line 218), at the level of the
        `for pass_name` body, so it does not depend on `--record` or benchmark mode.
    *   **Raw copy and `write_frame`:** between `acquisition_end_ns` and `iteration_end_ns`,
        after the pose checks, at the position of `recorder.record` whether or not a recorder
        exists.
    *   **End of pass:** after the frame loop, beside `recorder.close()`: `writer.close()`,
        then `check_pass(...)`. If it finds no problems, `writer.commit()`; otherwise
        `writer.mark_check_failed(problems)`. Then `writer = None`.
    *   **Failure:** in `except BaseException`, `writer.abort(error)` before the existing
        `write_json`, when `writer is not None`. The `finally` block makes no writer call.
    *   **Benchmark:** the `recording_ms` expression's `if recorder` becomes `if recorder or
        writer`, and `Benchmark(...)` receives `mcap={"storage": ...}` when the flag is on.
        Bytes per frame is reported in `status.json` only.
    *   **Run result:** if any pass ended `check_failed`, raise `RuntimeError` after preview
        encoding, `benchmark.write`, `camera_infrastructure.json` and `diagnostics.finish()`
        (after line 382), and before the `complete` status write. The run then ends `failed`
        with the per-pass details in `status.json`.

#### 10. `rov_sim/benchmark.py` (Modify)

*   **Type / Scope**: Benchmark report.
*   **Proposed Changes**: `Benchmark.__init__` gains the keyword `mcap=None`, stored. `write()`
    adds `"mcap": self.mcap` to the report only when it isn't `None`, so reports without the flag
    are unchanged.

#### 11. `scripts/launch.ps1` (Modify)

*   **Type / Scope**: PowerShell launcher.
*   **Proposed Changes**: Add `[Parameter()][string]$PixiEnv = $env:ROV_SIM_PIXI_ENV` as the
    **last** `param` entry, so existing positional calls bind as before. Apply the overlay steps
    from the Technical Plan's "Launcher" only when `$RunArguments -contains '--record-mcap'`:
    check `ROS_DISTRO` and the DLL first, then save and set the variables inside the existing
    `try`, and restore them in its `finally`. A variable that was unset is restored as unset.
    Error messages name the missing file and the install commands, or the `ROS_DISTRO` value
    found.

#### 12. `scripts/validate_mcap.ps1` (Create)

*   **Type / Scope**: Windows runtime validation (needs Isaac Sim, OceanSim assets and the Pixi
    environment). Parameters: `-SimRoot` (default `$env:ISAAC_SIM_PATH`), `-PixiEnv` (default
    `$env:ROV_SIM_PIXI_ENV`) and `-EvidenceRoot`, which must not already exist.
*   **Proposed Changes**: The script calls `launch.ps1`, not `python.bat` directly, because only
    the launcher applies the overlay. Each run is
    `launch.ps1 -IsaacSimPath $SimRoot -PixiEnv $PixiEnv -RunArguments @(... '--output-dir',
    <evidence>\<name>)`, with its console sent to `<evidence>\<name>.log`. As in
    `validate_6_1.ps1`, every run must have exactly one run directory, and its console must have
    no `[Error]`, `Traceback (most recent call last)` or `Fatal Python error` line. The script
    fails on the first unmet check:
    1.  **First bag:** `--headless --config configs/tank_photometric.yaml --camera-backend
        camera-sensor --experiment change_detection --frames 30 --record-mcap`. It requires
        exit 0, `status.json` `state == "complete"`, `mcap.before.state` and
        `mcap.after.state` both `complete`, `mcap.environment.process_image` ending in
        `kit.exe`, and `mcap.environment.numpy_version == "2.3.1"`.
    2.  **Stereo diagnostics:** `--headless --config configs/validation_6_1.yaml
        --camera-backend camera-sensor --experiment change_detection --frames 12
        --stereo-diagnostics --record-mcap`. It requires `<run>/diagnostics/summary.json`
        `status == "PASS"` and both bag passes in state `complete` (Goal 2).
    3.  **Failure path:** the first-bag arguments, with `-PixiEnv` pointing at a scratch
        directory that contains only an empty `Library\bin\rosbag2_storage_mcap.dll`, so the
        launcher check passes and the bootstrap fails inside Kit. It requires `status.json`
        `state == "failed"` with the bootstrap error recorded, and a `Traceback` in the console.
        The console scan above is skipped for this run. The exit code is recorded but not
        required to be non-zero, because Kit's Windows wrapper can return zero after a failure
        (README).
    4.  **Benchmark:** `--headless --config configs/tank_photometric.yaml --camera-backend
        camera-sensor --experiment change_detection --benchmark --frames 40 --record-mcap
        --mcap-storage none`, then the same with `zstd`. It requires supervisor
        `process_exit_code == 0` and `benchmark.json`. It prints pairs/s, mean and p95
        `recording_ms`, and `mcap.<pass>.bytes_per_frame` from `status.json`. The author picks
        the default storage from these numbers (Goal 7).

    The launcher environment, with and without the flag, is covered by the item 16 launcher
    test, which runs on CPU. This script does not repeat it.

#### 13. `tests/test_rosbag_contract.py` (Create)

*   **Type / Scope**: CPU unit tests (ordinary Python, NumPy from `requirements-tools.txt`).
*   **Proposed Changes**:
    *   `stamp_ns` against hand values, including integer exactness for fps 30 over 10,000
        frames; a float fps raises `TypeError`.
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
    *   opening writes `writing` to `status.json` before the first frame;
    *   `close` does not rename, and records `bag_bytes` and `bytes_per_frame`;
    *   `commit` renames `.staging/<pass>` to `mcap/<pass>` and sets `complete`;
    *   `mark_check_failed` leaves staging in place and sets `check_failed` with at most five
        problems;
    *   `abort` leaves staging in place, sets `failed` and never renames, and does nothing after
        `commit` or `mark_check_failed`;
    *   an exception in `write` propagates.

#### 14a. `tests/test_rosbag_check.py` (Create)

*   **Type / Scope**: CPU unit tests of `check_pass` with a fake `SequentialReader`.
*   **Proposed Changes**: The fake feeds complete, missing-frame, wrong-encoding, wrong-stamp
    and `/tf`-differs-from-pose bags, plus a `/tf_static` whose fake `TopicMetadata` offers
    volatile QoS. The tests assert the problem lists, and that the reader's `close()` is called
    even when reading raises.

#### 15. `tests/test_rosbag_deps.py` (Create)

*   **Type / Scope**: CPU unit tests of the bootstrap's failure paths.
*   **Proposed Changes**: With a temporary fake Pixi directory and patched `os.environ` and
    `sys.modules`:
    *   a missing `ROV_SIM_PIXI_ENV`, a missing DLL, a missing `site-packages\rosbag2_py`,
        `Library\bin` absent from `PATH`, a pre-loaded foreign `rclpy` or `rosbag2_py`,
        `rosbag2_py` or `rclpy` resolving outside `<env>`, a `rosbag2_py` version other than
        0.26.10, and a process image other than `kit.exe` each raise with item 5's
        expected-versus-found message (the process-image lookup is an injectable function);
    *   the NumPy identity check fails when a different module object is substituted;
    *   `sys.path` gains `site-packages` only at the end, and only once.

#### 16. `tests/test_standalone.py` (Modify)

*   **Type / Scope**: Existing CPU and PowerShell test module.
*   **Proposed Changes**:
    *   In `test_fresh_process_imports_and_cpu_cli_do_not_load_runtime`, add `"rov_sim.rosbag"`,
        `"rosbag2_py"` and `"rclpy"` to the forbidden-module prefixes, and add a variant that
        runs `--record-mcap --camera-backend camera-sensor --validate-only`.
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
        *   the fake's exit code (0, a failure code 3, and the native crash code `-1073741819`)
            is propagated with the overlay applied.
    *   Confirm the existing script-scan test (`test_standalone.py:245-264`) still passes with
        the new `validate_mcap.ps1`.

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
    *   **"Launch and reproduce change detection":** add the `--record-mcap` command, with
        `--camera-backend camera-sensor`.
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
    *   **"Validation using the pinned checkout":** a new dated subsection "MCAP recording (Pixi
        workspace)" with the Pixi workspace install. It lists `winget install prefix-dev.pixi`, cloning `IsaacSim-ros_workspaces`
        with `--branch IsaacSim-6.1.0 --recurse-submodules` to a short path, and
        `pixi install --locked` in `jazzy_ws`, without `pixi run build`. It records commit
        `a9e8471` and the `pixi.lock` SHA-256, and explains `ROV_SIM_PIXI_ENV`.
    *   **"Reproduce":** `scripts/validate_mcap.ps1`, and a new throughput results table
        (Goal 7), produced by step 4 of that script and compared with the 12.8005 pairs/s
        baseline.

#### 20. `docs/VALIDATION.md` (Modify)

*   **Type / Scope**: Validation documentation.
*   **Proposed Changes**:
    *   **"Completed checks":** a new dated entry for the new CPU tests.
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

#### 22. `rov_sim_review_plan.md` (Modify, planning document, untracked)

*   **Type / Scope**: Planning record.
*   **Proposed Changes**:
    *   Add a "Route change (2026-11-17)" decision: in-process `rosbag2_py.SequentialWriter`
        through the Pixi overlay replaces route C, which becomes the fallback. Link the research
        report. Mark the `.kit-venv` launcher decision and work items 1, 3, 4 and 6 as amended
        by this design. Work item 5 keeps its benchmark, with storage `none`/`zstd`.
    *   It is copied back from the worktree to `C:\rov-sim`, where the original lives.

### Verification Plan

*   **Compilation/Build**: No build step. `python -m compileall -q rov_sim tests` must pass.
*   **Unit Tests**: `python -m unittest discover -s tests -q` with ordinary Python and
    `requirements-tools.txt`. All existing tests (51 at the baseline) plus the new ones must
    pass.
*   **Static Analysis & Linting**: None is configured in the repository; none is added.
*   **Test Coverage Requirement**: Every row of the "Flag rules" table, every pass state, and
    every bootstrap failure message has a CPU test (items 13–17, including 14a). No percentage target is
    configured.
*   **E2E/Integration**:
    *   `scripts/validate_mcap.ps1 -SimRoot C:\isaacsim -PixiEnv
        C:\IsaacSim-ros_workspaces\jazzy_ws\.pixi\envs\default -EvidenceRoot <new dir>` passes
        steps 1–4.
    *   The WSL acceptance steps in `docs/VALIDATION.md` pass on the first bag.
    *   **Flag-off comparison (Goal 3):** in a worktree at tag `baseline/isaac-mcap` and on the
        branch, run the same commands with the flag off: `--validate-only` with the README
        configs, and `--headless --config configs/tank_photometric.yaml --camera-backend
        camera-sensor --experiment change_detection --frames 12 --record` with a fresh
        `--output-dir`. Diff the `--validate-only` output, each pass's `poses.jsonl`, the run
        directory's file list, and `status.json` with its time and duration fields removed. All
        must be identical. `scripts/validate_6_1.ps1` also still passes.

--------------------------------------------------------------------------------

*Drafted with EGM*
