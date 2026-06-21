import { useState } from "react";
import type { PermissionDecision, PermissionRequest } from "../../api/types";

interface PermissionCardProps {
  request: PermissionRequest;
  onResolve: (decision: PermissionDecision) => Promise<void>;
}

const FALLBACK_CHOICES: PermissionDecision[] = ["deny_once", "allow_once"];

const CHOICE_LABELS: Record<PermissionDecision, string> = {
  allow_once: "Allow once",
  allow_always: "Always allow",
  allow_turn: "Allow this turn",
  allow_all_turn: "Allow all turns",
  deny_once: "Deny",
  deny_always: "Always deny",
  deny_with_feedback: "Deny with feedback",
};

export function PermissionCard({ request, onResolve }: PermissionCardProps) {
  const [submittingDecision, setSubmittingDecision] = useState<PermissionDecision | null>(null);
  const choices = request.choices?.length ? request.choices : FALLBACK_CHOICES;

  async function resolve(decision: PermissionDecision) {
    if (submittingDecision) return;
    setSubmittingDecision(decision);
    try {
      await onResolve(decision);
    } catch {
      setSubmittingDecision(null);
    }
  }

  return (
    <section className="permission-card" aria-label="Permission required">
      <div className="eyebrow">Approval required · {request.kind}</div>
      <h3>{request.summary}</h3>
      <code>{request.scope}</code>
      <details>
        <summary>Review details</summary>
        <pre>{request.details.join("\n")}</pre>
      </details>
      <div className="permission-actions">
        {choices.map((choice) => (
          <button
            key={choice}
            className={choice.startsWith("allow") ? "primary" : undefined}
            disabled={submittingDecision !== null}
            onClick={() => void resolve(choice)}
          >
            {submittingDecision === choice ? "Submitting..." : CHOICE_LABELS[choice] ?? choice}
          </button>
        ))}
      </div>
    </section>
  );
}
