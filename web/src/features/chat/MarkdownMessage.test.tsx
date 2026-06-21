// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { MarkdownMessage } from "./MarkdownMessage";

afterEach(cleanup);

describe("MarkdownMessage", () => {
  it("renders links safely and leaves inline HTML as text", () => {
    render(<MarkdownMessage content={"Read [docs](https://example.com).\n<script>alert(1)</script>"} />);

    const link = screen.getByRole("link", { name: "docs" });
    expect(link).toHaveAttribute("rel", "noreferrer noopener");
    expect(link).toHaveAttribute("target", "_blank");
    expect(document.querySelector("script")).toBeNull();
    expect(document.body.textContent).toContain("<script>alert(1)</script>");
  });

  it("renders fenced code blocks with language labels", () => {
    render(<MarkdownMessage content={"```ts\nconst value = 1;\n```"} />);

    expect(screen.getByText("ts")).toBeInTheDocument();
    expect(screen.getByText("const value = 1;")).toBeInTheDocument();
  });
});
