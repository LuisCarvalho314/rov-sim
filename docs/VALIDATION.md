# Validation record

Checked on 2026-11-04 in WSL against the existing Windows installation. The Windows interop probe (`cmd.exe /c ver`) fails with `UtilBindVsockAnyPort: socket failed 1`; Kit and Windows USD binaries cannot execute here. Linux Python has no `pxr` module. **There has been no successful Isaac Sim runtime/rendering test in this session.**

## Completed checks

- Inspected the 471-line tank builder, generated manifest and README before editing. Found and read the stereo preview at `C:\rov_sim\rov_stereo_preview.py` without changing that directory.
- Located the active source-build runtime and extension. Inspected versions: Isaac Sim `5.0.0-rc.45+mr.0.1791e148.local`, OceanSim manifest `1.0.0`, Kit kernel `107.3.1+isaac.206797.8131b85d`.
- Verified `SimulationApp` supports the launch options used. The installed Python experience enables Vulkan by default; the launcher supplies `/app/vulkan=false` before Windows device creation.
- Checked Kit extension-manager and local USD/timeline APIs. Verified `rep.orchestrator.step` supports `rt_subframes`, `pause_timeline`, `delta_time` and `wait_for_render` in Replicator `1.12.16`.
- Checked `UW_Camera` constructor, named YAML fields, initialization, image buffer, close implementation and inherited `Camera.destroy()`. Cleanup handles partial initialization and annotator failures.
- Checked `WaterSurface` constructor, active-stage/MDL behavior, deformation arguments and photon controls. Animation retains one instance and uses an explicit wave clock.
- Confirmed `light:enableCaustics` in `omni.kit.property.light` `1.0.12`. The old speculative `inputs:enableCaustics` is absent from the new application.
- Confirmed asset registration points at `C:\isaacsim-assets\OceanSim_assets` and `Bluerov/BROV_low.usd` has a USD crate header. Composed units, geometry, heading and bounds require USD runtime inspection.
- AST comparison confirms `group`, `rgb`, `box`, `pipe`, `build_fixed_equipment` and `build_changed_object` exactly preserve the original functions. Legacy script and existing generated files remain untouched.
- `python3 run.py --validate-only`: passed, including from another working directory.
- `python3 -m compileall -q run.py config.py startup.py application.py recording.py scenes robots sensors environments experiments tests`: passed.
- `python3 -m unittest discover -s tests -v`: **15 passed**. Covers configuration/path validation, extension discovery, startup import order/backend options, shutdown after extension failure, camera cleanup after an annotator failure, repeatable trajectory/heading interpolation, PNG data/CRCs and previous-output preservation.

[source_validation.json](source_validation.json) records source paths, SHA-256 fingerprints and API signatures. Startup/cleanup tests use API doubles; they do not validate Kit, USD or GPU behavior.

## Required Windows runtime checks

Set the PowerShell runtime/extension variables from the README, then run:

```powershell
& $python run.py --startup-only
& $python run.py --scene tank --mode interactive --frames 10
& $python run.py --scene tank --headless --frames 10 --record
& $python run.py --scene tank --experiment change_detection --headless --frames 5 --record
```

1. **Startup:** confirm Kit reports D3D12, loads the requested OceanSim directory without dependency errors and exits cleanly.
2. **Stage/asset:** inspect the original equipment, BlueROV heading, dimensions, mount clearance and submerged placement. Check manifest asset units/bounds. Adjust `robot.model` alignment for the visual asset; the carrier body frame and stereo calibration stay explicit.
3. **Stereo:** verify both windows/PNGs are 752 × 480 and visually plausible. Runtime assertions check initialized K, parallel axes, 0.38 m baseline and fixed camera-to-body transforms. Confirm both cameras follow the trajectory.
4. **Water:** inspect the refractive MDL binding, size/height and optional animated deformation. Both passes must reset to the same wave phase and initial mesh.
5. **Physical caustics:** inspect rendering readback and logs, then compare caustics on/off runs with otherwise identical settings. Verify projected floor patterns respond to refractive waves. Assess DX12 and Vulkan separately if using both. Readback is never treated as proof of physical support.
6. **Experiment:** check that both passes contain five pose records and matching left/right PNG indices. Camera poses/calibration must match across passes. Initial USD snapshots should differ only in crate parent translation. Image differences can also reflect the crate's lighting/visibility and residual temporal rendering history.
7. **Lifecycle:** repeat a bounded run, close an unbounded GUI run and interrupt a capture with Ctrl+C. Check annotator/render-product cleanup, preservation of earlier outputs and `status.json` interruption reporting.

Offscreen OceanSim UI dependencies, model placement, Replicator readiness, DX12/CUDA interoperability, visible caustics and GPU resource release require runtime checks. There are no thrusters, hydrodynamics, lens housings or volumetric fluids. The authored scene clock is deterministic; bitwise/cross-backend RTX image repeatability is not guaranteed.
