// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { PermissionCard } from "./PermissionCard";

describe("PermissionCard", () => {
  it("disables actions while a resolution is pending", () => {
    const onResolve = vi.fn(() => new Promise<void>(() => undefined));
    render(
      <PermissionCard
        request={{ requestId: "perm-1", kind: "edit", summary: "Edit file", details: [], scope: "src/a.ts", createdAt: 0 }}
        onResolve={onResolve}
      />,
    );
    const allow = screen.getByRole("button", { name: "Allow once" });
    fireEvent.click(allow);
    fireEvent.click(allow);
    expect(onResolve).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("button", { name: "Resolving…" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Deny" })).toBeDisabled();
  });
});
