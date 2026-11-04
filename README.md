# Isaac Sim + OceanSim ROV inspection simulator

A standalone Python application for an underwater inspection tank, a kinematic OceanSim BlueROV, and vehicle-mounted underwater stereo cameras. Launch from PowerShell using Isaac Sim's bundled Python. The original pipes, fixtures, inspection panel, markers and crates are preserved from `rov_tank_builder.py`.

Implementation and CPU checks are complete. Two earlier Windows runs completed 10 and 30 stereo pairs, but neither recorded PNGs; the graphics API and physical caustics still need visual confirmation. A later validation attempt could not read part of the Isaac Sim installation in this restricted session. See the [latest runtime validation record](RUNTIME_VALIDATION_2026-11-04.md) and [original validation note](docs/VALIDATION.md).

## Prerequisites and inspected versions

- Windows and an NVIDIA RTX GPU/driver compatible with Isaac Sim 5.0 and OceanSim's CUDA/Warp rendering.
- Isaac Sim 5.0 bundled Python. The inspected local source build reports `5.0.0-rc.45+mr.0.1791e148.local`; it is not the final 5.0 release build.
- Existing OceanSim installation. Its inspected manifest reports **1.0.0**. The actual `UW_Camera`, `WaterSurface`, asset registration and local Isaac Sim/Kit sources determine this implementation. No OceanSim source files are modified.
- OceanSim's registered assets, including `Bluerov/BROV_low.usd`, and its `demo/water_material/Water.mdl` material.
- Packages already required by Isaac Sim/OceanSim: NumPy, Warp, Replicator and PyYAML. No separate virtual environment, C++, ROS 2 integration, OpenCV or image-writing package is required.

The active extension found here is `C:\isaacsim\_build\windows-x86_64\release\extsUser\OceanSim`. An identical camera implementation exists in `C:\isaacsim-backup\extsUser\OceanSim`. Prefer the active extension. The old stereo preview was read from `C:\rov_sim\rov_stereo_preview.py`; that directory and all existing generated scenes are untouched.

## Windows launch

From PowerShell:

```powershell
Set-Location C:\isaacsim-environments

# This machine has a source build; use its release runtime.
$python = 'C:\isaacsim\_build\windows-x86_64\release\python.bat'
$env:OCEANSIM_EXT_PATH = 'C:\isaacsim\_build\windows-x86_64\release\extsUser\OceanSim'

# Phase 1: start Kit, register/enable OceanSim, then close.
& $python run.py --startup-only

# Tank, BlueROV and two OceanSim processed-image preview windows.
& $python run.py --scene tank --mode interactive

# Short GUI smoke test; exits after 10 stereo pairs.
& $python run.py --scene tank --mode interactive --frames 10

# Offscreen RTX rendering; no OceanSim preview windows.
& $python run.py --scene tank --mode headless --frames 30

# Repeatable before/after inspection and paired PNG/pose capture.
& $python run.py --scene tank --experiment change_detection --mode headless --record
```

For a packaged installation with `python.bat` directly in `C:\isaacsim`:

```powershell
C:\isaacsim\python.bat run.py --scene tank --mode interactive
```

Configure a different installation through the launcher:

```powershell
$env:ISAAC_SIM_PATH = 'D:\NVIDIA\isaacsim'
.\launch.ps1 -RunArguments @('--scene', 'tank', '--mode', 'interactive')

# Or pass a root directly; source-build layouts are detected.
.\launch.ps1 -IsaacSimPath 'C:\isaacsim' -RunArguments @('--headless', '--frames', '10')
```

The launcher defaults to `C:\isaacsim` only when neither `-IsaacSimPath` nor `ISAAC_SIM_PATH` is supplied. Direct invocation must use the selected installation's bundled Python; configuration cannot switch an already running interpreter.

Interactive preview runs until the application closes or Ctrl+C is pressed. `--frames N` bounds a run. Headless preview defaults to 120 frames. An experiment defaults to 60 frames **per pass**, then exits, including in GUI mode. `--frames 0` is allowed only for unbounded interactive preview. The application controls rendering and time; pressing timeline Play is unnecessary. Ordinary preview starts at `robot.position_m` and `robot.rotation_xyz_deg`; configured trajectories are used for experiments.

## Configuration and extension loading

Edit [configs/tank.yaml](configs/tank.yaml), or use `--config configs/my_tank.yaml`. The supplied file uses JSON-style YAML, which is valid YAML and readable with the standard library **before** Kit loads its packages. Conventional YAML works when PyYAML is already importable before startup.

Relative paths resolve against this repository, even from another working directory. Paths accept environment variables such as `${ROV_OUTPUT_ROOT}`. In JSON-style YAML, use forward slashes or escaped backslashes for Windows paths.

