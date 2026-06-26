# Sandbox image: runs & grades ONE submission inside an isolated ROS 2 container.
#
# Build (per distro):
#   docker build -f backend/sandbox_image/Dockerfile \
#     --build-arg DISTRO=humble -t ros2-3dcv-sandbox:humble backend/sandbox_image
#
# The orchestrator drops solution.py (+ verification.json) into /job and runs:
#   python3 -m harness <module_id>
# which launches the student code as a subprocess and grades it (see harness/).
ARG DISTRO=humble
FROM ros:${DISTRO}-ros-base

# Perception + ecosystem packages used across the 14 modules. Pre-installed so
# submissions need ZERO network (containers run with --network none) and cold
# start is fast.
RUN apt-get update && apt-get install -y --no-install-recommends \
      python3-numpy python3-opencv \
      ros-${ROS_DISTRO}-cv-bridge \
      ros-${ROS_DISTRO}-vision-opencv \
      ros-${ROS_DISTRO}-sensor-msgs-py \
      ros-${ROS_DISTRO}-tf2-ros-py \
      ros-${ROS_DISTRO}-rosbag2-py \
      ros-${ROS_DISTRO}-rosbag2-storage-default-plugins \
      ros-${ROS_DISTRO}-example-interfaces \
      ros-${ROS_DISTRO}-action-tutorials-interfaces \
      ros-${ROS_DISTRO}-visualization-msgs \
    && rm -rf /var/lib/apt/lists/*

# Grading harness is baked into the image (read-only at runtime).
COPY harness /opt/harness/harness
COPY entrypoint.sh /opt/entrypoint.sh
RUN chmod +x /opt/entrypoint.sh

# Non-root; further hardening (cap-drop, no-new-privileges, seccomp, network
# none, read-only rootfs, cgroup limits) is applied at `docker run` time by the
# orchestrator (see backend/sandbox.py).
RUN useradd -m -u 1000 runner
USER runner
WORKDIR /job

ENTRYPOINT ["/opt/entrypoint.sh"]
