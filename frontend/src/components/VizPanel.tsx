import { useEffect, useRef } from "react";
import * as THREE from "three";

/**
 * WebGL "RViz-in-the-browser". Connects to /ws/viz, which relays the sandbox's
 * published visualization topics in the Foxglove schema:
 *   foxglove.PointCloud      -> THREE.Points
 *   foxglove.SceneUpdate     -> cubes/lines (MarkerArray, 3D bounding boxes)
 *   foxglove.FrameTransform  -> TF axes
 *   foxglove.PoseInFrame     -> camera-pose gizmo
 * Because the wire format IS Foxglove's, the same /ws/viz URL also opens in a
 * standalone Foxglove Studio. This component renders a minimal subset.
 */
export function VizPanel({ moduleId }: { moduleId: string }) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const host = ref.current!;
    const scene = new THREE.Scene();
    scene.background = new THREE.Color(0x0d1117);
    const camera = new THREE.PerspectiveCamera(60, host.clientWidth / host.clientHeight, 0.1, 100);
    camera.position.set(3, 3, 3);
    camera.lookAt(0, 0, 0);
    const renderer = new THREE.WebGLRenderer({ antialias: true });
    renderer.setSize(host.clientWidth, host.clientHeight);
    host.appendChild(renderer.domElement);
    scene.add(new THREE.GridHelper(10, 10, 0x30363d, 0x21262d));
    scene.add(new THREE.AxesHelper(1));

    const dynamic = new THREE.Group();
    scene.add(dynamic);

    const ws = new WebSocket(`ws://${location.host}/ws/viz?submission=${moduleId}`);
    ws.onmessage = (ev) => {
      let msg: any;
      try { msg = JSON.parse(ev.data); } catch { return; }
      if (msg.op === "info") return;
      // Decode a SceneUpdate of cube entities (3D bounding boxes) as an example.
      for (const entity of msg.entities ?? []) {
        for (const cube of entity.cubes ?? []) {
          const geo = new THREE.BoxGeometry(cube.size.x, cube.size.y, cube.size.z);
          const mat = new THREE.MeshBasicMaterial({ color: 0x58a6ff, wireframe: true });
          const mesh = new THREE.Mesh(geo, mat);
          mesh.position.set(cube.pose.position.x, cube.pose.position.y, cube.pose.position.z);
          dynamic.add(mesh);
        }
      }
    };

    let raf = 0;
    const tick = () => {
      dynamic.rotation.y += 0.002;
      renderer.render(scene, camera);
      raf = requestAnimationFrame(tick);
    };
    tick();

    return () => {
      cancelAnimationFrame(raf);
      ws.close();
      renderer.dispose();
      host.removeChild(renderer.domElement);
    };
  }, [moduleId]);

  return (
    <div className="viz-host" ref={ref}>
      <div className="viz-hint">Foxglove-schema stream · open the same /ws/viz URL in Foxglove Studio for full tools</div>
    </div>
  );
}
