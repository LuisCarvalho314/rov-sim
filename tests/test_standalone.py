"""CPU checks for startup safety, deterministic experiments and paired output."""
from __future__ import annotations

import copy
import io
import importlib.util
import json
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import types
import unittest
import warnings
import zlib
from pathlib import Path
from unittest.mock import patch

from rov_sim.config import ROOT, find_oceansim_extension, load_config, resolve_path, validate_config
from rov_sim.experiments.change_detection import object_position, trajectory_pose
from rov_sim.recording import PoseRecorder, create_run_directory, write_png
from rov_sim.preview import ffmpeg_command, generate_previews
import rov_sim.cli as run
import rov_sim.startup as startup
class ConfigurationTests(unittest.TestCase):
    def setUp(self):
        self.cfg = load_config()

    def test_paths_are_repository_relative_even_from_another_directory(self):
        with tempfile.TemporaryDirectory() as folder:
            original = Path.cwd()
            try:
                os.chdir(folder)
                self.assertEqual(resolve_path("outputs"), ROOT / "outputs")
                self.assertEqual(load_config(), self.cfg)
                with patch.dict(os.environ, {"OCEANSIM_EXT_PATH": ""}):
                    self.assertEqual(find_oceansim_extension(self.cfg), ROOT / "third_party/OceanSim")
            finally:
                os.chdir(original)

    def test_invalid_calibration_and_geometry_fail_before_startup(self):
        changes = (("stereo", "baseline_m", 0), ("stereo", "resolution", [752, 480.5]),
                   ("water", "height_m", 4), ("water", "size_m", [100, 100]),
                   ("robot", "position_m", [99, 0, 1]), ("simulation", "fps", float("nan")),
                   ("underwater", "atten_coeff", [-1, 0, 0]))
        for section, key, value in changes:
            with self.subTest(section=section, key=key):
                cfg = copy.deepcopy(self.cfg)
                cfg[section][key] = value
                with self.assertRaises(ValueError):
                    validate_config(cfg)

    def test_unknown_and_unsupported_caustics_backend_combination(self):
        self.cfg["rtx"]["caustics"] = True
        self.cfg["runtime"]["renderer"] = "PathTracing"
        with self.assertRaisesRegex(ValueError, "Photon caustics"):
            validate_config(self.cfg)
        self.cfg["runtime"]["renderer"] = "RealTimePathTracing"
        with self.assertRaisesRegex(ValueError, "Photon caustics"):
            validate_config(self.cfg)

    def test_renderer_profiles_and_legacy_geometry_match(self):
        modern = load_config()
        legacy = load_config("configs/tank_legacy.yaml")
        self.assertEqual(modern["runtime"]["renderer"], "RealTimePathTracing")
        self.assertFalse(modern["rtx"]["caustics"])
        self.assertEqual(legacy["runtime"]["renderer"], "RaytracedLighting")
        self.assertTrue(legacy["rtx"]["caustics"])
        self.assertEqual(modern["simulation"]["rt_subframes"], 1)
        for section in ("stereo", "tank", "water", "underwater", "robot", "experiment"):
            self.assertEqual(modern[section], legacy[section])

    def test_repeated_trajectory_frames_are_rejected(self):
        self.cfg["experiment"]["trajectory"][1]["frame"] = 0
        with self.assertRaisesRegex(ValueError, "strictly increasing"):
            validate_config(self.cfg)

    def test_preview_defaults_off_and_requires_recording(self):
        self.assertFalse(self.cfg["output"]["preview"]["enabled"])
        self.cfg["output"]["preview"]["enabled"] = True
        with self.assertRaisesRegex(ValueError, "requires PNG recording"):
            validate_config(self.cfg)
        self.cfg["output"]["record_images"] = True
        validate_config(self.cfg)
        with self.assertRaisesRegex(ValueError, "requires PNG recording"):
            run.main(["--validate-only", "--preview-mp4"])
        self.assertEqual(run.main(["--validate-only", "--record", "--preview-mp4"]), 0)

    def test_extension_discovery_uses_existing_directory(self):
        with tempfile.TemporaryDirectory() as folder:
            ext = Path(folder) / "extsUser/OceanSim"
            (ext / "config").mkdir(parents=True)
            (ext / "config/extension.toml").write_text('[package]\nversion="1.0.0"\n')
            with patch.dict(os.environ, {"ISAAC_PATH": folder, "OCEANSIM_EXT_PATH": str(ext)}):
                self.assertEqual(find_oceansim_extension(self.cfg), ext)
            self.assertEqual(find_oceansim_extension(self.cfg, str(ext)), ext)

    def test_pinned_extension_precedes_installation_fallback(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            pinned = root / 'third_party/OceanSim'
            installed = root / 'extsUser/OceanSim'
            for ext in (pinned, installed):
                (ext / 'config').mkdir(parents=True)
                (ext / 'config/extension.toml').write_text('[package]\nversion="1.0.0"\n')
            with patch('rov_sim.config.ROOT', root), patch.dict(os.environ, {'ISAAC_PATH': folder, 'OCEANSIM_EXT_PATH': ''}):
                self.assertEqual(find_oceansim_extension(self.cfg), pinned)
                self.assertEqual(find_oceansim_extension(self.cfg, str(installed)), installed)
                (pinned / 'config/extension.toml').unlink()
                self.assertEqual(find_oceansim_extension(self.cfg), installed)


class StartupTests(unittest.TestCase):
    def test_fresh_process_imports_and_cpu_cli_do_not_load_runtime(self):
        code = '''
import sys
import rov_sim
from rov_sim import cli, config
from rov_sim.experiments.change_detection import trajectory_pose
try:
    cli.main(["--help"])
except SystemExit as error:
    assert error.code == 0
assert cli.main(["--validate-only"]) == 0
assert cli.main(["--validate-only", "--record-mcap", "--headless", "--camera-backend", "camera-sensor"]) == 0
assert cli.main(["--validate-only", "--record-mcap", "--experiment", "change_detection",
                 "--camera-backend", "camera-sensor", "--mcap-storage", "zstd"]) == 0
for name in sys.modules:
    assert not name.startswith(("rov_sim.application", "isaacsim", "omni", "pxr", "carb", "oceansim",
                                "rov_sim.rosbag", "rosbag2_py", "rclpy")), name
'''
        result = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_help_and_validation_work_without_kit(self):
        for option in ("--help", "--validate-only"):
            result = subprocess.run([sys.executable, "-m", "rov_sim", option], cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("omni.usd", sys.modules)
        self.assertNotIn("pxr", sys.modules)

    def test_windows_launch_overrides_vulkan_before_graphics_startup(self):
        cfg = load_config()
        with patch.object(startup.os, "name", "nt"):
            options = startup.launch_options(cfg, True)
        self.assertIn("--/app/vulkan=false", options["extra_args"])
        self.assertTrue(options["headless"])
        self.assertTrue(options["fast_shutdown"])
        self.assertEqual(options["renderer"], "RealTimePathTracing")
        self.assertEqual(options["anti_aliasing"], 0)
        self.assertIn("--/persistent/rtx/modes/rt2/enabled=true", options["extra_args"])
        self.assertIn("--/persistent/rtx/modes/rt/enabled=true", options["extra_args"])
        self.assertIn("--/persistent/rtx/rendermode=RealTimePathTracing", options["extra_args"])
        self.assertIn("--/rtx/rendermode=RealTimePathTracing", options["extra_args"])
        with patch.object(startup.os, "name", "nt"):
            legacy = startup.launch_options(load_config("configs/tank_legacy.yaml"), True)
        self.assertIn("--/persistent/rtx/modes/rt/enabled=true", legacy["extra_args"])
        self.assertFalse(legacy["fast_shutdown"])
        with patch.object(startup.os, "name", "nt"):
            profiled = startup.launch_options(cfg, True, tracy=True)
        self.assertEqual(profiled["profiler_backend"], ["tracy"])
        self.assertIn("omni.kit.profiler.tracy", profiled["extra_args"])
        with self.assertRaisesRegex(ValueError, "may not override"):
            startup.launch_options(cfg, True, ("--/rtx/rendermode=RaytracedLighting",))

    def test_benchmark_supervisor_records_native_startup_failure(self):
        cfg = load_config()
        with tempfile.TemporaryDirectory() as folder:
            cfg["output"]["directory"] = folder
            child = types.SimpleNamespace(stdout=["native renderer crash\n"], wait=lambda: 3221225477)
            with patch.object(run.subprocess, "Popen", return_value=child) as spawned:
                self.assertEqual(run.supervise_benchmark(cfg, ["--benchmark", "--frames", "300"]), 1)
            directory = next(Path(folder).iterdir())
            status = json.loads((directory / "status.json").read_text(encoding="utf-8"))
            self.assertEqual(status["state"], "failed")
            self.assertEqual(status["process_exit_code"], 3221225477)
            self.assertEqual((directory / "kit_console.log").read_text(encoding="utf-8"), "native renderer crash\n")
            self.assertEqual(json.loads((directory / "config.json").read_text(encoding="utf-8")), cfg)
            self.assertIn("--_benchmark-child", spawned.call_args.args[0])
            self.assertIn(str(directory), spawned.call_args.args[0])
            self.assertEqual(spawned.call_args.args[0], [sys.executable, "-m", "rov_sim",
                             "--benchmark", "--frames", "300", "--_benchmark-child",
                             "--_benchmark-run-dir", str(directory)])
            self.assertEqual(spawned.call_args.kwargs["cwd"], ROOT)

    def test_benchmark_supervisor_rejects_launch_error_and_zero_exit_without_report(self):
        for launch_error in (True, False):
            with self.subTest(launch_error=launch_error), tempfile.TemporaryDirectory() as folder:
                cfg = load_config()
                cfg["output"]["directory"] = folder
                child = types.SimpleNamespace(stdout=["startup incomplete\n"], wait=lambda: 0)
                with patch.object(run.subprocess, "Popen", side_effect=OSError("cannot launch") if launch_error else None,
                                  return_value=child):
                    self.assertEqual(run.supervise_benchmark(cfg, ["--benchmark"]), 1)
                directory = next(Path(folder).iterdir())
                status = json.loads((directory / "status.json").read_text())
                self.assertEqual(status["state"], "failed")
                self.assertEqual(status["process_exit_code"], None if launch_error else 0)
                self.assertTrue((directory / "config.json").is_file())
                if launch_error:
                    self.assertIn("cannot launch", status["error"])
                else:
                    self.assertEqual((directory / "kit_console.log").read_text(), "startup incomplete\n")

    def test_app_closes_if_extension_startup_fails_and_restores_argv(self):
        events = []
        module = types.ModuleType("isaacsim")

        class FakeApp:
            def __init__(self, options, **kwargs):
                self.options = options
                events.append("start")
                self.test_args = sys.argv[:]

            def close(self):
                events.append("close")

        module.SimulationApp = FakeApp
        original = sys.argv
        with patch.dict(sys.modules, {"isaacsim": module}), \
             patch.object(run, "find_oceansim_extension", return_value=ROOT), \
             patch.object(startup, "launch_options", return_value={}), \
             patch.object(startup, "enable_oceansim", side_effect=RuntimeError("injected failure")):
            with self.assertRaisesRegex(RuntimeError, "injected failure"):
                run.main(["--startup-only"])
        self.assertEqual(events, ["start", "close"])
        self.assertIs(sys.argv, original)

    def test_record_mcap_flag_rules(self):
        base = ["--record-mcap", "--headless", "--camera-backend", "camera-sensor"]
        rejected_by_parser = (
            ["--record-mcap", "--camera-backend", "camera-sensor"],  # interactive default of 0 frames
            [*base, "--frames", "0"],
            ["--record-mcap", "--experiment", "change_detection", "--frames", "0"],
            [*base, "--startup-only"],
            [*base, "--benchmark", "--benchmark-mode", "render-only"],
            [*base, "--benchmark", "--benchmark-mode", "no-readback"],
            [*base, "--photometric-diagnostics"],
            ["--headless", "--mcap-storage", "zstd"],
            [*base, "--mcap-storage", "lz4"],
        )
        for args in rejected_by_parser:
            with self.subTest(args=args), patch("sys.stderr", new=io.StringIO()), self.assertRaises(SystemExit):
                run.parse_args(args)
        for backend in ("legacy", "tiled"):
            with self.subTest(backend=backend), self.assertRaisesRegex(ValueError, f"effective backend is {backend}"):
                run.main(["--record-mcap", "--headless", "--camera-backend", backend, "--validate-only"])
        # The default configuration's backend is not camera-sensor; the rule uses the effective backend.
        with self.assertRaisesRegex(ValueError, "requires the camera-sensor backend"):
            run.main(["--record-mcap", "--headless", "--validate-only"])
        allowed = (
            [*base, "--frames", "30"],
            ["--record-mcap", "--experiment", "change_detection", "--camera-backend", "camera-sensor"],
            [*base, "--benchmark", "--frames", "40"],
            [*base, "--experiment", "change_detection", "--stereo-diagnostics"],
            [*base, "--record", "--preview-mp4"],
            [*base, "--mcap-storage", "zstd"],
        )
        with patch("sys.stdout", new=io.StringIO()):
            for args in allowed:
                with self.subTest(args=args):
                    self.assertEqual(run.main([*args, "--validate-only"]), 0)
        self.assertEqual(run.parse_args(base).mcap_storage, "none")
        self.assertIsNone(run.parse_args(["--headless"]).mcap_storage)
        self.assertFalse(run.parse_args(["--headless"]).record_mcap)

    def test_record_mcap_rejects_fractional_fps(self):
        with tempfile.TemporaryDirectory(prefix="rov fps ") as folder:
            cfg = load_config()
            cfg["simulation"]["fps"] = 29.97
            config = Path(folder) / "fractional.yaml"
            config.write_text(json.dumps(cfg))
            with patch("sys.stdout", new=io.StringIO()):
                self.assertEqual(run.main(["--config", str(config), "--headless", "--validate-only"]), 0)
            with self.assertRaisesRegex(ValueError, "whole-number simulation.fps"):
                run.main(["--config", str(config), "--record-mcap", "--headless", "--camera-backend",
                          "camera-sensor", "--validate-only"])

    def test_headless_and_experiment_cannot_run_unbounded(self):
        for args in (["--headless", "--frames", "0"], ["--experiment", "change_detection", "--frames", "0"]):
            with patch("sys.stderr", new=io.StringIO()), self.assertRaises(SystemExit):
                run.parse_args(args)


@unittest.skipUnless(os.name == "nt" and shutil.which("powershell"), "Windows PowerShell launcher checks")
class PowerShellTests(unittest.TestCase):
    @staticmethod
    def quote(value):
        return "'" + str(value).replace("'", "''") + "'"

    def invoke(self, code, caller):
        result = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", code],
                                cwd=caller, capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result.stdout

    def test_parser_and_both_runtime_layouts_do_not_change_location(self):
        with tempfile.TemporaryDirectory(prefix="rov launcher ") as folder:
            caller = Path(folder)
            packaged, source = caller / "packaged runtime", caller / "source runtime"
            for runtime in (packaged / "python.bat", source / "_build/windows-x86_64/release/python.bat"):
                runtime.parent.mkdir(parents=True)
                runtime.write_text("@exit /b 0\n")
            self.invoke(f'''
$ErrorActionPreference = 'Stop'
$before = (Get-Location).Path
. {self.quote(ROOT / 'scripts/runtime.ps1')}
if ((Get-Location).Path -ne $before) {{ throw 'runtime helper changed location' }}
foreach ($script in Get-ChildItem {self.quote(ROOT / 'scripts')} -Filter *.ps1) {{
    $tokens = $null; $errors = $null
    [void][Management.Automation.Language.Parser]::ParseFile($script.FullName, [ref]$tokens, [ref]$errors)
    if ($errors.Count) {{ throw ($errors | Out-String) }}
}}
if ((Resolve-IsaacPython {self.quote(packaged)}) -ne {self.quote(packaged / 'python.bat')}) {{ throw 'packaged layout' }}
if ((Resolve-IsaacPython {self.quote(source)}) -ne {self.quote(source / '_build/windows-x86_64/release/python.bat')}) {{ throw 'source layout' }}
''', caller)

    def test_absolute_launcher_forwards_spaced_arguments_and_restores_location(self):
        with tempfile.TemporaryDirectory(prefix="rov launcher ") as folder:
            caller = Path(folder)
            runtime = caller / "runtime with spaces"
            runtime.mkdir()
            (runtime / "python.bat").write_text(f'@"{sys.executable}" %*\n@exit /b %errorlevel%\n')
            config = caller / "config with spaces.yaml"
            config.write_text(json.dumps(load_config()))
            for location in (ROOT, caller):
                self.invoke(f'''
$ErrorActionPreference = 'Stop'
$before = (Get-Location).Path
& {self.quote(ROOT / 'scripts/launch.ps1')} -IsaacSimPath {self.quote(runtime)} -RunArguments @('--validate-only','--config',{self.quote(config)},'--output-dir',{self.quote(caller / 'output with spaces')})
if ($LASTEXITCODE -ne 0) {{ throw 'validation failed' }}
if ((Get-Location).Path -ne $before) {{ throw 'caller directory lost' }}
& {self.quote(ROOT / 'scripts/launch.ps1')} -IsaacSimPath {self.quote(runtime)} -RunArguments @('--help')
if ($LASTEXITCODE -ne 0) {{ throw 'help failed' }}
& {self.quote(ROOT / 'scripts/launch.ps1')} -IsaacSimPath {self.quote(runtime)} -RunArguments @('--validate-only','--config',{self.quote(caller / 'missing config.yaml')})
if ($LASTEXITCODE -eq 0) {{ throw 'missing config accepted' }}
if ((Get-Location).Path -ne $before) {{ throw 'failure lost caller directory' }}
''', location)
            self.assertFalse((caller / 'output with spaces').exists())

    def test_capture_scripts_use_root_modules_and_retain_failure_checks(self):
        with tempfile.TemporaryDirectory(prefix="rov capture launcher ") as folder:
            caller = Path(folder)
            runtime = caller / "runtime with spaces"
            runtime.mkdir()
            helper = caller / "fake runtime.py"
            helper.write_text('''
import json, os, pathlib, sys
args = sys.argv[1:]
with open(os.environ['ROV_FIXTURE_LOG'], 'a') as out:
    out.write(json.dumps({'cwd': str(pathlib.Path.cwd()), 'args': args}) + '\\n')
assert args[:3] == ['-u', '-m', 'rov_sim'], args
if '--startup-only' in args:
    print('[Phase 1] SimulationApp and OceanSim startup succeeded.')
else:
    config = pathlib.Path(args[args.index('--config') + 1])
    assert config.is_absolute() and config.is_file(), config
    destination = pathlib.Path(args[args.index('--output-dir') + 1])
    assert destination.is_absolute(), destination
    run = destination / 'fixture_run'
    run.mkdir(parents=True)
    state = 'failed' if os.environ.get('ROV_FIXTURE_FAILURE') == 'status' else 'complete'
    (run / 'status.json').write_text(json.dumps({'state': state, 'process_exit_code': 0}))
    if '--benchmark' in args:
        (run / 'benchmark.json').write_text('{}')
failure = os.environ.get('ROV_FIXTURE_FAILURE')
if failure == 'log': print('[Error] injected runtime error')
sys.exit(7 if failure == 'exit' else 0)
''')
            (runtime / 'python.bat').write_text(f'@"{sys.executable}" "{helper}" %*\n@exit /b %errorlevel%\n')
            for name, extra, expected in (
                    ('run_photometric.ps1', "-Profiles @('baseline')", 1),
                    ('validate_photometric.ps1', '-SkipBenchmarks', 4),
                    ('validate_6_1.ps1', '-BenchmarkFrames 1 -Repeats 2 -SkipProfiling', 5)):
                for failure in ('', 'exit', 'log', 'status'):
                    with self.subTest(script=name, failure=failure):
                        evidence = caller / (name + (failure or 'success'))
                        if name == 'run_photometric.ps1':
                            (evidence / 'profiles').mkdir(parents=True)
                            (evidence / 'profiles/baseline.yaml').write_text(json.dumps(load_config()))
                        args = extra + (f' -EvidenceRoot {self.quote(evidence)}' if name != 'validate_6_1.ps1' else '')
                        log = caller / 'calls.jsonl'
                        log.write_text('')
                        # Redirect the timestamped output into the private fixture.
                        redirect = f'''function Join-Path($Path, $ChildPath) {{
    if ($ChildPath -like 'outputs/validation_6_1_*') {{ return {self.quote(evidence)} }}
    Microsoft.PowerShell.Management\\Join-Path $Path $ChildPath
}}''' if name == 'validate_6_1.ps1' else ''
                        self.invoke(f'''
$ErrorActionPreference = 'Stop'
$env:ROV_FIXTURE_LOG = {self.quote(log)}
$env:ROV_FIXTURE_FAILURE = {self.quote(failure)}
function python {{
    if ($args[0] -ne '-m' -or $args[1] -ne 'rov_sim.tools.validation.validate_recording') {{ throw 'validator module' }}
    if ((Get-Location).Path -ne {self.quote(ROOT)}) {{ throw 'validator cwd' }}
    $global:LASTEXITCODE = 0
}}
{redirect}
$before = (Get-Location).Path
$caught = $false
try {{ & {self.quote(ROOT / 'scripts' / name)} -SimRoot {self.quote(runtime)} {args} }}
catch {{ $caught = $true; Write-Output $_ }}
if ($caught -ne ${str(bool(failure)).lower()}) {{ throw 'unexpected failure result' }}
if ((Get-Location).Path -ne $before) {{ throw 'caller directory lost' }}
''', caller)
                        calls = [json.loads(line) for line in log.read_text().splitlines()]
                        count = expected if not failure else (2 if failure == 'status' and name == 'validate_6_1.ps1' else 1)
                        self.assertEqual(len(calls), count)
                        for call in calls:
                            self.assertEqual(Path(call['cwd']), ROOT)
                            self.assertEqual(call['args'][:3], ['-u', '-m', 'rov_sim'])


class RendererValidationTests(unittest.TestCase):
    def test_photometric_profiles_preserve_experiment_and_validate_controls(self):
        original = load_config("configs/tank_photometric_baseline.yaml")
        candidate = copy.deepcopy(original)
        candidate["rtx"]["antialiasing"] = 4
        candidate["rtx"]["settings"]["/rtx/post/tonemap/filmIso"] = 800.0
        validate_config(candidate)
        for section in ("tank", "robot", "stereo", "changes", "experiment", "underwater"):
            self.assertEqual(candidate[section], original[section])
        for bad in (-1, 1, 2, 5, True):
            candidate["rtx"]["antialiasing"] = bad
            with self.assertRaisesRegex(ValueError, "antialiasing"):
                validate_config(candidate)

    def test_readback_reports_mode_and_does_not_switch_renderer(self):
        cfg = load_config()
        values = {"/app/vulkan": False, "/rtx/rendermode": "RealTimePathTracing",
                  "/persistent/rtx/modes/rt2/enabled": True, "/rtx/post/aa/op": 0}

        class Settings:
            def get(self, key):
                return values.get(key)

            def set(self, key, value):
                values[key] = value

        carb = types.ModuleType("carb")
        carb.settings = types.SimpleNamespace(get_settings=lambda: Settings())
        pxr = types.ModuleType("pxr")
        pxr.UsdShade = object()
        with patch.dict(sys.modules, {"carb": carb, "carb.settings": carb.settings, "pxr": pxr}):
            spec = importlib.util.spec_from_file_location("_underwater_validation_check", ROOT / "rov_sim/environments/underwater.py")
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            report = module.configure_rtx(cfg)
            self.assertEqual(report["renderer_readback"], "RealTimePathTracing")
            self.assertTrue(report["rt2_enabled_readback"])
            self.assertFalse(report["processed_stereo_frame"])
            self.assertEqual(report["dlss_aa_readback"], 0)
            self.assertFalse(report["graphics_backend_runtime_confirmed"])
            values["/persistent/rtx/modes/rt2/enabled"] = False
            with self.assertRaisesRegex(RuntimeError, "not enabled"):
                module.configure_rtx(cfg)


class ExperimentTests(unittest.TestCase):
    def test_only_changed_object_position_differs(self):
        cfg = load_config()
        original = copy.deepcopy(cfg)
        self.assertEqual(object_position(cfg, "before"), [1.15, -0.65, 0.3])
        self.assertEqual(object_position(cfg, "after"), [1.65, -0.65, 0.3])
        self.assertEqual(cfg, original)

    def test_replayed_trajectory_is_identical_for_each_pass(self):
        cfg = load_config()
        points = cfg["experiment"]["trajectory"]
        before = [trajectory_pose(points, n) for n in range(60)]
        after = [trajectory_pose(points, n) for n in range(60)]
        self.assertEqual(before, after)
        self.assertEqual(before[0][0], points[0]["position_m"])
        self.assertEqual(before[-1][0], points[-1]["position_m"])
        self.assertEqual(trajectory_pose(points, 120)[0], points[-1]["position_m"])

    def test_heading_wrap_takes_short_rotation(self):
        points = [{"frame": n, "position_m": [n, 0, 1], "rotation_xyz_deg": [0, 0, yaw]}
                  for n, yaw in ((0, 170), (10, -170))]
        position, rotation = trajectory_pose(points, 5)
        self.assertEqual(position, [5, 0, 1])
        self.assertEqual(rotation, [0, 0, 180])


class RecordingTests(unittest.TestCase):
    def test_png_bytes_and_crc_roundtrip_without_an_image_dependency(self):
        class Row:
            def tobytes(self):
                return bytes([255, 0, 0, 255, 0, 255, 0, 255])

        class Frame:
            dtype, ndim, shape = "uint8", 3, (1, 2, 4)

            def __iter__(self):
                return iter([Row()])

        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "frame.png"
            write_png(path, Frame())
            data = path.read_bytes()
            self.assertEqual(data[:8], b"\x89PNG\r\n\x1a\n")
            chunks = {}
            offset = 8
            while offset < len(data):
                length = struct.unpack(">I", data[offset:offset + 4])[0]
                tag, payload = data[offset + 4:offset + 8], data[offset + 8:offset + 8 + length]
                crc = struct.unpack(">I", data[offset + 8 + length:offset + 12 + length])[0]
                self.assertEqual(crc, zlib.crc32(tag + payload) & 0xFFFFFFFF)
                chunks[tag] = payload
                offset += length + 12
            self.assertEqual(struct.unpack(">IIBBBBB", chunks[b"IHDR"]), (2, 1, 8, 6, 0, 0, 0))
            self.assertEqual(zlib.decompress(chunks[b"IDAT"]), b"\x00" + Row().tobytes())

    def test_recording_preserves_existing_runs_and_pairs_pose_index(self):
        with tempfile.TemporaryDirectory() as folder:
            first, second = create_run_directory(folder), create_run_directory(folder)
            self.assertNotEqual(first, second)
            recorder = PoseRecorder(first / "before", images=False)
            try:
                recorder.record(3, 0.1, {}, {"T_world_body": [[1]]})
            finally:
                recorder.close()
            line = json.loads((first / "before/poses.jsonl").read_text())
            self.assertEqual((line["frame"], line["time_s"], line["images"]), (3, 0.1, {}))
            with self.assertRaises(FileExistsError):
                PoseRecorder(first / "before", images=False)


class PreviewTests(unittest.TestCase):
    def setUp(self):
        self.cfg = load_config()["output"]["preview"]
        self.folder = tempfile.TemporaryDirectory(prefix="preview space ")
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)

    def make_pass(self, name, indices=(0, 1), times=None):
        directory = self.root / name
        for side in ("left", "right"):
            (directory / side).mkdir(parents=True)
            for index in indices:
                (directory / side / f"{index:06d}.png").write_bytes(b"original PNG")
        if times is None:
            times = [index / 30 for index in indices]
        (directory / "poses.jsonl").write_text("".join(json.dumps({"frame": index, "time_s": time}) + "\n"
                                                   for index, time in zip(indices, times)), encoding="utf-8")
        return directory

    def fake_ffmpeg(self, command, **kwargs):
        self.assertIsInstance(command, list)
        Path(command[-1]).write_bytes(b"video")
        return subprocess.CompletedProcess(command, 0, "", "")

    def test_command_stacks_full_resolution_and_handles_spaces(self):
        before = self.make_pass("before")
        command = ffmpeg_command("C:/Program Files/ffmpeg/bin/ffmpeg.exe", before / "left", before / "right",
                                 before / "stereo_preview.mp4", self.cfg)
        self.assertEqual(command[0], "C:/Program Files/ffmpeg/bin/ffmpeg.exe")
        self.assertIn(str(before / "left" / "%06d.png"), command)
        self.assertIn(str(before / "right" / "%06d.png"), command)
        self.assertEqual(command[command.index("-filter_complex") + 1], "[0:v][1:v]hstack=inputs=2[v]")
        self.assertEqual(command[command.index("-pix_fmt") + 1], "yuv420p")
        self.assertEqual(command[command.index("-movflags") + 1], "+faststart")
        self.assertIn("-n", command)
        self.assertNotIn("scale", " ".join(command))

    def test_stereo_and_comparison_use_correct_inputs_once(self):
        self.make_pass("before")
        self.make_pass("after")
        original = (self.root / "before/left/000000.png").read_bytes()
        with patch("rov_sim.preview.subprocess.run", side_effect=self.fake_ffmpeg) as mock_run:
            result = generate_previews(self.root, ("before", "after"), self.cfg | {"ffmpeg_executable": "C:/Program Files/ffmpeg.exe"})
        self.assertEqual(mock_run.call_count, 3)
        self.assertEqual(set(result), {"before_stereo", "after_stereo", "comparison"})
        comparison = mock_run.call_args_list[2].args[0]
        self.assertIn(str(self.root / "before/left/%06d.png"), comparison)
        self.assertIn(str(self.root / "after/left/%06d.png"), comparison)
        self.assertNotIn(str(self.root / "before/right/%06d.png"), comparison)
        self.assertEqual((self.root / "before/left/000000.png").read_bytes(), original)

    def test_missing_or_mismatched_frames_and_timestamps_fail_before_encoding(self):
        before = self.make_pass("before")
        self.make_pass("after")
        (before / "right/000001.png").unlink()
        with patch("rov_sim.preview.subprocess.run") as mock_run, self.assertRaisesRegex(ValueError, "nonconsecutive|indices/counts"):
            generate_previews(self.root, ("before", "after"), self.cfg | {"ffmpeg_executable": "ffmpeg"})
        mock_run.assert_not_called()
        (before / "right/000001.png").write_bytes(b"original PNG")
        (self.root / "after/poses.jsonl").write_text(json.dumps({"frame": 0, "time_s": 1}) + "\n" +
                                                      json.dumps({"frame": 1, "time_s": 2}) + "\n")
        with patch("rov_sim.preview.subprocess.run") as mock_run, self.assertRaisesRegex(ValueError, "timestamps differ"):
            generate_previews(self.root, ("before", "after"), self.cfg | {"ffmpeg_executable": "ffmpeg"})
        mock_run.assert_not_called()

    def test_before_after_frame_counts_must_match(self):
        self.make_pass("before")
        self.make_pass("after", indices=(0,))
        with patch("rov_sim.preview.subprocess.run") as mock_run, self.assertRaisesRegex(ValueError, "Before/after PNG frame indices or counts differ"):
            generate_previews(self.root, ("before", "after"), self.cfg | {"ffmpeg_executable": "ffmpeg"})
        mock_run.assert_not_called()

    def test_ffmpeg_failure_and_existing_video(self):
        before = self.make_pass("before")
        with patch("rov_sim.preview.subprocess.run", return_value=subprocess.CompletedProcess([], 1, "", "encoder unavailable")):
            with self.assertRaisesRegex(RuntimeError, "encoder unavailable"):
                generate_previews(self.root, ("before",), self.cfg | {"ffmpeg_executable": "ffmpeg"})
        self.assertEqual((before / "left/000000.png").read_bytes(), b"original PNG")
        (before / "stereo_preview.mp4").write_bytes(b"old video")
        with patch("rov_sim.preview.subprocess.run") as mock_run, self.assertRaises(FileExistsError):
            generate_previews(self.root, ("before",), self.cfg | {"ffmpeg_executable": "ffmpeg"})
        mock_run.assert_not_called()
        self.assertEqual((before / "stereo_preview.mp4").read_bytes(), b"old video")

    @unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg and ffprobe required")
    def test_real_encode_has_h264_side_by_side_dimensions(self):
        class Row:
            def tobytes(self):
                return bytes([40, 80, 120] * 2)

        class Frame:
            dtype, ndim, shape = "uint8", 3, (2, 2, 3)

            def __iter__(self):
                return iter((Row(), Row()))

        before = self.make_pass("before")
        for side in ("left", "right"):
            for index in (0, 1):
                write_png(before / side / f"{index:06d}.png", Frame())
        generate_previews(self.root, ("before",), self.cfg)
        video = before / "stereo_preview.mp4"
        probe = subprocess.run([shutil.which("ffprobe"), "-v", "error", "-select_streams", "v:0",
                                "-show_entries", "stream=codec_name,width,height,nb_frames", "-of", "json", str(video)],
                               capture_output=True, text=True, check=True)
        stream = json.loads(probe.stdout)["streams"][0]
        self.assertEqual((stream["codec_name"], stream["width"], stream["height"], stream["nb_frames"]),
                         ("h264", 4, 2, "2"))


class CameraCleanupTests(unittest.TestCase):
    @staticmethod
    def adapter(cameras):
        fake_pxr = types.ModuleType("pxr")
        fake_pxr.Gf = fake_pxr.Usd = fake_pxr.UsdGeom = object()
        robot = types.ModuleType("rov_sim.robots.bluerov")
        robot.VEHICLE_PATH = "/World/BlueROV"
        with patch.dict(sys.modules, {"pxr": fake_pxr, "rov_sim.robots.bluerov": robot}):
            spec = importlib.util.spec_from_file_location("_stereo_cleanup_check", ROOT / "rov_sim/sensors/stereo.py")
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
        adapter = module.StereoCameras.__new__(module.StereoCameras)
        adapter.cameras, adapter._closed = cameras, False
        return adapter

    def test_two_phase_cleanup_and_second_close(self):
        events = []

        class Annotator:
            def __init__(self, side, name):
                self.side, self.name = side, name
                self._render_products = [f"/{side}"]

            def detach(self, product):
                events.append(("detach", self.side, self.name))
                self._render_products.remove(product)

        class Camera:
            def __init__(self, side):
                self.side = side
                self._render_product_path = f"/{side}"
                self._rgba_annot = Annotator(side, "rgba")
                self._depth_annot = Annotator(side, "depth")
                self._fabric_time_annotator = Annotator(side, "reference")
                self._custom_annotators = {"rgb": Annotator(side, "isaac_rgb")}
                self._viewport = True
                self.wrapped_ui_elements = []
                self._acquisition_callback = object()
                self._stage_open_callback = object()
                self._timer_reset_callback = object()

            def close(self):
                self.fail("OceanSim.close must not run")

            def ui_destroy(self):
                events.append(("preview", self.side))

            def detach_annotator(self, name):
                self._custom_annotators.pop(name).detach(self._render_product_path)

            def destroy(self):
                events.append(("destroy", self.side))

        cameras = {side: Camera(side) for side in ("left", "right")}
        adapter = self.adapter(cameras)
        adapter.close()
        self.assertEqual([event for event in events if event[0] == "detach"],
                         [("detach", side, name) for side in ("left", "right")
                          for name in ("rgba", "depth", "reference", "isaac_rgb")])
        self.assertLess(max(i for i, event in enumerate(events) if event[0] == "detach"),
                        min(i for i, event in enumerate(events) if event[0] == "destroy"))
        self.assertEqual(events[-2:], [("destroy", "left"), ("destroy", "right")])
        adapter.close()
        self.assertEqual(events[-2:], [("destroy", "left"), ("destroy", "right")])
        for cam in cameras.values():
            self.assertIsNone(cam._acquisition_callback)
            self.assertIsNone(cam._stage_open_callback)
            self.assertIsNone(cam._timer_reset_callback)
        self.assertEqual(adapter.cameras, {})

    def test_partial_camera_and_failure_still_release_other_camera(self):
        events = []

        class Annotator:
            def __init__(self, products, fail=False):
                self._render_products = products
                self.fail = fail

            def detach(self, product):
                events.append(("detach", product))
                if self.fail:
                    raise RuntimeError("injected detach failure")

        class Camera:
            _viewport = False

            def __init__(self, side, partial=False):
                self.side = side
                self._render_product_path = f"/{side}"
                self._rgba_annot = Annotator([f"/{side}"], fail=side == "left")
                if not partial:
                    self._depth_annot = Annotator([f"/{side}"])

            def destroy(self):
                events.append(("destroy", self.side))
                if self.side == "left":
                    raise RuntimeError("injected destroy failure")

        adapter = self.adapter({"left": Camera("left", partial=True), "right": Camera("right")})
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            adapter.close()
        messages = [str(item.message) for item in caught]
        self.assertTrue(any("injected detach failure" in message for message in messages))
        self.assertTrue(any("injected destroy failure" in message for message in messages))
        self.assertIn(("detach", "/right"), events)
        self.assertEqual(events[-2:], [("destroy", "left"), ("destroy", "right")])
        self.assertEqual(adapter.cameras, {})


if __name__ == "__main__":
    unittest.main()
