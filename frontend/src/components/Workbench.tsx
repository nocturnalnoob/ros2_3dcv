import { useEffect, useMemo, useState } from "react";
import { useParams, Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import Editor from "@monaco-editor/react";
import ReactMarkdown from "react-markdown";
import { fetchCurriculum, runCode, submitCode, Module, Verdict } from "../api";
import { useProgress, useTheme } from "../store";
import { TerminalPane } from "./TerminalPane";
import { VizPanel } from "./VizPanel";
import { ThemeToggle } from "./ThemeToggle";

type Tab = "editor" | "terminal" | "viz";

export function Workbench() {
  const { id } = useParams();
  const { data } = useQuery({ queryKey: ["curriculum"], queryFn: fetchCurriculum });
  const module = useMemo(() => data?.find((m) => m.id === id), [data, id]);

  if (!module) return <div className="center">Loading module…</div>;
  return <WorkbenchInner key={module.id} module={module} />;
}

function WorkbenchInner({ module }: { module: Module }) {
  const { savedCode, saveCode, setStatus } = useProgress();
  const theme = useTheme((s) => s.theme);
  const [code, setCode] = useState(savedCode[module.id] ?? module.exercise.starterCode);
  const [tab, setTab] = useState<Tab>(module.exercise.type === "terminal" ? "terminal" : "editor");
  const [verdict, setVerdict] = useState<Verdict | null>(null);
  const [busy, setBusy] = useState<"run" | "submit" | null>(null);

  useEffect(() => saveCode(module.id, code), [code, module.id, saveCode]);

  async function onRun() {
    setBusy("run");
    setVerdict(await runCode(module.id, code).finally(() => setBusy(null)));
  }
  async function onSubmit() {
    setBusy("submit");
    const v = await submitCode(module.id, code).finally(() => setBusy(null));
    setVerdict(v);
    setStatus(module.id, v.passed ? "passed" : "attempted");
  }

  return (
    <div className="workbench">
      <aside className="lesson-pane">
        <Link to="/" className="back">← All modules</Link>
        <h1>{module.title}</h1>
        <p className="meta">~{module.estimatedMinutes} min · Phase {module.phase}</p>
        <ReactMarkdown>{module.lesson.markdown}</ReactMarkdown>
        <div className="exercise-box">
          <h3>Exercise</h3>
          <p>{module.exercise.prompt}</p>
          <p className="passdef"><strong>Passes when:</strong> {module.verification.humanDescription}</p>
        </div>
      </aside>

      <main className="work-pane">
        <nav className="tabs">
          {module.exercise.type === "python" && <TabBtn t="editor" tab={tab} set={setTab}>Editor</TabBtn>}
          {module.exercise.type === "terminal" && <TabBtn t="terminal" tab={tab} set={setTab}>Terminal</TabBtn>}
          <TabBtn t="viz" tab={tab} set={setTab}>Visualization</TabBtn>
          <div className="spacer" />
          <ThemeToggle />
          {module.exercise.type === "python" && (
            <>
              <button onClick={() => setCode(module.exercise.starterCode)}>Reset</button>
              <button onClick={onRun} disabled={!!busy}>{busy === "run" ? "Running…" : "Run"}</button>
              <button className="primary" onClick={onSubmit} disabled={!!busy}>
                {busy === "submit" ? "Grading…" : "Submit"}
              </button>
            </>
          )}
        </nav>

        <div className="tab-body">
          {tab === "editor" && (
            <Editor
              height="100%"
              language={module.exercise.editorLanguage}
              theme={theme === "dark" ? "vs-dark" : "light"}
              value={code}
              onChange={(v) => setCode(v ?? "")}
              options={{ minimap: { enabled: false }, fontSize: 14 }}
            />
          )}
          {tab === "terminal" && <TerminalPane moduleId={module.id} onGraded={setVerdict} />}
          {tab === "viz" && <VizPanel moduleId={module.id} />}
        </div>

        {verdict && <ResultPanel verdict={verdict} />}
      </main>
    </div>
  );
}

function TabBtn({ t, tab, set, children }: { t: Tab; tab: Tab; set: (t: Tab) => void; children: React.ReactNode }) {
  return (
    <button className={tab === t ? "tab active" : "tab"} onClick={() => set(t)}>
      {children}
    </button>
  );
}

function ResultPanel({ verdict }: { verdict: Verdict }) {
  return (
    <div className={`result ${verdict.passed ? "ok" : "fail"}`}>
      <div className="result-head">
        {verdict.passed ? "✅ Passed" : "❌ Not passed"} · {verdict.durationMs} ms
        {verdict.error && <span className="err"> — {verdict.error}</span>}
      </div>
      {verdict.checks.length > 0 && (
        <ul className="checks">
          {verdict.checks.map((c, i) => (
            <li key={i} className={c.passed ? "ok" : "fail"}>
              <span>{c.passed ? "✓" : "✗"}</span> <code>{c.kind}</code> — {c.message}
            </li>
          ))}
        </ul>
      )}
      {(verdict.stdout || verdict.stderr) && (
        <pre className="console">{verdict.stdout}{verdict.stderr}</pre>
      )}
    </div>
  );
}
