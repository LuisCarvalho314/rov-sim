# Photometric validation of the existing ROV change-detection tank

Date: 2026-11-14. Isaac Sim 6.1.0-rc.26, OceanSim 1.0.0, DirectX 12,
RTX Real-Time 2.0, RTX 4070 Ti SUPER, 752 x 480 per camera.

Use **`configs/tank_photometric.yaml`** for the selected configuration.
`configs/tank.yaml` remains unchanged by this task;
`configs/tank_photometric_baseline.yaml` preserves its starting contents.

## Finding and selected change

The dominant visibility failure is upstream of OceanSim: overhead illumination
does not adequately reach the submerged equipment through the shadow-casting
refractive surface in this RT2 configuration. AA-off then exposes stochastic
rendering noise. Exposure alone cannot recover surfaces receiving almost no light.

The selected configuration retains both overhead lights, the original animated
water and its shadows, and all existing equipment/materials. It adds two small
vehicle-mounted inspection area lamps, enables native-resolution DLAA, fixes
the shared exposure, and warms each pass for 30 frames. It preserves the original
60-frame trajectory, 0.38 m stereo baseline, camera mount/intrinsics,
0.5 m crate displacement and OceanSim processing parameters/kernels.

| Control | Selected value |
| --- | --- |
| Overhead lighting | Original two 2.2 x 1.5 m lamps, intensity 950, original positions/colour |
| Inspection lamps | Two RectLights, 0.12 x 0.08 m, intensity 60000 each |
| Lamp body-frame positions | `(0.48, -0.27, 0.15)`, `(0.48, 0.27, 0.15)` m |
| Lamp rotation | USD XYZ `(0,-90,0)` degrees, local -Z beam towards vehicle +X |
| Lamp colour | Original `(0.83,0.92,1.0)` |
| Tone mapping | ACES, op 6 |
| Exposure | ISO 1600, exposure time 0.02 s, renderer f-number 5 |
| Auto exposure | `/rtx/post/histogram/enabled=false` |
| AA | `/rtx/post/aa/op=4`, DLAA; no lower-resolution DLSS upscaling |
| Warmup / RT subframes | 30 / 1 |
| Water and underwater processing | Original settings, including surface shadows and animated 0.06 m waves |

Lamp sizes/intensities represent a plausible inspection-light arrangement, not
a measured BlueROV light calibration. No lamp fixture geometry was added. Exposure
controls are renderer photometric settings; camera geometry and mounting are
unchanged. Neither synthetic sensor noise nor a real low-light camera response is
being calibrated here.

## Root-cause evidence

Inspected `scenes/tank.py`, `scenes/equipment.py`, `scenes/primitives.py`,
`environments/underwater.py`, `experiments/change_detection.py`, both requested
configs, existing 6.1 captures/logs, and the installed OceanSim water/renderer
source. The original lights face downwards from z=3.35 m; the water is at 2.85 m.

| Effect | Evidence and interpretation |
| --- | --- |
| Illumination and surface shadows | Four times overhead intensity barely changes equipment brightness. Disabling only water shadows makes equipment visible. This isolates the surface-shadow/light-transport path as the main bottleneck; the shadow ablation is not the final scene. Submerged lamps provide direct illumination without removing the surface. |
| Exposure/tone mapping | Baseline readback: ACES, ISO 100, 20 ms, f/5, auto exposure off. ISO 400 alone fails. With submerged lamps and DLAA, ISO 800 and 1600 recover useful contrast; 1600 supplies more verified distant-equipment matches. Exposure is shared and fixed across views/passes. |
| Reflectance/textures | Original equipment uses USD display colours, with no authored inspection textures: metal `(0.33,0.39,0.43)`, rust `(0.47,0.27,0.15)`, blue `(0.15,0.31,0.45)`, plus lighter panel stripes/markers. These are relatively dark and broad faces are textureless. Original seams, bolts, stripe ends and corners become usable under illumination; material replacement is unnecessary for this improvement. |
| Normals | Equipment consists of USD Cube/Cylinder primitives, with renderer-generated normals. Logs identify malformed `primvar normal` data on the referenced BlueROV asset and a smooth-normal fallback on animated `/World/Water`, not missing equipment normals. These inherited warnings remain; no asset or kernel repair was attempted. |
| Water absorption/reflection/refraction | Installed `Water.mdl` has IOR about 1.8, tinted transmission `(0.612,0.714,0.747)`, depth about 0.0001 m, roughness 0 and a normal map. These are questionable physical-water defaults. A stage-local absorption-depth-only override to 10 m does not restore illumination, so absorption alone is not established as the cause. The opaque-looking shadow/RT2 transport interaction dominates this test. Final water material is unchanged. |
| OceanSim attenuation/backscatter | Raw RTX equipment mean is only 0.44/255 in the baseline, before any underwater processing. Processing raises it to 12.81 through backscatter while leaving contrast poor. Saved raw/processed buffers and the installed equation isolate attenuation/veiling from the lighting failure. The original coefficients remain unchanged. |
| RTX sampling/AA/denoising | DLAA alone removes most speckle but leaves equipment dark. Lamps with AA off still produce zero accepted fixed-equipment stereo matches. Lamps, adequate exposure and DLAA together recover consistent geometry. Default RT2 reconstruction/denoising remains in use; no separate denoiser tuning, frame generation or kernel optimization was introduced. |

