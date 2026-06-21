import { useState } from "react";
import type { PermissionRequest } from "../../api/types";

interface PermissionCardProps {
  request: PermissionRequest;
  onResolve: (decision: "allow_once" | "deny_once") => Promise<void>;
}

export function PermissionCard({ request, onResolve }: PermissionCardProps) {
  const [isSubmitting, setIsSubmitting] = useState(false);

  async function resolve(decision: "allow_once" | "deny_once") {
    if (isSubmitting) return;
    setIsSubmitting(true);
    try {
      await onResolve(decision);
    } catch {
      setIsSubmitting(false);
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
        <button disabled={isSubmitting} onClick={() => void resolve("deny_once")}>Deny</button>
        <button className="primary" disabled={isSubmitting} onClick={() => void resolve("allow_once")}>
          {isSubmitting ? "Resolving…" : "Allow once"}
        </button>
      </div>
    </section>
  );
}
