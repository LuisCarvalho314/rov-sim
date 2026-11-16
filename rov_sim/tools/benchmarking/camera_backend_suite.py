"""Matched camera runs in the existing tank. Use Isaac Sim's python.bat.

No scene/profile generation: every case uses the exact supplied configuration
and change_detection experiment. Each case gets a fresh process and run folder.
Re-running with --resume skips only completed cases with identical arguments.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

from rov_sim.config import BACKENDS, ROOT


def cases(repeats=3, frames=60, profiles=True, parity=True):
    for backend in BACKENDS:
        yield f"validation/{backend}", backend, ["--record", "--photometric-diagnostics"], 60
    for mode in ("full", "render-only", "no-readback"):
        for repeat in range(repeats):
            # Rotate order to avoid always giving one backend the warmest GPU.
            for backend in BACKENDS[repeat % 3:] + BACKENDS[:repeat % 3]:
                yield f"{mode}/{backend}_{repeat + 1}", backend, ["--benchmark", "--benchmark-mode", mode], frames
    if parity:
        for repeat in range(repeats):
            for backend in BACKENDS[1:]:
                yield f"depth-readback/{backend}_{repeat + 1}", backend, ["--benchmark", "--readback-degraded-depth"], frames
    if profiles:
        for backend in BACKENDS:
            yield f"profile/{backend}", backend, ["--benchmark", "--profile-tracy", "--profile-warp-gpu"], frames


def run_case(root, name, backend, flags, frames, config, resume):
    root, config = Path(root).resolve(), Path(config).resolve()
    destination = root / name
    arguments = ["--headless", "--config", str(config), "--camera-backend", backend,
                 "--experiment", "change_detection", "--frames", str(frames),
                 "--output-dir", str(destination), *flags]
    manifest = destination / "case.json"
    runs = list(destination.glob("*/status.json"))
    if manifest.exists():
        old = json.loads(manifest.read_text())
        if resume and old["arguments"] == arguments and old["exit_code"] == 0 and len(runs) == 1:
            if json.loads(runs[0].read_text())["state"] == "complete":
                print(f"SKIP {name}", flush=True)
                return
        raise RuntimeError(f"Existing or incomplete evidence: {destination}; choose a new root")
    destination.mkdir(parents=True, exist_ok=False)
    print(f"RUN {name}", flush=True)
    started = time.monotonic()
    with (destination / "console.log").open("w", encoding="utf-8") as log:
        child = subprocess.run([sys.executable, "-u", "-m", "rov_sim", *arguments],
                               stdout=log, stderr=subprocess.STDOUT, cwd=ROOT)
    manifest.write_text(json.dumps({"arguments": arguments, "exit_code": child.returncode,
                                    "wall_s_including_startup": time.monotonic() - started}, indent=2))
    runs = list(destination.glob("*/status.json"))
    if child.returncode != 0 or len(runs) != 1 or json.loads(runs[0].read_text())["state"] != "complete":
        raise RuntimeError(f"Failed {name}; inspect {destination / 'console.log'}")
    # Treat extension/render errors as failures even when Kit returns zero.
    log_text = (destination / "console.log").read_text(encoding="utf-8", errors="replace")
    if "[Error]" in log_text or "Traceback (most recent call last)" in log_text:
        raise RuntimeError(f"Runtime errors in {destination / 'console.log'}")
    print(f"PASS {name} ({time.monotonic() - started:.1f}s)", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True)
    parser.add_argument("--config", default=str(ROOT / "configs/tank_photometric.yaml"))
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--frames", type=int, default=60)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--skip-profiles", action="store_true")
    parser.add_argument("--skip-parity", action="store_true")
    parser.add_argument("--only", nargs="+", help="Run only these exact case names (with --resume)")
    args = parser.parse_args()
    if args.repeats < 1 or args.frames < 1:
        parser.error("repeats and frames must be positive")
    root, config = Path(args.root).resolve(), Path(args.config).resolve()
    root.mkdir(parents=True, exist_ok=args.resume)
    digest = hashlib.sha256(config.read_bytes()).hexdigest()
    source_files = [ROOT / p for p in ("rov_sim/application.py", "rov_sim/cli.py", "rov_sim/sensors/stereo.py", "rov_sim/sensors/rtx_stereo.py")]
    provenance = {"configuration": str(config), "configuration_sha256": digest,
                  "sources_sha256": {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in source_files},
                  "isaac_path": os.environ.get("ISAAC_PATH")}
    provenance_path = root / "provenance.json"
    if provenance_path.exists() and json.loads(provenance_path.read_text()) != provenance:
        raise RuntimeError("Configuration or acquisition source changed; use a new evidence root")
    provenance_path.write_text(json.dumps(provenance, indent=2))
    for case in cases(args.repeats, args.frames, not args.skip_profiles, not args.skip_parity):
        if args.only and case[0] not in args.only:
            continue
        run_case(root, *case, config, args.resume)
    print(f"SUITE COMPLETE {root}", flush=True)


if __name__ == "__main__":
    main()
