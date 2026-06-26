"""
Submission orchestrator — turns a student submission into a Verdict.

Flow:
  1. (optional) fast static AST pre-check to reject obvious abuse
  2. dispatch to the sandbox (sandbox.py)
  3. for /submit, the in-sandbox harness already evaluated the module's checks
     and emitted a structured verdict; we adopt it. If the harness failed to
     emit one (crash/timeout), we synthesize a failing verdict from logs.
"""
from __future__ import annotations

import ast
import time

from models import CheckResult, Module, RunRequest, SubmitRequest, Verdict
from sandbox import run_in_sandbox

# Imports/attrs that never make sense in a graded rclpy exercise and smell like
# sandbox-escape attempts. This is defense-in-depth; the container is the real
# boundary (see ARCHITECTURE §4).
_BANNED_IMPORTS = {"ctypes", "socket"}
_BANNED_CALLS = {"system", "popen", "fork", "execv", "execve", "spawn"}


def static_precheck(code: str) -> str | None:
    """Return an error string if the code is statically rejected, else None."""
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return f"SyntaxError: {e}"
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            mod = (getattr(node, "module", None) or "").split(".")[0]
            names = [a.name.split(".")[0] for a in node.names]
            if mod in _BANNED_IMPORTS or any(n in _BANNED_IMPORTS for n in names):
                return f"Disallowed import detected ({mod or names})."
        if isinstance(node, ast.Attribute) and node.attr in _BANNED_CALLS:
            return f"Disallowed call detected (.{node.attr})."
    return None


async def run_only(req: RunRequest) -> Verdict:
    """Execute without grading — return raw output for the 'Run' button."""
    err = static_precheck(req.code)
    if err:
        return Verdict(passed=False, stderr=err, error=err)
    started = time.monotonic()
    res = await run_in_sandbox(
        student_code=req.code,
        module_id=req.moduleId,
        distro=req.distro,
        timeout_s=15,
        grade=False,
    )
    return Verdict(
        passed=res.exit_code == 0 and not res.timed_out,
        stdout=res.stdout,
        stderr=res.stderr,
        durationMs=int((time.monotonic() - started) * 1000),
        error="Execution timed out." if res.timed_out else None,
    )


async def grade_submission(req: SubmitRequest, module: Module) -> Verdict:
    err = static_precheck(req.code)
    if err:
        return Verdict(passed=False, stderr=err, error=err)

    started = time.monotonic()
    res = await run_in_sandbox(
        student_code=req.code,
        module_id=req.moduleId,
        distro=req.distro,
        timeout_s=module.verification.timeoutSeconds,
        verification=module.verification.model_dump(),
        support_files=module.exercise.supportFiles,
        grade=True,
    )
    elapsed = int((time.monotonic() - started) * 1000)

    if res.timed_out:
        return Verdict(
            passed=False, stdout=res.stdout, stderr=res.stderr, durationMs=elapsed,
            error=f"Timed out after {module.verification.timeoutSeconds}s.",
            checks=[CheckResult(kind=c.kind, passed=False, message="not evaluated (timeout)")
                    for c in module.verification.checks],
        )

    if res.verdict_json is None:
        # Harness never produced a verdict → treat as failure, surface logs.
        return Verdict(
            passed=False, stdout=res.stdout, stderr=res.stderr, durationMs=elapsed,
            error="Grading harness did not emit a verdict (code likely crashed).",
            checks=[CheckResult(kind=c.kind, passed=False, message="not evaluated")
                    for c in module.verification.checks],
        )

    v = res.verdict_json
    return Verdict(
        passed=bool(v.get("passed")),
        checks=[CheckResult(**c) for c in v.get("checks", [])],
        stdout=res.stdout,
        stderr=res.stderr,
        durationMs=elapsed,
    )
