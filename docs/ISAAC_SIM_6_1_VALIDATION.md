# Isaac Sim 6.1 stereo ROV validation — 2026-11-14

**PASS:** the repository's existing `run.py` application, inspection tank, BlueROV, stereo adapter, OceanSim processing, deterministic trajectory and PNG/pose recorder ran successfully under Isaac Sim **6.1.0-rc.26+main.0.7c206f75.local**. This validation exercises the actual application and recording loop, beyond the successful independent OceanSim single-camera and stereo-builder diagnostics inspected first.

Windows, DirectX 12, RTX `RealTimePathTracing`, AA-off, one RT subframe, one NVIDIA GeForce RTX 4070 Ti SUPER (16 GB), driver **610.88**, Warp **1.16.0**, `cuda:0`, OceanSim **1.0.0**. The normal standalone viewport remains present. No performance or image-quality optimization was applied.

## Reproduction

From PowerShell in `C:\rov-sim`:

```powershell
.\validate_6_1.ps1
```

Defaults: runtime selected through `ISAAC_SIM_PATH` or `-SimRoot`, pinned OceanSim checkout, 30 warmup frames, three stationary pairs, two 12-pair moving passes, three separate 100-pair uninstrumented benchmarks, then one separate 100-pair Tracy/Warp/Hydra profile. Every invocation creates a new ignored `outputs/validation_6_1_<UTC>/` directory. The runner requires process completion, application status, fresh run directories and error-free console logs; recording validation additionally decodes and compares saved PNG/NPZ data. The offline verifier uses the local `python` with NumPy. `-SimRoot`, `-BenchmarkFrames`, `-Repeats` and `-SkipProfiling` are supported. Keep 100 or more measured frames and three repetitions for baseline comparisons; short harness checks are not performance baselines.

The launcher itself was executed with `-BenchmarkFrames 10 -Repeats 2 -SkipProfiling` and printed `ISAAC SIM 6.1 STEREO VALIDATION PASS`; fresh evidence is in `outputs/validation_6_1_20261114T130119Z/` and `outputs/validation_6_1/reproduction_check.log`. The full 100-pair measurements and profile below were run separately through the same application commands.

Individual runs use the original entry point:

```powershell
. ./runtime.ps1
$runtime = Resolve-IsaacPython $env:ISAAC_SIM_PATH
& $runtime -u run.py --headless --startup-only
& $runtime -u run.py --headless --frames 3 --record --stereo-diagnostics --config configs/validation_6_1.yaml
& $runtime -u run.py --headless --frames 12 --experiment change_detection --record --stereo-diagnostics --config configs/validation_6_1.yaml
& $runtime -u run.py --headless --benchmark --frames 100 --config configs/validation_6_1.yaml
& $runtime -u run.py --headless --benchmark --frames 100 --profile-tracy --profile-warp-gpu --config configs/validation_6_1.yaml
# Supply the actual run directory printed by the application:
python validate_recording.py outputs/validation_6_1/final_moving/20261114T125607Z_d2850de9
```

`configs/validation_6_1.yaml` retains the original tank, asset, water, optics and underwater parameters. It uses 30 warmup frames, disables preview windows and shortens the existing trajectory to frames 0–11, from `(-3.1,0,1.35)` to `(-2.6,0.12,1.40)` m and XYZ rotation `(0,0,0)` to `(1,-2,5)` degrees. Motion uses the existing interpolation and change-detection passes. Plain benchmarks hold the original vehicle pose; they still update the original animated water.

## Diagnosis and minimal changes

The first unchanged `python.bat` attempt failed before Python: its executable-copy setup could not write `kit/python/kit.exe` in the restricted session. Repeating with installation-write permission allowed the existing launcher to create its normal executable copy. Unmodified `run.py --startup-only` then activated OceanSim and exited successfully. No Isaac Sim rebuild, source patch or alternate simulation loop was required.

The first unchanged stationary run loaded the tank and BlueROV, then rejected AA readback **3** despite `SimulationApp(anti_aliasing=0)`. Installed `simulation_app.py` and the successful OceanSim diagnostics confirmed the post-bootstrap setting behavior. The compatibility patch in `environments/underwater.py` permits AA-off through `/rtx-transient/post/aa/limitedOps=false` when registered, then reapplies `/rtx/post/aa/op=0`. Validation verifies it survives warmup and capture. Cameras and kernels worked unchanged after this patch.

The application now delivers timeline STOP with camera graphs alive before teardown, following the installed camera lifecycle evidence. It retains the existing explicit annotator cleanup. Optional diagnostic hooks surround the existing render/capture loop. `stereo_diagnostics.py` adds a known target, captures raw buffers without changing them, checks geometry/processing, and takes inspection views after recording. `validate_recording.py` checks the actual saved files. Profiling retains the existing diagnostic kernel-call path and adds named Warp activity totals and Hydra GPU snapshots; ordinary benchmarks still call `UW_Camera.render()` normally.

