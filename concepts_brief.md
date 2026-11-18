# Isaac Sim stereo ground truth to MCAP

* **Author:** L.Carvalho
* **Date:** 2026-11-16
* **Status:** Route chosen: option C, a direct MCAP writer using the message layer. Two Goldfish rounds are complete (seven lenses each). The audit of conventions inherited from HoloOcean was done in the main session against the `rov_ws` consumer source. No final review of option C and no implementation have run.

> This brief records the original route C proposal. The shipped recorder uses
> `rosbag2_py.SequentialWriter` in Kit. See the [revised design](docs/designs/isaac-stereo-mcap.md)
> and [recording validation](docs/REPRODUCIBILITY.md#mcap-recording-pixi-workspace-2026-11-17).

## Overview

The user is moving from HoloOcean to Isaac Sim 6.1 (local build `6.1.0-rc.26`) and needs simulator data in the ROS 2 Jazzy workspace (`~/rov_ws`, WSL Ubuntu) as MCAP bags.

The chosen route:

* **Trigger:** a new flag, accepted only with the validated `camera-sensor` backend.
* **What it writes:** after each frame the existing loop has checked as fresh, a new separate `rov_sim` module writes ROS 2 messages straight into an MCAP file on Windows.
* **Serialization:** the ROS 2 Jazzy rclpy that ships with Isaac Sim's ROS 2 integration (`rclpy.serialization.serialize_message`).
* **Timestamps:** every message in a frame uses one integer nanosecond stamp, as header stamp, MCAP log time and MCAP publish time.
* **Reading it:** `rov_ws` tools read the result from `/mnt/c/...`.

What this route leaves out:

* No DDS link between Windows and WSL.
* No `ros2 bag record`.
* No `.wslconfig` change.
* No new reader in `rov_ws`.

Decided by the author:

* Use the integration's message layer, not its DDS transport.
* Raw Isaac RGB images, not the underwater-processed images.
* Depth in a later milestone.
* Separate modules.
* Reuse existing pieces first, including the change-detection trajectory.
* Isaac-native conventions, with no HoloOcean conventions carried over.
* Every change reversible in git.

## Analysis

### Why option C (summary of round 2)

The Isaac Sim source rules out the bridge's standard writers in the current loop:

* **They only publish while the timeline plays** (`isaacsim.core.nodes/nodes/OgnIsaacSimulationGate.cpp:47-66`). rov_sim keeps the timeline paused on purpose.
* **They take stamps only from physics steps.** rov_sim runs no physics, so every stamp would be the same.
* **They publish `rgb8` only** (`OgnROS2PublishImage.ogn:69-81`).
* **They have no ground-truth pose publisher.**

Recording over DDS with `ros2 bag record` adds two more problems:

* It logs the time each message arrives, which `bag_to_capture` rejects.
* Frames can be lost silently between Windows and WSL.

Writing the file directly avoids all of these: there is no transit to lose frames in, and every timestamp is set once by the loop. Full evidence: `brainstorm_synthesis_report_round2.md`.

### Conventions audit: what to keep, what to drop

The `rov_ws` MCAP contract (`src/rov_dataset_player/README.md`) was written for HoloOcean captures. This session read the code of the bag consumers to separate rules a consumer actually checks from rules that only exist because of HoloOcean. The consumers read were:

* `rov_reconstruction/bag_to_capture.py`
* `export_cusfm.validate_calibration`
* `rov_mapping/stereo.py` and `node.py`
* `rov_slam/contract.hpp`
* `rov_slam/scripts/rov_evaluation/inputs.py`

**Keep. Consumers check these, and they are general ROS 2 or stereo practice, not HoloOcean:**

| Rule | Who checks it | Evidence |
| --- | --- | --- |
| Topics `/stereo/{left,right}/{image_raw,camera_info}`, `/ground_truth/pose` (PoseStamped), `/tf_static` | bag_to_capture, rov_slam evaluation | `bag_to_capture.py:18-21` |
| One identical stamp on every message in a frame, equal to log time; strictly increasing; no duplicates | bag_to_capture, rov_slam evaluation | `bag_to_capture.py:164-178`; `inputs.py:229-243` |
| Frame ids `left_camera_optical_frame` / `right_camera_optical_frame`; image and CameraInfo frame ids and sizes match | bag_to_capture | `bag_to_capture.py:149-151` |
| Ground-truth pose `frame_id == "map"` and it is the left optical camera | bag_to_capture, rov_slam evaluation | `bag_to_capture.py:140-142`; `inputs.py:237` |
| `/tf_static` contains exactly one `left_camera_optical_frame → right_camera_optical_frame`, present in **every** frame bundle, with no rotation | bag_to_capture | `bag_to_capture.py:115-120, 133-134` |
| Undistorted pinhole: D = 0, R = I, P = [K | 0], right P[0,3] = −fx·baseline, positive horizontal baseline | export_cusfm, rov_slam | `export_cusfm.py:29-52`; `contract.hpp:99-110` |
| `bgr8` images | rov_mapping, rov_slam (bag_to_capture also accepts `rgb8`) | `stereo.py:233-236`; `contract.hpp:88` |
| ROS pixel-centre convention (cx = W/2 − 0.5) | ROS CameraInfo standard; not checked numerically | REP 104 / OpenCV |

**Drop. These are HoloOcean history that nothing reading the bag checks:**

| Inherited rule | Where it came from | Why drop it | Replacement |
| --- | --- | --- | --- |
| `map` rebased to the first left camera, with +X along its horizontal forward direction | Fixing HoloOcean world poses and ORB-SLAM's relative convention (`frames.py:169-189`) | bag_to_capture rebases to the first pose itself (`bag_to_capture.py:142-146`). Isaac's world is already metric, right-handed, Z-up and gravity-aligned. Rebasing each pass would also put the change-detection "before" and "after" passes in **different** map frames when their start poses differ, which defeats comparing them. | `map` = the Isaac tank world frame, unchanged, the same for every pass |
| Static `map → initial_left_camera_optical_frame` | Same rebasing | Used only by a Foxglove layout (`rov_mapping/foxglove/initial-camera.json`) and one test. No bag reader needs it. | Omit. The Foxglove layout can follow `map`. |
| `raw_pose_frame`, `dataset_pose_frame`, `source_convention` metadata; raw TUM pose; `SENSOR_FROM_OPTICAL` body-to-optical conversion | HoloOcean PoseSensor | Isaac's loop already gives `T_world_optical` per camera (`application.py:277-286`) | Publish `T_world_leftOptical` directly. Own `custom_data` keys: format name, version, writer commit, config hash, backend, pass name. |
| Nominal calibration file (`nominal_752x480.yaml`, fx = 376, 90° field of view) and the required `--calibration-file` | HoloOcean camera | Wrong for Isaac (fx ≈ 537.14). Option C does not use the converter. | CameraInfo built from rov_sim's `stereo_calibration.json`, in the ROS pixel convention |
| Decimal-second CSV/TUM timestamps checked as whole nanoseconds | HoloOcean capture files | No text timestamps in option C | One integer `stamp_ns = epoch + index · 10⁹ // fps` with a fixed non-zero epoch |
| Repeating `/tf_static` with every frame | `rov_ws` design for `--start-offset` playback | **Keep anyway**: bag_to_capture requires it in each bundle. It costs about 200 bytes per frame. | Same |

**Inherited, but not part of this change:**

* `bag_to_capture` turns a bag back into the HoloOcean capture layout (`cam0/`, `cam1/`, `groundtruth_tum.txt`, `dataset_pose_frame: initial_left_camera_optical`) and runs the HoloOcean reader for the reconstruction tools (`bag_to_capture.py:124-131, 179`). That stays inside `rov_ws` and needs nothing from the bag beyond the "keep" rules. If reconstruction later moves off that layout, it is separate `rov_ws` work.
* rov-sim's own camera geometry (752×480, 0.38 m baseline) matches the old HoloOcean rig. It is part of rov-sim's validated configuration (`configs/tank.yaml:84-90`) and nothing depends on it matching, so it stays as is.

### New practical finding: consumers open a rosbag2 directory, not a bare `.mcap`

`bag_to_capture` hashes `<bag>/metadata.yaml` (`bag_to_capture.py:28-30`), and both readers go through `rosbag2_py`. The output must therefore be a rosbag2 directory: `metadata.yaml` plus the `.mcap` file. Two ways to produce it:

* Run `ros2 bag reindex <dir> -s mcap` in WSL after the run. It is an existing tool and needs no new code.
* Write `metadata.yaml` from the simulator.

`reindex` is the simpler first step. Writing it directly makes the bag usable without an extra command.

### Remaining risks for option C

* **MCAP container library.** The Isaac bundle has no rosbag2 and no `mcap` package. The options:
  * install the pure-Python `mcap` package into Kit's Python, which is a dependency to pin;
  * write a small MCAP writer by hand, about 200 lines covering CRC, chunks and a summary index;
  * write uncompressed, unchunked MCAP, the simplest valid form.
* **Message schemas.** MCAP needs `ros2msg` schema text. Not yet checked: whether the bundled Jazzy `share/` contains the `.msg` files. If not, the few schemas (Image, CameraInfo, PoseStamped, TFMessage and their nested types) can be embedded as text.
* **Disk-write time and size.** Raw RGB stereo is about 2.2 MB per frame, about 2.2 GB per 1,000 frames uncompressed. Wall time per frame is unmeasured.
* **Raw RGB source.** The raw buffer lives on the GPU and is borrowed until the next render (`rtx_stereo.py:133-140, 178-182`). It must be copied to the CPU inside the same frame step, as clean depth will later.
* **Validated surface.** With the flag off, behaviour must stay byte-identical. With it on, freshness checks must still pass. The 12.6 pairs/s figure does not cover runs with the writer on.
* **Crash safety.** Write to a temporary name and rename on clean completion. Also write a frame manifest (index, `stamp_ns`) so the bag can be checked against it.

### Ideal Final Result

* **Recording:** one flag on the existing loop, `camera-sensor` only. For each accepted frame it writes raw RGB stereo as `bgr8`, both CameraInfos from rov_sim's calibration, the left camera pose in the Isaac world `map`, `/tf` and `/tf_static`. All share one integer stamp equal to log time. The output is a staged rosbag2 MCAP directory, one per change-detection pass, renamed on clean completion.
* **Reading:** `bag_to_capture`, `rov_mapping` replay and `rov_slam` evaluation read it from `/mnt/c/...` unchanged.
* **Not carried over:** HoloOcean map rebasing, the nominal calibration file, and HoloOcean metadata keys.

## Goals vs. Non-Goals

* **In-Scope Goals:**
  * A new Kit-free MCAP writer module in `rov_sim`, imported only inside functions, plus a flag accepted only with `camera-sensor`.
  * Seven contract topics as listed under "Keep", with raw RGB as `bgr8`.
  * `map` = Isaac world. CameraInfo from rov_sim's calibration in the ROS pixel convention.
  * One integer stamp per frame on every message and on log and publish time.
  * One rosbag2 MCAP directory per pass.
  * A frame manifest and a completeness check.
  * Feature branches in both repos.
* **Out-of-Scope Non-Goals:**
  * Depth (next milestone).
  * Underwater-processed images.
  * The bridge's DDS transport and `ros2 bag record`.
  * A live preview (possible later).
  * Lidar and labels.
  * Other backends.
  * `/clock`.
  * HoloOcean metadata keys and map rebasing.
  * Changes to `rov_ws` code.

## Alternatives Weighed

* **A. Bridge writers with `ros2 bag record`.** Rejected: they don't publish while the timeline is paused, stamps come only from physics, `rgb8` only, and no pose publisher (verified in the Isaac Sim source).
* **B. Custom rclpy publishers with `ros2 bag record`.** Rejected by the author in favour of the message layer: receive-time log stamps, silent DDS loss, and networking changes outside git.
* **New Isaac reader modules in `rov_ws` (round 1).** Superseded: option C produces bags that existing consumers read.
* **Rebasing `map` to the first left camera as the HoloOcean contract does.** Rejected after audit: no consumer needs it, and it would give the before and after passes different map frames.
* **The nominal `rov_ws` calibration file.** Rejected: wrong fx, which passes checks silently.
* **Underwater-processed images.** Rejected by the author for the first bag; raw images chosen.
* **Depth in the first bag.** Deferred by the author.
* **Exporting to the HoloOcean layout.** Rejected by the author.
* **rosbag2 on Windows.** Not available in the Isaac bundle.

## Key Decisions & Staging for Next Steps

**Decisions carried forward:**

1. **Route:** option C. Messages are serialized with the bundled Jazzy rclpy and written as MCAP on Windows.
2. **`map`:** the Isaac tank world frame, unchanged, the same for every pass.
3. **Frames and topics:** the "Keep" table. No `initial_left_camera_optical_frame`.
4. **Calibration:** taken from `stereo_calibration.json`, published with cx = W/2 − 0.5 and cy = H/2 − 0.5, right P[0,3] = −fx·0.38.
5. **Images:** raw RGB copied to the CPU in the same frame step, converted to `bgr8` in the writer, with a test on one known-colour pixel.
6. **Stamps:** `stamp_ns = epoch + index · 10⁹ // fps`, with a fixed non-zero epoch (value to choose). Used for header, log and publish time on every message.
7. **Output:** one rosbag2 MCAP directory per change-detection pass, staged and renamed on completion, with a manifest.

**Staging:**

1. **Commit the restructure.** Commit the pending `rov_sim/` restructure alone on `main`, excluding the report `.md` files and `.idea/`, and tag it. Create `feature/isaac-mcap` in rov-sim. No `rov_ws` branch is needed, because there is no `rov_ws` code change. Decide later where documentation updates go.
2. **Short spike** in a scratch script inside Kit:
   * Does `rclpy.serialization.serialize_message` work?
   * Does the Jazzy `share/` contain `.msg` files?
   * Can `mcap` be installed into Kit's Python, or is a hand-written writer needed?
   * Does `ros2 bag reindex` in WSL accept the file?
3. **First bag.** One change-detection "before" pass of 30 frames. Done when:
   * `/stereo/left/image_raw` has exactly 30 messages;
   * stamps are increasing, non-zero integers that match the manifest;
   * log time = publish time = header stamp;
   * images are `bgr8` and frames follow the "Keep" table;
   * CameraInfo matches `stereo_calibration.json`;
   * `bag_to_capture` and `rov_slam` evaluation accept it unchanged;
   * existing Kit-free tests pass, and behaviour with the flag off is unchanged.
4. **Next:** the "after" pass; then left planar depth as 32FC1 with the 1 mm tank-wall check; then an optional live preview.

**Open questions:**

1. MCAP library: install `mcap` into Kit's Python, or a hand-written minimal writer?
2. `metadata.yaml`: produce it with `ros2 bag reindex` in WSL, or write it from the simulator?
3. Where do `rov_ws` documentation updates go (its `AGENTS.md` requires docs to change with behaviour), given no code changes there?

Full review evidence: `C:\rov-sim\brainstorm_synthesis_report.md` (round 1) and `C:\rov-sim\brainstorm_synthesis_report_round2.md` (round 2).
