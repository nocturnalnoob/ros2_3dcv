# Sandbox image used by the orchestrator to execute & grade ONE submission.
# Built per ROS distro:  docker build -f sandbox.Dockerfile --build-arg DISTRO=humble -t ros2-3dcv-sandbox:humble .
ARG DISTRO=humble
FROM ros:${DISTRO}

# Perception + tooling deps used across the curriculum. Pre-installed so cold
# start is fast and submissions get zero network (run with --network none).
RUN apt-get update && apt-get install -y --no-install-recommends \
      python3-numpy python3-opencv \
      ros-${ROS_DISTRO}-cv-bridge \
      ros-${ROS_DISTRO}-vision-opencv \
      ros-${ROS_DISTRO}-tf2-ros-py \
      ros-${ROS_DISTRO}-rosbag2-py \
      ros-${ROS_DISTRO}-example-interfaces \
      ros-${ROS_DISTRO}-sensor-msgs-py \
    && rm -rf /var/lib/apt/lists/*

# Grading harness is baked in; the orchestrator drops solution.py +
# verification.json into the per-job tmpfs at /job and runs harness.py.
COPY harness.py /opt/harness.py

# Non-root, no new privileges enforced at `docker run` time (see sandbox.py).
RUN useradd -m -u 1000 runner
USER runner
WORKDIR /job

# Source ROS on login shells so `python3` sees rclpy.
RUN echo "source /opt/ros/${ROS_DISTRO}/setup.bash" >> /home/runner/.bashrc