| Configuration | Controls |
| --- | --- |
| `runtime` | Backend, renderer, optional extension directory/Kit experience and extra Kit arguments |
| `tank`, `lighting` | Dimensions, thickness, colours, overhead light positions, size and intensity |
| `robot` | Registered asset-relative filename, vehicle pose, visual-model alignment/scale |
| `stereo` | Resolution, baseline, focal/aperture ratio, clipping, preview and mounting pose |
| `underwater` | Named attenuation/backscatter values, range and depth noise |
| `water` | Surface height/dimensions/grid, shadow casting and wave parameters |
| `rtx` | Photon budget/bounces/filtering and registered RTX setting overrides |
| `changes` | Reference crate position and displacement vector |
| `experiment` | Frames per pass and frame-indexed vehicle waypoints |
| `output` | Output root and optional paired PNG recording |

Examples of individual edits in the existing file: set `water.wave.animated` to `true`, `water.wave.amplitude_m` to `0.03`, `underwater.atten_coeff` to `[0.12, 0.06, 0.03]`, or `output.directory` to `"${ROV_OUTPUT_ROOT}/inspection"`. When changing tank dimensions, resize `water.size_m` and check fixed equipment: its preserved fixture coordinates are designed for the 8 × 5 m tank and do not automatically rescale.

OceanSim's directory is selected in this order: `--oceansim-ext`, `OCEANSIM_EXT_PATH`, `runtime.oceansim_extension`, then `extsUser/OceanSim` under the runtime's `ISAAC_PATH`/configured `ISAAC_SIM_PATH`, including source-build layout. Pass the **extension directory containing `config/extension.toml`**, not the assets directory. The app registers its parent search path, checks which exact extension Kit resolved and enables it synchronously. Duplicate registrations produce an error.

BlueROV assets resolve through OceanSim's existing `get_oceansim_assets_path()` registration. If missing, use OceanSim's registration command once with your asset location:

```powershell
& $python "$env:OCEANSIM_EXT_PATH\config\register_asset_path.py" 'C:\isaacsim-assets\OceanSim_assets'
```

This is an installation repair, not part of startup. The application does not rewrite extension source or asset registration files.

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

Windows defaults to **DirectX 12**: `--/app/vulkan=false` reaches `SimulationApp` **before graphics startup**, with legacy `RaytracedLighting`. Installed `.kit` files are untouched. Use `--backend vulkan` for a separate alternative-backend validation run. Other launch flags go in `runtime.extra_args` or, for example, `--kit-arg=--/renderer/activeGpu=0`.

Photon caustics use the installed `WaterSurface.set_caustics()` API and source-verified **`light:enableCaustics`** property. The standalone app replaces the original builder's speculative `inputs:enableCaustics`. A multiplier of 40 means approximately 40 × 1024 photons per area light. Additional `rtx.settings` keys must already be registered by the running build; unknown paths fail.

`render_validation.json` records requested backend, `/app/vulkan`, renderer, bound material and photon settings. Readback shows settings were applied; it **does not prove the GPU/backend produced physical caustics**. Inspect the Kit log's actual graphics API, water refraction and illuminated floor. Do not infer Vulkan/DX12 equivalence from matching settings. NVIDIA documents these photon controls for [RTX Real-Time Legacy](https://docs.omniverse.nvidia.com/materials-and-rendering/latest/rtx-renderer_rt_legacy.html#caustics).

Physical RTX caustics arise from light transport through refractive water. `UW_Camera` separately applies image-space, depth-based attenuation and backscatter. An ordinary viewport can show the physical surface/caustics without the underwater appearance of processed camera streams. Water is a visual surface; no fluid volume or buoyancy is simulated.

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
after/...                      second experiment pass
```

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
| `recording.py` | Unique directories, metadata, poses and paired PNGs |

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
| No visible caustics | Check graphics API/render mode, refractive MDL, `light:enableCaustics`, light placement and floor illumination. Compare caustics on/off runs. |
| Background images differ | Match config, trajectory, seed, phase and warmup; evaluate residual photon/denoiser history separately. |

Sources: [OceanSim UW_Camera](https://github.com/umfieldrobotics/OceanSim/blob/main/isaacsim/oceansim/sensors/UW_Camera.py), [WaterSurface](https://github.com/umfieldrobotics/OceanSim/blob/main/isaacsim/oceansim/watersurface/WaterSurface.py), [Isaac Sim 5.0 SimulationApp](https://docs.isaacsim.omniverse.nvidia.com/5.0.0/py/source/extensions/isaacsim.simulation_app/docs/index.html). Installed sources take precedence over newer upstream APIs.