All pre-existing user changes were preserved. OceanSim production files were never edited; **48 source/material SHA-256 hashes** match before and after, including `UW_Camera.py`. Hash evidence is under ignored `outputs/validation_6_1/ocean_hashes_{before,after}.json`. The legacy camera API remains in use. Recording layout, scene builders, asset references, kinematic carrier, baseline and ordinary rendering kernels are preserved.

## Correctness results

| Requirement | Observed result |
| --- | --- |
| Startup and activation | Existing standalone `SimulationApp` and OceanSim startup marker; process exited 0 |
| Tank and vehicle | Original 8 × 5 × 3 m tank/equipment and registered `Bluerov/BROV_low.usd`; model AABB 0.457200 × 0.566018 × 0.253852 m; wet and labelled dry inspection images reviewed |
| Both cameras | Independent CUDA RGBA uint8 `(480,752,4)` and clean radial range float32 `(480,752)`; underwater RGBA and degraded depth valid |
| Geometry | Measured baseline approximately 0.379999995 m, parallel axes; fixed body-to-optical transforms within 1e-6 throughout motion |
| Intrinsics | Both `fx=fy≈537.142883`, `cx=376`, `cy=240`; 15/21 focal/aperture ratio; expected K verified by the existing adapter |
| Synchronization | Matching left/right `ReferenceTime`; both RGB and depth graph compute counts increase each pair; no update during acquisition/processing; timeline held at requested logical time |
| Underwater processing | Every RGB value checked against installed attenuation/backscatter equation, error ≤1.01 levels including uint8 truncation; alpha preserved; sigma-zero degraded range and rejection mask checked |
| Raw preservation | Raw RGB and clean range unchanged by both processing calls; left/right outputs do not alias |
| Motion and calibration | Both camera reprojections and independent tank-wall ranges agree with pose at all 24 moving samples; camera products stay fixed, no reinitialization |
| Recording | Three stationary and 24 moving PNG pairs; matching indices/timestamps/poses; saved underwater PNGs exactly equal corresponding NPZ arrays; before/after vehicle paths identical and crate displacement correct |

The diagnostic target is an emissive magenta box added to the actual tank; original lighting is unchanged. Its visible front-face centre is `(1.34,-0.30,1.65)` m. Correspondence is measured from the largest magenta component in each raw image independently of predicted pixel coordinates. Expected disparity is `fx * baseline / optical_Z`, with 1.25 px tolerance; epipolar row mismatch must be below 0.75 px and reconstructed depth error below 3%. Target and bare east-wall radial ranges are checked to 0.025 m using pixel-centre rays, including the off-axis range increase.

| Pose | Expected / measured disparity | Known / stereo optical Z |
| --- | --- | --- |
| Stationary / motion start | 51.15646 / 51.50000 px | 3.99000 / 3.96338 m |
| Motion end | 59.25359 / 59.08176 px | 3.44476 / 3.45478 m |

Left target radial range changes from **4.027252 to 3.574733 m**, agreeing with the independently predicted ray-plane intersection. Both passes produce the same geometry results. The existing pose recorder separately validates fixed extrinsics and stores full world/body/optical matrices. ReferenceTime may repeat for held-time rendering; graph recomputation and motion reprojection provide the additional freshness evidence. This establishes simulation synchronization, not physical exposure synchronization.

All final stationary, moving, uninstrumented benchmark and instrumented logs contain **zero `[Error]` entries, Python tracebacks or invalid-attribute cleanup messages**. Processes exited 0 and application states are complete. The existing **33 CPU tests passed**. Native wrapper exit codes alone are insufficient: the initial AA-failed capture returned wrapper code 0 but correctly wrote failed application status.

## Performance baseline

Three independent processes each warmed 30 rendered/processed pairs and measured 100 complete stereo pairs. No diagnostic target, overview product, raw-GT downloads, PNG encoding, tracing or CUDA-event profiling existed in the uninstrumented measured loops. Scene, original lights, animated water, resolution, renderer and camera settings match across repetitions. Both RGB and degraded depth kernels/readbacks execute for both cameras.

| Repetition | Fully processed pairs/s | Mean pair latency | p95 latency |
| --- | ---: | ---: | ---: |
| 1 | 11.7339 | 84.7459 ms | 94.0216 ms |
| 2 | 11.9868 | 82.9478 ms | 92.2601 ms |
| 3 | 11.7589 | 84.5555 ms | 94.1319 ms |

Aggregate sustained throughput over all measured iteration wall time: **11.8247 stereo pairs/s**. Aggregate acquisition latency: mean **84.0831 ms**, median **82.1206 ms**, p95 **93.6456 ms**, maximum **144.5615 ms**. Readiness retries: **0**. The existing benchmark's 20 Hz deadline is missed by all measured frames. Logical simulation time remains 30 Hz and does not describe achieved throughput.

Relative to the supplied Isaac Sim 5.0 reference of approximately **10.62 pairs/s**, measured throughput is **11.34% higher**. This is a historical comparison, not a controlled version-only speedup: the old installation, driver and full measurement conditions were not rerun or independently matched. Earlier OceanSim Full-app diagnostic timings include extra raw-GT downloads and a different application bootstrap; they are not this standalone baseline.

