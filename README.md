# ros2_3dcv — Interactive 3D Computer Vision + ROS 2 Course

An interactive course platform that teaches **3D computer vision through ROS 2**
(Humble/Jazzy) — the practical, robotics side of CV you don't get from a
math-heavy 3D-vision course: SLAM-adjacent concepts, point clouds, sensor
fusion, BEV/3D bounding boxes, LiDAR/LaserScan, depth, TF, and visualization.

Built for someone who has finished a 2D CV course (e.g. Stanford) and now wants
to *do robotics perception*, not derive epipolar geometry from scratch.

Students read a lesson, then immediately complete a coding exercise for that
topic in an in-browser Python (rclpy) editor — auto-graded by a sandboxed
backend that runs real ROS 2.

## What's here

| Path | What it is |
|------|------------|
| `docs/ARCHITECTURE.md` | Full web-app architecture: React frontend, FastAPI backend, safe rclpy sandbox, verification engine, simulated CLI, Foxglove/WebGL visualization. |
| `curriculum/curriculum.json` | The complete course: **14 modules** across 3 phases. Each has lesson text, a starter code stub, a full solution, and machine-checkable test-verification logic. |
| `curriculum/phase{1,2,3}.json` | The phases (source for the assembled `curriculum.json`). |
| `curriculum/schema.json` | JSON Schema for a module. |
| `frontend/` | React + Vite scaffold: course map, lesson viewer, Monaco editor, xterm terminal, WebGL viz panel. |
| `backend/` | FastAPI scaffold: submission orchestrator, locked-down sandbox runner, in-sandbox grading harness, simulated `ros2` CLI, viz WebSocket. |

## Curriculum

**Phase 1 — Core ROS 2 Mechanics (rclpy):** Nodes · Topics & QoS · Services ·
Actions · Parameters.
**Phase 2 — CV & Perception:** cv_bridge image pipelines · RGB-D depth ·
PointCloud2 3D reconstruction · Pose estimation.
**Phase 3 — Tools, Visualization & Ecosystem:** TF2 · rosbag2_py · RViz2 /
Foxglove markers · Gazebo LaserScan · CLI introspection.

Every exercise is graded by injecting synthetic sensor data with **known
ground truth** and asserting the student's output exactly (see each module's
`verification.harnessNotes`).

## Run it locally

```bash
# backend (gateway only; ROS lives in the sandbox image)
cd backend && pip install -r requirements.txt && uvicorn main:app --reload

# build the sandbox image (real ROS 2; used to run/grade submissions)
docker build -f backend/sandbox.Dockerfile --build-arg DISTRO=humble \
  -t ros2-3dcv-sandbox:humble backend

# frontend
cd frontend && npm install && npm run dev   # proxies /api and /ws to :8000
```

> The scaffolds are a working skeleton with the security model, grading
> contract, and data flow fully specified in `docs/ARCHITECTURE.md`. The
> curriculum content is complete and production-ready.

## Safety

Untrusted code never runs in the API process. Each submission executes in a
throwaway, network-isolated, resource-capped ROS 2 container on a unique
`ROS_DOMAIN_ID`, alongside a grading harness that injects inputs and emits a
structured verdict. See `docs/ARCHITECTURE.md` §4–5.
