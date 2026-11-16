"""Standalone lifecycle after SimulationApp has initialized Kit."""
from __future__ import annotations

import random
import os
import time
import subprocess
import warnings
from pathlib import Path

import carb.settings
import numpy as np
import omni.replicator.core as rep
import omni.timeline
import omni.usd

from rov_sim.config import resolve_path
from rov_sim.environments.underwater import UnderwaterEnvironment, configure_rtx
from rov_sim.experiments.change_detection import object_position, prepare_pass, trajectory_pose
from rov_sim.recording import PoseRecorder, create_run_directory, write_json
from rov_sim.preview import generate_previews
from rov_sim.robots.bluerov import VEHICLE_PATH, build_bluerov, set_pose
from rov_sim.scenes.tank import build_scene, build_inspection_lighting
from rov_sim.sensors.stereo import CAMERA_PATHS, StereoCameras, build_stereo_rig, tracy_zone, world_matrix


def _gpu_name():
    try:
        result = subprocess.run(["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
                                capture_output=True, text=True, timeout=3, check=False)
        return result.stdout.strip().splitlines() if result.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired):
        return None


def _memory_snapshot():
    """Outside measured iterations; device-wide VRAM and current-process RAM."""
    result = {"gpu_scope": "whole device, includes desktop and other applications"}
    try:
        import psutil
        info = psutil.Process().memory_info()
        result["process_memory_bytes"] = info._asdict()
    except ImportError:
        result["process_memory_bytes"] = None
    try:
        query = subprocess.run(["nvidia-smi", "--query-gpu=memory.used,memory.total",
                                "--format=csv,noheader,nounits"], capture_output=True,
                               text=True, timeout=3, check=False)
        result["gpu_used_total_mib"] = query.stdout.strip() if query.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired):
        result["gpu_used_total_mib"] = None
    return result


