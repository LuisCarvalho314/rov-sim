# Native ROS 2 recording on Windows: desk research

*   **Date:** 2026-11-16
*   **Scope:** desk research only, from Isaac Sim `6.1.0-rc.26` source at `C:\isaacsim\source`,
    the built extensions, NVIDIA's docs, and `ros2 bag record --help` in WSL Jazzy. Nothing was
    installed, and nothing in `design_draft.md` or `rov_sim_review_plan.md` was changed.
*   **Question:** can a native ROS 2 recording route replace route C (the `mcap` package plus
    `rclpy.serialization`), as asked: first `ros2 bag record -s mcap` on Windows through Isaac's
    ROS 2 bridge, then `rosbag2_py.SequentialWriter` inside Isaac Sim?
*   **Comparison baseline:** the route C spike ([rov_sim_review_plan.md, Spike result](./rov_sim_review_plan.md#spike-result))
    and the consumer rules in the brief's "Keep" table ([concepts_brief.md](./concepts_brief.md)).

## Summary

| Option | Source-level blockers found | Custom code still needed | Evidence still missing |
| --- | --- | --- | --- |
| 1. Bridge plus `ros2 bag record -s mcap` | Gate (built into the RGB pipeline), stamps, log time, `bgr8`, ground-truth pose | A timeline-play loop or an un-gated conversion node, stamp injection, a BGR conversion, a pose publisher, and `/clock` alignment | Runtime confirmation of the gate; frame loss and ordering over Zenoh |
| 2. `rosbag2_py.SequentialWriter` in Kit, Pixi environment | None found | The same message mapping as route C; no schema text; no reindex | Whether `rosbag2_py` imports in Kit under the Pixi environment; NumPy identity; throughput |
| Route C (fallback) | None (spike passed) | Schema text builder, message mapping, WSL reindex | Throughput (item 5) |

*   **Option 1 needs more workarounds than route C, not fewer.** All five blockers in the brief
    are confirmed in the 6.1 source; runtime confirmation is pending. Recording on Windows removes only the Windows-to-WSL
    transport. Each remaining blocker needs its own custom piece around the bridge.
*   **Option 2 is the only native option with no known blocker.** The research also weakens one
    risk I argued earlier (see "Correction" below). Its open questions can only be answered by
    installing NVIDIA's Pixi workspace and trying it.

## Correction to the draft

The earlier MCAP draft (see [Alternatives Considered](docs/designs/isaac-stereo-mcap.md#alternatives-considered)) said that RoboStack's `rclpy`, `rcl` and `rmw`
"would be loaded alongside the Jazzy DLLs Isaac already puts on `PATH`". The source shows that
this is not what happens in NVIDIA's documented workflow:

*   `setup_ros_env.bat` prepends the bundled `exts/isaacsim.ros2.core/jazzy/lib` to `PATH`
    **only if `ROS_DISTRO` is unset** (`USE_BUNDLED_ROS=true`). The Pixi workspace sets
    `ROS_DISTRO=jazzy` in `[activation.env]`, so the bundled libraries are not put first.
*   The bundled `jazzy/rclpy/__init__.py` extension first calls `restore_ros2_python_paths()`
    and tries the system `rclpy`. It falls back to the internal copy only if that import fails.
*   NVIDIA's [6.1 ROS 2 installation page](https://docs.isaacsim.omniverse.nvidia.com/6.1.0/installation/install_ros.html)
    lists Pixi as the supported native Windows setup for Jazzy and WSL2 as deprecated:
    "Isaac Sim can source the Pixi ROS installation directly."
*   The bundled Jazzy was itself built from a Pixi environment. Its ament index points at
    `C:/g/.../isaac_sim_ros_workspace/jazzy_ws/.pixi/envs/default\Library`.

The draft's in-process DLL-conflict argument should therefore be withdrawn, or replaced with
measured evidence, whichever way the decision goes.

## Option 1: Isaac's ROS 2 bridge plus `ros2 bag record -s mcap` on Windows

### What the 6.1 source shows

1.  **Gate.** `OgnIsaacSimulationGate::compute` enables its output only when
    `m_timeline->isPlaying()` (`isaacsim.core.nodes/nodes/OgnIsaacSimulationGate.cpp`). The
    gate is **built into the RGB pipeline**. The `LdrColorIsaacConvertRGBAToRGB` annotator
    takes both `LdrColorPtr` and `LdrColorIsaacSimulationGate` as inputs
    (`isaacsim.core.nodes/python/impl/extension.py:191-197`). The RGB writer
    `LdrColorROS2PublishImage` (`isaacsim.ros2.nodes/python/impl/extension.py:79`) builds on
    that annotator. The camera helper's `post_attach` only sets the gate's `step`.
    (Correction, 2026-11-16: an earlier version of this report said the writer had no gate and
    could be attached without the helper to bypass it. That was wrong.) Publishing with rov-sim's
    paused timeline therefore requires playing the timeline, or a custom un-gated conversion
    node.
2.  **Stamps.** `IsaacReadSimulationTime` returns `ISimulationManager::getSimulationTime()`,
    which advances only with physics steps (`OgnIsaacReadSimulationTime.cpp:70`). rov-sim runs
    no physics, so every stamp would be equal. The `SystemTime` writer variant gives wall-clock
    time instead. Neither gives `epoch + index·10⁹ // fps`. The publisher's `timeStamp` input is
    a `double` in seconds (`OgnROS2PublishImage.cpp:334`), so exact integer nanoseconds can't be
    guaranteed either. Fixing this would need a custom OmniGraph node or attribute override that
    feeds rov-sim's frame time into the writer graph.
3.  **Encoding.** `OgnROS2PublishImage.ogn:69-80`: "Input data is expected to already be in this
    format, no conversions are performed", with default `rgb8`. The RGB writer converts RGBA to
    RGB only. `rov_mapping` and `rov_slam` require `bgr8`, and changing `rov_ws` code is a
    non-goal. A BGR swizzle would need another custom node.
4.  **Ground-truth pose.** There is still no `PoseStamped` ground-truth publisher. `/tf` could come
    from the TF-tree publisher node, but `/ground_truth/pose` needs a custom `rclpy` publisher.
5.  **Log time.** `ros2 bag record` (Jazzy, `--help` checked in WSL) logs the receive time.
    The only alternative is `--use-sim-time`: "Use simulation time for message timestamps by
    subscribing to the /clock topic." No option records the header stamp as the log time
    ([rosbag2 Jazzy README](https://raw.githubusercontent.com/ros2/rosbag2/jazzy/README.md)).
    `bag_to_capture` requires log time equal to header stamp. That could only be met by publishing
    `/clock` with the frame stamp before each frame's messages, and relying on the recorder seeing
    the new `/clock` before the images arrive. That is a race, not a guarantee.
6.  **Transport.** NVIDIA's Pixi workspace uses `rmw_zenoh_cpp` ("Fast DDS is not applicable
    for Pixi-based installations") and needs a separate `pixi run zenoh` router. Recording on the
    same Windows host avoids the Windows-to-WSL network path, but frame loss under load is still
    possible with any publish/subscribe transport, and it has not been measured.

### What option 1 does solve

*   It is raw render-product RGB, matching the author's "raw images" decision.
*   QoS metadata and `metadata.yaml` are written by rosbag2, so no WSL reindex step and no
    `/tf_static` QoS gap.

### Assessment

Blockers 1 to 4 hold in the 6.1 source. Blocker 5 holds as a contract violation unless the
`/clock` race is accepted. Making
option 1 meet the "Keep" table means building custom pieces around the bridge: a gate bypass,
stamp injection, a BGR conversion and a pose publisher, plus a `/clock` alignment that can't be
guaranteed. That is more custom code than route C, and it reintroduces transport loss.

## Option 2: `rosbag2_py.SequentialWriter` inside Isaac Sim, through NVIDIA's Pixi workspace

### What the research shows

*   **Supported setup.** [NVIDIA 6.1 install page](https://docs.isaacsim.omniverse.nvidia.com/6.1.0/installation/install_ros.html):
    *   prerequisites are Windows 11, `winget install prefix-dev.pixi`, Git, MSVC Build Tools 2022,
        and Isaac Sim at `C:\isaacsim`;
    *   clone `isaac-sim/IsaacSim-ros_workspaces` with `--recurse-submodules`, then run
        `pixi install` and `pixi run build` in `jazzy_ws`;
    *   run with `pixi run zenoh` and `pixi run sim`;
    *   for standalone scripts, "use the bundled `python.bat` from a clean terminal".
*   **Workspace contents.** [`jazzy_ws/pixi.toml`](https://raw.githubusercontent.com/isaac-sim/IsaacSim-ros_workspaces/main/jazzy_ws/pixi.toml)
    uses the channels `robostack-jazzy` and `conda-forge`, includes win-64, and depends on
    `ros-jazzy-ros-base`. Its activation sets `RMW_IMPLEMENTATION=rmw_zenoh_cpp`,
    `ROS_DISTRO=jazzy`, `ROS_DOMAIN_ID=0` and `KMP_DUPLICATE_LIB_OK=TRUE`. It names no rosbag2 or
    MCAP package explicitly. Under REP 2001, `ros_base` includes `rosbag2`, and Jazzy's default
    storage plugin is MCAP. Both are **to be confirmed** in the solved Pixi lock.
*   **Windows builds.** RoboStack has a win-64 build of `ros-jazzy-rosbag2-storage-mcap`
    ([anaconda.org listing](https://anaconda.org/robostack-jazzy/ros-jazzy-rosbag2-storage-mcap/files/manage?page=2)).
    The build seen was `0.26.6` for Python 3.11. Whether the current lock gives a build for Kit's
    Python **3.12** must be checked after `pixi install`.
*   **Disk.** A forum user reports that `pixi install` pulled a second, complete Isaac Sim of
    about 12.8 GB into `.pixi`
    ([NVIDIA forum](https://forums.developer.nvidia.com/t/ros2-environment-for-isaac-sim-on-windows-11-wsl2-vs-native-pixi-looking-for-one-setup-to-commit-to/378548)).
    That is unverified and, per the author, not a concern.

### What option 2 would give

*   Stamps exactly as route C: `SequentialWriter.write(topic, data, timestamp_ns)` takes the
    integer log time, and the header is set by rov-sim. Publish time is not recorded separately
    by rosbag2's writer, so it stays equal by construction.
*   No transport, so no frame loss, and no Zenoh router needed for writing.
*   `metadata.yaml` and per-topic `offered_qos_profiles` written by rosbag2, which removes the WSL
    reindex step and the `/tf_static` QoS gap.
*   No schema text in rov-sim: rosbag2 takes it from the type support.
*   The message mapping (images, CameraInfo, pose, TF, stamps) is the same as route C. It moves
    unchanged into the new writer.

### Risks and open questions (to be measured, not assumed)

1.  **Import in Kit.** Does `import rosbag2_py` work inside `kit.exe` (`python.bat`) with the Pixi
    environment's variables (`PATH`, `AMENT_PREFIX_PATH`, `PYTHONPATH`, `ROS_DISTRO`) applied?
    The Pixi environment's Python must match Kit's CPython 3.12 ABI for the `rosbag2_py`
    extension modules to load.
2.  **NumPy and other shared packages.** With the Pixi `PYTHONPATH` restored, does `numpy` still
    resolve to Kit's 2.3.1? Does Warp, OceanSim or Replicator change behaviour? This matters for
    the validated surface.
3.  **Launcher.** NVIDIA's `sim` task launches `isaac-sim.sh`/`.bat`, not `python.bat -m rov_sim`.
    rov-sim would need `launch.ps1` to apply the Pixi environment (for example
    `pixi shell-hook`, or `pixi run` wrapping `python.bat`), only with the recording flag. The
    interpreter must still run as `kit.exe`, and exit codes must still propagate.
4.  **MCAP plugin load.** Does `rosbag2_py.SequentialWriter` with `storage_id="mcap"` find the
    plugin through `AMENT_PREFIX_PATH` inside Kit?
5.  **Throughput and output.** Compare with route C on the same 40-pair CameraSensor benchmark,
    for:
    *   pairs/s and `recording_ms`;
    *   dropped frames (expected none, since no transport);
    *   exact stamps;
    *   QoS metadata;
    *   WSL reading with `bag_to_capture`, `rov_slam` evaluation and `ros2 bag play`.
6.  **Reproducibility.** The Pixi workspace and its lock live outside rov-sim's git. Pinning means
    recording the workspace commit and the `pixi.lock` hash, or vendoring a minimal
    `pixi.toml`/lock into rov-sim.

## Measured: standard bridge plus `ros2 bag record -s mcap` (2026-11-17)

**Setup.** No change to Kit's Python paths, DLL paths or environment.

*   **Kit:** Isaac Sim's unchanged `python.bat`, with its default bundled Jazzy (`ROS_DISTRO`
    unset, `rmw_zenoh_cpp`).
*   **Pixi environment:** NVIDIA's `IsaacSim-ros_workspaces` tag `IsaacSim-6.1.0`
    (`a9e8471`), `pixi install --locked`, with no `pixi run build`.
*   **Router and recorder:** the Zenoh router (`pixi run zenoh`) and `ros2 bag record -s mcap`
    run from that environment, natively on Windows. `rmw_zenoh_cpp` is 0.2.9 and `rclcpp` is
    28.1.18 on both sides. The recorder is stopped through its `Stop` service.
*   **Scene:** a scratch script builds rov-sim's tank, BlueROV, stereo rig, RTX settings, OceanSim
    water and change-detection trajectory. It publishes through NVIDIA's documented helpers only:
    `ROS2CameraHelper` (rgb) ×2, a stereo `ROS2CameraInfoHelper`, `ROS2PublishTransformTree`,
    and `ROS2PublishClock`. The timeline plays, with `SimulationManager.setup_simulation(dt=1/30)`
    and `app.update()` per frame, as in NVIDIA's `camera_periodic.py`.
*   **Run:** 8 warmup frames, then 300 frames at 752×480. Verified in WSL Jazzy with `ros2 bag info`,
    a `rosbag2_py` verifier, and `bag_to_capture` itself.

| Measurement | Run 1 (default log time) | Run 2 (`--use-sim-time`) | Route C requirement |
| --- | --- | --- | --- |
| Kit exit; recorder stop | 0; clean (`metadata.yaml` written, QoS recorded) | Same | — |
| Loop rate (updates/s); p50 / p95 frame time | 48.8; 19.2 / 26.6 ms | 46.6; 19.2 / 29.0 ms | Not comparable: no `wait_for_render`, no OceanSim processing or readback |
| Images recorded, left / right | 301 / 301 (of 308 updated) | 300 / 300 | One per loop frame |
| Stereo pairs with identical stamp | 301 | 300 | All |
| Missing steps inside the recorded range | 1 (0.33 %) | 1 (0.33 %) | 0 |
| Frames lost at start and end | First ≈ 6 updates; last 2 (images trail `/clock` by 2 steps) | Same | 0 |
| Consecutive identical images | 0 | 0 | 0 |
| Encoding | `rgb8` | `rgb8` | `bgr8` |
| Header stamps | Simulation time 0.2–10.233 s, strictly increasing | 0.233–10.233 s | `epoch + i·10⁹//fps` |
| Log time − header stamp, images | ≈ 1.79·10¹² ms (wall clock) | 33–67 ms; left median +33 ms, right +67 ms | 0, identical for the whole bundle |
| CameraInfo cx, cy | 376, 240 (pixel corner) | Same | 375.5, 239.5 (ROS pixel centre) |
| Right P[0,3] | −204.114 = −fx·0.38 | Same | Same |
| TF | `World→Left`, `World→Right` (USD camera prims) | Same | `map → left_camera_optical_frame`; `/tf_static` left→right optical |
| `/ground_truth/pose`, `/tf_static` | Absent (no standard publisher) | Absent | Present |
| `bag_to_capture` | **Rejected:** "Require stereo Image/CameraInfo, ground-truth pose and static camera TF topics" | Not run (same missing topics) | Accepts |

### Result: the standard workflow fails measured requirements

1.  **Consumer acceptance.** `bag_to_capture` rejects the bag. Adding the missing topics would
    still leave its stamp check failing (`bag_to_capture.py:176`): the standard recorder's log
    time is wall-clock arrival time, or with `--use-sim-time` it lags by one to two frames and
    differs between the left and right images of one frame. No standard recorder option
    records the header stamp.
2.  **Frame loss.** One frame is lost inside the stream in both runs, plus about 6 at the start
    and 2 at the end. Route C loses none by construction.
3.  **Encoding and calibration conventions.** `rgb8` against the `bgr8` that `rov_mapping` and
    `rov_slam` require; cx and cy half a pixel off the ROS convention.
4.  **Validated surface.** The timeline must play, with `SimulationManager` stepping. rov-sim's
    validated loop keeps it paused and uses `orchestrator.step(wait_for_render=True)`.
5.  **Throughput** was not the limit. The recorder kept up with about 65 MB/s of images, and loop
    rate was not the bottleneck.

### Unfollowed evidence: in-process `SequentialWriter`

Run before the author stopped this line of work, not verified in WSL. With a minimal overlay,
`SequentialWriter` (storage `mcap`) wrote a seven-topic bag with `metadata.yaml` in all four
variants. The overlay was:

*   plain `python.bat`;
*   `CONDA_PREFIX` and `AMENT_PREFIX_PATH` set to the Pixi environment;
*   Pixi `Library\bin` **appended** to `PATH`;
*   Pixi `site-packages` appended to `sys.path`;
*   `ROS_DISTRO` unset or `jazzy`.

The four variants were standalone and inside a live `SimulationApp`, each with and without
`ROS_DISTRO=jazzy`. All four ran as `kit.exe` with NumPy at Kit's 2.3.1 and no `[Error]` lines.
Applying the full Pixi activation instead (`pixi run`) broke it: Pixi's NumPy 2.5.1 shadowed
Kit's, and Isaac's torch failed with `WinError 1114` on `c10_cuda.dll`. This route needs exactly
the path and DLL changes the author has ruled out.

### Verified in WSL afterwards (author chose `SequentialWriter`, 2026-11-17)

*   **Verifier:** all four in-process bags pass the route C spike's WSL verifier **without
    `ros2 bag reindex`**: seven topics; log time = publish time = header stamp; frame ids;
    `bgr8`; the known-colour pixel; CameraInfo; pose in `map`; `/tf_static` left→right +0.38 m;
    `/tf`.
*   **QoS:** recorded per topic. `/tf_static` is stored as reliable, **transient-local**.
*   **`bag_to_capture`:** accepts the in-Kit bag (bundled, `ROS_DISTRO` unset) unchanged:
    "Completed extraction: 3 pairs", exit 0.
*   **Cost:** in Kit, 0.12–0.14 s for 3 frames, including pure-Python synthetic image
    construction. Default MCAP storage, about 2.18 MB per frame. Real cost is to be measured by
    the 40-pair benchmark.

**Decision (author): in-process `rosbag2_py.SequentialWriter`, kept simple.** Route C is the
fallback.

## Proposed evidence-collection plan (superseded by the measured results above)

This follows the author's order, but runs option 1 as a blocker check first. Four of its five
blockers are confirmed in source, and a full benchmark is useful only if they don't hold at
runtime.

1.  **Install** NVIDIA's `IsaacSim-ros_workspaces` (branch matching Isaac Sim 6.1) outside
    rov-sim, at a short path such as `C:\IsaacSim-ros_workspaces`. Run `pixi install` and
    `pixi run build` in `jazzy_ws`, and record the commit, `pixi.lock` hash, Python version, and
    whether `rosbag2_py` and `rosbag2_storage_mcap` are present.
2.  **Option 1 blocker check** (scratch scripts, timeline paused, as in rov-sim):
    *   whether `LdrColorROS2PublishImage` attached without the helper publishes per
        `orchestrator.step`;
    *   which stamp it carries;
    *   the encoding;
    *   whether `ros2 bag record -s mcap --use-sim-time` with a per-frame `/clock` gives
        log time = header stamp over at least 300 frames.

    Benchmark option 1 only if every blocker turns out not to hold.
3.  **Option 2 import check:** whether `rosbag2_py` imports inside `kit.exe` under the Pixi
    environment, with NumPy identity and the process image recorded, as in the route C spike.
4.  **Option 2 spike:** rewrite the route C spike's seven-topic, three-frame sample through
    `SequentialWriter` (`mcap`), inside a running `SimulationApp`. Check it with the same WSL
    verifier: no reindex needed, plus the QoS metadata now present.
5.  **Benchmark** option 2 against route C on 40 CameraSensor pairs, for pairs/s, `recording_ms`,
    bytes per frame, dropped frames, stamps, QoS and WSL playback.
6.  **Decide**, then revise `design_draft.md`. Route C stays the fallback.

Steps 1 to 5 change no rov-sim code. They need a native ROS 2 Jazzy installation outside the
repository, which the author has now authorised.
