# Isaac Sim 6.1 RTX stereo camera comparison

Use `--camera-backend camera-sensor` for the best validated new backend. It improves processed stereo throughput by **30.8%** over the matched legacy implementation. The **20 pairs/s target is not met**. Legacy remains the default and fallback. Correctly synchronized tiled capture is slower than individual sensors in this installed build.

| Backend | Three independent run rates, pairs/s | Pooled pairs/s | Sample standard deviation |
| --- | --- | ---: | ---: |
| OceanSim UW_Camera | 9.625, 9.692, 9.609 | **9.642** | 0.044 |
| Two CameraSensor instances | 12.651, 12.639, 12.546 | **12.612** | 0.057 |
| TiledCameraSensor, two physical views, pose flush | 10.889, 10.862, 10.606 | **10.784** | 0.156 |

Each run measures the original 60-frame before pass and 60-frame after pass, including the original 0.5 m crate relocation. Backend order rotates between repetitions. All use `configs/tank_photometric.yaml`: original scene and trajectory, 752 x 480 per view, 0.38 m baseline, inspection lighting, ACES/ISO 1600 exposure, DLAA, animated water, original underwater parameters, 30 warmup steps per pass, one RTX subframe, DirectX 12 and RTX Real-Time 2.0. Hardware is RTX 4070 Ti SUPER; runtime is Isaac Sim 6.1.0-rc.26 and OceanSim 1.0.0. These moving measurements are compared to a fresh matched legacy baseline, rather than the historical approximately 10.33 pairs/s result.

Legacy and individual evidence is under `outputs/rtx_camera_6_1_final`. Corrected tiled evidence is under `outputs/rtx_camera_6_1_tiled_flush`. The authoritative merged report is `outputs/rtx_camera_6_1_final/camera_comparison_validated.json`. Each root retains source/configuration hashes, arguments and exit codes. The later source revision adds a tiled-only pose flush; legacy and individual behavior is unchanged.

The initial tiled result of 13.43 pairs/s is **excluded**. Cross-backend validation caught two motion samples rendered at the previous vehicle pose despite fresh ReferenceTime and annotator compute counts. Their inferred wall displacement was 8.4743 mm, matching one original trajectory step of 8.4746 mm. A held-time `app.update()` before tiled capture removes that lag. The vehicle pose, wave phase and logical timestamp remain held; its additional rendering/update cost is included in corrected measurements. The geometric validator now requires 1 mm agreement on an independently known wall, and a regression test rejects this stale-pose case.

The alternative acquisition implementation is isolated in `sensors/rtx_stereo.py`. `sensors/stereo.py` retains the original legacy implementation. No OceanSim source or underwater kernel is modified. Backend selection uses `stereo.backend`, overridden by `--camera-backend`.

| Installed API/source | Verified behavior |
| --- | --- |
| RtxCamera, `rtx_camera.py` | Wraps existing USD camera prims, adds OmniSensorAPI and supports autotrigger tick rate zero. Optical properties remain on the camera prims. |
| CameraSensor, `camera_sensor.py` | Creates/attaches a render product in its constructor. Resolution is `(height, width)`. `get_data()` returns `(Warp array or None, info)` and defaults to CUDA. |
| TiledCameraSensor, `tiled_camera_sensor.py` | Supports RGBA and distance_to_camera on one tiled render product containing the ordered left/right camera paths. CUDA untile kernels fill reusable batch buffers. |
| `_camera_common.py` | RGBA is uint8, four channels from the RGB annotator. Radial depth is float32 with a trailing singleton channel. RGB would slice off alpha. |
| `_sensor_base.py` | Attaches CUDA annotators with `do_array_copy=False`. Product-level `has_data()` is insufficient for individual channel readiness. `_invalidate_sensor()` provides the installed destructor cleanup; there is no public close method in this build. |

