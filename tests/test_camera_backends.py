"""CPU checks protecting selection and matched benchmark accounting."""
import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

from rov_sim.config import BACKENDS
from rov_sim.tools.benchmarking.camera_backend_suite import cases
from rov_sim.tools.benchmarking import camera_backend_suite as suite
from rov_sim.config import ROOT
from rov_sim.tools.benchmarking.compare_camera_backends import matched_configuration, summarize_reports
from rov_sim.config import load_config, validate_config
from rov_sim.cli import main, parse_args


class CameraBackendTests(unittest.TestCase):
    def test_suite_child_command_resume_and_failure_checks(self):
        for state, log, succeeds in (("complete", "ok", True),
                                     ("starting_kit", "ok", False),
                                     ("complete", "[Error] extension failed", False),
                                     ("complete", "Traceback (most recent call last)", False)):
            with self.subTest(state=state, log=log), tempfile.TemporaryDirectory() as folder:
                root = Path(folder)
                config = (ROOT / "configs/tank_photometric.yaml").resolve()
                destination = root / "validation/legacy"

                def child(command, **kwargs):
                    self.assertEqual(command[:4], [sys.executable, "-u", "-m", "rov_sim"])
                    self.assertEqual(kwargs["cwd"], ROOT)
                    self.assertEqual(command[command.index("--config") + 1], str(config))
                    self.assertEqual(command[command.index("--output-dir") + 1], str(destination))
                    self.assertIn("--photometric-diagnostics", command)
                    run = destination / "run"
                    run.mkdir()
                    (run / "status.json").write_text(json.dumps({"state": state}))
                    kwargs["stdout"].write(log)
                    return types.SimpleNamespace(returncode=0)

                args = (root, "validation/legacy", "legacy", ["--record", "--photometric-diagnostics"], 60, config)
                with patch.object(suite.subprocess, "run", side_effect=child) as spawned:
                    if succeeds:
                        suite.run_case(*args, False)
                        before = {p: p.read_bytes() for p in destination.rglob('*') if p.is_file()}
                        suite.run_case(*args, True)
                        self.assertEqual(spawned.call_count, 1)
                        for resume in (False, True):
                            changed = list(args)
                            changed[4] = 12
                            with self.assertRaisesRegex(RuntimeError, "Existing or incomplete evidence"):
                                suite.run_case(*changed, resume)
                        self.assertEqual(before, {p: p.read_bytes() for p in before})
                    else:
                        with self.assertRaises(RuntimeError):
                            suite.run_case(*args, False)

    def test_suite_provenance_uses_moved_sources_and_refuses_changed_or_old_roots(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder) / "new evidence"
            argv = ["suite", "--root", str(root), "--only", "no-cases"]
            with patch.object(sys, "argv", argv):
                suite.main()
            path = root / "provenance.json"
            original = path.read_bytes()
            provenance = json.loads(original)
            self.assertEqual(provenance["configuration"], str(ROOT / "configs/tank_photometric.yaml"))
            self.assertEqual(provenance["sources_sha256"], {
                str(ROOT / p): hashlib.sha256((ROOT / p).read_bytes()).hexdigest()
                for p in ("rov_sim/application.py", "rov_sim/cli.py", "rov_sim/sensors/stereo.py", "rov_sim/sensors/rtx_stereo.py")})
            with patch.object(sys, "argv", [*argv, "--resume"]):
                suite.main()
            self.assertEqual(path.read_bytes(), original)
            for sources in ({str(ROOT / "run.py"): "old hash"},
                            {**provenance["sources_sha256"], str(ROOT / "rov_sim/cli.py"): "changed"}):
                stale = {**provenance, "sources_sha256": sources}
                path.write_text(json.dumps(stale))
                before = path.read_bytes()
                with patch.object(sys, "argv", [*argv, "--resume"]), self.assertRaisesRegex(RuntimeError, "new evidence root"):
                    suite.main()
                self.assertEqual(path.read_bytes(), before)

    def test_legacy_default_and_explicit_selection_before_kit(self):
        self.assertIsNone(parse_args([]).camera_backend)
        self.assertEqual(load_config()["stereo"].get("backend", "legacy"), "legacy")
        for backend in BACKENDS:
            self.assertEqual(main(["--validate-only", "--camera-backend", backend]), 0)
        cfg = load_config()
        cfg["stereo"]["backend"] = "single-view-depth"
        with self.assertRaisesRegex(ValueError, "stereo.backend"):
            validate_config(cfg)

    def test_matched_configuration_keeps_renderer_optics_and_water(self):
        cfg = load_config("configs/tank_photometric.yaml")
        other = copy.deepcopy(cfg)
        other["stereo"]["backend"] = "tiled"
        other["output"]["directory"] = "another/evidence/root"
        self.assertEqual(matched_configuration(cfg), matched_configuration(other))
        for section, key, value in (("rtx", "antialiasing", 0),
                                    ("stereo", "baseline_m", .2),
                                    ("underwater", "atten_coeff", [0, 0, 0]),
                                    ("simulation", "warmup_frames", 1)):
            changed = copy.deepcopy(other)
            changed[section][key] = value
            self.assertNotEqual(matched_configuration(cfg), matched_configuration(changed))

    def test_suite_rotates_order_and_keeps_original_capture(self):
        all_cases = list(cases())
        self.assertEqual([c[1] for c in all_cases[:3]], list(BACKENDS))
        self.assertTrue(all(c[3] == 60 and c[2] == ["--record", "--photometric-diagnostics"] for c in all_cases[:3]))
        normal = [c for c in all_cases if c[0].startswith("full/")]
        self.assertEqual(len(normal), 9)
        self.assertEqual([c[1] for c in normal[3:6]], ["camera-sensor", "tiled", "legacy"])
        self.assertTrue(all("--profile-tracy" not in c[2] for c in normal))
        self.assertEqual(len([c for c in all_cases if c[0].startswith("profile/")]), 3)

    @staticmethod
    def report(elapsed=2., drain=0., mode="full"):
        return {"configuration": load_config("configs/tank_photometric.yaml"), "measurement_mode": mode,
                "summary": {"stereo_pairs": 20, "acquisition_wall_clock_s": elapsed,
                            "gpu_drain_ms": drain, "readiness_retries": 0,
                            "throughput_unit": "processed_stereo_pairs",
                            "stage_statistics": {"render_ms": {"cumulative_ms": 1000}, "gpu_readback_ms": None}}}

    def test_pooled_throughput_includes_gpu_drain_and_weights_duration(self):
        result = summarize_reports([self.report(1, 500, "no-readback"), self.report(2, 500, "no-readback")])
        self.assertEqual(result["pooled_per_s"], 10)
        self.assertEqual(result["mean_stage_ms"]["render_ms"], 50)
        self.assertIsNone(result["mean_stage_ms"]["gpu_readback_ms"])

    def test_refuses_instrumented_or_unmatched_results(self):
        for key, value in (("tracy_enabled", True), ("warp_gpu_timing", {"activities": {}})):
            report = self.report()
            report[key] = value
            with self.assertRaisesRegex(ValueError, "Instrumented"):
                summarize_reports([report])
        report = self.report()
        report["configuration"]["rtx"]["antialiasing"] = 0
        with self.assertRaisesRegex(ValueError, "Unmatched"):
            summarize_reports([self.report(), report])


if __name__ == "__main__":
    unittest.main()
