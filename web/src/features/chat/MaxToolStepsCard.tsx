import type { TerminalPayload } from "../../api/types";

export function MaxToolStepsCard({
  terminal,
  disabled,
  onContinue,
}: {
  terminal: TerminalPayload;
  disabled: boolean;
  onContinue: () => void;
}) {
  return (
    <section className="incomplete-card" aria-labelledby="tool-limit-title">
      <div className="card-kicker">Incomplete turn</div>
      <h3 id="tool-limit-title">Tool-call limit reached</h3>
      <p>This task is not finished. MiniCode used <strong>{terminal.usedSteps}</strong> of <strong>{terminal.maxSteps}</strong> available tool steps in this turn.</p>
      <button type="button" disabled={disabled} onClick={onContinue}>
        Continue from existing results
      </button>
    </section>
  );
}
