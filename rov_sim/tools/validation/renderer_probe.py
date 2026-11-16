"""Minimal manual Isaac Sim renderer startup probe; no ROV or OceanSim imports."""
from __future__ import annotations

import argparse
import sys


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--renderer", choices=("RealTimePathTracing", "RaytracedLighting"), default="RealTimePathTracing")
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--no-stage", action="store_true", help="Skip default stage creation and viewport wait")
    parser.add_argument("--disable-viewport-updates", action="store_true")
    parser.add_argument("--aa", type=int, choices=(0, 3), default=0, help="0=disabled; 3=DLSS")
    parser.add_argument("--no-mode-flag", action="store_true")
    parser.add_argument("--force-rt2-flag", action="store_true", help="Enable RT2 even when selecting legacy mode")
    parser.add_argument("--isaac-50-rt2-flags", action="store_true", help="Use NVIDIA forum's Isaac Sim 5.0 RTX 2.0 startup arguments")
    parser.add_argument("--fast-shutdown", action="store_true")
    args = parser.parse_args(argv)
    extra = ["--/app/vulkan=false"]
    if not args.no_mode_flag:
        mode = "rt2" if args.renderer == "RealTimePathTracing" else "rt"
        extra.append(f"--/persistent/rtx/modes/{mode}/enabled=true")
    if args.force_rt2_flag and "--/persistent/rtx/modes/rt2/enabled=true" not in extra:
        extra.append("--/persistent/rtx/modes/rt2/enabled=true")
    if args.isaac_50_rt2_flags:
        extra.extend(("--/persistent/rtx/modes/rt/enabled=true",
                      "--/persistent/rtx/rendermode=RealTimePathTracing",
                      "--/rtx/rendermode=RealTimePathTracing"))
    config = {"headless": args.headless, "renderer": args.renderer,
              "anti_aliasing": args.aa, "create_new_stage": not args.no_stage,
              "disable_viewport_updates": args.disable_viewport_updates,
              "fast_shutdown": args.fast_shutdown, "extra_args": extra}
    print(f"PROBE_CONFIG {config}", flush=True)
    original_argv = sys.argv
    app = None
    try:
        sys.argv = [original_argv[0]]
        from isaacsim import SimulationApp
        app = SimulationApp(config)
        print("PROBE_INITIALIZED", flush=True)
        import carb.settings
        settings = carb.settings.get_settings()
        print(f"PROBE_READBACK renderer={settings.get('/rtx/rendermode')} "
              f"rt2={settings.get('/persistent/rtx/modes/rt2/enabled')} "
              f"aa={settings.get('/rtx/post/aa/op')} vulkan={settings.get('/app/vulkan')}", flush=True)
        app.update()
        print("PROBE_UPDATED", flush=True)
    finally:
        sys.argv = original_argv
        if app is not None:
            app.close()


if __name__ == "__main__":
    main()
