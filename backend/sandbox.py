"""
Host-side sandbox runner — executes untrusted student code inside an isolated,
ephemeral ROS 2 container and returns captured output + the harness verdict.

SECURITY MODEL (see docs/ARCHITECTURE.md §4):
  * one throwaway container per submission, destroyed on completion
  * no network egress; DDS confined to loopback on a unique ROS_DOMAIN_ID
  * non-root user, dropped caps, no-new-privileges
  * cgroup CPU/mem/PID caps + hard wall-clock timeout, process-group kill

The container itself runs backend/sandbox_image (built via its Dockerfile),
whose entrypoint runs `python3 -m harness <module_id>`. For grading we drop
solution.py + verification.json into the mounted /job dir; the in-container
harness launches the student code and emits a VERDICT: line we parse here.

For a non-grading "Run", we instead run the student file directly so the user
just sees stdout/stderr.
"""
from __future__ import annotations

import asyncio
import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

SANDBOX_IMAGE = {
    "humble": "ros2-3dcv-sandbox:humble",
    "jazzy": "ros2-3dcv-sandbox:jazzy",
}
_DOMAIN_COUNTER = os.getpid() % 100


@dataclass
class SandboxResult:
    stdout: str
    stderr: str
    verdict_json: dict | None
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
    verification: dict | None = None,
    support_files: dict[str, str] | None = None,
    grade: bool,
) -> SandboxResult:
    support_files = support_files or {}
    image = SANDBOX_IMAGE.get(distro, SANDBOX_IMAGE["humble"])
    domain_id = _next_domain_id()

    with tempfile.TemporaryDirectory(prefix="ros2_3dcv_") as scratch:
        job = Path(scratch)
        (job / "solution.py").write_text(student_code)
        if verification is not None:
            (job / "verification.json").write_text(json.dumps(verification))
        for name, content in support_files.items():
            (job / name).write_text(content)

        cmd = _container_command(image, job, domain_id, module_id, grade)
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        timed_out = False
        try:
            out_b, err_b = await asyncio.wait_for(
                proc.communicate(), timeout=timeout_s + 25)
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


def _container_command(image: str, job: Path, domain_id: int,
                       module_id: str, grade: bool) -> list[str]:
    """Locked-down container invocation. Swap docker→gVisor/podman per
    deployment; the flags encode the security model. The image ENTRYPOINT is
    the grading harness; for a plain "Run" we override it to just exec the
    student file so the user sees raw output."""
    base = [
        "docker", "run", "--rm",
        "--network", "none",
        "--cap-drop", "ALL",
        "--security-opt", "no-new-privileges",
        "--pids-limit", "256",
        "--memory", "512m", "--cpus", "1.0",
        "-e", f"ROS_DOMAIN_ID={domain_id}",
        "-v", f"{job}:/job:rw",
    ]
    if grade:
        return [*base, image, module_id]
    # Non-grading run: override entrypoint to source ROS and run solution.py.
    run_cmd = ("source /opt/ros/$ROS_DISTRO/setup.bash && "
               "timeout -s KILL 15 python3 /job/solution.py")
    return [*base, "--entrypoint", "bash", image, "-lc", run_cmd]


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
