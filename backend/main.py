"""
ros2_3dcv backend — FastAPI gateway.

Responsibilities:
  * serve the curriculum (read-only)
  * accept code submissions and hand them to the sandbox orchestrator
  * expose the simulated `ros2` CLI over a WebSocket (Module 14 etc.)
  * forward sandbox visualization data to the browser in Foxglove schema

ROS 2 itself never runs in this process — only inside the per-submission
sandbox (see sandbox.py). This keeps the gateway light and the ROS toolchain
swappable per distro.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from models import Module, RunRequest, SubmitRequest, Verdict
from orchestrator import grade_submission, run_only
from terminal_sim import Ros2CliEmulator

# Default resolves curriculum/ as a sibling of backend/ (bare-metal layout).
# In Docker the backend is copied to /app, so docker-compose sets
# CURRICULUM_PATH=/app/curriculum/curriculum.json to match the mount.
CURRICULUM_PATH = Path(
    os.environ.get(
        "CURRICULUM_PATH",
        Path(__file__).resolve().parent.parent / "curriculum" / "curriculum.json",
    )
)

app = FastAPI(title="ros2_3dcv", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten in production
    allow_methods=["*"],
    allow_headers=["*"],
)


def _load_curriculum() -> dict[str, Module]:
    if not CURRICULUM_PATH.exists():
        return {}
    raw = json.loads(CURRICULUM_PATH.read_text())
    modules = raw["modules"] if isinstance(raw, dict) else raw
    return {m["id"]: Module(**m) for m in modules}


CURRICULUM: dict[str, Module] = _load_curriculum()


# ---------------------------------------------------------------------------
# Curriculum
# ---------------------------------------------------------------------------
@app.get("/api/curriculum")
def get_curriculum() -> list[Module]:
    return sorted(CURRICULUM.values(), key=lambda m: m.order)


@app.get("/api/curriculum/{module_id}")
def get_module(module_id: str) -> Module:
    if module_id not in CURRICULUM:
        raise HTTPException(404, f"unknown module {module_id}")
    return CURRICULUM[module_id]


# ---------------------------------------------------------------------------
# Run (no grading) / Submit (graded)
# ---------------------------------------------------------------------------
@app.post("/api/run", response_model=Verdict)
async def run(req: RunRequest) -> Verdict:
    _require_module(req.moduleId)
    return await run_only(req)


@app.post("/api/submit", response_model=Verdict)
async def submit(req: SubmitRequest) -> Verdict:
    module = _require_module(req.moduleId)
    return await grade_submission(req, module)


def _require_module(module_id: str) -> Module:
    if module_id not in CURRICULUM:
        raise HTTPException(404, f"unknown module {module_id}")
    return CURRICULUM[module_id]


# ---------------------------------------------------------------------------
# Simulated ROS 2 CLI (Module 14 and CLI practice)
# ---------------------------------------------------------------------------
@app.websocket("/ws/terminal")
async def terminal(ws: WebSocket) -> None:
    await ws.accept()
    emulator = Ros2CliEmulator()
    await ws.send_json({"type": "banner", "text": emulator.banner()})
    try:
        while True:
            cmd = await ws.receive_text()
            result = emulator.execute(cmd)
            await ws.send_json({"type": "output", "text": result.output})
            if result.graded is not None:
                await ws.send_json({"type": "graded", "verdict": result.graded})
    except WebSocketDisconnect:
        return


# ---------------------------------------------------------------------------
# Visualization stream (Foxglove schema)
# ---------------------------------------------------------------------------
@app.websocket("/ws/viz")
async def viz(ws: WebSocket) -> None:
    """
    Forward a submission's published viz topics to the browser in Foxglove
    schema. In the full implementation this attaches to the sandbox's Foxglove
    WebSocket bridge and relays frames; here it documents the contract.
    """
    await ws.accept()
    await ws.send_json({
        "op": "info",
        "note": "Connect the sandbox Foxglove bridge here and relay frames "
                "(foxglove.PointCloud / SceneUpdate / FrameTransform / PoseInFrame).",
    })
    try:
        while True:
            await ws.receive_text()  # client keepalive / subscribe ops
    except WebSocketDisconnect:
        return


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok", "modules": str(len(CURRICULUM))}
