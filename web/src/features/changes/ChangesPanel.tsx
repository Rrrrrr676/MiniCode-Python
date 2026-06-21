import type { DiffResponse } from "../../api/types";

export function ChangesPanel({ diff, loading }: { diff: DiffResponse | null; loading: boolean }) {
  if (loading) return <p className="muted">Reading workspace changes…</p>;
  if (!diff || diff.files.length === 0) return <p className="empty-note">Working tree is clean.</p>;
  return (
    <div className="changes-list">
      <div className="change-totals"><span>+{diff.additions}</span><span>−{diff.deletions}</span></div>
      {diff.files.map((file) => (
        <details key={file.path} className="change-file">
          <summary>
            <span>{file.path}</span>
            <small>+{file.additions} −{file.deletions}</small>
          </summary>
          <pre className="diff-patch">{file.patch}</pre>
        </details>
      ))}
      {diff.truncated && <p className="muted">Large diff truncated at the safe display limit.</p>}
    </div>
  );
}
