"""
In-sandbox grading harness (runs INSIDE the ROS 2 sandbox container, never in
the API process). It is invoked as `harness.py <module_id>`.

It does three things:
  1. spins up sibling rclpy probe nodes / injects synthetic sensor data with
     known ground truth (per the module's verification.harnessNotes),
  2. launches the student's solution.py in the same ROS_DOMAIN_ID,
  3. evaluates the module's declarative `checks` and prints exactly one line:
        VERDICT:{"passed": bool, "checks": [{kind,passed,message}, ...]}
     which sandbox.py extracts and the orchestrator returns to the browser.

This file is a representative reference implementation showing the check-kind
dispatch and two concrete probes (stdout + perception input injection). The
production harness has one routine per check kind enumerated in
docs/ARCHITECTURE.md §5.
"""
from __future__ import annotations

import importlib.util
import io
import json
import re
import sys
import threading
from contextlib import redirect_stderr, redirect_stdout

# The harness loads the module's verification spec from a sidecar the
# orchestrator drops next to solution.py (kept simple here).
SPEC_PATH = "/job/verification.json"


def load_spec() -> dict:
    try:
        with open(SPEC_PATH) as f:
            return json.load(f)
    except FileNotFoundError:
        return {"checks": []}


def run_student_capture() -> tuple[str, str, Exception | None]:
    """Import & run solution.py, capturing stdout/stderr. For nodes that block
    in rclpy.spin(), the production harness runs this in a thread and tears the
    context down after the probes finish; here we capture a bounded run."""
    out, err = io.StringIO(), io.StringIO()
    exc: Exception | None = None
    spec = importlib.util.spec_from_file_location("solution", "/job/solution.py")
    mod = importlib.util.module_from_spec(spec)
    try:
        with redirect_stdout(out), redirect_stderr(err):
            t = threading.Thread(target=spec.loader.exec_module, args=(mod,), daemon=True)
            t.start()
            t.join(timeout=10)
    except Exception as e:  # noqa: BLE001
        exc = e
    return out.getvalue(), err.getvalue(), exc


# --- check-kind dispatch ---------------------------------------------------
def check_stdout_contains(params, ctx) -> tuple[bool, str]:
    text = params.get("text") or params.get("expected", "")
    hay = ctx["stdout"] + "\n" + ctx["stderr"]
    ok = text in hay
    return ok, (f"found '{text}'" if ok else f"missing '{text}'")


def check_stdout_regex(params, ctx) -> tuple[bool, str]:
    pat = params["pattern"]
    hay = ctx["stdout"] + "\n" + ctx["stderr"]
    ok = re.search(pat, hay) is not None
    return ok, (f"matched /{pat}/" if ok else f"no match /{pat}/")


def check_node_exists(params, ctx) -> tuple[bool, str]:
    """Real impl: a sibling rclpy node calls get_node_names() and looks for the
    target. Sketched here against a graph snapshot captured during the run."""
    name = params["name"]
    ok = name in ctx.get("node_names", [])
    return ok, (f"node '{name}' present" if ok else f"node '{name}' not in graph")


# Map every check kind from the curriculum to a routine. Perception kinds
# (numeric_close, topic_msg_type, marker_array_valid, tf_published,
# bag_file_written, rate_approx, ...) are wired the same way against probe
# nodes that injected known inputs — omitted here for brevity but enumerated
# in ARCHITECTURE §5.
DISPATCH = {
    "stdout_contains": check_stdout_contains,
    "stdout_regex": check_stdout_regex,
    "node_exists": check_node_exists,
}


def main(module_id: str) -> None:
    spec = load_spec()
    stdout, stderr, exc = run_student_capture()
    node_names = []  # filled by the real probe node; empty in this sketch
    ctx = {"stdout": stdout, "stderr": stderr, "node_names": node_names, "exc": exc}

    results = []
    for chk in spec.get("checks", []):
        fn = DISPATCH.get(chk["kind"])
        if fn is None:
            results.append({"kind": chk["kind"], "passed": False,
                            "message": "check kind not implemented in this harness"})
            continue
        try:
            ok, msg = fn(chk.get("params", {}), ctx)
        except Exception as e:  # noqa: BLE001
            ok, msg = False, f"check raised: {e}"
        results.append({"kind": chk["kind"], "passed": ok, "message": msg})

    verdict = {"passed": bool(results) and all(r["passed"] for r in results),
               "checks": results}
    print("VERDICT:" + json.dumps(verdict))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "")
