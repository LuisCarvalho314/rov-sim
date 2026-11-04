# Windows runtime validation, 2026-11-04

This record supplements [the original validation note](docs/VALIDATION.md), which predates the Windows runs below. Existing output directories were preserved.

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
