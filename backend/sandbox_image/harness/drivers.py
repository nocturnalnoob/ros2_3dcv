"""
Per-module grading drivers. Each driver:
  * launches the student's solution.py as a subprocess on the shared domain,
  * injects synthetic inputs with KNOWN ground truth and/or probes the ROS graph,
  * returns a list of check-result dicts {kind, passed, message}.

Each driver is keyed by module id in DRIVERS. Message imports are done locally
so a missing package only affects its own module, not the whole harness.
"""
from __future__ import annotations

import math
import os
import re
import subprocess
import tempfile
import time

import rclpy
from rclpy.node import Node

from .util import (
    BackgroundExecutor, Repeater, StudentProcess,
    bad, node_exists, ok, service_type, topic_type, wait_until,
)

RUN_WINDOW = 6.0  # seconds a spinning student node is allowed to run


# --------------------------------------------------------------------------- #
# Module 1 — Nodes
# --------------------------------------------------------------------------- #
def m1(bg: BackgroundExecutor) -> list[dict]:
    probe = Node("m1_probe")
    bg.add(probe)
    student = StudentProcess().start()
    wait_until(lambda: "System initialized" in student.output()
               or not student.alive(), timeout=6.0)
    out = student.output()
    student.stop()
    out += student.output()
    return [
        ok("stdout_contains", "found 'System initialized'")
        if "System initialized" in out
        else bad("stdout_contains", "missing 'System initialized' in output"),
        ok("node_exists", "node 'system_node' observed")
        if node_exists(probe, "system_node", out)
        else bad("node_exists", "node 'system_node' not in graph or logs"),
    ]


# --------------------------------------------------------------------------- #
# Module 2 — Topics @ 2 Hz
# --------------------------------------------------------------------------- #
def m2(bg: BackgroundExecutor) -> list[dict]:
    from std_msgs.msg import String
    probe = Node("m2_probe")
    bg.add(probe)
    stamps: list[float] = []
    probe.create_subscription(String, "chatter",
                              lambda _m: stamps.append(time.monotonic()), 10)
    student = StudentProcess().start()
    time.sleep(RUN_WINDOW)
    out = student.output()
    student.stop()
    out += student.output()

    results = [
        ok("topic_published", f"received {len(stamps)} msgs on /chatter")
        if stamps else bad("topic_published", "no messages on /chatter"),
        ok("topic_msg_type", "type std_msgs/msg/String")
        if topic_type(probe, "chatter") == "std_msgs/msg/String"
        else bad("topic_msg_type", f"type={topic_type(probe, 'chatter')}"),
    ]
    if len(stamps) >= 2:
        hz = (len(stamps) - 1) / (stamps[-1] - stamps[0])
        results.append(
            ok("rate_approx", f"~{hz:.2f} Hz")
            if abs(hz - 2.0) <= 0.4
            else bad("rate_approx", f"{hz:.2f} Hz not within 2.0 +/- 0.4"))
    else:
        results.append(bad("rate_approx", "too few messages to measure rate"))
    results.append(
        ok("stdout_contains", "subscriber printed 'I heard:'")
        if "I heard:" in out
        else bad("stdout_contains", "missing 'I heard:'"))
    return results


# --------------------------------------------------------------------------- #
# Module 3 — Service server
# --------------------------------------------------------------------------- #
def m3(bg: BackgroundExecutor) -> list[dict]:
    from example_interfaces.srv import AddTwoInts
    probe = Node("m3_probe")
    bg.add(probe)
    client = probe.create_client(AddTwoInts, "add_two_ints")
    student = StudentProcess().start()
    available = wait_until(lambda: client.service_is_ready(), timeout=6.0)

    def call(a: int, b: int):
        req = AddTwoInts.Request()
        req.a, req.b = a, b
        fut = client.call_async(req)
        wait_until(lambda: fut.done(), timeout=5.0)
        return fut.result()

    results = []
    stype = service_type(probe, "add_two_ints")
    results.append(
        ok("service_available", "add_two_ints [example_interfaces/srv/AddTwoInts]")
        if available and stype == "example_interfaces/srv/AddTwoInts"
        else bad("service_available", f"available={available} type={stype}"))

    r1 = call(41, 1) if available else None
    r2 = call(10, 20) if available else None
    if r1 is not None and r2 is not None and r1.sum == 42 and r2.sum == 30:
        results.append(ok("introspection", "41+1=42 and 10+20=30"))
    else:
        results.append(bad("introspection",
                           f"got {getattr(r1,'sum',None)} and {getattr(r2,'sum',None)}"))

    out = student.output()
    student.stop()
    out += student.output()
    results.append(ok("stdout_contains", "server logged 'sum=42'")
                   if "sum=42" in out
                   else bad("stdout_contains", "missing 'sum=42'"))
    return results


