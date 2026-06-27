import { useEffect, useRef } from "react";
import { Terminal } from "xterm";
import { FitAddon } from "xterm-addon-fit";
import "xterm/css/xterm.css";
import { Verdict } from "../api";

// xterm.js wired to the backend's simulated `ros2` CLI (/ws/terminal).
// The backend emulator (terminal_sim.py) grades the typed command sequence and
// pushes a "graded" verdict when the Module-14 sequence is complete.
export function TerminalPane({
  moduleId,
  onGraded,
}: {
  moduleId: string;
  onGraded: (v: Verdict) => void;
}) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!ref.current) return;
    const term = new Terminal({ convertEol: true, fontSize: 14, theme: { background: "#0d1117" } });
    const fit = new FitAddon();
    term.loadAddon(fit);
    term.open(ref.current);
    fit.fit();

    const ws = new WebSocket(`ws://${location.host}/ws/terminal?module=${moduleId}`);
    let line = "";
    const prompt = () => term.write("\r\n$ ");

    ws.onmessage = (ev) => {
      const msg = JSON.parse(ev.data);
      if (msg.type === "banner") {
        term.write(msg.text);
        prompt();
      } else if (msg.type === "output") {
        term.write("\r\n" + msg.text);
        prompt();
      } else if (msg.type === "graded") {
        onGraded({ passed: true, checks: msg.verdict.checks, stdout: "", stderr: "", durationMs: 0 });
        term.write("\r\n\x1b[32m✓ Exercise passed!\x1b[0m");
        prompt();
      }
    };

    term.onData((d) => {
      if (d === "\r") {
        ws.send(line);
        line = "";
      } else if (d === "") {
        if (line.length) {
          line = line.slice(0, -1);
          term.write("\b \b");
        }
      } else {
        line += d;
        term.write(d);
      }
    });

    return () => {
      ws.close();
      term.dispose();
    };
  }, [moduleId, onGraded]);

  return <div className="terminal-host" ref={ref} />;
}
