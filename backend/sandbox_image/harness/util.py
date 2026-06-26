"""
Shared helpers for the in-container grading harness.

Execution model (all inside ONE submission container):
  * the harness process calls rclpy.init() once and spins a MultiThreadedExecutor
    in a background thread, so all harness node callbacks fire while drivers wait;
  * the student's solution.py runs as a SEPARATE subprocess on the same
    ROS_DOMAIN_ID (localhost-only DDS), so harness<->student pub/sub, services,
    actions, params and TF all discover each other normally;
  * the student's merged stdout+stderr is captured (rcutils logs go to stderr).
"""
from __future__ import annotations

import os
import re
import signal
import subprocess
import sys
import threading
import time
from typing import Callable, Optional

import rclpy
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node


# --------------------------------------------------------------------------- #
# verdict helpers
# --------------------------------------------------------------------------- #
def ok(kind: str, msg: str) -> dict:
    return {"kind": kind, "passed": True, "message": msg}


def bad(kind: str, msg: str) -> dict:
    return {"kind": kind, "passed": False, "message": msg}


# --------------------------------------------------------------------------- #
# background executor — spins harness nodes so their callbacks run
# --------------------------------------------------------------------------- #
class BackgroundExecutor:
    def __init__(self) -> None:
        self.executor = MultiThreadedExecutor()
        self._thread: Optional[threading.Thread] = None
        self._stop = False

    def add(self, node: Node) -> None:
        self.executor.add_node(node)

    def start(self) -> None:
        self._thread = threading.Thread(target=self._spin, daemon=True)
        self._thread.start()

    def _spin(self) -> None:
        while rclpy.ok() and not self._stop:
            try:
                self.executor.spin_once(timeout_sec=0.1)
            except Exception:  # noqa: BLE001 — keep grading alive
                time.sleep(0.05)

    def stop(self) -> None:
        self._stop = True
        if self._thread:
            self._thread.join(timeout=2.0)


# --------------------------------------------------------------------------- #
# student subprocess with merged-output capture
# --------------------------------------------------------------------------- #
class StudentProcess:
    def __init__(self, path: str = "/job/solution.py",
                 argv: Optional[list[str]] = None,
                 env_extra: Optional[dict[str, str]] = None) -> None:
        self.path = path
        self.argv = argv or []
        self.env_extra = env_extra or {}
        self.proc: Optional[subprocess.Popen] = None
        self._buf: list[str] = []
        self._reader: Optional[threading.Thread] = None

    def start(self) -> "StudentProcess":
        env = os.environ.copy()
        env.update(self.env_extra)
        self.proc = subprocess.Popen(
            [sys.executable, self.path, *self.argv],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            env=env, text=True, bufsize=1,
        )
        self._reader = threading.Thread(target=self._read, daemon=True)
        self._reader.start()
        return self

    def _read(self) -> None:
        assert self.proc and self.proc.stdout
        for line in self.proc.stdout:
            self._buf.append(line)

    def output(self) -> str:
        return "".join(self._buf)

    def alive(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def wait(self, timeout: float) -> None:
        if not self.proc:
            return
        try:
            self.proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            pass

    def stop(self) -> None:
        if self.proc and self.proc.poll() is None:
            self.proc.send_signal(signal.SIGINT)  # break rclpy.spin() cleanly
            try:
                self.proc.wait(timeout=3.0)
            except subprocess.TimeoutExpired:
                self.proc.kill()


# --------------------------------------------------------------------------- #
# polling / timing
# --------------------------------------------------------------------------- #
def wait_until(predicate: Callable[[], bool], timeout: float = 8.0,
               interval: float = 0.05) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return predicate()


class Repeater:
    """Call `fn` every `interval` seconds in a daemon thread until stopped.
    Used to re-publish synthetic inputs so the student node receives them
    regardless of when its subscription finishes matching."""
    def __init__(self, fn: Callable[[], None], interval: float = 0.1) -> None:
        self.fn = fn
        self.interval = interval
        self._stop = False
        self._thread = threading.Thread(target=self._run, daemon=True)

    def start(self) -> "Repeater":
        self._thread.start()
        return self

    def _run(self) -> None:
        while not self._stop:
            try:
                self.fn()
            except Exception:  # noqa: BLE001
                pass
            time.sleep(self.interval)

    def stop(self) -> None:
        self._stop = True


# --------------------------------------------------------------------------- #
# ROS graph introspection
# --------------------------------------------------------------------------- #
def _norm(topic: str) -> str:
    return "/" + topic.lstrip("/")


def node_present(probe: Node, name: str) -> bool:
    return name in probe.get_node_names()


def topic_type(probe: Node, topic: str) -> Optional[str]:
    target = _norm(topic)
    for name, types in probe.get_topic_names_and_types():
        if name == target and types:
            return types[0]
    return None


def service_type(probe: Node, service: str) -> Optional[str]:
    target = _norm(service)
    for name, types in probe.get_service_names_and_types():
        if name == target and types:
            return types[0]
    return None


def node_exists(probe: Node, name: str, student_output: str = "") -> bool:
    """Graph presence OR the node's logger token in stdout. The logger fallback
    makes this robust for short-lived nodes (e.g. spin_once) that may exit
    before DDS discovery completes."""
    if node_present(probe, name):
        return True
    return re.search(r"\[" + re.escape(name) + r"\]", student_output) is not None