# --------------------------------------------------------------------------- #
# Module 4 — Action client (harness provides the Fibonacci server)
# --------------------------------------------------------------------------- #
def m4(bg: BackgroundExecutor) -> list[dict]:
    from action_tutorials_interfaces.action import Fibonacci
    from rclpy.action import ActionServer

    state = {"goal_received": False}

    def execute_cb(goal_handle):
        state["goal_received"] = True
        order = goal_handle.request.order
        seq = [0, 1]
        fb = Fibonacci.Feedback()
        for i in range(1, order):
            seq.append(seq[i] + seq[i - 1])
            fb.partial_sequence = seq
            goal_handle.publish_feedback(fb)
            time.sleep(0.3)
        goal_handle.succeed()
        result = Fibonacci.Result()
        result.sequence = seq
        return result

    server_node = Node("m4_fib_server")
    ActionServer(server_node, Fibonacci, "fibonacci", execute_cb)
    bg.add(server_node)
    time.sleep(0.5)  # let the server advertise

    student = StudentProcess().start()
    wait_until(lambda: "Result:" in student.output() or not student.alive(),
               timeout=RUN_WINDOW + 4)
    out = student.output()
    student.stop()
    out += student.output()

    target = "Result: [0, 1, 1, 2, 3, 5, 8, 13, 21, 34, 55]"
    return [
        ok("callback_invoked", "Fibonacci goal received by server")
        if state["goal_received"]
        else bad("callback_invoked", "server never received a goal"),
        ok("stdout_regex", "feedback line observed")
        if re.search(r"Feedback: \[.*\]", out)
        else bad("stdout_regex", "no 'Feedback: [...]' line"),
        ok("stdout_contains", "exact result for order=10")
        if target in out
        else bad("stdout_contains", f"missing '{target}'"),
    ]


# --------------------------------------------------------------------------- #
# Module 5 — Parameters
# --------------------------------------------------------------------------- #
def m5(bg: BackgroundExecutor) -> list[dict]:
    student = StudentProcess().start()
    saw_default = wait_until(
        lambda: "current max_velocity = 1.0" in student.output(), timeout=6.0)

    # read default via the ros2 CLI (external observer)
    got = _ros2_param_get("/drive_node", "max_velocity")
    # inject a new value externally and let the loop re-read it
    _ros2_param_set("/drive_node", "max_velocity", "2.5")
    saw_updated = wait_until(
        lambda: "current max_velocity = 2.5" in student.output(), timeout=6.0)

    out = student.output()
    student.stop()
    return [
        ok("param_value", "default max_velocity == 1.0")
        if (got is not None and abs(got - 1.0) < 1e-6)
        else bad("param_value", f"default read as {got}"),
        ok("stdout_contains", "logged default 1.0")
        if saw_default else bad("stdout_contains", "missing 'current max_velocity = 1.0'"),
        ok("stdout_contains", "logged injected 2.5")
        if saw_updated else bad("stdout_contains", "missing 'current max_velocity = 2.5'"),
    ]


def _ros2_param_get(node: str, name: str):
    try:
        r = subprocess.run(["ros2", "param", "get", node, name],
                           capture_output=True, text=True, timeout=5)
        m = re.search(r"[-+]?\d*\.?\d+", r.stdout)
        return float(m.group()) if m else None
    except Exception:  # noqa: BLE001
        return None


def _ros2_param_set(node: str, name: str, value: str) -> None:
    try:
        subprocess.run(["ros2", "param", "set", node, name, value],
                       capture_output=True, text=True, timeout=5)
    except Exception:  # noqa: BLE001
        pass


