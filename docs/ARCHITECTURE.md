# ros2_3dcv — Web App Architecture

An interactive **3D Computer Vision + ROS 2** course. Students read a lesson,
then complete a coding exercise (rclpy Python or a simulated CLI session) in an
in-browser editor. A sandboxed backend runs/grades the code and streams
visualization data (PointClouds, Markers, TF, Odometry) to the browser.

This document is the high-level design. It is intentionally implementation-light
where the scaffolds in `frontend/` and `backend/` already show the concrete code.

---

## 1. System Overview

```
┌──────────────────────────────────────────────────────────────────────────┐
│                              Browser (React)                               │
│                                                                            │
│  ┌────────────┐  ┌──────────────┐  ┌─────────────┐  ┌──────────────────┐  │
│  │  Lesson    │  │  Monaco code │  │  xterm.js    │  │  Viz panel       │  │
│  │  (Markdown)│  │  editor      │  │  terminal     │  │  (WebGL / 3D)    │  │
│  └────────────┘  └──────────────┘  └─────────────┘  └──────────────────┘  │
│         │               │                  │                  ▲            │
│         │   REST        │  REST            │  WS              │  WS         │
└─────────┼───────────────┼──────────────────┼──────────────────┼────────────┘
          │               │                  │                  │
          ▼               ▼                  ▼                  │
┌──────────────────────────────────────────────────────────────┼────────────┐
│                         API Gateway (FastAPI)                  │            │
│                                                                │            │
│  /api/curriculum     /api/submit        /ws/terminal     /ws/viz            │
│        │                  │                   │                ▲            │
│        ▼                  ▼                   ▼                │            │
│  curriculum.json    Submission Orchestrator   Terminal sim    Viz bridge    │
│                           │                   (fake ros2 CLI) (Foxglove ws) │
│                           ▼                                                  │
│                  ┌─────────────────────────────────────┐                    │
│                  │        Sandbox Pool (workers)        │                    │
│                  │  one ephemeral container per submit  │                    │
│                  │  ┌───────────────────────────────┐   │                    │
│                  │  │ ROS 2 (Humble/Jazzy) + rclpy   │   │                    │
│                  │  │ student script  +  test harness│   │                    │
│                  │  │ isolated DDS domain            │   │                    │
│                  │  └───────────────────────────────┘   │                    │
│                  └─────────────────────────────────────┘                    │
└──────────────────────────────────────────────────────────────────────────┘
```

**Core idea:** the browser never runs ROS. Every submission is shipped to a
short-lived, locked-down sandbox that has a real ROS 2 install. A *test harness*
runs alongside the student's node (publishing synthetic sensor data, probing the
ROS graph) and emits a structured verdict. Visualization data is forwarded to
the browser over WebSockets in the Foxglove-compatible schema.

---

## 2. Frontend (React)

**Stack:** React + Vite + TypeScript, Zustand (state), TanStack Query (server
state), `@monaco-editor/react` (editor), `xterm.js` (terminal), `react-markdown`
(lessons), Three.js / `regl` (WebGL viz), and the Foxglove WebSocket client
schema for live data.

### Layout / routes
- `/` — course map: phases → modules, progress badges.
- `/module/:id` — the workbench (split pane):
  - **Left:** lesson Markdown (theory) + objectives + the exercise prompt.
  - **Right (tabs):**
    - *Editor* — Monaco, seeded with `exercise.starterCode`. "Run" and "Submit".
    - *Terminal* — xterm.js for `type: "terminal"` modules (the simulated CLI).
    - *Visualization* — WebGL canvas subscribing to `/ws/viz`.
  - **Bottom:** output console + per-check pass/fail table from the grader.

### Key components
| Component | Responsibility |
|-----------|----------------|
| `CourseMap` | Renders curriculum tree from `/api/curriculum`, tracks progress (localStorage + optional user account). |
| `LessonPane` | Sanitized Markdown render of `lesson.markdown`. |
| `CodeEditor` | Monaco; manages dirty state, reset-to-starter, submit. |
| `TerminalPane` | xterm.js wired to `/ws/terminal`; renders the simulated `ros2` CLI. |
| `VizPanel` | WebGL renderer; decodes Foxglove-schema messages from `/ws/viz` (PointCloud, MarkerArray, TF, PoseStamped). |
| `ResultPanel` | Shows orchestrator verdict: overall pass + per-`check` rows with messages. |

