"""
Entry point run inside the sandbox container:  python3 -m harness <module_id>

It initializes rclpy, dispatches to the module's driver, and prints exactly one
line the host orchestrator parses:

    VERDICT:{"passed": bool, "checks": [{kind, passed, message}, ...]}
"""
from __future__ import annotations

import json
import sys

import rclpy

from .drivers import DRIVERS
from .util import BackgroundExecutor


def _emit(verdict: dict) -> None:
    print("VERDICT:" + json.dumps(verdict), flush=True)


def main() -> int:
    module_id = sys.argv[1] if len(sys.argv) > 1 else ""
    driver = DRIVERS.get(module_id)
    if driver is None:
        _emit({"passed": False, "checks": [],
               "error": f"no in-container driver for '{module_id}' "
                        f"(module-14 is graded by the ros2 CLI emulator)"})
        return 0

    rclpy.init()
    bg = BackgroundExecutor()
    bg.start()
    try:
        checks = driver(bg)
        verdict = {"passed": bool(checks) and all(c["passed"] for c in checks),
                   "checks": checks}
    except Exception as e:  # noqa: BLE001
        verdict = {"passed": False, "checks": [],
                   "error": f"{type(e).__name__}: {e}"}
    finally:
        bg.stop()
        try:
            rclpy.shutdown()
        except Exception:  # noqa: BLE001
            pass

    _emit(verdict)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