# --------------------------------------------------------------------------- #
# Module 6 — cv_bridge filter (publish bgr8, expect mono8 republished)
# --------------------------------------------------------------------------- #
def m6(bg: BackgroundExecutor) -> list[dict]:
    import numpy as np
    from cv_bridge import CvBridge
    from sensor_msgs.msg import Image
    bridge = CvBridge()
    probe = Node("m6_probe")
    bg.add(probe)
    pub = probe.create_publisher(Image, "/image_raw", 10)

    arr = np.zeros((48, 64, 3), dtype=np.uint8)
    arr[:, :] = (100, 150, 200)  # BGR

    def publish():
        msg = bridge.cv2_to_imgmsg(arr, encoding="bgr8")
        msg.header.stamp.sec = 42
        msg.header.stamp.nanosec = 7
        msg.header.frame_id = "camera_color_optical_frame"
        pub.publish(msg)

    received: list = []
    probe.create_subscription(Image, "/image_filtered", received.append, 10)
    student = StudentProcess().start()
    rep = Repeater(publish, 0.1).start()
    wait_until(lambda: bool(received), timeout=RUN_WINDOW)
    rep.stop()
    out = student.output()
    student.stop()

    results = [
        ok("node_exists", "grayscale_filter present")
        if node_exists(probe, "grayscale_filter", out)
        else bad("node_exists", "grayscale_filter not found"),
        ok("topic_msg_type", "sensor_msgs/msg/Image")
        if topic_type(probe, "/image_filtered") == "sensor_msgs/msg/Image"
        else bad("topic_msg_type", f"{topic_type(probe, '/image_filtered')}"),
    ]
    if not received:
        return results + [bad("image_republished", "no /image_filtered message"),
                          bad("numeric_close", "no output to inspect")]
    m = received[0]
    dims_ok = m.encoding == "mono8" and m.height == 48 and m.width == 64
    results.append(ok("image_republished", "mono8 48x64")
                   if dims_ok else bad("image_republished",
                                       f"enc={m.encoding} {m.height}x{m.width}"))
    try:
        gray = bridge.imgmsg_to_cv2(m, desired_encoding="mono8")
        center = int(gray[24, 32])
    except Exception as e:  # noqa: BLE001
        center = -1
        results.append(bad("numeric_close", f"decode failed: {e}"))
        return results
    results.append(ok("numeric_close", f"center pixel={center} (~150)")
                   if abs(center - 150) <= 2
                   else bad("numeric_close", f"center pixel={center}, expected ~150"))
    return results


# --------------------------------------------------------------------------- #
# Module 7 — depth center pixel (two trials: 1500 then 1200)
# --------------------------------------------------------------------------- #
def m7(bg: BackgroundExecutor) -> list[dict]:
    import numpy as np
    from cv_bridge import CvBridge
    from sensor_msgs.msg import Image
    bridge = CvBridge()
    probe = Node("m7_probe")
    bg.add(probe)
    pub = probe.create_publisher(Image, "/camera/depth/image_rect_raw", 10)

    def depth_msg(center: int, other_max: int):
        arr = np.full((480, 640), 800, dtype=np.uint16)
        arr[10, 10] = 999
        arr[0, 0] = other_max
        arr[240, 320] = center
        m = bridge.cv2_to_imgmsg(arr, encoding="16UC1")
        m.header.frame_id = "camera_depth_optical_frame"
        return m

    student = StudentProcess().start()
    rep1 = Repeater(lambda: pub.publish(depth_msg(1500, 4000)), 0.1).start()
    saw1 = wait_until(
        lambda: re.search(r"^Center distance: 1500 mm$",
                          student.output(), re.M) is not None, timeout=RUN_WINDOW)
    rep1.stop()
    rep2 = Repeater(lambda: pub.publish(depth_msg(1200, 4000)), 0.1).start()
    saw2 = wait_until(
        lambda: re.search(r"^Center distance: 1200 mm$",
                          student.output(), re.M) is not None, timeout=RUN_WINDOW)
    rep2.stop()
    out = student.output()
    student.stop()

    trials_ok = saw1 and saw2
    return [
        ok("node_exists", "depth_center_reader present")
        if node_exists(probe, "depth_center_reader", out)
        else bad("node_exists", "depth_center_reader not found"),
        ok("stdout_regex", "center tracked planted value (1500 then 1200)")
        if trials_ok
        else bad("stdout_regex",
                 f"trial1(1500)={saw1} trial2(1200)={saw2} — center pixel not read correctly"),
    ]


