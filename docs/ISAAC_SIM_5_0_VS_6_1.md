# OceanSim 5.0 versus 6.1: keep-or-revert assessment

2026-11-14. **Recommendation: retain 5.0 as the project baseline; there is no
demonstrated version-specific benefit sufficient to justify maintaining the 6.1
port. This recommendation is provisional because the controlled 5.0 experiment
is blocked.** Keep the validated 6.1 installation and captures intact: it is the
working fallback until an independently usable 5.0 environment is available.
No claim of equivalent 5.0 image quality, or measured 5.0 superiority, is made.

This assessment adds installation/source inspection and a CPU re-evaluation of
saved measurements. **No new successful simulator captures or throughput runs
were obtained.** Neither simulator, OceanSim production files, nor the validated
6.1 application/configuration was changed. No rebuild or installation repair was
attempted.

## Blocking finding

Entry paths in the recorded attempt below are historical; current commands are in the [README](../README.md).

`C:\isaacsim-5\_build\windows-x86_64\release\VERSION` reports
`5.0.0-rc.45+mr.0.1791e148.local`, but its generated files resolve as follows:

| Generated 5.0 path, relative to release | Actual destination |
| --- | --- |
| `apps/isaacsim.exp.base.python.kit` | `C:\isaacsim\source\apps\isaacsim.exp.base.python.kit`, package/application **6.1.0** |
| `exts/isaacsim.simulation_app/isaacsim/simulation_app/simulation_app.py` | `C:\isaacsim\source\extensions\isaacsim.simulation_app\isaacsim\simulation_app\simulation_app.py` |

`C:\isaacsim-backup` has the same two cross-installation destinations. The old
source app under `C:\isaacsim-5\source\apps` still says 5.0.0, but the generated
launcher does not use it. Thus neither old directory is an isolated runnable
5.0 environment, despite its version file and Kit-107 extension cache.

The 5.0 `python.bat -u run.py --headless --startup-only`, with its own OceanSim
extension explicitly selected, was attempted normally and outside the sandbox.
The latter removed the initial registry-cache permission failure, but still
failed dependency resolution:
`isaacsim.exp.base.python-6.1.0 -> isaacsim.exp.base-6.1.0` requires unavailable
`isaacsim.anim.robot.schema`. Exit was 1, before OceanSim activation. This is an
installation isolation problem, not evidence of an OceanSim photometric failure.
Replacing links, assembling an alternative experience, or rebuilding would be
environment repair beyond this comparison. No other environment was substituted.

Fresh logs and resolved-path/hash evidence are in
[`outputs/version_comparison_20261114`](../outputs/version_comparison_20261114/).

## Configurations and comparability

The existing `run.py`, `application.py`, `sensors/stereo.py`,
`environments/underwater.py`, benchmark CSV/JSON accounting,
`evaluate_photometry.py`, `validate_photometry.py` and recorded diagnostic
summaries supply the experiment. The older Script Editor integration in
`C:\rov_sim1` was inspected but not substituted for this established standalone
capture path; its asynchronous preview is not a controlled throughput reference.

| Control | Original photometric baseline | Selected photometric configuration |
| --- | --- | --- |
| Config | `configs/tank_photometric_baseline.yaml` | `configs/tank_photometric.yaml` |
| Scene, calibration, route, processing | Original tank/BlueROV/equipment; unchanged in selected | Same |
| Cameras | 752 × 480 each, 0.38 m baseline, 15/21 mm focal/aperture, parallel pinhole cameras | Same |
| Primary trajectory | 60 pairs before and 60 after; body x=-3.1 to -2.6 m; crate moves 0.5 m | Same |
| Water | Animated 0.06 m waves, surface shadows on; original material and attenuation/backscatter | Same |
| Overhead lamps | Original two lamps, intensity 950 | Same |
| Inspection lamps | None | Two body-mounted 0.12 × 0.08 m lamps, intensity 60000 each |
| Exposure / tone map | ISO 100; default ACES, 20 ms, f/5, auto exposure off in saved readbacks | Explicit ISO 1600, ACES op 6, 20 ms, f/5, auto exposure off |
| AA / subframes | AA off / 1 | Native DLAA op 4 / 1 |
| Warmup | 8 in original image baseline; 30 in later baseline benchmark | 30 |

The selected configuration is ready for reuse with the 5.0 launcher and explicit
5.0 `--oceansim-ext`, without a duplicate scene implementation or altered kernels.
**It has not been successfully applied or validated in 5.0.** Its registered
exposure controls, DLAA enum, resulting resolution and temporal behavior still
need live readback there. Matching settings would not prove matching renderer
light transport, denoising or temporal history between Kit versions.

