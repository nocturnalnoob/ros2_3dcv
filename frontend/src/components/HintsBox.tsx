import { useState } from "react";

/**
 * Progressive hints: the student reveals them one at a time, gentlest first,
 * so they take only as much help as they need. A separate, deliberately
 * out-of-the-way button loads the full solution into the editor.
 */
export function HintsBox({
  hints,
  onRevealSolution,
}: {
  hints: string[];
  onRevealSolution: () => void;
}) {
  const [shown, setShown] = useState(0);
  if (!hints || hints.length === 0) return null;

  return (
    <div className="hints-box">
      <h3>💡 Stuck? Hints</h3>
      <ol className="hint-list">
        {hints.slice(0, shown).map((h, i) => (
          <li key={i}>{h}</li>
        ))}
      </ol>
      {shown < hints.length ? (
        <button onClick={() => setShown(shown + 1)}>
          {shown === 0 ? "Show a hint" : `Next hint (${shown + 1}/${hints.length})`}
        </button>
      ) : (
        <p className="hint-exhausted">
          That's every hint. Still stuck? You can load the full solution and
          study it line by line.
        </p>
      )}
      <button
        className="reveal-solution"
        onClick={() => {
          if (
            window.confirm(
              "Load the full solution into the editor? Try the hints first — " +
                "you learn far more by assembling it yourself."
            )
          )
            onRevealSolution();
        }}
      >
        Reveal full solution
      </button>
    </div>
  );
}
