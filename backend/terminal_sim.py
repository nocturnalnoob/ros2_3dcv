"""
Simulated `ros2` CLI for the web terminal (Module 14 + CLI practice).

This is a deterministic emulator, NOT a real shell. It pre-loads a fake ROS
graph and parses a useful subset of `ros2 ...` commands, returning realistic
output. It records the command sequence so the grader can verify Module 14:
  1. find a topic's type      -> ros2 topic type /turtle1/cmd_vel
  2. inspect its structure    -> ros2 interface show geometry_msgs/msg/Twist
  3. publish a mock message   -> ros2 topic pub ... /turtle1/cmd_vel ...

Because nothing real is executed, CLI lessons are safe and reproducible.
"""
from __future__ import annotations

import re
import shlex
from dataclasses import dataclass

# ---- fake graph -----------------------------------------------------------
TOPICS = {
    "/turtle1/cmd_vel": "geometry_msgs/msg/Twist",
    "/turtle1/pose": "turtlesim/msg/Pose",
    "/rosout": "rcl_interfaces/msg/Log",
    "/parameter_events": "rcl_interfaces/msg/ParameterEvent",
}
NODES = ["/turtlesim"]
INTERFACES = {
    "geometry_msgs/msg/Twist": (
        "Vector3  linear\n"
        "\tfloat64 x\n\tfloat64 y\n\tfloat64 z\n"
        "Vector3  angular\n"
        "\tfloat64 x\n\tfloat64 y\n\tfloat64 z"
    ),
    "turtlesim/msg/Pose": (
        "float32 x\nfloat32 y\nfloat32 theta\n"
        "float32 linear_velocity\nfloat32 angular_velocity"
    ),
}


@dataclass
class CliResult:
    output: str
    graded: dict | None = None  # populated when the Module-14 sequence completes


class Ros2CliEmulator:
    def __init__(self) -> None:
        self.history: list[str] = []

    def banner(self) -> str:
        return (
            "ros2_3dcv simulated terminal — a node '/turtlesim' is running.\n"
            "There is an unknown topic '/turtle1/cmd_vel'. Find its type, inspect "
            "its structure, then publish a mock message to make the turtle move.\n"
        )

    def execute(self, raw: str) -> CliResult:
        cmd = raw.strip()
        if not cmd:
            return CliResult("")
        self.history.append(cmd)
        try:
            parts = shlex.split(cmd)
        except ValueError:
            parts = cmd.split()

        out = self._dispatch(parts, cmd)
        return CliResult(out, graded=self._maybe_grade())

    # -- command dispatch ---------------------------------------------------
    def _dispatch(self, parts: list[str], raw: str) -> str:
        if parts[:1] != ["ros2"]:
            return f"{parts[0]}: command not found (this terminal only runs `ros2`)"
        if len(parts) < 2:
            return "usage: ros2 <command> ..."
        group, *rest = parts[1:]

        if group == "topic":
            return self._topic(rest, raw)
        if group == "node":
            return self._node(rest)
        if group == "interface":
            return self._interface(rest)
        return f"ros2: '{group}' is not a known command group here"

    def _topic(self, rest: list[str], raw: str) -> str:
        if not rest:
            return "usage: ros2 topic <list|type|echo|info|pub>"
        sub = rest[0]
        if sub == "list":
            return "\n".join(sorted(TOPICS))
        if sub == "type":
            t = rest[1] if len(rest) > 1 else ""
            return TOPICS.get(t, f"Could not determine type of topic '{t}'")
        if sub == "info":
            t = rest[1] if len(rest) > 1 else ""
            ty = TOPICS.get(t)
            if not ty:
                return f"Unknown topic '{t}'"
            return f"Type: {ty}\nPublisher count: 1\nSubscription count: 1"
        if sub == "echo":
            t = rest[1] if len(rest) > 1 else ""
            return (f"linear:\n  x: 0.0\n  y: 0.0\n  z: 0.0\nangular:\n  x: 0.0\n  y: 0.0\n  z: 0.0\n---"
                    if t in TOPICS else f"Unknown topic '{t}'")
        if sub == "pub":
            t = next((a for a in rest[1:] if a.startswith("/")), "")
            if t not in TOPICS:
                return f"Failed to publish: unknown topic '{t}'"
            return f"publishing to {t} [{TOPICS[t]}]\npublished message"
        return f"ros2 topic: unknown subcommand '{sub}'"

    def _node(self, rest: list[str]) -> str:
        if rest[:1] == ["list"]:
            return "\n".join(NODES)
        return "usage: ros2 node list"

    def _interface(self, rest: list[str]) -> str:
        if rest[:1] == ["show"] and len(rest) > 1:
            return INTERFACES.get(rest[1], f"Unknown interface '{rest[1]}'")
        return "usage: ros2 interface show <type>"

    # -- grading (Module 14) ------------------------------------------------
    def _maybe_grade(self) -> dict | None:
        joined = "\n".join(self.history)
        steps = [
            (r"ros2\s+topic\s+type\s+/turtle1/cmd_vel", "found the topic's type"),
            (r"ros2\s+interface\s+show\s+geometry_msgs/msg/Twist", "inspected the message structure"),
            (r"ros2\s+topic\s+pub\s+.*?/turtle1/cmd_vel\s+geometry_msgs/msg/Twist", "published a mock message"),
        ]
        checks = []
        for pat, desc in steps:
            ok = re.search(pat, joined) is not None
            checks.append({"kind": "command_matches", "passed": ok, "message": desc})
        # Order matters: each step must appear after the previous one.
        ordered = self._in_order([p for p, _ in steps], joined)
        if all(c["passed"] for c in checks) and ordered:
            return {"passed": True, "checks": checks}
        return None  # keep waiting until the full ordered sequence is typed

    @staticmethod
    def _in_order(patterns: list[str], text: str) -> bool:
        pos = 0
        for pat in patterns:
            m = re.search(pat, text[pos:])
            if not m:
                return False
            pos += m.end()
        return True