# --------------------------------------------------------------------------- #
# Module 8 — point cloud threshold
# --------------------------------------------------------------------------- #
def m8(bg: BackgroundExecutor) -> list[dict]:
    from std_msgs.msg import Header
    from sensor_msgs.msg import PointCloud2
    from sensor_msgs_py import point_cloud2
    probe = Node("m8_probe")
    bg.add(probe)
    pub = probe.create_publisher(PointCloud2, "/points", 10)
    nan = float("nan")
    pts = [(1.0, 0.0, 0.0), (0.0, 0.0, 1.4), (0.8, 0.8, 0.8),
           (1.0, 1.0, 1.0), (3.0, 0.0, 0.0), (nan, nan, nan)]

    def publish():
        header = Header()
        header.frame_id = "map"
        pub.publish(point_cloud2.create_cloud_xyz32(header, pts))

    student = StudentProcess().start()
    rep = Repeater(publish, 0.1).start()
    saw = wait_until(
        lambda: re.search(r"^Points within 1\.5 m: 3$",
                          student.output(), re.M) is not None, timeout=RUN_WINDOW)
    rep.stop()
    out = student.output()
    student.stop()
    return [
        ok("node_exists", "near_point_counter present")
        if node_exists(probe, "near_point_counter", out)
        else bad("node_exists", "near_point_counter not found"),
        ok("stdout_regex", "counted exactly 3 points within 1.5 m")
        if saw
        else bad("stdout_regex", "did not print 'Points within 1.5 m: 3'"),
    ]


# --------------------------------------------------------------------------- #
# Module 9 — pose estimation
# --------------------------------------------------------------------------- #
def m9(bg: BackgroundExecutor) -> list[dict]:
    import numpy as np
    from cv_bridge import CvBridge
    from sensor_msgs.msg import Image
    from geometry_msgs.msg import PoseStamped
    bridge = CvBridge()
    probe = Node("m9_probe")
    bg.add(probe)
    pub = probe.create_publisher(Image, "/image_raw", 10)
    arr = np.zeros((480, 640, 3), dtype=np.uint8)

    def publish():
        m = bridge.cv2_to_imgmsg(arr, encoding="bgr8")
        m.header.stamp.sec = 99
        m.header.stamp.nanosec = 5
        m.header.frame_id = "camera_color_optical_frame"
        pub.publish(m)

    got: list[PoseStamped] = []
    probe.create_subscription(PoseStamped, "/estimated_pose", got.append, 10)
    student = StudentProcess().start()
    rep = Repeater(publish, 0.1).start()
    wait_until(lambda: bool(got), timeout=RUN_WINDOW)
    rep.stop()
    out = student.output()
    student.stop()

    results = [
        ok("node_exists", "pose_estimator present")
        if node_exists(probe, "pose_estimator", out)
        else bad("node_exists", "pose_estimator not found"),
        ok("topic_msg_type", "geometry_msgs/msg/PoseStamped")
        if topic_type(probe, "/estimated_pose") == "geometry_msgs/msg/PoseStamped"
        else bad("topic_msg_type", f"{topic_type(probe, '/estimated_pose')}"),
    ]
    if not got:
        return results + [bad("numeric_close", "no PoseStamped received")] * 4
    p = got[0].pose
    for field, val, exp in [("position.x", p.position.x, 0.64),
                            ("position.y", p.position.y, 0.48),
                            ("position.z", p.position.z, 1.0),
                            ("orientation.w", p.orientation.w, 1.0)]:
        results.append(ok("numeric_close", f"pose.{field}={val:.4f}")
                       if abs(val - exp) <= 1e-4
                       else bad("numeric_close", f"pose.{field}={val:.4f}, expected {exp}"))
    return results


