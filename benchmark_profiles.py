"""Generate comparable A-D benchmark configurations from a base config."""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path

from config import load_config


PROFILES = {"A": (True, 4, False), "B": (True, 1, False),
            "C": (False, 1, False), "D": (True, 1, True)}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default="configs/tank.yaml")
    parser.add_argument("--directory", type=Path, default=Path("outputs"))
    args = parser.parse_args(argv)
    base = load_config(args.base)
    args.directory.mkdir(parents=True, exist_ok=True)
    for name, (caustics, subframes, recording) in PROFILES.items():
        cfg = copy.deepcopy(base)
        cfg["rtx"]["caustics"] = caustics
        cfg["simulation"]["rt_subframes"] = subframes
        cfg["output"]["record_images"] = recording
        cfg["output"]["preview"]["enabled"] = False
        path = args.directory / f"{name}.yaml"
        path.write_text(json.dumps(cfg, indent=2) + "\n", encoding="utf-8")
        print(path)


if __name__ == "__main__":
    main()
