"""Standalone lifecycle after SimulationApp has initialized Kit."""
from __future__ import annotations

import random
import time
import subprocess
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
from preview import generate_previews
from robots.bluerov import VEHICLE_PATH, build_bluerov, set_pose
from scenes.tank import build_scene
from sensors.stereo import CAMERA_PATHS, StereoCameras, build_stereo_rig, world_matrix


def _gpu_name():
    try:
        result = subprocess.run(["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
                                capture_output=True, text=True, timeout=3, check=False)
        return result.stdout.strip().splitlines() if result.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired):
        return None


def run(app, cfg, args, extension, headless):
    benchmark_mode = getattr(args, "benchmark", False)
    if benchmark_mode:
        from benchmark import Benchmark
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
    status = {"state": "initializing", "completed_frames": {}, "extension": extension,
              "preview": {"requested": cfg["output"]["preview"]["enabled"], "state": "pending" if cfg["output"]["preview"]["enabled"] else "disabled", "videos": {}}}
    write_json(directory / "status.json", status)
    print(f"[Output] {directory}")
    water = stereo = recorder = benchmark = None
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
        if benchmark_mode:
            benchmark = Benchmark(cfg, recording=cfg["output"]["record_images"],
                                  warmup=cfg["simulation"]["warmup_frames"], gpu=_gpu_name(),
                                  versions={"isaac_sim": getattr(app, "_app_version", None),
                                            "oceansim": extension["extension_id"]})
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
            for warmup_index in range(cfg["simulation"]["warmup_frames"]):
                if benchmark_mode:
                    warmup_time_s = warmup_index / cfg["simulation"]["fps"]
                    timeline.set_current_time(warmup_time_s)
                    water.update(warmup_time_s)
                render_step()
                if benchmark_mode:
                    stereo.render_pair()
            if not benchmark_mode or cfg["output"]["record_images"]:
                recorder = PoseRecorder(directory / pass_name, images=cfg["output"]["record_images"])
            index = 0
            status["state"] = f"running_{pass_name}"
            write_json(directory / "status.json", status)
            while frames == 0 or index < frames:
                if not app.is_running():
                    if frames == 0:
                        break
                    raise InterruptedError("Application closed during a bounded capture")
                start_ns = time.perf_counter_ns() if benchmark_mode else None
                time_s = index / cfg["simulation"]["fps"]
                timeline.set_current_time(time_s)
                if experiment:
                    set_pose(stage, *trajectory_pose(cfg["experiment"]["trajectory"], index))
                water.update(time_s)
                scene_end_ns = time.perf_counter_ns() if benchmark_mode else None
                timings = {"annotator_acquisition_ms": 0.0, "processing_readback_combined_ms": 0.0} if benchmark_mode else None
                render_ns = 0
                pair = None
                retries = 0
                for attempt in range(cfg["simulation"]["readiness_attempts"]):
                    render_start_ns = time.perf_counter_ns() if benchmark_mode else None
                    render_step()
                    if benchmark_mode:
                        render_ns += time.perf_counter_ns() - render_start_ns
                    pair = stereo.render_pair(timings) if benchmark_mode else stereo.render_pair()
                    if pair is not None:
                        break
                    retries += 1
                if pair is None:
                    raise RuntimeError("Stereo RGB/depth annotators did not become ready. Check Kit's RTX/CUDA/Replicator errors and the active graphics API.")
                acquisition_end_ns = time.perf_counter_ns() if benchmark_mode else None
                body = world_matrix(stage, VEHICLE_PATH)
                poses = {"T_world_body": body.tolist(), "T_world_optical": {
                    side: world_matrix(stage, path, optical=True).tolist() for side, path in CAMERA_PATHS.items()
                }, "T_world_changed_object": world_matrix(stage, "/World/Changes/MovableCrate").tolist()}
                # Check that inherited transforms continue to follow the ROV.
                for side, matrix in poses["T_world_optical"].items():
                    if not np.allclose(np.linalg.inv(body) @ matrix, initial_extrinsics[side], atol=1e-5):
                        raise RuntimeError(f"{side} camera no longer follows the vehicle with fixed calibration")
                if recorder is not None:
                    recorder.record(index, time_s, pair, poses)
                iteration_end_ns = time.perf_counter_ns() if benchmark_mode else None
                if benchmark_mode:
                    row = {"frame": index, "pass": pass_name, "simulation_time_s": time_s,
                           "scene_update_ms": (scene_end_ns - start_ns) / 1e6,
                           "render_ms": render_ns / 1e6, **timings,
                           "underwater_processing_ms": None, "gpu_readback_ms": None,
                           "recording_ms": (iteration_end_ns - acquisition_end_ns) / 1e6 if recorder else 0.0,
                           "acquisition_total_ms": (acquisition_end_ns - start_ns) / 1e6,
                           "iteration_total_ms": (iteration_end_ns - start_ns) / 1e6,
                           "readiness_retries": retries}
                    benchmark.add(row, start_ns=start_ns, acquisition_end_ns=acquisition_end_ns,
                                  iteration_end_ns=iteration_end_ns)
                index += 1
                status["completed_frames"][pass_name] = index
                if benchmark_mode and (index % 100 == 0 or index == frames):
                    print(benchmark.progress(frames * len(passes)), flush=True)
            if recorder is not None:
                recorder.close()
            recorder = None
            write_json(directory / "status.json", status)
            print(f"[Capture] {pass_name}: {index} stereo pairs processed.")
        encoding_start_ns = time.perf_counter_ns() if benchmark_mode and cfg["output"]["preview"]["enabled"] else None
        if cfg["output"]["preview"]["enabled"]:
            status["state"] = "encoding_previews"
            status["preview"]["state"] = "encoding"
            write_json(directory / "status.json", status)

            def preview_result(name, result):
                status["preview"]["videos"][name] = result
                write_json(directory / "status.json", status)

            generate_previews(directory, passes, cfg["output"]["preview"], on_result=preview_result)
            status["preview"]["state"] = "complete"
        if benchmark_mode:
            report = benchmark.write(directory, calibration=calibration, render_validation=render_report,
                                     mp4_encoding_s=(time.perf_counter_ns() - encoding_start_ns) / 1e9 if encoding_start_ns else None)
            print(f"[Benchmark] {report['summary']['effective_pairs_per_s']:.2f} processed pairs/s; "
                  f"{report['summary']['missed_deadlines']} acquisition deadlines missed", flush=True)
        status["state"] = "complete"
        write_json(directory / "status.json", status)
        print(f"[Done] {directory}")
    except BaseException as error:
        status["state"] = "interrupted" if isinstance(error, (KeyboardInterrupt, InterruptedError)) else "failed"
        status["error"] = f"{type(error).__name__}: {error}"
        if status["preview"]["state"] == "encoding":
            status["preview"]["state"] = "failed"
            status["preview"]["error"] = status["error"]
        write_json(directory / "status.json", status)
        raise
    finally:
        # Run all cleanup while Kit's renderer and extension manager still live.
        if recorder is not None:
            recorder.close()
        if stereo is not None:
            stereo.close()
        try:
            rep.orchestrator.stop()
            rep.orchestrator.wait_until_complete()
        except Exception as error:
            warnings.warn(f"Replicator cleanup: {error}")
        if water is not None:
            water.close()
        timeline.stop()
