"""Standalone ROV simulator. Invoke with Isaac Sim 5.0's bundled Python."""
from __future__ import annotations

import argparse
import sys

from config import find_oceansim_extension, load_config, resolve_path, validate_config


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="configs/tank.yaml")
    parser.add_argument("--scene", choices=["tank"], default="tank")
    parser.add_argument("--mode", choices=["interactive", "headless"], default="interactive")
    parser.add_argument("--headless", action="store_true", help="Alias for --mode headless")
    parser.add_argument("--experiment", choices=["change_detection"])
    parser.add_argument("--frames", type=int, help="Frames per pass; 0 keeps interactive preview open")
    parser.add_argument("--record", action="store_true", help="Record paired underwater PNGs and ground truth")
    parser.add_argument("--preview-mp4", action="store_true", help="Encode MP4 previews from recorded PNGs (requires --record or output.record_images)")
    parser.add_argument("--output-dir", help="Output root; each invocation creates a unique run directory")
    parser.add_argument("--oceansim-ext", help="Existing extension directory containing config/extension.toml")
    parser.add_argument("--backend", choices=["d3d12", "vulkan"])
    parser.add_argument("--kit-arg", action="append", default=[], help="Extra Kit option, e.g. --kit-arg=--/renderer/activeGpu=0")
    parser.add_argument("--validate-only", action="store_true", help="Validate config without importing Isaac Sim")
    parser.add_argument("--startup-only", action="store_true", help="Start Kit, enable OceanSim, then close")
    args = parser.parse_args(argv)
    if args.frames is not None and args.frames < 0:
        parser.error("--frames must be nonnegative")
    if args.frames == 0 and (args.experiment or args.headless or args.mode == "headless"):
        parser.error("--frames 0 is only valid for interactive preview without an experiment")
    return args


def main(argv=None):
    args = parse_args(argv)
    cfg = load_config(args.config)
    if args.backend:
        cfg["runtime"]["backend"] = args.backend
    if args.output_dir:
        cfg["output"]["directory"] = args.output_dir
    if args.record:
        cfg["output"]["record_images"] = True
    if args.preview_mp4:
        cfg["output"]["preview"]["enabled"] = True
    validate_config(cfg)
    if args.validate_only:
        print(f"Configuration valid: {resolve_path(args.config)}")
        return 0
    directory = find_oceansim_extension(cfg, args.oceansim_ext)
    from startup import enable_oceansim, launch_options

    headless = args.headless or args.mode == "headless"
    options = launch_options(cfg, headless, args.kit_arg)
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
        from application import run

        run(app, cfg, args, extension, headless)
        return 0
    finally:
        sys.argv = original_argv
        if app is not None:
            app.close()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("Stopped by user.")
