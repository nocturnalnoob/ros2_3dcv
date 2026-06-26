#!/usr/bin/env python3
"""
Local grader — run a single submission against the real sandbox container,
without the web app. Useful for authoring/CI.

Usage:
  # grade the reference solution shipped in the curriculum
  python3 grade.py module-8

  # grade your own file
  python3 grade.py module-8 path/to/my_solution.py

  # pick a distro (must have built ros2-3dcv-sandbox:<distro>)
  python3 grade.py module-8 --distro jazzy

Requires: a running Docker daemon and a built sandbox image
(`make build` in this directory). Module 14 is a terminal exercise and is
graded by the ros2 CLI emulator (backend/terminal_sim.py), not here.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import shutil
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[2]
CURRICULUM = ROOT / "curriculum" / "curriculum.json"


def load_module(module_id: str) -> dict:
    data = json.loads(CURRICULUM.read_text())
    for m in data["modules"]:
        if m["id"] == module_id:
            return m
    sys.exit(f"unknown module '{module_id}'")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("module_id")
    ap.add_argument("solution", nargs="?", help="solution .py (default: reference)")
    ap.add_argument("--distro", default="humble")
    ap.add_argument("--image", default=None)
    args = ap.parse_args()

    module = load_module(args.module_id)
    if module["exercise"]["type"] == "terminal":
        sys.exit("module-14 is a terminal exercise; grade it via the CLI emulator.")

    image = args.image or f"ros2-3dcv-sandbox:{args.distro}"
    job = pathlib.Path(tempfile.mkdtemp(prefix="grade_"))
    try:
        code = (pathlib.Path(args.solution).read_text()
                if args.solution else module["exercise"]["solutionCode"])
        (job / "solution.py").write_text(code)
        (job / "verification.json").write_text(json.dumps(module["verification"]))

        cmd = [
            "docker", "run", "--rm",
            "--network", "none",
            "--cap-drop", "ALL",
            "--security-opt", "no-new-privileges",
            "--pids-limit", "256",
            "--memory", "512m", "--cpus", "1.0",
            "-e", "ROS_DOMAIN_ID=77",
            "-v", f"{job}:/job:rw",
            image, args.module_id,
        ]
        print(f"$ {' '.join(cmd)}\n", file=sys.stderr)
        proc = subprocess.run(cmd, capture_output=True, text=True,
                              timeout=module["verification"]["timeoutSeconds"] + 25)
    finally:
        shutil.rmtree(job, ignore_errors=True)

    verdict = None
    for line in proc.stdout.splitlines():
        if line.startswith("VERDICT:"):
            verdict = json.loads(line[len("VERDICT:"):])

    if verdict is None:
        print("=== container stdout ===\n" + proc.stdout)
        print("=== container stderr ===\n" + proc.stderr)
        sys.exit("no VERDICT emitted — see logs above")

    status = "PASSED ✅" if verdict["passed"] else "NOT PASSED ❌"
    print(f"\n{args.module_id}: {status}")
    for c in verdict.get("checks", []):
        mark = "✓" if c["passed"] else "✗"
        print(f"  {mark} {c['kind']}: {c['message']}")
    if verdict.get("error"):
        print(f"  error: {verdict['error']}")
    return 0 if verdict["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