def run(app, cfg, args, extension, headless):
    benchmark_mode = getattr(args, "benchmark", False)
    diagnostic_mode = getattr(args, "benchmark_mode", "full") if benchmark_mode else "full"
    tracy = bool(getattr(args, "profile_tracy", False))
    if benchmark_mode:
        from rov_sim.benchmark import Benchmark
    seed = cfg["simulation"]["seed"]
    random.seed(seed)
    np.random.seed(seed)
    rep.set_global_seed(seed)
    rep.orchestrator.set_capture_on_play(False)
    timeline = omni.timeline.get_timeline_interface()
    timeline.set_auto_update(False)
    timeline.pause()
    directory = (Path(args._benchmark_run_dir) if getattr(args, "_benchmark_run_dir", None)
                 else create_run_directory(resolve_path(cfg["output"]["directory"])))
    write_json(directory / "config.json", cfg)
    status = {"state": "initializing", "completed_frames": {}, "extension": extension,
              "preview": {"requested": cfg["output"]["preview"]["enabled"], "state": "pending" if cfg["output"]["preview"]["enabled"] else "disabled", "videos": {}}}
    write_json(directory / "status.json", status)
    print(f"[Output] {directory}")
    water = stereo = recorder = benchmark = diagnostics = photometry = None
    drain_ms = 0.0
    warp_gpu_timing = None
    hydra_stats = None
    rtx_gpu_samples = []
    collecting_gpu = False
    memory_samples = []
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
        build_inspection_lighting(stage, cfg)
        build_stereo_rig(stage, cfg["stereo"])
        if getattr(args, "stereo_diagnostics", False):
            from rov_sim.diagnostics.stereo_diagnostics import StereoDiagnostics
            diagnostics = StereoDiagnostics(stage, cfg, directory)
        for side, path in CAMERA_PATHS.items():
            x, y, z = world_matrix(stage, path)[:3, 3]
            width, length, _ = cfg["tank"]["dimensions_m"]
            if abs(x) >= width / 2 or abs(y) >= length / 2 or not 0 < z < cfg["water"]["height_m"]:
                raise RuntimeError(f"{side} camera is outside the submerged tank: {(x, y, z)}")
        print("[Phase 2] Tank, kinematic BlueROV and vehicle-mounted USD cameras created.")

        render_report = configure_rtx(cfg)
        water = UnderwaterEnvironment(stage, cfg)
        if getattr(args, "photometric_diagnostics", False):
            from rov_sim.diagnostics.photometric_diagnostics import PhotometricCapture
            photometry = PhotometricCapture(stage, cfg, directory)
        render_report["water_material"] = water.material_path
        settings = carb.settings.get_settings()
        render_report["settings_readback"] = {
            key: settings.get(key) for key in (
                *(("/rtx/caustics/enabled", "/rtx/raytracing/caustics/photonCountMultiplier",
                   "/rtx/raytracing/caustics/photonMaxBounces", "/rtx/raytracing/caustics/eawFilteringSteps")
                  if cfg["runtime"]["renderer"] == "RaytracedLighting" else ()),
                *cfg["rtx"]["settings"].keys(),
            )
        }
        write_json(directory / "render_validation.json", render_report)
        camera_backend = cfg["stereo"].get("backend", "legacy")
        if camera_backend == "legacy":
            stereo = StereoCameras(stage, cfg, directory, headless=headless)
        else:
            from rov_sim.sensors.rtx_stereo import RtxStereoCameras
            stereo = RtxStereoCameras(stage, cfg, directory, headless=headless)
        render_report["camera_backend"] = camera_backend
        stereo.download_degraded_depth = diagnostics is not None or cfg["stereo"].get("readback_degraded_depth", False)
        calibration = stereo.calibration()
        if benchmark_mode:
            benchmark = Benchmark(cfg, recording=cfg["output"]["record_images"],
                                  warmup=cfg["simulation"]["warmup_frames"], gpu=_gpu_name(),
                                  mode=diagnostic_mode, tracy=tracy,
                                  versions={"isaac_sim": (Path(os.environ["ISAAC_PATH"]) / "VERSION").read_text().strip(),
                                            "oceansim": extension["extension_id"]})
        write_json(directory / "stereo_calibration.json", calibration)
        print("[Phase 3] OceanSim stereo initialized; intrinsics, baseline and relative axes verified.")
        print("[Phase 4] Refractive WaterSurface and renderer settings applied; visual appearance requires inspection.")

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

        def render_step(timings=None):
            if not app.is_running():
                raise InterruptedError("Isaac Sim window closed before the run completed")
            sync_ms = stereo.before_render() if camera_backend != "legacy" else 0.0
            if camera_backend == "tiled":
                # Kit 110's tiled view cache can lag a USD parent pose by one
                # update despite fresh annotator counts/ReferenceTime. Flush
                # that pose while logical time is held before capturing.
                app.update()
            if timings is not None:
                timings["gpu_synchronization_ms"] += sync_ms
            with tracy_zone("ROV/StereoRenderStep", tracy):
                if diagnostics is not None:
                    diagnostics.before_render(stereo)
                rep.orchestrator.step(
                    rt_subframes=cfg["simulation"]["rt_subframes"], delta_time=0.0,
                    pause_timeline=True, wait_for_render=True,
                )
                if camera_backend != "legacy":
                    stereo.after_render()
            if collecting_gpu and hydra_stats is not None:
                rtx_gpu_samples.append(hydra_stats.get_gpu_profiler_result())
            return sync_ms

        def validate_images(pair, evidence):
            image_checks = {}
            for side in ("left", "right"):
                image = pair[side]
                rgb = image[..., :3]
                if image.shape[:2] != (cfg["stereo"]["resolution"][1], cfg["stereo"]["resolution"][0]) or not np.any(rgb):
                    raise RuntimeError(f"{side} OceanSim image has wrong dimensions or is entirely black")
                image_checks[side] = {"shape": list(image.shape), "nonzero_rgb": True}
            render_report["image_checks"] = image_checks
            render_report["processed_stereo_frame"] = True
            render_report["frame_evidence"] = evidence
            write_json(directory / "render_validation.json", render_report)

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
            if benchmark_mode:
                memory_samples.append({"pass": pass_name, "phase": "after_warmup", **_memory_snapshot()})
            status["state"] = f"running_{pass_name}"
            write_json(directory / "status.json", status)
            if getattr(args, "profile_warp_gpu", False):
                import warp as wp
                from omni.hydra.engine.stats import HydraEngineStats
                hydra_stats = HydraEngineStats()
                wp.timing_begin(cuda_filter=wp.TIMING_KERNEL | wp.TIMING_KERNEL_BUILTIN |
                                wp.TIMING_MEMCPY | wp.TIMING_MEMSET, synchronize=False)
                collecting_gpu = True
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
                timings = {"annotator_acquisition_ms": 0.0, "underwater_processing_ms": 0.0,
                           "gpu_readback_ms": 0.0, "gpu_synchronization_ms": 0.0,
                           "processing_readback_combined_ms": 0.0} if benchmark_mode else None
                render_ns = 0
                pair = None
                retries = 0
                for attempt in range(cfg["simulation"]["readiness_attempts"]):
                    render_start_ns = time.perf_counter_ns() if benchmark_mode else None
                    sync_ms = render_step(timings)
                    if diagnostics is not None:
                        diagnostics.capture_inputs(stereo)
                    if benchmark_mode:
                        render_ns += time.perf_counter_ns() - render_start_ns - int(sync_ms * 1e6)
                    if diagnostic_mode == "render-only":
                        pair = {}
                    elif diagnostic_mode == "no-readback":
                        pair = stereo.render_pair(timings, diagnostic_mode="no-readback", tracy=tracy)
                    elif tracy:
                        pair = stereo.render_pair(timings, diagnostic_mode="full", tracy=True)
                    else:
                        pair = stereo.render_pair(timings) if benchmark_mode else stereo.render_pair()
                    if pair is not None:
                        break
                    retries += 1
                if pair is None:
                    raise RuntimeError("Stereo RGB/depth annotators did not become ready. Check Kit's RTX/CUDA/Replicator errors and the active graphics API.")
                if diagnostics is not None:
                    diagnostics.validate_pair(stereo, pair, pass_name, index, time_s,
                                              save=index in (0, frames - 1))
                if photometry is not None and index in (0, 15, 30, 45, frames - 1):
                    photometry.capture(stereo, pair, pass_name, index)
                if diagnostic_mode == "full" and not render_report["processed_stereo_frame"]:
                    validate_images(pair, "Both OceanSim processed stereo images passed readiness checks after a rendered step; visual refraction and attenuation require image inspection.")
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
                           "underwater_processing_ms": timings["underwater_processing_ms"] if camera_backend != "legacy" or tracy or diagnostic_mode == "no-readback" else None,
                           "gpu_readback_ms": timings["gpu_readback_ms"] if (camera_backend != "legacy" or tracy) and diagnostic_mode == "full" else None,
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
            if getattr(args, "profile_warp_gpu", False):
                collecting_gpu = False
                drain_start_ns = time.perf_counter_ns()
                activities = wp.timing_end(synchronize=True)
                finalize_ms = (time.perf_counter_ns() - drain_start_ns) / 1e6
                categories = {wp.TIMING_KERNEL: "kernel", wp.TIMING_KERNEL_BUILTIN: "builtin_kernel",
                              wp.TIMING_MEMCPY: "memcpy", wp.TIMING_MEMSET: "memset"}
                if warp_gpu_timing is None:
                    warp_gpu_timing = {"activities": {}, "finalize_wall_ms": 0.0,
                                       "scope": "Warp CUDA activities only; RTX/DX12 GPU work is in the Tracy trace"}
                warp_gpu_timing["finalize_wall_ms"] += finalize_ms
                for activity in activities:
                    name = categories.get(activity.filter, f"other_{activity.filter}")
                    item = warp_gpu_timing["activities"].setdefault(name, {"count": 0, "gpu_elapsed_ms": 0.0})
                    item["count"] += 1
                    item["gpu_elapsed_ms"] += activity.elapsed
                    by_name = warp_gpu_timing.setdefault("by_name", {})
                    named = by_name.setdefault(activity.name, {"count": 0, "gpu_elapsed_ms": 0.0})
                    named["count"] += 1
                    named["gpu_elapsed_ms"] += activity.elapsed
                if diagnostic_mode == "no-readback":
                    drain_ms += finalize_ms
            if diagnostic_mode != "full":
                if diagnostic_mode == "no-readback" and not getattr(args, "profile_warp_gpu", False):
                    import warp as wp
                    drain_start_ns = time.perf_counter_ns()
                    wp.synchronize()  # Diagnostic mode only: include queued Warp work before reporting throughput.
                    drain_ms += (time.perf_counter_ns() - drain_start_ns) / 1e6
                # Validation is outside measured rows; both diagnostic modes
                # still prove the configured stereo/OceanSim output works.
                pair = None
                for _ in range(cfg["simulation"]["readiness_attempts"]):
                    render_step()
                    pair = stereo.render_pair()
                    if pair is not None:
                        break
                if pair is None:
                    raise RuntimeError("Post-benchmark OceanSim stereo validation did not become ready")
                validate_images(pair, "Post-benchmark OceanSim stereo pair validated outside measured diagnostic frames.")
            if benchmark_mode:
                memory_samples.append({"pass": pass_name, "phase": "after_capture_and_gpu_drain", **_memory_snapshot()})
            write_json(directory / "status.json", status)
            label = "stereo pairs processed" if diagnostic_mode == "full" else "diagnostic steps submitted"
            print(f"[Capture] {pass_name}: {index} {label}.")
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
            if hydra_stats is not None:
                write_json(directory / "rtx_gpu_samples.json", {
                    "scope": "Hydra GPU profiler per completed render step; reported GPU events, not wall pipeline latency. Multiple updates/products may occur per stereo pair.",
                    "samples": rtx_gpu_samples})
            report = benchmark.write(directory, calibration=calibration, render_validation=render_report,
                                     drain_ms=drain_ms, warp_gpu_timing=warp_gpu_timing,
                                     mp4_encoding_s=(time.perf_counter_ns() - encoding_start_ns) / 1e9 if encoding_start_ns else None)
            report["memory_samples"] = memory_samples
            report["camera_infrastructure"] = (stereo.infrastructure_report() if camera_backend != "legacy" else
                                                {"backend": "legacy", "render_products": [c.get_render_product_path() for c in stereo.cameras.values()]})
            write_json(directory / "benchmark.json", report)
            unit = report["summary"]["throughput_unit"]
            print(f"[Benchmark] {report['summary']['effective_pairs_per_s']:.2f} {unit}/s; "
                  f"{report['summary']['missed_deadlines']} acquisition deadlines missed", flush=True)
        if camera_backend != "legacy":
            write_json(directory / "camera_infrastructure.json", stereo.infrastructure_report())
        status["state"] = "complete"
        if diagnostics is not None:
            diagnostics.finish()
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
        try:
            rep.orchestrator.stop()
            rep.orchestrator.wait_until_complete()
        except Exception as error:
            warnings.warn(f"Replicator cleanup: {error}")
        # Deliver STOP while sensor graphs still exist (Kit 110 callbacks).
        timeline.stop()
        app.update()
        if diagnostics is not None:
            diagnostics.close()
        if stereo is not None:
            stereo.close()
        if water is not None:
            water.close()
