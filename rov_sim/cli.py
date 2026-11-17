"""Standalone ROV simulator. Invoke with Isaac Sim's bundled Python (6.1 validated)."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

from rov_sim.config import BACKENDS, ROOT, find_oceansim_extension, load_config, resolve_path, validate_config


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="configs/tank.yaml")
    parser.add_argument("--scene", choices=["tank"], default="tank")
    parser.add_argument("--mode", choices=["interactive", "headless"], default="interactive")
    parser.add_argument("--headless", action="store_true", help="Alias for --mode headless")
    parser.add_argument("--experiment", choices=["change_detection"])
    parser.add_argument("--frames", type=int, help="Frames per pass; 0 keeps interactive preview open")
    parser.add_argument("--record", action="store_true", help="Record paired underwater PNGs and ground truth")
    parser.add_argument("--stereo-diagnostics", action="store_true", help="Add a known target and validate raw RGB, clean range, synchronization and disparity")
    parser.add_argument("--photometric-diagnostics", action="store_true", help="Save raw RGB/range and scene evidence without adding targets (outside benchmarks)")
    parser.add_argument("--benchmark", action="store_true", help="Measure processed stereo throughput after warmup")
    parser.add_argument("--profile-python", action="store_true", help="Save cProfile data for the benchmark application run")
    parser.add_argument("--profile-tracy", action="store_true", help="Enable Kit Tracy CPU/GPU zones and capture a trace")
    parser.add_argument("--profile-warp-gpu", action="store_true", help="Collect Warp CUDA activity timings during measured frames")
    parser.add_argument("--benchmark-mode", choices=("full", "render-only", "no-readback"), default="full",
                        help="Opt-in diagnostic stage measured by --benchmark")
    parser.add_argument("--preview-mp4", action="store_true", help="Encode MP4 previews from recorded PNGs (requires --record or output.record_images)")
    parser.add_argument("--output-dir", help="Output root; each invocation creates a unique run directory")
    parser.add_argument("--oceansim-ext", help="Existing extension directory containing config/extension.toml")
    parser.add_argument("--backend", choices=["d3d12", "vulkan"])
    parser.add_argument("--camera-backend", choices=BACKENDS,
                        help="Camera acquisition backend; defaults to stereo.backend or legacy")
    parser.add_argument("--readback-degraded-depth", action="store_true",
                        help="Also download degraded depth on RTX backends (readback parity experiment)")
    parser.add_argument("--kit-arg", action="append", default=[], help="Extra Kit option, e.g. --kit-arg=--/renderer/activeGpu=0")
    parser.add_argument("--validate-only", action="store_true", help="Validate config without importing Isaac Sim")
    parser.add_argument("--startup-only", action="store_true", help="Start Kit, enable OceanSim, then close")
    parser.add_argument("--record-mcap", action="store_true",
                        help="Write one rosbag2 MCAP bag per pass (camera-sensor only; needs ROV_SIM_PIXI_ENV)")
    parser.add_argument("--mcap-storage", choices=("none", "zstd"),
                        help="MCAP storage preset for --record-mcap: none (default) or zstd (rosbag2 zstd_fast)")
    parser.add_argument("--_benchmark-child", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--_benchmark-run-dir", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.frames is not None and args.frames < 0:
        parser.error("--frames must be nonnegative")
    if args.frames == 0 and (args.experiment or args.headless or args.mode == "headless" or args.benchmark):
        parser.error("--frames 0 is only valid for interactive preview without an experiment")
    if args.benchmark and args.startup_only:
        parser.error("--benchmark requires a capture run, not --startup-only")
    if args.profile_python and not args.benchmark:
        parser.error("--profile-python requires --benchmark")
    if args.profile_tracy and not args.benchmark:
        parser.error("--profile-tracy requires --benchmark")
    if args.profile_warp_gpu and not args.benchmark:
        parser.error("--profile-warp-gpu requires --benchmark")
    if args.benchmark_mode != "full" and not args.benchmark:
        parser.error("--benchmark-mode requires --benchmark")
    if args.stereo_diagnostics and args.benchmark:
        parser.error("Run --stereo-diagnostics separately from --benchmark; raw GT downloads change timing")
    if args.photometric_diagnostics and (args.benchmark or args.stereo_diagnostics):
        parser.error("Photometric diagnostics require a separate target-free, unbenchmarked run")
    if args.mcap_storage is not None and not args.record_mcap:
        parser.error("--mcap-storage requires --record-mcap")
    if args.record_mcap:
        headless = args.headless or args.mode == "headless"
        if args.frames == 0 or (args.frames is None and not args.experiment and not headless):
            parser.error("--record-mcap needs a bounded pass; set --frames above 0, --headless or --experiment")
        if args.startup_only:
            parser.error("--record-mcap requires a capture run, not --startup-only")
        if args.benchmark_mode != "full":
            parser.error("--record-mcap requires --benchmark-mode full; other modes skip readback")
        if args.photometric_diagnostics:
            parser.error("Run --photometric-diagnostics separately from --record-mcap")
        args.mcap_storage = args.mcap_storage or "none"
    return args


def supervise_benchmark(cfg, argv, *, tracy=False):
    """Keep a parent alive to report native Kit crashes during startup."""
    from rov_sim.recording import create_run_directory, write_json

    directory = create_run_directory(resolve_path(cfg["output"]["directory"]))
    write_json(directory / "config.json", cfg)
    write_json(directory / "status.json", {"state": "starting_kit", "completed_frames": {}})
    print(f"[Benchmark output] {directory}", flush=True)
    command = [sys.executable, "-m", "rov_sim", *argv,
               "--_benchmark-child", "--_benchmark-run-dir", str(directory)]
    capture = capture_log = None
    try:
        if tracy:
            runtime = Path(os.environ.get("ISAAC_PATH", ""))
            candidates = sorted((runtime / "extscache").glob("omni.kit.profiler.tracy-*/bin/capture.exe"))
            if not candidates:
                raise OSError("Installed Isaac Sim Tracy capture.exe not found under ISAAC_PATH/extscache")
            capture_log = (directory / "tracy_capture.log").open("w", encoding="utf-8")
            capture = subprocess.Popen([str(candidates[-1]), "-o", str(directory / "capture.tracy"), "-s", "120"],
                                       stdout=capture_log, stderr=subprocess.STDOUT,
                                       creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        child = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                 text=True, encoding="utf-8", errors="replace", cwd=ROOT)
        with (directory / "kit_console.log").open("w", encoding="utf-8") as log:
            for line in child.stdout:
                print(line, end="", flush=True)
                log.write(line)
        code = child.wait()
    except OSError as error:
        code = None
        launch_error = f"{type(error).__name__}: {error}"
    if capture is not None:
        try:
            capture_code = capture.wait(timeout=15)
        except subprocess.TimeoutExpired:
            capture.terminate()
            capture_code = capture.wait(timeout=5)
        capture_log.close()
    else:
        capture_code = None
    status = json.loads((directory / "status.json").read_text(encoding="utf-8"))
    status["process_exit_code"] = code
    status["console_log"] = "kit_console.log"
    if tracy:
        trace = directory / "capture.tracy"
        status["tracy_trace"] = "capture.tracy" if trace.is_file() and trace.stat().st_size else None
        status["tracy_capture_exit_code"] = capture_code
        if (directory / "benchmark.json").is_file():
            report_path = directory / "benchmark.json"
            report = json.loads(report_path.read_text(encoding="utf-8"))
            report["tracy_trace"] = status["tracy_trace"]
            report["tracy_capture_exit_code"] = capture_code
            write_json(report_path, report)
    if code != 0 or status.get("state") != "complete" or not (directory / "benchmark.json").is_file():
        status["state"] = "failed"
        phase = ("after benchmark capture during shutdown" if (directory / "benchmark.json").is_file()
                 else "before a complete benchmark report")
        status.setdefault("error", launch_error if code is None else
                          f"Isaac Sim process exited with code {code} {phase}; inspect the Kit crash log")
        write_json(directory / "status.json", status)
        print(f"[Benchmark failed] {directory}: {status['error']}", file=sys.stderr, flush=True)
        return 1
    write_json(directory / "status.json", status)
    return 0


def main(argv=None):
    args = parse_args(argv)
    cfg = load_config(args.config)
    if args.camera_backend:
        cfg["stereo"]["backend"] = args.camera_backend
    if args.readback_degraded_depth:
        cfg["stereo"]["readback_degraded_depth"] = True
    if args.backend:
        cfg["runtime"]["backend"] = args.backend
    if args.output_dir:
        cfg["output"]["directory"] = args.output_dir
    if args.benchmark:
        cfg["output"]["preview"]["enabled"] = False
    if args.record:
        cfg["output"]["record_images"] = True
    if args.preview_mp4:
        cfg["output"]["preview"]["enabled"] = True
    if args.benchmark_mode != "full" and (cfg["output"]["record_images"] or cfg["output"]["preview"]["enabled"]):
        raise ValueError("Diagnostic benchmark modes require PNG and MP4 recording disabled")
    validate_config(cfg)
    if args.record_mcap:
        backend = cfg["stereo"].get("backend", "legacy")
        if backend != "camera-sensor":
            raise ValueError(f"--record-mcap requires the camera-sensor backend; effective backend is {backend}")
        fps = cfg["simulation"]["fps"]
        if isinstance(fps, bool) or float(fps) != int(fps):
            raise ValueError(f"--record-mcap requires a whole-number simulation.fps; found {fps}")
    if args.validate_only:
        print(f"Configuration valid: {resolve_path(args.config)}")
        return 0
    if args.benchmark and not args._benchmark_child:
        return supervise_benchmark(cfg, list(sys.argv[1:] if argv is None else argv), tracy=args.profile_tracy)
    directory = find_oceansim_extension(cfg, args.oceansim_ext)
    from rov_sim.startup import enable_oceansim, launch_options

    headless = args.headless or args.mode == "headless"
    options = launch_options(cfg, headless, args.kit_arg, tracy=args.profile_tracy)
    app = None
    original_argv = sys.argv
    try:
        # SimulationApp forwards sys.argv to Kit. Keep application flags out of
        # Kit's parser; all Kit overrides are passed explicitly in extra_args.
        sys.argv = [original_argv[0]]
        from isaacsim import SimulationApp

        kwargs = {}
        if cfg["runtime"]["experience"]:
            kwargs["experience"] = str(resolve_path(cfg["runtime"]["experience"]))
        app = SimulationApp(options, **kwargs)
        sys.argv = original_argv
        extension = enable_oceansim(app, directory)
        if args.startup_only:
            print("[Phase 1] SimulationApp and OceanSim startup succeeded.")
            return 0
        # Every import of carb, omni, pxr and OceanSim is below app startup.
        from rov_sim.application import run

        if args.profile_python:
            import cProfile

            profiler = cProfile.Profile()
            try:
                profiler.runcall(run, app, cfg, args, extension, headless)
            finally:
                profiler.dump_stats(str(Path(args._benchmark_run_dir) / "python_profile.pstats"))
        else:
            run(app, cfg, args, extension, headless)
        return 0
    except Exception:
        # Fast Kit shutdown can terminate the interpreter before an exception
        # reaches __main__. Keep failures visible in redirected validation logs.
        import traceback
        traceback.print_exc()
        sys.stderr.flush()
        raise
    finally:
        sys.argv = original_argv
        if app is not None:
            app.close()