### Data flow
1. Page load → `GET /api/curriculum` (cached). Editor seeded with `starterCode`.
2. **Run** → `POST /api/run` returns raw stdout/stderr only (no grading).
3. **Submit** → `POST /api/submit` returns the structured verdict (see §5).
4. Viz tab open → opens `/ws/viz?submission=<id>`; backend replays the
   sandbox's published viz topics in Foxglove schema; `VizPanel` renders them.

The viz panel speaks the **Foxglove WebSocket protocol** so the same data can be
opened in a standalone Foxglove Studio by pointing it at the same `/ws/viz` URL —
no separate integration path.

---

## 3. Backend (FastAPI)

**Stack:** FastAPI + Uvicorn, Pydantic models, a Redis (or in-memory) job queue,
and a pool of sandbox workers. ROS 2 lives **only** inside the sandbox image, not
in the API process, so the gateway stays light and the ROS toolchain is
swappable per distro.

### Endpoints
| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/api/curriculum` | Full curriculum (or per-module). |
| `GET` | `/api/curriculum/{module_id}` | One module. |
| `POST` | `/api/run` | Execute code, return stdout/stderr, no grade. |
| `POST` | `/api/submit` | Execute + run the module's verification harness → verdict. |
| `WS` | `/ws/terminal` | Simulated `ros2` CLI session (Module 14 etc.). |
| `WS` | `/ws/viz` | Foxglove-schema visualization stream for a submission. |

### Submission Orchestrator
1. Validate request (module id, code, size limits).
2. Look up the module's `verification` block from the curriculum.
3. Acquire a sandbox from the pool; mount the student code as `solution.py` and
   the harness for that module as `harness.py`.
4. Launch under a fresh, isolated `ROS_DOMAIN_ID` so submissions never see each
   other's ROS graph. Apply resource limits (§4).
5. Collect the harness's structured verdict (a JSON line on a dedicated fd) +
   captured stdout/stderr; tear the sandbox down.
6. Return the verdict (§5) and, if the module produces viz, keep a short replay
   buffer addressable by `/ws/viz`.

---

## 4. Safe Code Evaluation (the security core)

Untrusted Python runs in **layers of isolation**; never in the API process.

**Isolation**
- One **ephemeral container** (or gVisor/Firecracker microVM for stronger
  isolation) per submission, destroyed on completion.
- **No network egress** (drop all outbound; DDS is confined to loopback +
  a unique `ROS_DOMAIN_ID`). This also blocks data exfiltration.
- **Read-only root FS** except a per-job `tmpfs` scratch dir (used for e.g.
  rosbag output in Module 11).
- Non-root user, dropped Linux capabilities, `no-new-privileges`, seccomp
  profile restricting syscalls.

**Resource limits**
- CPU + memory cgroup caps; PID cap; wall-clock timeout (`verification.timeoutSeconds`,
  default 15–20s) with hard kill of the whole process group.
- Output size cap (truncate stdout/stderr) to prevent log-flooding.

**Static pre-checks (fast reject before spawning a sandbox)**
- AST scan rejecting obvious abuse (`os.system`, `subprocess` to network tools,
  `socket`, `ctypes`, dunder import tricks). This is *defense in depth*, not the
  primary boundary — the container is.

**Sandbox image**
- Base: `ros:humble` / `ros:jazzy` with `rclpy`, `cv_bridge`, `sensor_msgs_py`,
  `tf2_ros`, `rosbag2_py`, numpy, opencv pre-installed → fast cold start.
- The per-module **test harness** is baked in and selected by module id.

---

## 5. Verification Engine

Each module carries a declarative `verification` block (see the curriculum
schema). The orchestrator maps each `check.kind` to a harness routine. The
harness runs as a sibling rclpy node in the same sandbox/domain as the student
code and produces a verdict:

```jsonc
{
  "passed": true,
  "checks": [
    { "kind": "stdout_contains", "passed": true,  "message": "found 'System initialized'" },
    { "kind": "node_exists",     "passed": true,  "message": "node 'system_node' present in graph" }
  ],
  "stdout": "....",
  "stderr": "....",
  "durationMs": 1840
}
```

### Check kinds (the grading vocabulary)
| Kind | How the harness verifies it |
|------|------------------------------|
| `stdout_contains` / `stdout_regex` | Match captured stdout/stderr against text/pattern (rcutils logs included). |
| `node_exists` | Harness node calls `get_node_names()` and asserts the student node appears. |
| `topic_published` / `topic_msg_type` | Probe subscriber confirms a topic exists, has the right type, and (optionally) receives ≥1 message. |
| `rate_approx` | Time successive messages; assert mean Hz within tolerance (e.g. 2 Hz ± 0.3). |
| `service_available` | Harness client calls the student's service with known args; asserts the response. |
| `param_value` | Harness sets a parameter externally, then asserts the student re-reads/logs the new value. |
| `numeric_close` | Assert a published numeric (e.g. depth at center pixel, filtered point count) equals ground truth within tolerance. |
| `tf_published` | Harness `TransformListener` looks up `map→camera_link` and validates the transform. |
| `marker_array_valid` | Probe captures a `MarkerArray`; asserts CUBE type, non-zero scale, valid frame, unique ids (Foxglove-renderable). |
| `bag_file_written` | Harness opens the produced bag with `rosbag2_py` `SequentialReader` and asserts topic + message count + deserialized contents. |
| `command_sequence` | (Terminal modules) match the typed CLI command sequence against expected regexes in order. |

**Injecting inputs:** for perception modules the harness *publishes synthetic
sensor data with known ground truth* (an `Image` with a planted center value, a
`PointCloud2` with known points, a `LaserScan` with a planted close range), then
asserts the student's output exactly.

---

## 6. Simulated Terminal (Module 14 & CLI practice)

The web terminal does **not** shell into the sandbox. `/ws/terminal` is backed by
a **`ros2` CLI emulator**: a small state machine pre-loaded with a fake ROS graph
(e.g. an unknown topic `/turtle1/cmd_vel` of type `geometry_msgs/msg/Twist`). It
parses `ros2 topic type`, `ros2 interface show`, `ros2 topic list/echo`,
`ros2 topic pub`, etc., returns realistic output, and records the command
sequence for `command_sequence` grading. This keeps CLI lessons fully
deterministic and safe, with no real subprocess.

For modules that benefit from the *real* CLI, the same commands can instead be
proxied into the per-submission sandbox — but the emulator is the default for
graded CLI exercises.

---

## 7. Visualization Streaming

- The sandbox runs a **Foxglove WebSocket bridge** (or `rosbridge`) exposing the
  student's published viz topics.
- `/ws/viz` forwards those messages to the browser in **Foxglove schema**
  (`foxglove.PointCloud`, `foxglove.SceneUpdate` for markers/boxes,
  `foxglove.FrameTransform` for TF, `foxglove.PoseInFrame`).
- The `VizPanel` renders them with WebGL — a lightweight "RViz-in-the-browser".
- Because the wire format *is* Foxglove's, a student can alternatively open
  Foxglove Studio against the same endpoint for the full toolset. Gazebo/RViz
  views are simulated client-side (WebGL) rather than streaming pixels, keeping
  bandwidth low and the experience headless-friendly.

---

## 8. Persistence & Progress
- **Curriculum**: `curriculum/curriculum.json` (built from `phase{1,2,3}.json`),
  served read-only. Versioned in git.
- **User progress**: per-module status (`not_started | attempted | passed`),
  last submitted code, timestamps. localStorage for anonymous use; Postgres +
  auth for accounts.
- **Submissions** (optional analytics): store verdict + truncated logs for
  debugging exercise quality.

---

## 9. Deployment
- Frontend: static build on a CDN.
- API: containerized FastAPI behind a reverse proxy; horizontally scalable.
- Sandbox workers: autoscaled pool; each submission gets a fresh container/microVM.
- Sandbox image pinned per ROS distro (`humble`, `jazzy`) so the course can offer
  both. Concurrency, queue depth, and per-IP rate limits protect the pool.

---

## 10. Repo Map
```
ros2_3dcv/
├── docs/ARCHITECTURE.md      ← this file
├── curriculum/
│   ├── phase1.json           ← Modules 1–5  (Core ROS 2 Mechanics)
│   ├── phase2.json           ← Modules 6–9  (CV & Perception)
│   ├── phase3.json           ← Modules 10–14 (Tools, Viz, Ecosystem)
│   ├── curriculum.json       ← assembled full course (built from phases)
│   └── schema.json           ← JSON Schema for a module
├── frontend/                 ← React + Vite scaffold
└── backend/                  ← FastAPI scaffold (orchestrator, sandbox, harness, CLI emulator)
```