Saved 6.1 runs used 6.1.0-rc.26, DirectX 12, RT2, RTX 4070 Ti SUPER and driver
610.88. Both historical 5.0 reports identify that GPU, but their driver/version
metadata and concurrent load were not fully recorded. Their Python was 3.11.13;
6.1 uses 3.12.13. They used 8 warmup frames. Performance captures are stationary
at the original initial pose with animated water, without PNGs, targets or
diagnostic downloads; moving image captures are separate. No controlled moving
throughput comparison exists.

## Image quality and stereo evidence

**The following are measured 6.1 configuration effects, not 6.1-versus-5.0 effects.**
Re-evaluating all five sampled before poses with the existing quality and stereo
functions exactly reproduced the saved baseline, selected and selected-repeat
metrics. Calibration and sampled body/optical poses match across these runs.

| Metric, five before views | 6.1 original | 6.1 selected | Independent selected repeat |
| --- | ---: | ---: | ---: |
| Equipment raw mean Y | 0.44 | 83.47 | 83.53 |
| Equipment processed mean Y | 12.81 | 80.93 | 80.98 |
| Processed equipment fraction Y<20 | 99.04% | 0% | 0% |
| Accepted fixed-equipment stereo matches/view | 0 | 12–16 | 14–17 |
| Fixed-equipment pass feature repeatability | 4.0% | 64.1% | 64.3% |
| Same-pose before/after fixed-equipment MAE Y | 0.67 | 0.75 | 0.74 |

Y denotes Rec.709-weighted 8-bit code values, not physical luminance. Masks use
depth-projected equipment bounds and exclude both crate positions. Dark constant
images explain the low baseline MAE; it does not establish useful consistency.
Selected raw-channel clipping is about 0.215%; processed clipping is zero.

Stereo uses the same SIFT settings and clean-range gates: projection ≤2 px,
epipolar error ≤1 px, positive disparity, right-view visibility agreement, and
triangulated Z within 10% of clean-range Z. Selected accepted-match median
projection errors are 0.17–0.33 px. These statistics concern accepted sparse
matches, not an unbiased dense-depth accuracy test or SLAM success rate.

Existing selected geometry validation passes on its separate rotated 12-pair
route in both passes. Known-target stereo at the endpoint gives optical Z
3.4400 m versus 3.4448 m known; wall ranges, mount transforms, clean/degraded
depth, synchronization and PNG/NPZ equality also pass. That diagnostic adds a
target and is excluded from the primary photometry and benchmarks.

Fresh buffer verification rechecked 40 selected/repeated views: matching left/right
ReferenceTime, persisted AA, exact PNG/processed-buffer equality and underwater
equation error <1.01 levels. Early baseline files lack per-sample ReferenceTime
metadata and equipment bounds; its metrics use the same common bounds as the
existing evaluator. Baseline synchronization was not independently reverified.
Saved stationary results show temporal standard deviation falling 1.061→0.284
levels. None of these findings measures 5.0 photometric performance.

Available equivalent-pose side-by-side images (**both rows are 6.1**; columns are
raw before, processed before, processed after; rows original and selected):

![6.1 original versus selected at the identical original frame-zero pose](../outputs/photometric_6_1/baseline_vs_selected.png)

[Left/right pairs at frames 0 and 59](../outputs/photometric_6_1/matched_stereo_before_after.png).
A matched 5.0/6.1 image panel cannot be supplied because no valid 5.0 capture was
possible. Historical benchmark runs did not save PNGs.

## Throughput and bottlenecks

Recomputed from the existing per-pair CSVs and completed-run JSONs; all entries
below are **previously measured**, not fresh GPU runs. Throughput uses a common
acquisition-wall-clock denominator; SD is between independent process rates.

| Environment/configuration | Runs × measured pairs | Pairs/s | Between-run SD | Mean / p95 acquisition ms |
| --- | ---: | ---: | ---: | ---: |
| Historical 5.0 legacy, caustics off | 1 × 300 | 10.6249 | Unknown | 93.59 / 105.09 |
| Historical 5.0 RT2, original | 1 × 300 | 10.3459 | Unknown | 96.11 / 110.93 |
| 6.1 RT2 original, earlier | 3 × 100 | 11.8254 | 0.1394 | 84.08 / 93.65 |
| 6.1 RT2 original, later check | 1 × 100 | 13.0429 | Unknown | 76.37 / 77.90 |
| 6.1 RT2 selected | 3 × 100 | 10.3322 | 0.0382 | 96.46 / 98.96 |
| 5.0 selected | Blocked | — | — | — |

Selected process rates are 10.3639, 10.2899, 10.3432 (CV 0.37%); original rates
are 11.7339, 11.9868, 11.7589 (CV 1.18%). Correlated frames are not treated as
300 independent trials for a version-effect confidence interval. The supplied
11.8247 uses iteration wall time, versus 11.8254 acquisition wall time; that tiny
accounting difference does not affect this decision.

