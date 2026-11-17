"""Generate comparable RTX 2.0 and Legacy benchmark configurations."""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path

from rov_sim.config import load_config, validate_config


PROFILES = {"A": ("RealTimePathTracing", False),
            "B": ("RaytracedLighting", False),
            "C": ("RaytracedLighting", True)}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default="configs/tank.yaml")
    parser.add_argument("--directory", type=Path, default=Path("outputs"))
    args = parser.parse_args(argv)
    base = load_config(args.base)
    args.directory.mkdir(parents=True, exist_ok=True)
    for name, (renderer, caustics) in PROFILES.items():
        cfg = copy.deepcopy(base)
        cfg["runtime"]["renderer"] = renderer
        cfg["rtx"]["caustics"] = caustics
        cfg["simulation"]["rt_subframes"] = 1
        cfg["output"]["record_images"] = False
        cfg["output"]["preview"]["enabled"] = False
        validate_config(cfg)
        path = args.directory / f"{name}.yaml"
        path.write_text(json.dumps(cfg, indent=2) + "\n", encoding="utf-8")
        print(path)


if __name__ == "__main__":
    main()
