> Historical report: commands and results below describe the original layout. See [current commands](../../README.md).

# Windows runtime validation, 2026-11-04

## RTX 2.0 crash diagnosis and fix (later session)

The initial benchmark A process is visible in the Kit log for `21:29:18`: it launched D3D12 with `--/persistent/rtx/modes/rt2/enabled=true`, then crashed inside `carb.scenerenderer-rtx.plugin.dll` while `SimulationApp.__init__` waited for the viewport. It made no output run directory. Minimal `renderer_probe.py` reproduced the crash with an empty stage, both headless and GUI, with DLSS disabled or enabled, and with viewport updates disabled. Skipping stage creation allowed `SimulationApp` to initialize but did not test a rendered frame. Omitting the RTX 2.0 flag also initialized, but that flag read back false, so this did not confirm RTX 2.0 rendering.

[NVIDIA's Isaac Sim 5.0 forum recipe](https://forums.developer.nvidia.com/t/enable-new-rtx-realtime-2-0-in-simulationapp/342829/9) adds legacy mode registration plus persistent and active `RealTimePathTracing` selections. The minimal probe initialized and updated with those settings, RTX 2.0 read back true, and D3D12 active. The real application then passed `--startup-only` and acquired three processed stereo pairs. Its graceful shutdown exited with `0xC0000005`; the minimal probe with `fast_shutdown=true` exited 0. The application now uses fast shutdown for RTX 2.0 after its explicit cleanup.

A supervised 300-pair A run completed with exit code 0 and `status.json` complete. `render_validation.json` recorded two nonblack 752 × 480 processed images, RTX 2.0 mode enabled, and D3D12 setting readback. The A/B/C reports matched on GPU, backend, stereo calibration, geometry, underwater processing, warmup and one subframe. The run did not record PNGs, so visual water refraction and attenuation remain unverified. The benchmark reports remain under ignored `outputs/` and are not committed. Warp printed CUDA driver-entry warnings during startup; they did not prevent this capture.

## Earlier RTX 2.0 migration check

The default `RealTimePathTracing` and explicit legacy `RaytracedLighting` profiles both passed CPU configuration validation. A new `--startup-only` attempt for each profile on this Windows host failed before renderer initialization: Kit could not read `c:/isaacsim/_build/windows-x86_64/release/exts/omni.pip.compute/pip_prebundle/cv2` (`PermissionError: [WinError 5] Access is denied`), and dependent extensions failed to start. Neither attempt printed the Phase 1 success marker. The default attempt's `python.bat` wrapper returned 0 despite Kit errors, so that exit code is not a successful smoke test. No RTX 2.0 frames, image appearance, or processed stereo throughput were measured in this migration. Repair the installation access and run the README's A/B/C benchmarks and short recorded image checks before drawing renderer comparisons.

This record supplements [the original validation note](../VALIDATION.md), which predates the Windows runs below. Existing output directories were preserved.

## Evidence from earlier Windows runs

| Run directory | Recorded state | Pose records | PNGs | Result |
| --- | --- | ---: | ---: | --- |
| `outputs/20261104T163355Z_ebbe8da5` | `running_before` | 642 | 0 | Termination and cleanup unknown; no Kit or Python process remains. |
| `outputs/20261104T163801Z_137db7ff` | `complete` | 10 | 0 | Bounded stereo processing completed. |
| `outputs/20261104T163941Z_5c1f8c70` | `complete` | 30 | 0 | Bounded stereo processing completed. |

The completed runs used the active OceanSim extension and registered assets. Their reports requested D3D12 (`/app/vulkan=false`), read back `RaytracedLighting`, and reported 752 x 480 stereo calibration with a 0.38 m baseline. These are partial Kit, stage, stereo and Replicator results. The reports do not independently prove which graphics API Kit used or that physical caustics appeared. The runs did not use `--record`, so image quality cannot be assessed.

## Current-session startup attempt

The installed `C:\isaacsim\_build\windows-x86_64\release\python.bat` was invoked with `run.py --startup-only` and `OCEANSIM_EXT_PATH` set to the active OceanSim directory. Kit logged `PermissionError: [WinError 5] Access is denied` while scanning `exts/omni.pip.compute/pip_prebundle/cv2`. Many Python extensions then failed to import, followed by a fatal shutdown trace. Direct file inspection confirmed that this session cannot list that directory in either the active or backup Isaac Sim tree. The wrapper returned exit code 0 despite the Kit errors; **this startup attempt did not pass**. A valid attempt requires the `[Phase 1] SimulationApp and OceanSim startup succeeded.` marker and a clean Kit log, not the wrapper exit code alone.

A repeat attempt at 16:55 UTC produced the same permission error and extension failures. The wrapper again returned 0, and the Phase 1 success marker was absent.

The independent configuration check (`python run.py --validate-only`) passed, and all 15 unit tests passed in this session. No application code was changed.

## Remaining acceptance checks

Run from a Windows session that can read the installed extension tree, using the PowerShell setup in the README:

```powershell
& $python run.py --startup-only
& $python run.py --scene tank --mode interactive --frames 10
& $python run.py --scene tank --headless --frames 10 --record
& $python run.py --scene tank --experiment change_detection --headless --frames 5 --record
```

Confirm the actual Kit graphics API and clean shutdown. Inspect the tank, BlueROV scale/heading and mount clearance, both processed camera images, refractive water, and caustics-on/off floor renders. The recorded headless run must have ten matched left/right 752 x 480 PNGs and ten pose records. Each experiment pass must have five matched PNG pairs and poses, identical camera calibration/trajectory, and the intended crate displacement. Finally, repeat a bounded run, close an unbounded preview and interrupt a capture with Ctrl+C to verify cleanup, preservation of earlier outputs and `status.json` reporting. A forced process termination cannot update the status file.
