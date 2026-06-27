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
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

SANDBOX_IMAGE = {
    "humble": "ros2-3dcv-sandbox:humble",
    "jazzy": "ros2-3dcv-sandbox:jazzy",
}
_DOMAIN_COUNTER = os.getpid() % 100

# When the API itself runs inside a container, the sandbox it launches via the
# host docker daemon is a SIBLING container — so the `-v` bind mount path must
# be a path the HOST can see, not one inside the API container. We solve this
# with a volume shared between host and API at matching paths:
#   * CONTAINER_JOBS_DIR — where the API writes job files (inside the API container)
#   * HOST_JOBS_DIR      — the same volume's path on the HOST (passed to `docker -v`)
# docker-compose.yml sets both. When unset (API running directly on the host),
# we fall back to the system temp dir and use the path as-is.
CONTAINER_JOBS_DIR = os.environ.get("CONTAINER_JOBS_DIR")
HOST_JOBS_DIR = os.environ.get("HOST_JOBS_DIR")


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

    # The grader shells out to the `docker` CLI. If it isn't on PATH (api image
    # built without it) fail with a clear message instead of a 500.
    if shutil.which("docker") is None:
        return SandboxResult(
            stdout="",
            stderr="Docker CLI not found in the API container. Rebuild it with "
                   "`docker compose build api` (it needs the docker client to "
                   "launch the grading sandbox).",
            verdict_json=None, timed_out=False, exit_code=127)

    with tempfile.TemporaryDirectory(prefix="ros2_3dcv_", dir=CONTAINER_JOBS_DIR) as scratch:
        job = Path(scratch)
        (job / "solution.py").write_text(student_code)
        if verification is not None:
            (job / "verification.json").write_text(json.dumps(verification))
        for name, content in support_files.items():
            (job / name).write_text(content)

        # Path the host docker daemon must mount. In compose mode the job lives
        # in the shared volume, so translate the container path to the host one.
        if CONTAINER_JOBS_DIR and HOST_JOBS_DIR:
            host_job_path = os.path.join(HOST_JOBS_DIR, job.name)
        else:
            host_job_path = str(job)

        cmd = _container_command(image, host_job_path, domain_id, module_id, grade)
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except FileNotFoundError:
            return SandboxResult(
                stdout="",
                stderr="Could not launch `docker`. Ensure the docker CLI is "
                       "installed in the API container and the socket is mounted.",
                verdict_json=None, timed_out=False, exit_code=127)
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

        # `docker run` exits 125 when the sandbox image hasn't been built yet.
        if proc.returncode == 125 and (
                "Unable to find image" in stderr or "No such image" in stderr):
            stderr += (
                f"\n\nThe sandbox image '{image}' is not built yet. Build it once:\n"
                "  cd backend/sandbox_image && make build\n"
                "(this downloads ROS 2 — a few GB — and is required for Run/Submit).")

        verdict = _extract_verdict(stdout)
        return SandboxResult(
            stdout=_strip_verdict(stdout),
            stderr=stderr,
            verdict_json=verdict,
            timed_out=timed_out,
            exit_code=proc.returncode or 0,
        )


def _container_command(image: str, host_job_path: str, domain_id: int,
                       module_id: str, grade: bool) -> list[str]:
    """Locked-down container invocation. Swap docker→gVisor/podman per
    deployment; the flags encode the security model. The image ENTRYPOINT is
    the grading harness; for a plain "Run" we override it to just exec the
    student file so the user sees raw output. host_job_path must be a path the
    docker daemon (host) can see — see HOST_JOBS_DIR above."""
    base = [
        "docker", "run", "--rm",
        "--network", "none",
        "--cap-drop", "ALL",
        "--security-opt", "no-new-privileges",
        "--pids-limit", "256",
        "--memory", "512m", "--cpus", "1.0",
        "-e", f"ROS_DOMAIN_ID={domain_id}",
        "-v", f"{host_job_path}:/job:rw",
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