# --------------------------------------------------------------------------- #
# Module 10 — TF2 dynamic transform
# --------------------------------------------------------------------------- #
def m10(bg: BackgroundExecutor) -> list[dict]:
    import tf2_ros
    from rclpy.time import Time
    probe = Node("m10_probe")
    bg.add(probe)
    buf = tf2_ros.Buffer()
    tf2_ros.TransformListener(buf, probe)
    student = StudentProcess().start()

    samples: list[tuple[float, float, float]] = []
    quats: list[tuple[float, float, float, float]] = []

    def sample():
        try:
            tf = buf.lookup_transform("map", "camera_link", Time())
            t = tf.transform.translation
            q = tf.transform.rotation
            samples.append((t.x, t.y, t.z))
            quats.append((q.x, q.y, q.z, q.w))
        except Exception:  # noqa: BLE001
            pass

    deadline = time.monotonic() + 4.0
    while time.monotonic() < deadline and len(samples) < 6:
        sample()
        time.sleep(0.2)
    out = student.output()
    student.stop()

    results = [
        ok("node_exists", "tf_circle_publisher present")
        if node_exists(probe, "tf_circle_publisher", out)
        else bad("node_exists", "tf_circle_publisher not found"),
    ]
    if not quats:
        return results + [bad("tf_published", "no map->camera_link transform seen"),
                          bad("tf_published", "no samples for motion check")]
    qnorm = math.sqrt(sum(c * c for c in quats[-1]))
    results.append(ok("tf_published", f"valid quaternion (norm={qnorm:.3f})")
                   if abs(qnorm - 1.0) < 0.05
                   else bad("tf_published", f"quaternion norm={qnorm:.3f}"))
    if len(samples) >= 3:
        d = math.dist(samples[0], samples[-1])
        results.append(ok("tf_published", f"motion delta={d:.3f} m")
                       if d > 0.05
                       else bad("tf_published", f"static transform (delta={d:.3f} m)"))
    else:
        results.append(bad("tf_published", f"only {len(samples)} samples (<3)"))
    return results


# --------------------------------------------------------------------------- #
# Module 11 — rosbag2 write (no spin; student exits)
# --------------------------------------------------------------------------- #
def m11(bg: BackgroundExecutor) -> list[dict]:
    import rosbag2_py
    from rclpy.serialization import deserialize_message
    from std_msgs.msg import String

    tmp = tempfile.mkdtemp(prefix="m11_")
    bag_uri = os.path.join(tmp, "student_bag")
    student = StudentProcess(argv=[bag_uri],
                             env_extra={"STUDENT_BAG_URI": bag_uri}).start()
    student.wait(timeout=10.0)
    student.stop()

    meta = os.path.join(bag_uri, "metadata.yaml")
    results = [
        ok("bag_file_written", "bag dir + metadata.yaml present")
        if os.path.isdir(bag_uri) and os.path.exists(meta)
        else bad("bag_file_written", f"missing bag/metadata at {bag_uri}"),
    ]
    if not os.path.exists(meta):
        return results + [bad("bag_file_written", "cannot read bag contents")]

    try:
        reader = rosbag2_py.SequentialReader()
        reader.open(
            rosbag2_py.StorageOptions(uri=bag_uri, storage_id="sqlite3"),
            rosbag2_py.ConverterOptions(input_serialization_format="cdr",
                                        output_serialization_format="cdr"))
        types = {t.name: t.type for t in reader.get_all_topics_and_types()}
        count, data_val = 0, None
        while reader.has_next():
            topic, raw, _ts = reader.read_next()
            if topic == "/chatter":
                count += 1
                data_val = deserialize_message(raw, String).data
        good = (types.get("/chatter") == "std_msgs/msg/String"
                and count == 1 and data_val == "hello bag")
        results.append(ok("bag_file_written",
                          "/chatter std_msgs/msg/String x1 data='hello bag'")
                       if good else
                       bad("bag_file_written",
                           f"type={types.get('/chatter')} count={count} data={data_val!r}"))
    except Exception as e:  # noqa: BLE001
        results.append(bad("bag_file_written", f"reader error: {e}"))
    return results