| Stage | Uninstrumented mean per pair | Separate instrumented mean |
| --- | ---: | ---: |
| Pose/water update | 1.4242 ms | 1.4159 ms |
| Blocking RTX/render step, CPU wall | 58.2949 ms | 66.7926 ms |
| External RGB/depth acquisition/readiness, both cameras | 1.4621 ms | 1.6428 ms |
| OceanSim processing plus readback, combined wall | 22.7744 ms | 19.5480 ms |
| UW kernel allocation/submission, host wall | unavailable separately | 0.8191 ms |
| Four processed-image/degraded-depth readbacks, including GPU waits | unavailable separately | 17.1272 ms |
| End-to-end pair latency | 84.0831 ms | 89.5225 ms |
| Sustained stereo pairs/s | 11.8247 aggregate | 11.1111 |

The separate 100-pair profile enables existing Tracy stage instrumentation and Warp CUDA activity timing. Its diagnostic capture path invokes the same installed kernels with the same arguments; ordinary throughput above uses the actual normal `UW_Camera.render()` path. Stage timers are CPU wall times. Readback includes pending GPU waits, allocation/copy overhead and transfers; enqueue time is not GPU execution time. Stages do not sum exactly due to internal annotator fetches and Python bookkeeping. Instrumentation changes scheduling and costs, so individual columns from different runs must not be subtracted to infer optimization opportunities.

Hydra's measured **GPU RTX Rendering event** averages **15.6994 ms** (median 15.0820, p95 17.2476). Left/right camera child scopes average **5.7732 / 5.5148 ms**. The RTX event includes the retained normal viewport and scene work. Snapshots are the latest GPU profiler frame after each completed stereo step; a blocking step can drive multiple Kit updates, so these event durations are not a complete sum of all GPU work per pair. All top-level Hydra scopes, including SDG work, average 16.7601 ms. No nested durations were added to their parents.

Warp CUDA events separately measure **0.11630 ms/pair** for the two UW RGB kernels and **0.02057 ms/pair** for the two depth-degradation kernels: **0.13687 ms/pair** combined GPU execution. All Warp DtoH events total **1.02158 ms/pair**, including water-update transfer work as well as stereo outputs; this is not an isolated four-image-copy measurement. The final profiling drain takes 5.9867 ms outside measured rows. Warp measurements exclude DX12/RTX execution. These GPU figures must not be added to wall timings or treated as sustained throughput.

## Evidence and limitations

All paths below are relative to `C:\rov-sim`; generated evidence is ignored by Git:

- Stationary: `outputs/validation_6_1/final_stationary/20261114T125536Z_b6af081c/`.
- Moving: `outputs/validation_6_1/final_moving/20261114T125607Z_d2850de9/`.
- Three baseline runs: `outputs/validation_6_1/benchmarks/20261114T124934Z_897a460b/`, `20261114T125008Z_80233056/`, `20261114T125043Z_2e97b9b2/`.
- Profile: `outputs/validation_6_1/final_profiled/20261114T125628Z_757f4aac/`, including `benchmark.json`, per-pair CSV, named CUDA totals, `rtx_gpu_samples.json` and `capture.tracy`.
- Aggregate numeric report: `outputs/validation_6_1/measurements_summary.json`; console logs and CPU test logs are in the same root.

Stationary/moving runs contain normal `before/left`, `before/right`, `after/...` PNGs and `poses.jsonl`, initialized calibration, configuration, scene manifests and exported USD. `diagnostics/summary.json` records every numerical check; first/last samples per pass additionally contain raw PNGs, clean-range visualizations and lossless NPZ arrays with raw/underwater RGBA and clean/degraded radial ranges. `recording_verification.json` records disk verification. Wet overview and labelled dry tank/vehicle inspections are generated after stereo capture; dry inspections hide water and use dome fill and must not be used as underwater appearance evidence.

Images were inspected. The original above-water lights and shadow-casting refractive water produce **very dark equipment in RT2**, and AA-off produces visible grain. Target, geometry, stereo processing and metric ranges remain valid. This baseline deliberately retains the lighting and quality settings; it does not establish useful photometric fidelity for inspection/SLAM, refractive housing calibration, or physical caustics. Caustics are off. Underwater kernels use their existing image-space model; the known unused `max_range` argument behavior was not changed.

Warnings remain for the BlueROV asset's malformed normal primvar, water normal fallback, inherited SyntheticData host-copy path, and renderer interface release. The Hydra profiler also emits a no-default-engine-UID warning when created; subsequent samples contain valid nonzero renderer/camera GPU events. No warnings were hidden or treated as measurements. Asset normals, long-duration stability, optional GUI preview/MP4 output and alternative renderers/backends are outside this validation's tested scope.

Restoration and baseline validation are complete. Recommended separate follow-ups are lighting/photometric validation and detailed analysis of render/update/readback scheduling using the saved trace. Performance optimization, experimental-camera migration, ROS 2 and SLAM remain separate tasks.
