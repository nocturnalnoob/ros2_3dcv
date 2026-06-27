# Running & grading locally

This is the Docker-based grading stack: a real ROS 2 container runs each
submission and a grading harness inside it injects synthetic inputs and emits a
verdict. Module 14 is a terminal exercise graded by the `ros2` CLI emulator
(`backend/terminal_sim.py`), not a container.

## Prerequisites
- Docker daemon running (`docker info` works).
- ~3–4 GB disk for the ROS 2 sandbox image.

## 1. Build the sandbox image
```bash
cd backend/sandbox_image
make build                 # builds ros2-3dcv-sandbox:humble
# or: make build DISTRO=jazzy
```
This installs ROS 2 (`ros-base`) plus `cv_bridge`, `sensor_msgs_py`, `tf2_ros`,
`rosbag2_py`, `example_interfaces`, `action_tutorials_interfaces`,
`visualization_msgs`, numpy and OpenCV, and bakes in the grading harness.

## 2. Grade a solution
```bash
# grade the reference solution for a module
make grade MODULE=module-8
python3 grade.py module-8

# grade your own file
python3 grade.py module-8 ~/my_attempt.py

# sanity-check every reference solution end-to-end
make grade-all
```
Example output:
```
module-8: PASSED ✅
  ✓ node_exists: near_point_counter present
  ✓ stdout_regex: counted exactly 3 points within 1.5 m
```

## 3. Run the full web app (optional)
```bash
# build the sandbox image first (step 1), then, from the repo root:
docker compose up --build
# web:  http://localhost:5173    api: http://localhost:8000
```
Run it **from the repo root** — compose uses `${PWD}` to share the job
directory between the host and the API container (see below).

The API spawns one sandbox container per submission, so it mounts the host
Docker socket (docker-out-of-docker). Two things must be true for grading to
work, and the UI now tells you clearly if they aren't:

1. **The sandbox image is built** (step 1). Otherwise: *"The sandbox image
   '…' is not built yet."*
2. **The API image has the docker CLI.** It does (`backend/Dockerfile` installs
   `docker.io`), but if you see *"Docker CLI not found in the API container"*
   your running image is stale — rebuild it: `docker compose build api`.

**Why the shared `.sandbox-jobs/` volume?** The API runs in a container, but the
sandbox it launches is a *sibling* container on the host daemon — so the bind
mount must use a path the **host** can see, not one inside the API container.
Compose mounts `./.sandbox-jobs` into the API at `/sandbox-jobs` and passes both
paths (`CONTAINER_JOBS_DIR`, `HOST_JOBS_DIR=${PWD}/.sandbox-jobs`) so the API
writes job files there and tells the host daemon the matching host path.

> **Simpler alternative for a solo learner:** skip docker-in-docker entirely —
> run the API directly on the host (`cd backend && pip install -r requirements.txt
> && uvicorn main:app`) and the web with `cd frontend && npm install && npm run
> dev`. Then the API creates job dirs the host daemon can see directly (no shared
> volume needed) and `docker` is already on your PATH. You still need the sandbox
> image (step 1). Or skip the web app and just use `grade.py` (step 2).

In production, replace docker-out-of-docker with a dedicated locked-down worker
pool (gVisor/Firecracker) — see ARCHITECTURE §4.

## How a submission is graded
1. `POST /api/submit` → orchestrator writes `solution.py` + `verification.json`
   to a temp `/job` dir and `docker run`s the sandbox image (network none,
   caps dropped, no-new-privileges, cgroup limits, unique `ROS_DOMAIN_ID`).
2. The container entrypoint sources ROS, isolates DDS to localhost, and runs
   `python3 -m harness <module_id>`.
3. The harness (`backend/sandbox_image/harness/`) starts the student code as a
   subprocess on the same domain, runs the module's driver — which publishes
   synthetic sensor data with known ground truth and/or probes the ROS graph,
   services, actions, params, TF, or the written bag — and prints
   `VERDICT:{...}`.
4. The host parses the verdict and returns per-check pass/fail to the browser.

## What each module's driver injects (ground truth)
| Module | Harness injects / probes | Pass condition |
|--------|--------------------------|----------------|
| 1 Nodes | graph probe + log scan | logs "System initialized"; `system_node` present |
| 2 Topics | probe subscriber on `/chatter` | String type, ~2 Hz (±0.4), "I heard:" |
| 3 Services | client calls `add_two_ints` (41+1, 10+20) | sums 42 & 30; logs "sum=42" |
| 4 Actions | harness runs the Fibonacci **server** | goal received, feedback + exact result for order 10 |
| 5 Params | reads, then sets `max_velocity=2.5` via CLI | logs both 1.0 and 2.5 |
| 6 cv_bridge | publishes bgr8 48×64 all (100,150,200) | mono8 48×64, center≈150, header copied |
| 7 Depth | 16UC1 480×640, center=1500 then 1200 | prints exact center mm for both trials |
| 8 PointCloud2 | 6 points incl. NaN, 3 within 1.5 m | prints "Points within 1.5 m: 3" |
| 9 Pose | publishes 640×480 image | PoseStamped x=0.64,y=0.48,z=1.0,w=1.0 |
| 10 TF2 | TransformListener samples `map→camera_link` | valid quaternion + motion >0.05 m |
| 11 rosbag2 | passes bag URI; reopens the bag | `/chatter` String ×1, data "hello bag" |
| 12 Markers | probe subscriber on `/detected_boxes` | ≥2 CUBE markers, valid scale/frame/alpha/ids |
| 13 Gazebo | publishes `/scan` with a 0.30 m return | zero Twist on `/cmd_vel` |
| 14 CLI | `ros2` emulator (no container) | ordered type→show→pub command sequence |

## Caveat
The harness was authored against ROS 2 Humble/Jazzy APIs and verified
statically (all Python compiles, JSON/YAML/shell lint clean). It has **not**
been executed end-to-end in this environment because it requires a Docker
daemon + the ROS 2 image, neither of which is available where it was built. Run
`make build && make grade-all` on a Docker-capable machine to exercise it; the
drivers are written to the same contract as the reference solutions, so expect
minor real-world tuning (discovery timeouts, QoS) on first run.
