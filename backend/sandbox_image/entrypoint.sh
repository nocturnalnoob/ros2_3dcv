#!/usr/bin/env bash
# Container entrypoint: source ROS, isolate DDS to localhost on a unique domain,
# then run the grading harness for the given module.
#   usage: entrypoint.sh <module_id>
set -euo pipefail

source "/opt/ros/${ROS_DISTRO}/setup.bash"

# DDS isolation: keep discovery on loopback only so concurrent submissions never
# see each other's ROS graph. ROS_DOMAIN_ID is provided by the orchestrator.
export ROS_DOMAIN_ID="${ROS_DOMAIN_ID:-42}"
export ROS_LOCALHOST_ONLY=1                     # Humble
export ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST  # Jazzy+ (LOCALHOST_ONLY deprecated)

# Make the baked-in harness package importable.
export PYTHONPATH="/opt/harness:${PYTHONPATH:-}"

MODULE_ID="${1:-}"
exec python3 -m harness "${MODULE_ID}"
