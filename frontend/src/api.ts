// Thin client for the ros2_3dcv backend.

export interface Check {
  kind: string;
  description?: string;
  params?: Record<string, unknown>;
}
export interface Exercise {
  prompt: string;
  type: "python" | "terminal";
  editorLanguage: string;
  starterCode: string;
  solutionCode: string;
  supportFiles?: Record<string, string>;
}
export interface Module {
  id: string;
  phase: number;
  order: number;
  title: string;
  topic: string;
  estimatedMinutes: number;
  learningObjectives: string[];
  lesson: { markdown: string };
  exercise: Exercise;
  verification: {
    strategy: string;
    humanDescription: string;
    checks: Check[];
    timeoutSeconds: number;
    harnessNotes: string;
  };
}
export interface CheckResult {
  kind: string;
  passed: boolean;
  message: string;
}
export interface Verdict {
  passed: boolean;
  checks: CheckResult[];
  stdout: string;
  stderr: string;
  durationMs: number;
  error?: string | null;
}

export async function fetchCurriculum(): Promise<Module[]> {
  const r = await fetch("/api/curriculum");
  if (!r.ok) throw new Error("failed to load curriculum");
  return r.json();
}

export async function runCode(moduleId: string, code: string): Promise<Verdict> {
  return post("/api/run", { moduleId, code });
}
export async function submitCode(moduleId: string, code: string): Promise<Verdict> {
  return post("/api/submit", { moduleId, code });
}

async function post(url: string, body: unknown): Promise<Verdict> {
  const r = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return r.json();
}
