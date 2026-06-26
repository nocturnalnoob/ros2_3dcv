"""
Sandbox runner — executes untrusted student code inside an isolated, ephemeral
ROS 2 container and returns captured output + the harness verdict.

SECURITY MODEL (see docs/ARCHITECTURE.md §4):
  * one throwaway container (or gVisor/Firecracker microVM) per submission
  * no network egress; DDS confined to loopback on a unique ROS_DOMAIN_ID
  * read-only rootfs except a per-job tmpfs scratch dir
  * non-root user, dropped caps, no-new-privileges, seccomp
  * cgroup CPU/mem/PID caps + hard wall-clock timeout, process-group kill

This module shells out to a container runtime. The exact runtime
(docker/podman/gVisor) is deployment-specific; the command below is illustrative
and isolated behind run_in_sandbox() so it can be swapped without touching the
orchestrator.
"""
from __future__ import annotations

import asyncio
import json
import os
import shlex
import tempfile
from dataclasses import dataclass
from pathlib import Path

SANDBOX_IMAGE = {
    "humble": "ros2-3dcv-sandbox:humble",
    "jazzy": "ros2-3dcv-sandbox:jazzy",
}
# Each submission gets a unique domain id so graphs never collide.
_DOMAIN_COUNTER = os.getpid() % 100


@dataclass
class SandboxResult:
    stdout: str
    stderr: str
    verdict_json: dict | None  # structured verdict emitted by harness.py, or None
    timed_out: bool
    exit_code: int


def _next_domain_id() -> int:
    global _DOMAIN_COUNTER
    _DOMAIN_COUNTER = (_DOMAIN_COUNTER + 1) % 200 + 1  # 1..200
    return _DOMAIN_COUNTER


async def run_in_sandbox(
    *,
    student_code: str,
    module_id: str,
    distro: str,
    timeout_s: int,
    support_files: dict[str, str] | None = None,
    grade: bool,
) -> SandboxResult:
    """Write code to a scratch dir, run it (optionally with the grading harness)
    in a locked-down container, and collect results."""
    support_files = support_files or {}
    image = SANDBOX_IMAGE.get(distro, SANDBOX_IMAGE["humble"])
    domain_id = _next_domain_id()

    with tempfile.TemporaryDirectory(prefix="ros2_3dcv_") as scratch:
        job = Path(scratch)
        (job / "solution.py").write_text(student_code)
        for name, content in support_files.items():
            (job / name).write_text(content)

        # The grading entrypoint runs harness.py, which imports/launches the
        # student's solution and the per-module checks, then prints one JSON
        # line prefixed with VERDICT: . When not grading we just run solution.py.
        entry = (
            f"ros2 run_or_python harness.py {shlex.quote(module_id)}"
            if grade
            else "python3 solution.py"
        )

        cmd = _container_command(image, job, domain_id, entry)
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        timed_out = False
        try:
            out_b, err_b = await asyncio.wait_for(proc.communicate(), timeout=timeout_s + 3)
        except asyncio.TimeoutError:
            timed_out = True
            proc.kill()
            out_b, err_b = await proc.communicate()

        stdout = _truncate(out_b.decode(errors="replace"))
        stderr = _truncate(err_b.decode(errors="replace"))
        verdict = _extract_verdict(stdout)
        return SandboxResult(
            stdout=_strip_verdict(stdout),
            stderr=stderr,
            verdict_json=verdict,
            timed_out=timed_out,
            exit_code=proc.returncode or 0,
        )


def _container_command(image: str, job: Path, domain_id: int, entry: str) -> list[str]:
    """Illustrative locked-down container invocation. Swap docker→gVisor/podman
    per deployment. The flags encode the security model."""
    inner = (
        f"export ROS_DOMAIN_ID={domain_id} ROS_LOCALHOST_ONLY=1; "
        f"cd /job && timeout -s KILL {30} bash -lc {shlex.quote(entry)}"
    )
    return [
        "docker", "run", "--rm",
        "--network", "none",                 # no egress
        "--read-only",                        # rootfs read-only
        "--tmpfs", "/job:rw,exec,size=64m",  # scratch (rosbag output etc.)
        "--user", "1000:1000",
        "--cap-drop", "ALL",
        "--security-opt", "no-new-privileges",
        "--pids-limit", "256",
        "--memory", "512m", "--cpus", "1.0",
        "-v", f"{job}:/job_src:ro",          # source mounted read-only; copied into tmpfs by entry
        image,
        "bash", "-lc", f"cp -r /job_src/* /job/ && {inner}",
    ]


def _truncate(s: str, limit: int = 32_000) -> str:
    return s if len(s) <= limit else s[:limit] + "\n...[truncated]..."


def _extract_verdict(stdout: str) -> dict | None:
    for line in stdout.splitlines():
        if line.startswith("VERDICT:"):
            try:
                return json.loads(line[len("VERDICT:"):])
            except json.JSONDecodeError:
                return None
    return None


def _strip_verdict(stdout: str) -> str:
    return "\n".join(l for l in stdout.splitlines() if not l.startswith("VERDICT:"))
