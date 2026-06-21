import { useEffect, useMemo, useState } from "react";
import { api } from "../../api/client";
import type { DiffFile, DiffPatchResponse, DiffResponse } from "../../api/types";

const INITIAL_FILE_LIMIT = 100;
const PATCH_LIMIT_BYTES = 1_000_000;
const EXPANDED_PATCH_LIMIT_BYTES = 5_000_000;

type PatchState =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "ready"; patch: DiffPatchResponse }
  | { status: "error"; message: string };

function cacheKey(revision: string, path: string, expanded = false) {
  return `${revision}:${expanded ? "expanded" : "preview"}:${path}`;
}

function statusLabel(file: DiffFile) {
  if (file.isBinary) return "Binary";
  return file.status.charAt(0).toUpperCase() + file.status.slice(1);
}

function PatchBody({
  file,
  patchState,
  onLoadFull,
}: {
  file: DiffFile;
  patchState: PatchState;
  onLoadFull: () => void;
}) {
  if (file.isBinary) return <p className="muted change-note">Binary file preview is not available.</p>;
  if (patchState.status === "loading") return <p className="muted change-note">Loading patch…</p>;
  if (patchState.status === "error") return <p className="muted change-note">{patchState.message}</p>;
  if (patchState.status !== "ready") return null;
  if (!patchState.patch.patch) return <p className="muted change-note">No textual patch available.</p>;

  return (
    <>
      <pre className="diff-patch">{patchState.patch.patch}</pre>
      {patchState.patch.truncated && (
        <div className="patch-truncated">
          <span>Patch truncated for responsiveness.</span>
          <button type="button" className="quiet-button" onClick={onLoadFull}>
            Load more
          </button>
        </div>
      )}
    </>
  );
}

export function ChangesPanel({
  diff,
  loading,
  sessionId,
}: {
  diff: DiffResponse | null;
  loading: boolean;
  sessionId: string;
}) {
  const [visibleLimit, setVisibleLimit] = useState(INITIAL_FILE_LIMIT);
  const [expandedPaths, setExpandedPaths] = useState<Record<string, boolean>>({});
  const [patchCache, setPatchCache] = useState<Record<string, PatchState>>({});

  useEffect(() => {
    setVisibleLimit(INITIAL_FILE_LIMIT);
    setExpandedPaths({});
    setPatchCache({});
  }, [diff?.revision, sessionId]);

  const visibleFiles = useMemo(
    () => diff?.files.slice(0, visibleLimit) ?? [],
    [diff?.files, visibleLimit],
  );

  async function loadPatch(file: DiffFile, expanded = false) {
    if (!diff || !sessionId || file.isBinary) return;
    const key = cacheKey(diff.revision, file.path, expanded);
    if (patchCache[key]?.status === "ready" || patchCache[key]?.status === "loading") return;
    setPatchCache((cache) => ({ ...cache, [key]: { status: "loading" } }));
    try {
      const patch = await api.getDiffFile(
        sessionId,
        file.path,
        expanded ? EXPANDED_PATCH_LIMIT_BYTES : PATCH_LIMIT_BYTES,
      );
      setPatchCache((cache) => ({ ...cache, [key]: { status: "ready", patch } }));
    } catch (error) {
      setPatchCache((cache) => ({
        ...cache,
        [key]: {
          status: "error",
          message: error instanceof Error ? error.message : "Could not load patch.",
        },
      }));
    }
  }

  function patchState(file: DiffFile): PatchState {
    if (!diff) return { status: "idle" };
    const expanded = patchCache[cacheKey(diff.revision, file.path, true)];
    return expanded ?? patchCache[cacheKey(diff.revision, file.path)] ?? { status: "idle" };
  }

  if (loading) return <p className="muted">Reading workspace changes…</p>;
  if (!diff || diff.files.length === 0) return <p className="empty-note">Working tree is clean.</p>;

  return (
    <div className="changes-list">
      <div className="change-totals" aria-label="Change totals">
        <span>+{diff.additions}</span>
        <span>-{diff.deletions}</span>
        <small>{diff.files.length} files</small>
      </div>
      {visibleFiles.map((file) => {
        const isExpanded = expandedPaths[file.path] === true;
        return (
          <details
            key={file.path}
            className="change-file"
            onToggle={(event) => {
              const open = event.currentTarget.open;
              setExpandedPaths((paths) => ({ ...paths, [file.path]: open }));
              if (open) void loadPatch(file);
            }}
          >
            <summary>
              <span>{file.path}</span>
              <small>
                {statusLabel(file)} · +{file.additions} -{file.deletions}
              </small>
            </summary>
            {isExpanded && (
              <PatchBody
                file={file}
                patchState={patchState(file)}
                onLoadFull={() => void loadPatch(file, true)}
              />
            )}
          </details>
        );
      })}
      {visibleLimit < diff.files.length && (
        <button
          type="button"
          className="load-more-files"
          onClick={() => setVisibleLimit((limit) => limit + INITIAL_FILE_LIMIT)}
        >
          Show next {Math.min(INITIAL_FILE_LIMIT, diff.files.length - visibleLimit)} files
        </button>
      )}
      {diff.truncated && <p className="muted">Large diff summary truncated at the safe display limit.</p>}
    </div>
  );
}
