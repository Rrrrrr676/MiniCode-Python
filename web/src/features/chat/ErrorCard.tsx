import type { FailurePayload } from "../../api/types";

export function ErrorCard({ error }: { error: FailurePayload }) {
  return (
    <section className="error-card" role="alert">
      <div className="eyebrow">Turn failed · {error.errorType}</div>
      <h3>The agent stopped with an error</h3>
      <p>{error.message}</p>
      <code>{error.traceId}</code>
    </section>
  );
}
