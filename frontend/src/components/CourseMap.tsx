import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { fetchCurriculum, Module } from "../api";
import { useProgress } from "../store";
import { ThemeToggle } from "./ThemeToggle";

const PHASE_TITLES: Record<number, string> = {
  1: "Phase 1 · Core ROS 2 Mechanics (rclpy)",
  2: "Phase 2 · ROS 2 Computer Vision & Perception",
  3: "Phase 3 · Tools, Visualization & Ecosystem",
};

export function CourseMap() {
  const { data, isLoading, error } = useQuery({
    queryKey: ["curriculum"],
    queryFn: fetchCurriculum,
  });
  const status = useProgress((s) => s.status);

  if (isLoading) return <div className="center">Loading curriculum…</div>;
  if (error) return <div className="center">Failed to load curriculum.</div>;

  const byPhase = groupBy(data ?? [], (m) => m.phase);

  return (
    <div className="course-map">
      <header>
        <div>
          <h1>3D Computer Vision + ROS 2</h1>
          <p>Read the theory, then complete the exercise in the in-browser editor.</p>
        </div>
        <ThemeToggle />
      </header>
      {Object.keys(byPhase)
        .map(Number)
        .sort()
        .map((phase) => (
          <section key={phase}>
            <h2>{PHASE_TITLES[phase]}</h2>
            <ul className="module-list">
              {byPhase[phase]
                .sort((a, b) => a.order - b.order)
                .map((m) => (
                  <li key={m.id}>
                    <Link to={`/module/${m.id}`}>
                      <span className={`badge ${status[m.id] ?? "not_started"}`} />
                      <span className="m-order">M{m.order}</span>
                      <span className="m-title">{m.title}</span>
                      <span className="m-type">{m.exercise.type}</span>
                    </Link>
                  </li>
                ))}
            </ul>
          </section>
        ))}
    </div>
  );
}

function groupBy<T>(arr: T[], key: (t: T) => number): Record<number, T[]> {
  return arr.reduce((acc, item) => {
    const k = key(item);
    (acc[k] ||= []).push(item);
    return acc;
  }, {} as Record<number, T[]>);
}
