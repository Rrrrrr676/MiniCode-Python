import { useState } from "react";
import type { FailurePayload } from "../../api/types";

export function ErrorCard({
  error,
  onDismiss,
  onRetry,
}: {
  error: FailurePayload;
  onDismiss: () => void;
  onRetry: () => void;
}) {
  const [copied, setCopied] = useState(false);

  async function copyTraceId() {
    try {
      await navigator.clipboard.writeText(error.traceId);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1400);
    } catch {
      setCopied(false);
    }
  }

  return (
    <section className="error-card" role="alert">
      <div className="eyebrow">Turn failed · {error.errorType}</div>
      <h3>The agent stopped with an error</h3>
      <p>{error.message}</p>
      <code>{error.traceId}</code>
      <div className="error-actions">
        <button type="button" className="quiet-button" onClick={() => void copyTraceId()}>
          {copied ? "Copied" : "Copy trace"}
        </button>
        <button type="button" className="quiet-button" onClick={onRetry}>Retry</button>
        <button type="button" className="quiet-button" onClick={onDismiss}>Close</button>
      </div>
    </section>
  );
}