# --------------------------------------------------------------------------- #
# Module 12 — MarkerArray of CUBE bounding boxes
# --------------------------------------------------------------------------- #
def m12(bg: BackgroundExecutor) -> list[dict]:
    from visualization_msgs.msg import Marker, MarkerArray
    probe = Node("m12_probe")
    bg.add(probe)
    got: list[MarkerArray] = []
    probe.create_subscription(MarkerArray, "/detected_boxes", got.append, 10)
    student = StudentProcess().start()
    wait_until(lambda: bool(got), timeout=RUN_WINDOW)
    out = student.output()
    student.stop()

    results = [
        ok("topic_msg_type", "visualization_msgs/msg/MarkerArray")
        if topic_type(probe, "/detected_boxes") == "visualization_msgs/msg/MarkerArray"
        else bad("topic_msg_type", f"{topic_type(probe, '/detected_boxes')}"),
    ]
    if not got:
        return results + [bad("marker_array_valid", "no MarkerArray received")]
    markers = got[0].markers
    ids = [(m.ns, m.id) for m in markers]
    problems = []
    if len(markers) < 2:
        problems.append(f"only {len(markers)} markers (<2)")
    if any(m.type != Marker.CUBE for m in markers):
        problems.append("not all CUBE")
    if any(m.scale.x <= 0 or m.scale.y <= 0 or m.scale.z <= 0 for m in markers):
        problems.append("zero scale")
    if any(not m.header.frame_id for m in markers):
        problems.append("empty frame_id")
    if any(m.color.a <= 0 for m in markers):
        problems.append("alpha<=0")
    if len(set(ids)) != len(ids):
        problems.append("duplicate (ns,id)")
    results.append(ok("marker_array_valid",
                      f"{len(markers)} valid CUBE markers")
                   if not problems else bad("marker_array_valid", "; ".join(problems)))
    return results


# --------------------------------------------------------------------------- #
# Module 13 — LaserScan e-stop
# --------------------------------------------------------------------------- #
def m13(bg: BackgroundExecutor) -> list[dict]:
    from sensor_msgs.msg import LaserScan
    from geometry_msgs.msg import Twist
    probe = Node("m13_probe")
    bg.add(probe)
    pub = probe.create_publisher(LaserScan, "/scan", 10)
    inf = float("inf")

    def publish():
        s = LaserScan()
        s.angle_min, s.angle_max = -1.57, 1.57
        s.angle_increment = 3.14 / 18
        s.range_min, s.range_max = 0.05, 10.0
        s.ranges = [5.0] * 8 + [0.30] + [inf] * 2 + [5.0] * 8  # planted 0.30 m
        pub.publish(s)

    got: list[Twist] = []
    probe.create_subscription(Twist, "/cmd_vel", got.append, 10)
    student = StudentProcess().start()
    rep = Repeater(publish, 0.1).start()
    wait_until(lambda: bool(got), timeout=RUN_WINDOW)
    rep.stop()
    out = student.output()
    student.stop()

    sub_ok = node_exists(probe, "emergency_stop", out)
    results = [
        ok("node_exists", "emergency_stop present")
        if sub_ok else bad("node_exists", "emergency_stop not found"),
    ]
    if not got:
        return results + [bad("topic_published", "no Twist on /cmd_vel for close obstacle")]
    t = got[0]
    zero = all(abs(v) < 1e-9 for v in (t.linear.x, t.linear.y, t.linear.z,
                                       t.angular.x, t.angular.y, t.angular.z))
    results.append(ok("topic_published", "zero Twist e-stop published")
                   if zero else bad("topic_published",
                                    f"Twist not zero: lin.x={t.linear.x} ang.z={t.angular.z}"))
    return results


DRIVERS = {
    "module-1": m1, "module-2": m2, "module-3": m3, "module-4": m4, "module-5": m5,
    "module-6": m6, "module-7": m7, "module-8": m8, "module-9": m9, "module-10": m10,
    "module-11": m11, "module-12": m12, "module-13": m13,
    # module-14 is a terminal exercise graded by the ros2 CLI emulator, not here.
}