The absorption input change is a diagnostic ablation, not evidence that the MDL's
physical transport was corrected. RT2's legacy photon-caustic controls remain
disabled. The work establishes an effective photometric configuration for
submerged-object inspection, not a physically calibrated ocean surface or camera
housing model. Direct views of submerged equipment do not cross the surface;
reflected surface features should not be treated as physical stereo landmarks.

Installed `omni.rtx.settings.core` confirms DLAA enum 4 and the exposure paths.
External references: [NVIDIA RT2 controls](https://docs.omniverse.nvidia.com/materials-and-rendering/latest/rtx-renderer_rt.html)
and [post-processing controls](https://docs.omniverse.nvidia.com/materials-and-rendering/latest/rtx_post-processing.html).
Local registered-setting readbacks take precedence over moving online documentation.

## Controlled experiment and measurements

Every primary profile uses the original tank and 60-frame trajectory from
`tank.yaml`: body x=-3.1 to -2.6 m, original fixed heading. Each process records
60 synchronized stereo pairs before and 60 after. The crate moves from
`(1.15,-0.65,0.30)` to `(1.65,-0.65,0.30)` m. Sampling for quantitative raw/depth
analysis is at frames 0,15,30,45,59 in both passes. All PNG pairs/poses are retained.
The selected profile is repeated in an independent process.

These primary comparisons have **no emissive diagnostic target**. Each isolated
profile changes one control relative to its parent where practical:

| Profile | Parent/change | Mean processed equipment Y | Valid fixed-equipment stereo matches, before views |
| --- | --- | ---: | ---: |
| baseline | Original | 12.81 | 0 |
| light4 | Baseline / overhead intensity x4 | 13.30 | 0 |
| exposure4 | Baseline / ISO 400 | 13.31 | 0 |
| water_depth10 | Baseline / MDL depth 10 m only | 12.82 | 0 |
| shadow_off | Baseline / surface shadows disabled | 27.47 | 2–6 |
| dlaa | Baseline / AA 4 | 12.84 | 0 |
| shadow_off_dlaa | Shadow-off / AA 4 | 27.57 | 8–16 |
| lamps | Baseline / two submerged lamps | 17.73 | 0 |
| lamps_dlaa | Lamps / AA 4 | 18.11 | 0 |
| lamps_dlaa_iso800 | Lamps+DLAA / ISO 800 | 54.56 | 8–17 |
| lamps_dlaa_iso1600 | Lamps+DLAA / ISO 1600 | 80.91 | 12–18 |
| recommended | ISO 1600 profile / warmup 30 and explicit unchanged exposure defaults | 80.93 | 12–16 |
| recommended_repeat | Independent repeat | 80.98 | 14–17 |

`Y` is Rec.709-weighted **8-bit RGB code value**, not radiometric luminance.
Equipment masks use clean-range world points inside original equipment bounds
with 12 mm tolerance, eroded one pixel. They exclude the union of both projected
crate locations with an additional four-pixel margin. This deliberately emphasizes
fixed equipment and does not count the moved object as a background inconsistency.
AABB masks are an approximation, not semantic ground-truth segmentation.

| Metric, average over five before views | Original | Selected |
| --- | ---: | ---: |
| Raw equipment mean Y | 0.44 | 83.47 |
| Processed equipment mean Y | 12.81 | 80.93 |
| Raw equipment Y<10 fraction | 99.29% | 0.024% |
| Processed equipment Y<20 fraction | 99.04% | 0% |
| Raw equipment any RGB channel >=250 | 0% | 0.215% |
| Processed equipment any RGB channel >=250 | 0% | 0% |
| Processed local std, 7x7 | 1.83 | 5.66 |
| Processed mean gradient magnitude | 0.55 | 2.71 |
| Fixed-equipment SIFT detections, left | 5.6 | 72.2 |
| Fixed-equipment pass repeatability | 4.0% | 64.1% |
| Fixed-equipment same-pose pass MAE Y | 0.67 | 0.75 |
| Moved-crate region pass MAE Y | 1.50 | 27.85 |

The small raw clipping fraction is concentrated in lamp highlights. Attenuation
can lower already-clipped values; zero processed clipping does not recover that
lost information. ISO 800 has less raw highlight clipping but fewer accepted
matches in some views. Dark, nearly constant baseline images also have low MAE:
MAE alone cannot demonstrate repeatability or useful visibility.

SIFT settings are identical everywhere: cap 1800, contrast threshold .02, edge
threshold 10, reciprocal nearest-neighbour ratio .75. Matches must satisfy all of:
known-range projection error <=2 px, epipolar row error <=1 px, positive disparity,
right-view range/visibility agreement within max(0.08 m,1.5%), and triangulated
optical Z within 10% of clean range-derived Z. No fitted fundamental matrix can
absorb incorrect calibration. These gates reject noise, many repeated-pipe aliases
and view-dependent glints. A higher detector count alone is not called an improvement.

| Original trajectory frame | Fixed valid matches before / after | Other unchanged background valid matches, before | Fixed match median GT error | Occupied fixed cells in 8x5 image grid |
| --- | ---: | ---: | ---: | ---: |
| 0 | 12 / 14 | 22 | 0.33 px | 6 |
| 15 | 16 / 21 | 34 | 0.17 px | 6 |
| 30 | 15 / 16 | 39 | 0.31 px | 6 |
| 45 | 13 / 17 | 40 | 0.25 px | 6 |
| 59 | 14 / 16 | 33 | 0.22 px | 5 |

Accepted fixed features span approximately 2.36–6.38 m optical depth across the
route. They are spatially sparse, concentrated on existing equipment detail;
large plain wall/crate faces remain weakly textured. About 52–65% of reciprocal
ratio-filtered fixed matches pass the depth gates in the selected before views.
This documents why ungated counts are insufficient. Fine stripe/bolt/corner
features survive DLAA, but it remains a temporal renderer, not a noise-free
ground-truth appearance generator.

## Repeatability and correctness

All selected and repeated original-trajectory pose records preserve identical
left/right K and body-to-optical matrices and reproduce the before/after vehicle
path. The selected same-pose fixed-equipment MAE is 0.64–0.98 levels; p95 absolute
differences are 2–4 levels. Only 0.019–0.108% of those equipment pixels differ by
more than ten levels. The moved-crate-region MAE is 25.60–30.35 levels, roughly
37 times the average fixed-equipment residual. This is a diagnostic signal contrast,
not change-detector accuracy, and the moved crate can alter real shadows outside
its projected bounds.

The existing 6.1 geometric/recording validator also passes under the selected
lighting/exposure/AA: two 12-pair passes along its **existing** validation trajectory,
which includes yaw/pitch/roll. Its known target, wall radial ranges, stereo
disparity, clean/degraded range, synchronization, mount transforms, PNG bytes and
0.5 m displacement retain their original tolerances. The first attempt's fixed
marker colour threshold was biased by high exposure. The marker's diffuse/emissive
strength is now inversely scaled with configured exposure for this diagnostic
only; position, size, depth and geometric tolerances are unchanged. The failed
attempt remains saved under `checks/`; the successful run is under `checks_final/`.

Independent-run statistics, stationary temporal statistics, complete saved-buffer
equation checks and source hashes are in `verification.json`. All 34 CPU tests pass.
No OceanSim production source/material file was edited.

A supplementary target-free run follows the existing rotated validation route,
without changing its waypoints: valid fixed-equipment stereo matches are 11 at
frame 0 and 19 at frame 11; equipment mean Y is 79.6 and 84.2, pass repeatability
about 61–62%, and fixed-equipment MAE 0.91–1.01 levels. This adds a different viewing
orientation while keeping the primary experiment's original route intact.

The CPU USD audit in `scene_preservation.json` compares 36 protected prims in the
original, selected and repeated snapshots. Their types, geometric/calibration
attributes and relationship targets match exactly. The intended camera ISO change
is checked separately: both cameras are 100 in the baseline and 1600 in both
selected runs. The preserved source hashes are also shipped in
`docs/photometric_oceansim_hashes.json` so verification does not depend on older
ignored validation directories.

Across independent processes, fixed-equipment MAE is 0.37–0.51 levels, with
68.5–76.2% same-pose SIFT repeatability. Features valid in stereo in both inspection
passes repeat at 40–71.4%; these small sets contain 6–11 common accepted landmarks
per sampled pose. This is useful sparse evidence, not a claim of complete feature
tracking. The plain surfaces and remaining glints still limit coverage.

For 20-pair stationary runs, temporal variation on fixed equipment over frames
5–19 has mean per-pixel standard deviation **1.061 -> 0.284** levels, and its p95
falls **5.693 -> 0.647**. Mean consecutive-frame absolute variation falls
**0.635 -> 0.161**. The original animated water remains active, so these measurements
include physical scene animation as well as stochastic renderer variation.
Forty saved selected/repeated camera views exactly match their recorded PNGs and
the unmodified underwater equation to <1.01 code levels, including uint8 truncation.
All 48 previously hashed OceanSim Python/material files match the pre-task hashes.

## Performance

Three independent selected runs each warm 30 frames and measure 100 processed
stereo pairs, using the ordinary `UW_Camera.render()` path without diagnostic
readbacks, targets, PNG recording, tracing or GPU event timing. They hold the
original initial vehicle pose and animate the original water, matching the earlier
stationary benchmark method. They run sequentially, with no analysis or other
simulator jobs running concurrently. The selected full-trajectory image captures
are separate from performance measurements.

| Selected repetition | Processed pairs/s | Mean pair latency | p95 latency |
| --- | ---: | ---: | ---: |
| 1 | 10.3639 | 96.1695 ms | 98.0132 ms |
| 2 | 10.2899 | 96.8348 ms | 99.3533 ms |
| 3 | 10.3432 | 96.3634 ms | 97.1474 ms |

Aggregate **10.3322 pairs/s**, mean **96.4559 ms**, median **95.8554 ms**,
p95 **98.9553 ms**, maximum **156.3303 ms**; zero readiness retries. This is
**12.62% less throughput** and **14.71% greater mean latency** than the earlier
11.8247 pairs/s / 84.0831 ms baseline. All measured pairs still exceed the existing
50 ms deadline. Image quality was retained despite the throughput cost.

| Stage, mean wall time per stereo pair | Earlier original baseline | Fresh original check (100 pairs) | Selected (300 pairs) |
| --- | ---: | ---: | ---: |
| Blocking RTX/render step | 58.2949 ms | 41.9027 ms | 47.6335 ms |
| OceanSim processing plus readback | 22.7744 ms | 32.0457 ms | 46.3486 ms |
| RGB/depth readiness | 1.4621 ms | 1.1545 ms | 1.1783 ms |
| End-to-end acquisition | 84.0831 ms | 76.3654 ms | 96.4559 ms |
| Sustained throughput | 11.8247/s | 13.0429/s | 10.3322/s |

The fresh original check is 13.04/s, so the contemporaneous configuration cost is
about **20.78% throughput**. It is a single check, whereas both the supplied baseline
and selected aggregate use three runs. The variation between historical and fresh
original timings precludes attributing every stage difference to AA or lamps.
In particular, asynchronous GPU work can move waiting time between the blocking
render and readback zones. These are CPU wall boundaries, not pure RTX/CUDA times.

A separate 100-pair Tracy/Warp profile measures 9.9000 pairs/s with instrumentation:
render 54.0604 ms, combined processing/readback 43.8274 ms, host kernel submission
0.6775 ms and readback/waits 41.7926 ms. Named CUDA activities total **0.08048 ms/pair**
for the two underwater RGB kernels and **0.02216 ms/pair** for the two degraded-depth
kernels. Their combined GPU execution is about **0.10265 ms/pair**; large readback
wall time must not be described as OceanSim kernel execution. The trace and Hydra
GPU snapshots retain the RTX timing evidence. No optimization was attempted.
The earlier separate profile measured about 0.13687 ms/pair for these same four
unchanged CUDA kernels; this small activity difference is not evidence of a kernel
optimization or a controlled GPU-clock comparison.

## Evidence and reproduction

Saved evidence root: `outputs/photometric_6_1/` (ignored by Git).

- `baseline_vs_selected.png`: native-resolution raw/processed comparison.
- `controlled_comparisons.png`: every profile, raw before / processed before / processed after.
- `matched_stereo_before_after.png`: all four stereo/session views at original frames 0 and 59.
- `metrics.json`, `summary.csv`: full photometry, feature, geometry and repeatability results.
- Each profile's timestamp directory: config, calibration, USD snapshots, all 120
  paired PNGs/poses, raw RTX PNGs and ten NPZ evidence bundles.
- `photometry/matches_*.png`, `fixed_mask_*.png`: accepted matches and evaluated regions.
- `checks_final/`: known-geometry validation, stationary captures, ordinary
  benchmark repetitions and separate Tracy/Warp profile. `oriented/` is an
  additional target-free capture along the pre-existing 6.1 validation trajectory;
  its own `metrics.json` is under `checks_final/`.
- `verification.json`: saved-buffer, independent-run, temporal and protected-source evidence.

Run from PowerShell in `C:\rov-sim` with the installed Isaac Sim environment:

```powershell
. ./runtime.ps1
$runtime = Resolve-IsaacPython $env:ISAAC_SIM_PATH
# Use the pinned checkout; configure external assets with OCEANSIM_ASSET_PATH.
Remove-Item Env:OCEANSIM_EXT_PATH -ErrorAction SilentlyContinue
& $runtime -u run.py --headless --experiment change_detection --frames 60 --record --photometric-diagnostics --config configs/tank_photometric.yaml
```

Recreate the controlled profiles into a **new** evidence directory:

```powershell
python photometric_profiles.py --root outputs/photometric_repro/profiles
.\run_photometric.ps1 -EvidenceRoot outputs/photometric_repro -Profiles baseline,light4,exposure4,shadow_off,water_depth10,dlaa,shadow_off_dlaa,lamps,lamps_dlaa,lamps_dlaa_iso800,lamps_dlaa_iso1600,recommended,recommended_repeat
python evaluate_photometry.py outputs/photometric_repro
python summarize_photometry.py outputs/photometric_repro
.\validate_photometric.ps1 -EvidenceRoot outputs/photometric_repro/checks
python evaluate_photometry.py outputs/photometric_repro/checks --profiles oriented
python validate_photometry.py outputs/photometric_repro
& $runtime -u verify_photometric_scene.py outputs/photometric_repro
python -m unittest discover -s tests -q
```

Offline tools require ordinary Python with NumPy, OpenCV and Pillow; no new runtime
dependencies are added to the simulator. Runners check application status and
console errors, because a Windows wrapper exit code alone can conceal a failed
capture. They refuse to overwrite existing evidence. `--photometric-diagnostics`
is explicitly excluded from benchmarks and from target-bearing diagnostics.

## Limits of the result

This validates visibility, sparse stereo geometry and equivalent-condition
repeatability in the retained experiment. It does not establish SLAM trajectory
accuracy, reconstruction quality or learned change-detector performance. Only the
existing 50 cm relocation was tested; 10 cm detection accuracy is not established.
The original route spans 0.5 m at fixed heading, so broad multi-view coverage and
many inspection orientations remain outside that retained route. Supplemental
validation uses the existing rotated 6.1 trajectory. No scene simplification,
trajectory/camera migration, material texture addition, ROS change, SLAM work,
Gaussian-splat training or pipeline/kernel optimization was performed.
