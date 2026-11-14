# Isaac Sim 6.1 + OceanSim ROV inspection simulator

A standalone Windows application for an underwater inspection tank, a kinematic
OceanSim BlueROV and vehicle-mounted underwater stereo cameras. The original
pipes, fixtures, inspection panel, markers, crates, camera calibration and
change-detection trajectory are retained.

The validated OceanSim dependency is the Git submodule at
[`third_party/OceanSim`](third_party/OceanSim), forked from
[`umfieldrobotics/OceanSim`](https://github.com/umfieldrobotics/OceanSim) into
[`LuisCarvalho314/OceanSim`](https://github.com/LuisCarvalho314/OceanSim).
Its pinned revision is `53c45e5c3aafa3c6ce44a344b07a082a980633ef`.
The fork preserves upstream history, BSD-3-Clause licensing and attribution.
Do not replace this checkout with a separately installed OceanSim copy.

## Prerequisites and validated build

- Windows, PowerShell, Git with submodule support and an NVIDIA RTX GPU.
- Isaac Sim **6.1.0-rc.26+main.0.7c206f75.local**, using its bundled Python.
  Validation used Kit 110, DirectX 12, RTX Real-Time 2.0, Warp 1.16.0,
  an RTX 4070 Ti SUPER (16 GB) and NVIDIA driver 610.88.
  Other 6.1 builds need their own validation, particularly the experimental cameras.
- A working Isaac Sim installation with its supplied runtime dependencies,
  graphics access and writable runtime/user caches. Both packaged and source-build
  layouts are supported. Git does not distribute or build Isaac Sim.
- External OceanSim assets, including `Bluerov/BROV_low.usd`. Follow the upstream
  [asset download instructions](https://github.com/umfieldrobotics/OceanSim/blob/main/docs/subsections/installation.md).
  Obtain and comply with each asset's license. Downloaded assets and NVIDIA
  material libraries are not redistributed here. The upstream water MDL references
  NVIDIA's external material library; it must be reachable or cached by the runtime.
- Ordinary Python with NumPy for CPU tests and recording checks. Full offline
  photometric analysis additionally uses OpenCV and Pillow; tested versions are in
  [requirements-tools.txt](requirements-tools.txt). Use Isaac Sim's bundled
  packages for simulation; do not install these tools over its runtime packages.
- Optional MP4 previews need FFmpeg with `libx264` on PATH, or a configured
  `output.preview.ffmpeg_executable`.

## Fresh checkout and asset setup

```powershell
git clone --recurse-submodules https://github.com/LuisCarvalho314/rov-sim.git
Set-Location rov-sim
# For an existing checkout:
git submodule update --init --recursive
git submodule status

# Set these to your own installation and downloaded asset directories.
$env:ISAAC_SIM_PATH = 'D:/NVIDIA/isaacsim'
$env:OCEANSIM_ASSET_PATH = 'D:/assets/OceanSim_assets'
# Clear any old installed-extension override so the pinned checkout is selected.
Remove-Item Env:OCEANSIM_EXT_PATH -ErrorAction SilentlyContinue
. ./runtime.ps1
$runtime = Resolve-IsaacPython $env:ISAAC_SIM_PATH
```

`ISAAC_SIM_PATH` may name a packaged runtime or a source-build root containing
`_build/windows-x86_64/release/python.bat`. Launchers also accept an explicit
`-IsaacSimPath` or `-SimRoot`. Machine paths are never required in tracked configs.

The fork reads `OCEANSIM_ASSET_PATH` first. Alternatively persist registration
locally with `python third_party/OceanSim/config/register_asset_path.py 'D:/assets/OceanSim_assets'`.
The resulting `asset_path.json` is ignored. Asset downloads stay outside both repos.
No extension copying or modification of the Isaac Sim installation is required.

## Launch and reproduce change detection

```powershell
# Activate the pinned OceanSim extension, then close.
./launch.ps1 -RunArguments @('--headless','--startup-only')
# Interactive tank and original legacy stereo backend.
./launch.ps1 -RunArguments @('--config','configs/tank_photometric.yaml')
# Recommended experimental CameraSensor backend; two existing physical views.
./launch.ps1 -RunArguments @('--config','configs/tank_photometric.yaml','--camera-backend','camera-sensor')
# Original 60-frame trajectory per pass and 0.5 m crate relocation.
& $runtime -u run.py --headless --config configs/tank_photometric.yaml --camera-backend camera-sensor --experiment change_detection --frames 60 --record
```

`legacy` remains the default and fallback. `--camera-backend tiled` selects the
experimental two-view TiledCameraSensor, including the required pose flush.
All backends retain the original scene, optical calibration and OceanSim Warp
underwater equations. The selected photometric profile adds inspection lamps,
fixed ACES/ISO 1600 exposure and DLAA. `configs/tank_photometric_baseline.yaml`
retains the original lighting profile; `configs/tank_legacy.yaml` selects legacy RTX
photon caustics. The new camera APIs use version-specific internals and can change.

Each invocation creates a unique ignored directory under `outputs/`, containing
resolved config, calibration, render settings, scene snapshots, status, paired PNGs
and ground-truth poses. `--frames N` bounds frames per experiment pass. Experiments
default to 60 per pass; headless preview defaults to 120; interactive preview may
run until closed. The application owns time and rendering; timeline Play is unnecessary.
`--output-dir` selects a different root. `--record --preview-mp4` adds MP4 previews.

## Validation and benchmarks

```powershell
python -m pip install -r requirements-tools.txt
python -m unittest discover -s tests -q
& $runtime run.py --validate-only
# Known target, synchronization, radial range, disparity, PNG and pose checks.
& $runtime -u run.py --headless --config configs/validation_6_1.yaml --camera-backend camera-sensor --experiment change_detection --frames 12 --record --stereo-diagnostics
# Pass the actual unique run folder printed above:
python validate_recording.py outputs/YOUR_RUN_FOLDER
# Startup, legacy stationary/moving checks, three benchmarks and a separate profile.
./validate_6_1.ps1
# Original trajectory, selected photometry, all three backends and matched benchmarks.
& $runtime -u camera_backend_suite.py --root outputs/camera_reproduction
python compare_camera_backends.py outputs/camera_reproduction
python evaluate_photometry.py outputs/camera_reproduction/validation --profiles legacy camera-sensor tiled
& $runtime -u verify_camera_scene.py outputs/camera_reproduction
# Individual uninstrumented moving benchmark; keep diagnostics separate.
& $runtime -u run.py --headless --config configs/tank_photometric.yaml --camera-backend camera-sensor --experiment change_detection --benchmark --frames 100
```

Use fresh evidence roots; suites refuse to overwrite prior captures. Validate
`status.json`, the startup success marker and console errors as well as process
exit codes: Kit's Windows wrapper can return zero after a failure. Raw-buffer
diagnostics, image analysis and profiling run separately from throughput trials.
See [6.1 validation](docs/ISAAC_SIM_6_1_VALIDATION.md),
[photometric reproduction](docs/PHOTOMETRIC_6_1.md),
[camera comparison and synchronization](docs/RTX_CAMERA_6_1.md), and
[version-control validation](docs/REPRODUCIBILITY.md).

Matched historical moving measurements deliver **9.642 pairs/s** (legacy),
**12.612 pairs/s** (CameraSensor) and **10.784 pairs/s** (synchronized tiled).
The **20 Hz processed stereo target remains unmet**. These are hardware/build
specific measurements, separate from the short submodule smoke tests.
Experimental APIs, temporal denoising and stochastic rendering limit portability
and pixel repeatability. No thruster dynamics, SLAM, learned change detector,
real lens/housing refraction or real underwater calibration are implemented.
The experiment validates a 0.5 m relocation; 0.1 m detection accuracy is unproven.
The [5.0/6.1 assessment](docs/ISAAC_SIM_5_0_VS_6_1.md) is retained as historical
evidence; its 5.0 comparison was blocked by cross-linked installations.

## Configuration and extension loading

Edit [configs/tank.yaml](configs/tank.yaml), or pass `--config` for another profile.
Relative paths resolve against this repository and accept environment variables
such as `${ROV_OUTPUT_ROOT}`. Supplied configs use JSON-style YAML, readable before
Kit starts; other YAML requires PyYAML in the launching interpreter.

OceanSim lookup order is `--oceansim-ext`, `OCEANSIM_EXT_PATH`,
`runtime.oceansim_extension`, **the pinned `third_party/OceanSim` checkout**, then
installation `extsUser/OceanSim` fallbacks. Explicit overrides are available for
development; reproducibility requires the pinned checkout. The extension path
must contain `config/extension.toml`, and must not point to the asset directory.
Startup verifies Kit loaded the requested directory and rejects unresolved or
ambiguous registrations. Configure assets independently using `OCEANSIM_ASSET_PATH`.

## Coordinate frames and calibration

The stage uses metres and Z up. `/World/BlueROV` is the carrier with **+X forward, +Y left, +Z up**. Moving it moves both the model reference and the stereo rig. Asset units are converted to metres; a Y-up asset is rotated into Z-up. Additional visual-model translation, rotation and scale belong in `robot.model`, independently of the camera mount. Referenced rigid bodies are disabled and the carrier is kinematic. No thrusters or hydrodynamics are simulated.

```text
/World/BlueROV                    configurable pose / trajectory
  /ModelAlignment/UpAxis/Asset    OceanSim Bluerov/BROV_low.usd reference
  /StereoRig                     configurable mount in body coordinates
    /Left                        local x = -0.19 m
    /Right                       local x = +0.19 m
```

USD cameras look along **−Z** with **+Y image up**. Default mount rotation `[90, 0, -90]` maps camera −Z to vehicle +X, camera +Y to vehicle +Z, and camera +X to vehicle −Y. Both optical axes are parallel. Exported optical frames use **X right, Y down, Z forward**. Mount rotation uses USD `rotateXYZ`, in degrees; translations/baseline are metres. Mount translation is the midpoint between cameras.

Startup checks asset units/up axis, plausible model bounds, submerged camera origins, baseline, parallel axes, identical initialized sensor intrinsics and agreement with configuration. Each captured pair checks fixed camera-to-body transforms. **Actual model heading and mount clearance from the housing still require visual inspection on Windows.** Bounds alone do not establish heading or lens occlusion.

`stereo_calibration.json` exports both K matrices, baseline, pinhole distortion values and `T_body_optical`. Matrices use column vectors: `p_parent = T_parent_child @ p_child`. Defaults give fx = fy ≈ 537.143 px, cx = 376 px, cy = 240 px. This describes virtual pinhole cameras; there is no lens/housing refraction or real underwater calibration model.

OceanSim 1.0.0's `UW_param` docstring and implementation disagree about attenuation/backscatter slice ordering. The adapter supplies `UW_yaml_path` with **named fields**, preserving the installed version's actual defaults. Processed images use that version's `_uw_frame` buffer; this access and lifecycle handling are confined to `sensors/stereo.py`.

## Water and RTX caustics

`WaterSurface` creates OceanSim's mesh and refractive MDL on the active stage. One instance survives the run. Optional `deform()` calls use logical simulation time; both passes reset to the same wave phase. Zero amplitude preserves the flat grid, avoiding OceanSim's positive amplitude clamp.

Windows defaults to **DirectX 12**: `--/app/vulkan=false` reaches `SimulationApp` **before graphics startup**. `runtime.renderer` defaults to `RealTimePathTracing`; `configs/tank_legacy.yaml` selects `RaytracedLighting` with photon caustics. This installed Isaac Sim 5.0 / Kit 107 build crashes when only the RTX 2.0 mode flag is enabled. The startup code uses [NVIDIA's Isaac Sim 5.0 recipe](https://forums.developer.nvidia.com/t/enable-new-rtx-realtime-2-0-in-simulationapp/342829/9): it enables both real-time modes and selects `RealTimePathTracing` in persistent and active Kit settings before viewport creation. These settings agree with `SimulationApp`'s renderer argument. RTX 2.0 uses Kit's fast shutdown after the application's explicit camera, water and Replicator cleanup; graceful shutdown caused a process access violation on this build. DLSS antialiasing is disabled for this comparison and Frame Generation is not enabled. Use `--backend vulkan` for a separate alternative-backend validation run. Other nonrenderer launch flags go in `runtime.extra_args` or, for example, `--kit-arg=--/renderer/activeGpu=0`.

Legacy photon caustics use the installed `WaterSurface.set_caustics()` API and source-verified **`light:enableCaustics`** property. The standalone app replaces the original builder's speculative `inputs:enableCaustics`. A multiplier of 40 means approximately 40 × 1024 photons per area light. Additional `rtx.settings` keys must already be registered by the running build; unknown paths fail.

`render_validation.json` records requested renderer, renderer setting readback, backend setting, RTX 2.0 mode flag, DLSS antialiasing, subframes, legacy photon settings and whether a processed stereo pair was acquired. A frame proves the capture path ran; it does not prove physical refraction, attenuation or caustics are visually correct. Inspect recorded PNGs and the Kit graphics API log. Photon caustics are supported only in the legacy profile. NVIDIA documents these controls for [RTX Real-Time Legacy](https://docs.omniverse.nvidia.com/materials-and-rendering/latest/rtx-renderer_rt_legacy.html#caustics).

Legacy physical RTX caustics arise from light transport through refractive water. `UW_Camera` separately applies image-space, depth-based attenuation and backscatter. An ordinary viewport can show the physical surface/caustics without the underwater appearance of processed camera streams. Water is a visual surface; no fluid volume or buoyancy is simulated.

## Experiments and output

Each invocation creates `outputs/<UTC timestamp>_<unique suffix>/`, or a run directory under `--output-dir`. Existing `generated_tank` files, older captures and prior runs are preserved.

```text
config.json                     resolved configuration
underwater_parameters.json      named OceanSim rendering parameters
stereo_calibration.json          initialized calibration / fixed extrinsics
render_validation.json          requested/read-back rendering settings
scene_manifest.json             experiment and asset information
status.json                     initializing/running/complete/failed/interrupted
tank_before_rtx.usda            reference snapshot at initial trajectory pose
tank_after_rtx.usda             displaced-crate snapshot, for experiments
before/poses.jsonl              frame, logical time and ground truth
before/left/000000.png          present with --record
before/right/000000.png
before/stereo_preview.mp4     with --record --preview-mp4
after/...                      second experiment pass
after/stereo_preview.mp4      with --record --preview-mp4 in experiments
comparison_preview.mp4        before/after left-camera comparison in experiments
```

Stereo previews place left and right frames side by side. The default 752 × 480 source yields a 1504 × 480 MP4. The comparison preview places corresponding before and after **left-camera** frames side by side, also 1504 × 480 at the default resolution. FFmpeg runs after all PNGs and pose files have been written. Missing indices, mismatched pass timestamps and FFmpeg errors fail preview generation and are recorded in `status.json`; existing PNGs and metadata remain available. Existing MP4s are not overwritten.

H.264 compression is for visual inspection only. Use the original lossless PNGs and `poses.jsonl` for scientific analysis. MP4s preserve the configured spatial resolution but are lossy, and their frame rate can differ from the simulation rate. Preview generation requires installed FFmpeg/libx264 and adequate free disk space; it does not create previews for an unbounded interactive run until that recording ends.

The experiment constructs one stage. Each pass sets the crate parent translation, resets the vehicle trajectory and wave phase, exports the initial scene, and warms rendering with the same number of frames. Snapshots share background, initial vehicle pose and calibration. BlueROV and MDL references remain external, so snapshots require those assets to stay available.

Waypoints specify vehicle position and XYZ rotation at integer frames. Translation is linear; rotation uses shortest per-axis Euler interpolation. The last waypoint is held. This is a minimal repeatable trajectory, not a general rotational spline/controller. `--frames` truncates/extends capture without changing waypoint timing.

Logical time is `frame / simulation.fps`. Poses/wave phase are held while `rep.orchestrator.step(delta_time=0, wait_for_render=True)` renders subframes, then both `UW_Camera` streams are processed without an intervening step. Both must be ready before a sample is recorded, with bounded retries. Ground truth includes `T_world_body`, both `T_world_optical` matrices and `T_world_changed_object`.

PNG names and pose records share frame indices; image paths are relative to their pass directory. Depth is used internally by OceanSim and is not saved as stereo input. Pose records are saved even without `--record`; PNG recording is optional. Standard-library PNG encoding and synchronous writes prioritize correctness over throughput.

Geometry, trajectory, phase and seed are deterministic. RTX photon sampling, denoisers and temporal history can still differ across passes/machines; bitwise repeatability is not promised. Defaults disable antialiasing to reduce temporal image history, but caustic filtering may retain its own history. Evaluate warmup and quality for each experiment.

## Architecture and extension points

| Module | Responsibility |
| --- | --- |
| `run.py`, `startup.py` | CLI, ordered app initialization, extension loading and final shutdown |
| `config.py`, `configs/tank.yaml` | Parameters, paths and early validation |
| `application.py` | One stage, rendering, pass sequencing and cleanup |
| `scenes/tank.py`, `equipment.py`, `primitives.py` | Tank, original equipment/crates and USD helpers |
| `robots/bluerov.py` | Asset reference, units/up-axis alignment and kinematic carrier |
| `sensors/stereo.py` | Parallel cameras, calibration and `UW_Camera` adapter/cleanup |
| `environments/underwater.py` | Surface, deformation and verified RTX controls |
| `experiments/change_detection.py` | Crate displacement and repeatable trajectory |
| `recording.py`, `preview.py` | Unique directories, metadata, poses, paired PNGs and post-capture MP4s |

Add objects in `scenes/equipment.py` using `box`, `pipe` or USD references. Group meshes for each movable object under one Xform and change that parent between passes. Builders run once; do not add transform operations or recreate geometry in the render loop. Simple primitives/display colours preserve the original appearance; production inspection surfaces may need textures.

Add robots under `robots/` with a metre-based carrier and separate model alignment/sensor mount. Add scenes/sensors by wiring their creation into `application.run()` after startup, extending CLI choices as needed. Sensors need explicit initialization and cleanup using installed APIs. Add experiments as simple pass-setup/trajectory functions under `experiments/`, register a CLI choice and select their sequence in `application.py`; export new ground truth via `PoseRecorder`.

`rov_tank_builder.py` remains an unchanged legacy Script Editor template for comparison; the standalone app never imports it. Six reusable geometry/helper functions match the original Python AST exactly. No ROS 2 workspace is modified.

## Checks and troubleshooting

CPU checks using ordinary Python with NumPy, or the configured bundled Python:

```powershell
& $python run.py --validate-only
& $python -m unittest discover -s tests -v
& $python -m compileall -q run.py config.py startup.py application.py recording.py scenes robots sensors environments experiments
```

`--validate-only` validates configuration without importing Kit or requiring OceanSim; it does not test assets or GPU rendering. See [source/API evidence](docs/source_validation.json) and [Windows runtime checks](docs/VALIDATION.md).

| Symptom | Action |
| --- | --- |
| `isaacsim`/`carb`/`omni` import failure | Use the chosen installation's `python.bat`. Ordinary Python is for CPU checks. |
| Missing `python.bat` | This source build uses `_build\windows-x86_64\release\python.bat`; the launcher detects it. |
| OceanSim missing/wrong copy | Set `OCEANSIM_EXT_PATH` to the manifest directory; remove duplicate Kit registrations. |
| Missing assets | Check OceanSim registration and `Bluerov/BROV_low.usd`. |
| Unsupported API | Compare installed source/version to `docs/source_validation.json`; do not guess methods/keywords. |
| Headless fails | OceanSim still loads UI extension dependencies. Check extension/CUDA/Replicator errors; offscreen RTX requires a supported GPU. |
| Black/empty streams | Confirm D3D12 in logs, submerged cameras, clear housing/mount and working RTX/Replicator. Try bounded GUI mode and increase warmup/readiness for compilation if needed. |
| Model size/heading wrong | Inspect manifest units/bounds, then adjust `robot.model` alignment/scale against the actual asset. |
| Plain viewport lacks underwater tint | Inspect OceanSim preview windows or recorded PNGs; attenuation is separate from the water material. |
| No visible legacy caustics | Select `tank_legacy.yaml`; check graphics API/render mode, refractive MDL, `light:enableCaustics`, light placement and floor illumination. Compare caustics on/off runs. |
| Background images differ | Match config, trajectory, seed, phase and warmup; evaluate residual photon/denoiser history separately. |

Sources: [OceanSim UW_Camera](https://github.com/umfieldrobotics/OceanSim/blob/main/isaacsim/oceansim/sensors/UW_Camera.py), [WaterSurface](https://github.com/umfieldrobotics/OceanSim/blob/main/isaacsim/oceansim/watersurface/WaterSurface.py), [Isaac Sim 5.0 SimulationApp](https://docs.isaacsim.omniverse.nvidia.com/5.0.0/py/source/extensions/isaacsim.simulation_app/docs/index.html). Installed sources take precedence over newer upstream APIs.
# Benchmarking processed stereo throughput

Run a bounded benchmark with the normal RTX, OceanSim and stereo path:

```powershell
.\launch.ps1 -RunArguments @('--scene', 'tank', '--headless', '--benchmark', '--frames', '300')
```

The standard tank config does not record PNGs. Benchmark mode skips pose and image recording in that case and disables MP4 previews. Use `--record` to include PNG compression, disk writes and poses. Use `--record --preview-mp4` to time post-capture FFmpeg encoding. A custom config with `output.record_images=true` also records in benchmark mode. `--config` accepts alternative JSON-style YAML files.

The run directory contains `benchmark.json` and `benchmark_frames.csv`, alongside the resolved config, render validation and status files. Progress prints every 100 pairs. Effective pairs/s is measured wall-clock throughput across completed CPU stereo pairs, including retries and gaps between measured iterations. The 50 ms deadline uses individual acquisition latency. Simulation-time 30 FPS and GUI viewport FPS are separate measures.

Benchmark mode creates its run directory before starting Kit and supervises Kit in a child process. `status.json` records the process exit code, including a native renderer crash before `SimulationApp` returns; `kit_console.log` keeps the child console output. A crash is reported as a failed run even if Kit wrote a partial `benchmark.json` before failing during shutdown.

Add `--profile-python` to a benchmark command to save `python_profile.pstats` before Kit shuts down. This profiles application setup, warmup and capture; use `pstats` to inspect call counts and time in OceanSim, Replicator and Python I/O. Profiling adds overhead, so use the ordinary benchmark for throughput comparisons.

For a 100-frame RTX 2.0 stage comparison, use the same A profile for all three runs:

```powershell
python benchmark_profiles.py
.\launch.ps1 -RunArguments @('--headless','--benchmark','--frames','100','--config','outputs/A.yaml','--profile-tracy','--benchmark-mode','render-only')
.\launch.ps1 -RunArguments @('--headless','--benchmark','--frames','100','--config','outputs/A.yaml','--profile-tracy','--benchmark-mode','no-readback')
.\launch.ps1 -RunArguments @('--headless','--benchmark','--frames','100','--config','outputs/A.yaml','--profile-tracy','--benchmark-mode','full')
```

`--profile-tracy` enables the installed Kit Tracy extension and captures `capture.tracy` in each run directory. The CPU zones separate the blocking stereo render step, RGB/depth annotator fetch, OceanSim RGB and depth kernel submission, and CPU readback. View the trace with the Tracy viewer supplied by Isaac Sim. Add `--profile-warp-gpu` when numeric Warp CUDA kernel, copy and memset activity durations are needed; this explicitly synchronizes at the **end** of the measured run and adds profiling overhead. It is off by default. Tracy's RTX/DX12 GPU timeline is not included in Warp's CUDA totals.

Render-only counts blocking stereo render steps; no-readback submits both OceanSim RGB/depth kernels without calling `.numpy()` and reports a final GPU drain separately; full counts acquired CPU stereo pairs. Render-only and no-readback acquire one normal OceanSim stereo pair **after** measured frames to validate dimensions and nonblack left/right images. The diagnostic OceanSim path mirrors the installed OceanSim 1.0.0 `UW_Camera.render()` kernel calls, while ordinary runs continue to use that method directly. All three modes retain the same cameras, scene, trajectory, water animation, warmup, backend, renderer and image quality settings. The stage timers are CPU wall times: `underwater_processing_ms` measures GPU submission, and `gpu_readback_ms` includes transfer and any wait for pending GPU work. Use the trace to locate GPU stalls; do not interpret either timer as pure GPU execution time.

Generate comparable profiles and run each under the same machine and driver conditions:

```powershell
python benchmark_profiles.py
.\launch.ps1 -RunArguments @('--scene','tank','--headless','--benchmark','--frames','300','--config','outputs/A.yaml')
.\launch.ps1 -RunArguments @('--scene','tank','--headless','--benchmark','--frames','300','--config','outputs/B.yaml')
.\launch.ps1 -RunArguments @('--scene','tank','--headless','--benchmark','--frames','300','--config','outputs/C.yaml')
python compare_benchmarks.py --latest-profiles outputs
```

The A–C profiles use identical geometry, stereo calibration, trajectory, warmup, underwater processing and one RTX subframe. A uses RTX 2.0 with caustics off; B uses legacy RTX with caustics off; C uses legacy RTX with photon caustics on. All disable DLSS and PNG recording. Each command processes 300 stereo pairs. `benchmark.json` and the comparison output label the renderer. Do not commit measured results unless needed for a separate report.

`--latest-profiles outputs` locates the newest completed 300-pair run for each A/B/C profile. It reports a missing profile if any run has not completed. You can also pass three actual run directories or `benchmark.json` files directly; angle-bracket names in examples are placeholders and must never be typed literally in PowerShell.

In an ordinary benchmark without `--profile-tracy`, `render_ms` is the blocking `rep.orchestrator.step(wait_for_render=True)` wall time. `annotator_acquisition_ms` covers the external RGB/depth readiness calls. OceanSim's `UW_Camera.render()` fetches those annotators again, launches RGB and degraded-depth Warp kernels, then calls `.numpy()` on both results. Those internal fetches, GPU processing and CPU readback are measured together as `processing_readback_combined_ms`; `underwater_processing_ms` and `gpu_readback_ms` are explicitly unavailable. This avoids attributing asynchronous CUDA work to a Python call without a GPU synchronization boundary. `recording_ms` includes pose validation and, when enabled, PNG and pose writes. FFmpeg is timed separately after capture. Stage timing sums need not equal total acquisition because Python and pose bookkeeping also consume time.

Compare instrumented runs with an ordinary benchmark because tracing and GPU activity timing can add overhead. For a finer RTX/DX12 breakdown, inspect the captured Tracy GPU timeline; Warp timing covers CUDA work only. A long CPU readback zone may be a wait for earlier GPU work rather than a long GPU copy.
