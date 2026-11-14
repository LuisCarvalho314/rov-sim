"""CPU checks protecting selection and matched benchmark accounting."""
import copy
import unittest

from camera_backend_suite import BACKENDS, cases
from compare_camera_backends import matched_configuration, summarize_reports
from config import load_config, validate_config
from run import main, parse_args


class CameraBackendTests(unittest.TestCase):
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
