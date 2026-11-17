"""Audit original geometry and installed source hashes; bundled Python, no Kit app."""
from pathlib import Path
import argparse
import hashlib
import json
import os
import sys


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("--tiled-root", type=Path)
    args = parser.parse_args()
    runtime = Path(os.environ["ISAAC_PATH"])
    usd_libraries = list((runtime / "extscache").glob("omni.usd.libs-*"))
    if len(usd_libraries) != 1:
        raise RuntimeError("Expected one installed USD extension")
    sys.path.insert(0, str(usd_libraries[0]))
    dll_directory = os.add_dll_directory(str(usd_libraries[0] / "bin"))
    from pxr import Usd, UsdGeom
    import numpy as np
    from rov_sim.config import BACKENDS

    def protected(stage):
        result = {}
        for prim in stage.Traverse():
            path = str(prim.GetPath())
            if not path.startswith(("/World/Tank", "/World/FixedEquipment", "/World/Changes",
                                    "/World/BlueROV/StereoRig", "/World/BlueROV/InspectionLight",
                                    "/World/Lighting", "/World/Looks", "/World/Water")):
                continue
            attrs = prim.GetAttributes()
            if prim.GetTypeName() == "Camera":
                # Wrappers normalize identity xform ops and may round translations
                # to float32. Compare evaluated transforms separately. Tiled
                # rendering attaches the primary camera's shared exposure state.
                attrs = [a for a in attrs if not a.GetName().startswith(
                    ("omni:sensor:", "_replicator:", "xformOp", "exposure:", "omni:rtx:"))]
            result[path] = {"type": prim.GetTypeName(),
                            "attributes": {a.GetName(): repr(a.Get()) for a in attrs},
                            "relationships": {r.GetName(): [str(x) for x in r.GetTargets()] for r in prim.GetRelationships()}}
        return result

    runs = {b: next(((args.tiled_root if b == "tiled" and args.tiled_root else args.root) / "validation" / b).glob("*/tank_before_rtx.usda")).parent for b in BACKENDS}
    comparisons = {}
    camera_state = {}
    for session in ("before", "after"):
        baseline = protected(Usd.Stage.Open(str(runs["legacy"] / f"tank_{session}_rtx.usda"), Usd.Stage.LoadNone))
        for backend in BACKENDS:
            stage = Usd.Stage.Open(str(runs[backend] / f"tank_{session}_rtx.usda"), Usd.Stage.LoadNone)
            legacy_stage = Usd.Stage.Open(str(runs["legacy"] / f"tank_{session}_rtx.usda"), Usd.Stage.LoadNone)
            actual = protected(stage)
            differences = {p: {"legacy": baseline.get(p), "actual": actual.get(p)}
                           for p in baseline.keys() | actual.keys() if baseline.get(p) != actual.get(p)}
            if differences:
                (args.root / "scene_differences.json").write_text(json.dumps(differences, indent=2))
                raise AssertionError(f"Protected scene differs for {backend}/{session}")
            comparisons[f"{backend}/{session}"] = {"protected_prims": len(actual), "exact_match": True}
            camera_state[f"{backend}/{session}"] = {}
            for side in ("Left", "Right"):
                path = f"/World/BlueROV/StereoRig/{side}"
                cam, original = stage.GetPrimAtPath(path), legacy_stage.GetPrimAtPath(path)
                matrix = np.array(UsdGeom.Xformable(cam).ComputeLocalToWorldTransform(Usd.TimeCode.Default()))
                expected = np.array(UsdGeom.Xformable(original).ComputeLocalToWorldTransform(Usd.TimeCode.Default()))
                if not np.allclose(matrix, expected, rtol=0, atol=1e-6):
                    raise AssertionError(f"Camera pose changed: {backend}/{session}/{side}")
                camera_state[f"{backend}/{session}"][side] = {
                    "transform_max_difference": float(np.max(np.abs(matrix - expected))),
                    "authored_exposure": {a.GetName(): repr(a.Get()) for a in cam.GetAttributes() if a.GetName().startswith("exposure:")}}
    from rov_sim.config import ROOT, find_oceansim_extension, load_config
    ocean = find_oceansim_extension(load_config())
    saved = json.loads((ROOT / 'docs/oceansim_source_hashes.json').read_text())
    # Git may check text out with LF or CRLF on Windows. The fork manifest
    # hashes LF-normalized source, independently of core.autocrlf.
    changed = [row["relative_path"] for row in saved
               if hashlib.sha256((ocean / row["relative_path"]).read_bytes().replace(b'\r\n', b'\n')).hexdigest() != row["sha256"]]
    if changed:
        raise AssertionError(f"OceanSim source changed: {changed}")
    api = runtime.parents[2] / "source/extensions/isaacsim.sensors.experimental.rtx/python/impl"
    sources = {str(api / name): digest(api / name) for name in (
        "rtx_camera.py", "camera_sensor.py", "tiled_camera_sensor.py", "_sensor_base.py", "_camera_common.py")}
    result = {"status": "PASS", "scene_comparisons": comparisons,
              "camera_state": camera_state,
              "oceansim_python_files_unchanged": len(saved), "installed_rtx_source_sha256": sources,
              "scope": "Exact scene attributes/relationships including water, lights and optical geometry. Camera transforms compared numerically at 1e-6; identity-op normalization, sensor metadata and camera exposure schemas are excluded from exact comparison and exposure values are reported separately. Tiled product has shared primary-camera exposure. Photometric agreement is checked from captured buffers. USD references remain external."}
    result["tiled_evidence_root"] = str(args.tiled_root or args.root)
    filename = "scene_and_source_audit_validated.json" if args.tiled_root else "scene_and_source_audit.json"
    (args.root / filename).write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
