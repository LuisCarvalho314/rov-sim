"""Generate controlled profiles from the preserved original tank configuration."""
import copy
import json
from pathlib import Path

from rov_sim.config import ROOT


def generate(root="outputs/photometric_6_1/profiles"):
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    base = json.loads((ROOT / "configs/tank_photometric_baseline.yaml").read_text())
    variants = {"baseline": copy.deepcopy(base)}
    for name in ("light4", "exposure4", "shadow_off", "water_depth10", "dlaa"):
        variants[name] = copy.deepcopy(base)
    variants["light4"]["lighting"]["intensity"] *= 4
    variants["exposure4"]["rtx"]["settings"]["/rtx/post/tonemap/filmIso"] = 400.0
    variants["shadow_off"]["water"]["cast_shadows"] = False
    variants["water_depth10"]["water"]["material"] = {"depth": 10.0}
    variants["dlaa"]["rtx"]["antialiasing"] = 4
    for name in ("lamps", "lamps_dlaa"):
        variants[name] = copy.deepcopy(base)
        variants[name]["lighting"]["inspection_lights"] = [
            {"position_m": [.48,y,.15], "rotation_xyz_deg": [0,-90,0],
             "size_m": [.12,.08], "intensity":60000.0} for y in (-.27,.27)]
    variants["lamps_dlaa"]["rtx"]["antialiasing"] = 4
    for name,iso in (("lamps_dlaa_iso800",800.0),("lamps_dlaa_iso1600",1600.0)):
        variants[name] = copy.deepcopy(variants["lamps_dlaa"])
        variants[name]["rtx"]["settings"]["/rtx/post/tonemap/filmIso"] = iso
    variants["shadow_off_dlaa"] = copy.deepcopy(variants["shadow_off"])
    variants["shadow_off_dlaa"]["rtx"]["antialiasing"] = 4
    variants["recommended"] = copy.deepcopy(variants["lamps_dlaa_iso1600"])
    variants["recommended"]["simulation"]["warmup_frames"] = 30
    variants["recommended"]["rtx"]["settings"].update({
        "/rtx/post/tonemap/op":6, "/rtx/post/tonemap/exposureTime":.02,
        "/rtx/post/tonemap/fNumber":5.0, "/rtx/post/histogram/enabled":False})
    variants["recommended_repeat"] = copy.deepcopy(variants["recommended"])
    for name, cfg in variants.items():
        (root / f"{name}.yaml").write_text(json.dumps(cfg, indent=2) + "\n")
    return variants


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default="outputs/photometric_6_1/profiles")
    generate(parser.parse_args().root)