The selected 6.1 configuration loses about 12.63% throughput against the earlier
6.1 original and 20.78% against the later single original check. It is descriptively
2.75% below historical 5.0 legacy and 0.13% below historical 5.0 RT2; neither is
a controlled version effect. The 6.1 original's between-session shift to 13.04/s
also limits causal attribution. All measured pairs miss the existing 50 ms budget.

Selected mean CPU wall boundaries are 47.63 ms blocking render, 46.35 ms combined
OceanSim processing/readback, and 1.18 ms readiness. A separate instrumented
profile measures about **0.103 ms/pair actual CUDA execution** across the two RGB
and two depth kernels; its throughput is 9.90/s. Thus the large combined wall
zone is not evidence of expensive underwater kernels: pending RTX/GPU work,
synchronization and readback dominate those boundaries. Exact GPU scheduling
attribution would require matched traces; no optimization was attempted.

## Functionality and maintenance

| Area | Evidence and implication |
| --- | --- |
| OceanSim camera/water/kernels | Of 48 compared Python/material files, 40 are byte-identical, including `UW_Camera.py`, `WaterSurface.py`, renderer utilities and water materials. All 48 current 6.1 hashes still match the validated manifest. No new underwater formation model is demonstrated. |
| Port changes | Eight UI/example files differ: four PhysX `acquire_physx_interface`→`get_physx_interface` and menu-cleanup changes; three removed obsolete array-widget imports; one example semantic-label API migration. Sonar semantic equivalence was not validated. Exact diff is saved with the audit. |
| Application compatibility | Current source re-applies AA after bootstrap and clears registered `limitedOps`; it delivers timeline STOP before camera teardown. RT2 registration of both modes plus persistent/active selection and fast shutdown originated with the 5.0 workaround. These are compatibility costs, not demonstrated research capabilities. |
| Synchronization/readback | Shared path: blocking Replicator stereo step, held logical pose/time, annotator readiness, sequential normal `UW_Camera.render()` calls and CPU outputs. 6.1 diagnostics validate freshness; no new port-specific synchronization advantage is established. |
| Rendering/functionality | Historical 5.0 already ran RT2. Legacy photon caustics are unavailable in the chosen RT2 mode; both compared RT2 profiles keep them off. No required tank/stereo/change-detection feature is shown to require 6.1. |
| Reliability | Bounded 6.1 runs pass, with inherited normal/host-copy/release warnings. There is no matched long-duration reliability study or measured maintenance-hours comparison. Mixed source links are an observed operational hazard; broader reliability claims would be assumptions. |

The photometric gains plausibly transfer through the existing scene/configuration
controls, but **that is an untested hypothesis in 5.0**. There is currently no
measured quality, speed or required-functionality advantage attributable to 6.1.
Retaining 5.0 avoids accepting an additional compatibility surface without a
demonstrated project benefit; it does not justify deleting the only currently
validated runnable environment.

## Reproduction and remaining decision gate

Historical read-only audit command (the retained local script records the original source paths; use the [README](../README.md) for current reproduction):

```powershell
python outputs/version_comparison_20261114/audit_saved_evidence.py
```

It saves `audit.json`, exact source diff, benchmark provenance/hashes, recomputed
metrics and preservation checks. All 40 pre-existing workspace Python/config
files in its preservation manifest remained unchanged. Original evidence remains
in `outputs/photometric_6_1` and `outputs/validation_6_1`; historical 5.0 references
are `outputs/20261104T213007Z_2e30de7c` (legacy) and
`outputs/20261104T220616Z_46c661c5` (RT2). Their Isaac-version field is null;
5.0 attribution relies on the dated runtime/source records, not that JSON field.

Once 5.0 is independently runnable, verify actual application/Kit identity before
accepting any frames. Reuse the existing selected config unchanged and
`outputs/photometric_6_1/checks_final/baseline_warm30.yaml` for matched warmup.
For each runtime/config, use fresh output roots with the existing commands:

```powershell
# Set $runtime, $extension, $config and a unique $destination for each cell.
& $runtime -u -m rov_sim --headless --oceansim-ext $extension --config $config --experiment change_detection --frames 60 --record --photometric-diagnostics --output-dir $destination
# Repeat selected captures in another process; use baseline/recommended/
# recommended_repeat parent names for the existing evaluators.
python -m rov_sim.tools.photometry.evaluate_photometry $evidenceRoot
python -m rov_sim.tools.photometry.summarize_photometry $evidenceRoot
# Separate performance jobs: at least three independent 300-pair processes
# per runtime/config, interleaved sequentially across versions, no tracing.
& $runtime -u -m rov_sim --headless --oceansim-ext $extension --config $config --benchmark --frames 300 --output-dir $benchmarkDestination
```

Keep geometry/calibration/trajectory/water and device/driver fixed; check settings
readbacks, equal poses and registered DLAA support. Run the existing geometry
diagnostic separately and retain every failure. The existing metric gates should
remain unchanged. Until that missing 5.0 cell exists, the keep-or-revert decision
is a provisional engineering judgment, not a completed controlled experiment.
