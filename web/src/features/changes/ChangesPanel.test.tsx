// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { DiffResponse } from "../../api/types";
import { api } from "../../api/client";
import { ChangesPanel } from "./ChangesPanel";

vi.mock("../../api/client", () => ({
  api: {
    getDiffFile: vi.fn(),
  },
}));

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

function diff(files: DiffResponse["files"]): DiffResponse {
  return {
    files,
    additions: files.reduce((total, file) => total + file.additions, 0),
    deletions: files.reduce((total, file) => total + file.deletions, 0),
    truncated: false,
    revision: "rev-1",
  };
}

describe("ChangesPanel", () => {
  it("loads and renders patch text only after a file is expanded", async () => {
    vi.mocked(api.getDiffFile).mockResolvedValue({
      path: "src/a.ts",
      additions: 1,
      deletions: 0,
      status: "modified",
      isBinary: false,
      patch: "diff --git a/src/a.ts b/src/a.ts\n+hello",
      truncated: false,
      revision: "rev-1",
    });

    const { container } = render(
      <ChangesPanel
        sessionId="session-1"
        loading={false}
        diff={diff([{ path: "src/a.ts", additions: 1, deletions: 0, status: "modified", isBinary: false }])}
      />,
    );

    expect(screen.queryByText(/hello/)).not.toBeInTheDocument();
    const details = container.querySelector("details") as HTMLDetailsElement;
    details.open = true;
    fireEvent(details, new Event("toggle", { bubbles: true }));

    expect(api.getDiffFile).toHaveBeenCalledWith("session-1", "src/a.ts", 1_000_000);
    await screen.findByText(/hello/);
  });

  it("renders large change sets in batches", () => {
    const files = Array.from({ length: 105 }, (_, index) => ({
      path: `file-${index}.txt`,
      additions: 1,
      deletions: 0,
      status: "modified",
      isBinary: false,
    }));

    render(<ChangesPanel sessionId="session-1" loading={false} diff={diff(files)} />);

    expect(screen.getByText("file-99.txt")).toBeInTheDocument();
    expect(screen.queryByText("file-104.txt")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Show next 5 files" }));
    expect(screen.getByText("file-104.txt")).toBeInTheDocument();
  });

  it("clears cached patches when the revision changes", async () => {
    vi.mocked(api.getDiffFile).mockResolvedValue({
      path: "src/a.ts",
      additions: 1,
      deletions: 0,
      status: "modified",
      isBinary: false,
      patch: "+first",
      truncated: false,
      revision: "rev-1",
    });

    const first = diff([{ path: "src/a.ts", additions: 1, deletions: 0, status: "modified", isBinary: false }]);
    const { container, rerender } = render(<ChangesPanel sessionId="session-1" loading={false} diff={first} />);
    const details = container.querySelector("details") as HTMLDetailsElement;
    details.open = true;
    fireEvent(details, new Event("toggle", { bubbles: true }));
    await screen.findByText(/\+first/);

    rerender(
      <ChangesPanel
        sessionId="session-1"
        loading={false}
        diff={{ ...first, revision: "rev-2" }}
      />,
    );

    await waitFor(() => expect(screen.queryByText(/\+first/)).not.toBeInTheDocument());
  });
});