Installed implementation sources are under `C:/isaacsim/source/extensions/isaacsim.sensors.experimental.rtx/python/impl/`. Inspected examples include `create_camera_basic.py`, `camera_annotator_devices.py`, `camera_tiled.py` and associated sensor tests. Installed sources take precedence over the [published experimental API documentation](https://docs.isaacsim.omniverse.nvidia.com/6.0.0/py/source/extensions/isaacsim.sensors.experimental.rtx/docs/index.html). SingleViewDepthCameraSensor is never used.

The adapter reuses the existing USD cameras, optics, poses and calibration. It checks their geometry before and after wrapping. After the existing blocking Replicator render step, it acquires both channel payloads, checks CUDA residency, shape, dtype, fresh compute counts and matching product reference times. Depth's trailing channel is removed with a CUDA reshape view. There is no channel swizzle, normalization, image flip or radial-to-planar conversion.

It submits the installed `UW_render` and `UW_depth_turbidity_attenuator` for both views into persistent CUDA outputs, preserving their named parameters and frame-indexed noise seeds. It downloads RGB for the existing output/recording interface, and degraded depth only when requested. Clean radial range remains separate and unchanged. GPU-only mode fences the Warp stream before the renderer can reuse borrowed annotator buffers, and includes the final GPU drain in throughput. Full capture already blocks in `.numpy()`.

| Separate experiment, three repetitions | Legacy | Individual | Corrected tiled |
| --- | ---: | ---: | ---: |
| Render-only stereo updates/s | 10.534 | 12.554 | 10.844 |
| GPU-only processed stereo jobs/s, including final drain | 10.237 | 12.629 | 10.712 |
| Full output with degraded-depth downloads restored, pairs/s | mandatory in baseline | 12.614 | not repeated after pose fix |

Full-output throughput excludes PNG compression, disk recording, raw diagnostics, Tracy and Warp activity profiling. Memory snapshots occur outside measured iterations. The depth-readback parity experiment uses `--readback-degraded-depth`. Individual full output at 12.612 pairs/s and parity at 12.614 are effectively equal at this run-to-run variation. Its GPU-only rate is 12.629 and render-only rate 12.554. CPU output downloads and underwater mathematics therefore are not the dominant remaining limit in the new backend.

The inherited legacy acquisition/render graph remains present in its diagnostic modes. No-readback means no explicit OceanSim output downloads during measured frames, rather than a guarantee that every internal legacy renderer node avoids host copies.

| Normal host stage means, ms per stereo pair | Legacy | Individual | Corrected tiled |
| --- | ---: | ---: | ---: |
| Scene update | 4.685 | 5.583 | 4.638 |
| Blocking render/update, including tiled pose flush | 52.454 | 70.796 | 85.357 |
| External camera acquisition | 1.224 | 1.242 | 1.105 |
| OceanSim GPU submission | unavailable separately | 0.307 | 0.241 |
| Requested RGB readback including waits | unavailable separately | 0.991 | 1.039 |
| Combined OceanSim processing/readback | 44.900 | split above | split above |

These are host wall-clock boundaries, not exclusive GPU execution costs. Legacy normal capture calls production UW_Camera.render(), including internal fetches, allocations, kernels and RGB/degraded-depth downloads. The new adapter reuses outputs and submits both views before downloading requested data. Work and waits move between timing boundaries: the shorter new total does not mean its blocking render step is shorter.

Separate Tracy/Warp profiles measured **0.133, 0.044 and 0.086 ms** of OceanSim CUDA kernel activity per pair for legacy, individual and corrected tiled. They run the same unmodified kernels; cache and scheduling differences do not establish changed mathematics or intrinsic kernel efficiency. The legacy CPU readback zone took **41.19 ms/pair**, while all recorded Warp device-to-host copy activity totalled **0.920 ms/pair**. Copy totals for individual and tiled were 0.480 and 0.576 ms/pair. These include water-mesh readback, not solely images. Legacy recorded 600 DtoH operations for 120 pairs; the alternatives recorded 360, consistent with removing two degraded-depth downloads per pair.

The gap between copy activity and blocking wall time is evidence of synchronization/scheduling cost, rather than 41 ms of PCIe copying. CUDA activity excludes RTX/DX12 rendering; host render time includes Kit dispatch, rendering waits and interop. The measurements do not uniquely partition every driver/renderer wait. Retained `capture.tracy` and `rtx_gpu_samples.json` files expose those timelines. Instrumented profile rates were 9.730, 12.376 and 10.435 pairs/s; they are separate from normal results and provide no universal overhead correction. The slightly faster legacy profile is within scheduling variation and uses the split diagnostic path.

Numerical and visual validation uses the original scene without added targets:

- All K matrices match exactly. All recorded poses, baseline and body-to-optical transforms match legacy within 1e-6. Wrapper identity-op normalization and nanometre-scale float rounding are evaluated as transforms.
- 240 PNGs per backend pass CRC, dimensions and pairing checks. Twenty sampled raw/processed views per backend agree with saved image buffers, retain RGBA uint8 ordering and alpha, preserve DLAA and have synchronized reference times.
- Replaying actual production UW_Camera.render() on identical CUDA inputs gives bitwise-identical RGB and degraded depth for both alternatives. Clean inputs remain unchanged. Independent attenuation/backscatter evaluation differs by at most one 8-bit level because of truncation.
- Independent wall radial-range error is below 0.8 micrometres in every sampled view after the tiled fix. Individual range matches legacy exactly. Corrected tiled left range matches exactly; right range p99 difference is approximately 1.9 micrometres, with occasional rasterization-edge differences.
- At original route frames 0/15/30/45/59, valid fixed-equipment stereo matches are 17/17/16/11/17 for legacy, 16/19/19/12/19 for individual and 9/17/18/18/14 for corrected tiled. Per-view median known-depth reprojection errors span 0.11-0.28, 0.18-0.37 and 0.20-0.41 px respectively. The original fixed gates include positive disparity, row error <=1 px, range/visibility agreement and triangulated Z within 10%. Counts vary with temporal rendering and do not prove identical appearance.
- Fixed-equipment before/after MAE is approximately 0.63-1.01 luminance code levels; the moved-crate region is approximately 25-30 levels for all backends. This preserves the experiment's change signal without claiming learned detector accuracy.
- USD auditing preserves tank, equipment, crate, water, lights and optical attributes. Tiled rendering authors shared exposure state on its primary camera, so exposure schemas are reported separately from geometric equality. All 48 protected OceanSim Python source hashes remain unchanged.

Full-run process RSS ranges were 9.46-9.72 GiB (legacy), 9.44-9.68 GiB (individual), and 9.39-9.62 GiB (tiled). Device-wide VRAM snapshots were 4737-4746, 4727-4767 and 4778-4810 MiB respectively. VRAM includes the desktop and other applications and does not establish per-camera allocation sizes. No readiness retries, capture failures or progressive memory growth were seen in bounded repetitions. This is not an hours-long soak test.

Use the new backend with the existing recorder:

```powershell
. ./runtime.ps1
$runtime = Resolve-IsaacPython $env:ISAAC_SIM_PATH
& $runtime -u run.py --headless --config configs/tank_photometric.yaml --camera-backend camera-sensor --experiment change_detection --frames 60 --record
```

Select `--camera-backend tiled` for the synchronized tiled alternative, or `legacy` for the original implementation. Unsupported experimental APIs fail explicitly. Calibration, pose conventions and recording files remain unchanged. Shutdown drains CUDA work while Kit is alive, detaches reference annotators, invokes the installed runtime's idempotent cleanup and releases arrays/products/windows. The application retains ownership of timeline, Replicator, water and SimulationApp shutdown.

Reproduce into a new directory, and perform offline image analysis after benchmarks finish:

```powershell
& $runtime -u camera_backend_suite.py --root outputs/rtx_camera_repro
python compare_camera_backends.py outputs/rtx_camera_repro
python evaluate_photometry.py outputs/rtx_camera_repro/validation --profiles legacy camera-sensor tiled
& $runtime -u verify_camera_scene.py outputs/rtx_camera_repro
python -m unittest discover -s tests -q
```

The final source automatically includes the tiled pose flush. The runner refuses to overwrite evidence; `--resume` requires matching arguments and acquisition-source hashes and skips only completed cases. `--only` can select cases. Runtime errors fail the suite even if Kit returns zero. All **43 CPU tests pass**, including fences, partial cleanup, backend selection, matched/drain-inclusive accounting and rejection of one-frame-old geometry.

To inspect the retained evidence, which spans the tiled-only synchronization correction:

```powershell
python compare_camera_backends.py outputs/rtx_camera_6_1_final --tiled-root outputs/rtx_camera_6_1_tiled_flush
& $runtime -u verify_camera_scene.py outputs/rtx_camera_6_1_final --tiled-root outputs/rtx_camera_6_1_tiled_flush
```

The individual backend provides a measured reason to use the new infrastructure on the operational 6.1 installation. This does not establish a 6.1-versus-5.0 version speedup or solve the 20 pairs/s requirement. Tiling reduces render-product count, but its required synchronization removes its apparent advantage here. Retain legacy as fallback and prefer individual sensors for this experiment.
