"""Standalone lifecycle after SimulationApp has initialized Kit."""
from __future__ import annotations

import random
import warnings

import carb.settings
import numpy as np
import omni.replicator.core as rep
import omni.timeline
import omni.usd

from config import resolve_path
from environments.underwater import UnderwaterEnvironment, configure_rtx
from experiments.change_detection import object_position, prepare_pass, trajectory_pose
from recording import PoseRecorder, create_run_directory, write_json
from robots.bluerov import VEHICLE_PATH, build_bluerov, set_pose
from scenes.tank import build_scene
from sensors.stereo import CAMERA_PATHS, StereoCameras, build_stereo_rig, world_matrix


def run(app, cfg, args, extension, headless):
    seed = cfg["simulation"]["seed"]
    random.seed(seed)
    np.random.seed(seed)
    rep.set_global_seed(seed)
    rep.orchestrator.set_capture_on_play(False)
    timeline = omni.timeline.get_timeline_interface()
    timeline.set_auto_update(False)
    timeline.pause()
    directory = create_run_directory(resolve_path(cfg["output"]["directory"]))
    write_json(directory / "config.json", cfg)
    status = {"state": "initializing", "completed_frames": {}, "extension": extension}
    write_json(directory / "status.json", status)
    print(f"[Output] {directory}")
    water = stereo = recorder = None
    try:
        context = omni.usd.get_context()
        # SimulationApp normally creates an empty stage. Reuse it rather than
        # opening another stage and invalidating extension/sensor state.
        if context.get_stage() is None and not context.new_stage():
            raise RuntimeError("Could not create the active USD stage")
        stage = context.get_stage()
        stage.SetTimeCodesPerSecond(cfg["simulation"]["fps"])
        stage.SetFramesPerSecond(cfg["simulation"]["fps"])
        build_scene(stage, cfg)
        robot_report = build_bluerov(stage, cfg["robot"])
        build_stereo_rig(stage, cfg["stereo"])
        for side, path in CAMERA_PATHS.items():
            x, y, z = world_matrix(stage, path)[:3, 3]
            width, length, _ = cfg["tank"]["dimensions_m"]
            if abs(x) >= width / 2 or abs(y) >= length / 2 or not 0 < z < cfg["water"]["height_m"]:
                raise RuntimeError(f"{side} camera is outside the submerged tank: {(x, y, z)}")
        print("[Phase 2] Tank, kinematic BlueROV and vehicle-mounted USD cameras created.")

        render_report = configure_rtx(cfg)
        water = UnderwaterEnvironment(stage, cfg)
        render_report["water_material"] = water.material_path
        settings = carb.settings.get_settings()
        render_report["settings_readback"] = {
            key: settings.get(key) for key in (
                "/rtx/caustics/enabled", "/rtx/raytracing/caustics/photonCountMultiplier",
                "/rtx/raytracing/caustics/photonMaxBounces", "/rtx/raytracing/caustics/eawFilteringSteps",
                *cfg["rtx"]["settings"].keys(),
            )
        }
        write_json(directory / "render_validation.json", render_report)
        stereo = StereoCameras(stage, cfg, directory, headless=headless)
        calibration = stereo.calibration()
        write_json(directory / "stereo_calibration.json", calibration)
        print("[Phase 3] OceanSim stereo initialized; intrinsics, baseline and relative axes verified.")
        print("[Phase 4] Refractive WaterSurface and RTX settings applied; visible caustics require inspection.")

        experiment = args.experiment == "change_detection"
        passes = ("before", "after") if experiment else ("before",)
        frames = args.frames
        if frames is None:
            frames = cfg["experiment"]["frames_per_pass"] if experiment else (cfg["simulation"]["headless_frames"] if headless else 0)
        manifest = {
            "scene": "tank", "experiment": args.experiment, "seed": seed,
            "simulation_fps": cfg["simulation"]["fps"], "frames_per_pass": frames,
            "robot": robot_report, "calibration": "stereo_calibration.json",
            "render_validation": "render_validation.json", "resolved_config": "config.json",
            "changed_prim": "/World/Changes/MovableCrate",
            "positions_m": {name: object_position(cfg, name) for name in passes},
            "scene_files": {name: f"tank_{name}_rtx.usda" for name in passes},
            "record_images": cfg["output"]["record_images"],
            "clock": "Logical time = frame/fps; pose and wave phase held constant during synchronized render subframes",
            "repeatability": "Deterministic scene, trajectory and water phase; RTX temporal history and GPU rendering are not guaranteed bitwise identical across passes/backends",
        }
        write_json(directory / "scene_manifest.json", manifest)
        initial_extrinsics = calibration["T_body_optical"]

        def render_step():
            if not app.is_running():
                raise InterruptedError("Isaac Sim window closed before the run completed")
            rep.orchestrator.step(
                rt_subframes=cfg["simulation"]["rt_subframes"], delta_time=0.0,
                pause_timeline=True, wait_for_render=True,
            )

        for pass_name in passes:
            rep.set_global_seed(seed)
            if experiment:
                prepare_pass(stage, cfg, pass_name)
            timeline.set_current_time(0.0)
            water.update(0, force=True)
            # Snapshots have the same initial camera pose, water phase and
            # background. No stage reopen or geometry recreation is needed.
            scene_path = directory / f"tank_{pass_name}_rtx.usda"
            if not stage.GetRootLayer().Export(str(scene_path)):
                raise RuntimeError(f"Could not export {scene_path}")
            for _ in range(cfg["simulation"]["warmup_frames"]):
                render_step()
            recorder = PoseRecorder(directory / pass_name, images=cfg["output"]["record_images"])
            index = 0
            status["state"] = f"running_{pass_name}"
            write_json(directory / "status.json", status)
            while frames == 0 or index < frames:
                if not app.is_running():
                    if frames == 0:
                        break
                    raise InterruptedError("Application closed during a bounded capture")
                time_s = index / cfg["simulation"]["fps"]
                timeline.set_current_time(time_s)
                if experiment:
                    set_pose(stage, *trajectory_pose(cfg["experiment"]["trajectory"], index))
                water.update(time_s)
                pair = None
                for _ in range(cfg["simulation"]["readiness_attempts"]):
                    render_step()
                    pair = stereo.render_pair()
                    if pair is not None:
                        break
                if pair is None:
                    raise RuntimeError("Stereo RGB/depth annotators did not become ready. Check Kit's RTX/CUDA/Replicator errors and the active graphics API.")
                body = world_matrix(stage, VEHICLE_PATH)
                poses = {"T_world_body": body.tolist(), "T_world_optical": {
                    side: world_matrix(stage, path, optical=True).tolist() for side, path in CAMERA_PATHS.items()
                }, "T_world_changed_object": world_matrix(stage, "/World/Changes/MovableCrate").tolist()}
                # Check that inherited transforms continue to follow the ROV.
                for side, matrix in poses["T_world_optical"].items():
                    if not np.allclose(np.linalg.inv(body) @ matrix, initial_extrinsics[side], atol=1e-5):
                        raise RuntimeError(f"{side} camera no longer follows the vehicle with fixed calibration")
                recorder.record(index, time_s, pair, poses)
                index += 1
                status["completed_frames"][pass_name] = index
            recorder.close()
            recorder = None
            write_json(directory / "status.json", status)
            print(f"[Capture] {pass_name}: {index} stereo pairs processed.")
        status["state"] = "complete"
        write_json(directory / "status.json", status)
        print(f"[Done] {directory}")
    except BaseException as error:
        status["state"] = "interrupted" if isinstance(error, (KeyboardInterrupt, InterruptedError)) else "failed"
        status["error"] = f"{type(error).__name__}: {error}"
        write_json(directory / "status.json", status)
        raise
    finally:
        # Run all cleanup while Kit's renderer and extension manager still live.
        if recorder is not None:
            recorder.close()
        try:
            rep.orchestrator.stop()
            rep.orchestrator.wait_until_complete()
        except Exception as error:
            warnings.warn(f"Replicator cleanup: {error}")
        if stereo is not None:
            stereo.close()
        if water is not None:
            water.close()
        timeline.stop()
