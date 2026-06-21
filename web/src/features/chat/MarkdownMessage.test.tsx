// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MarkdownMessage } from "./MarkdownMessage";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

beforeEach(() => {
  vi.stubGlobal("requestAnimationFrame", (callback: FrameRequestCallback) => {
    callback(0);
    return 1;
  });
  vi.stubGlobal("cancelAnimationFrame", vi.fn());
});

describe("MarkdownMessage", () => {
  it("renders GFM semantics while keeping raw HTML and unsafe links inert", () => {
    render(<MarkdownMessage content={[
      "# Title",
      "## Section",
      "### Detail",
      "Read **bold**, *italic*, ~~old~~, and `inline`.",
      "- item",
      "- [x] done",
      "> quote",
      "| A | B |\n| - | - |\n| 1 | 2 |",
      "---",
      "[docs](https://example.com) [unsafe](javascript:alert(1))",
      "<script>alert('never')</script>",
    ].join("\n\n")} />);

    expect(screen.getByRole("heading", { level: 1, name: "Title" })).toBeInTheDocument();
    expect(screen.getByText("bold").tagName).toBe("STRONG");
    expect(screen.getByText("inline").tagName).toBe("CODE");
    expect(screen.getByRole("table")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "docs" })).toHaveAttribute("rel", "noreferrer noopener");
    expect(screen.getByRole("link", { name: "docs" })).toHaveAttribute("target", "_blank");
    expect(screen.getByText("unsafe").closest("a")).toHaveAttribute("href", "");
    expect(document.querySelector("script")).toBeNull();
    expect(document.body.textContent).toContain("<script>alert('never')</script>");
  });

  it("keeps an unclosed streaming fence safe and visible", () => {
    render(<MarkdownMessage content={"Starting\n\n```ts\nconst value = 1;"} />);

    expect(screen.getByText("ts")).toBeInTheDocument();
    expect(screen.getByText("const value = 1;")).toBeInTheDocument();
  });

  it("collapses long code, hides a plain-text language badge, and copies exact content", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", { configurable: true, value: { writeText } });
    const code = Array.from({ length: 30 }, (_, index) => `line ${index + 1}`).join("\n");
    render(<MarkdownMessage content={`\`\`\`\n${code}\n\`\`\``} />);

    const details = screen.getByText("30 lines").closest("details");
    expect(details).not.toHaveAttribute("open");
    expect(screen.queryByText("text")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Copy code" }));
    expect(writeText).toHaveBeenCalledWith(code);
  });

  it("creates unique stable heading ids and returns focus when the outline closes", () => {
    render(<MarkdownMessage idPrefix="answer-1" content={"## Same\n\n### Same\n\n## Three\n\n### Four"} />);

    const headings = screen.getAllByRole("heading");
    expect(headings.map((heading) => heading.id)).toEqual([
      "md-answer-1-same",
      "md-answer-1-same-2",
      "md-answer-1-three",
      "md-answer-1-four",
    ]);

    const trigger = screen.getByRole("button", { name: /Contents/ });
    fireEvent.click(trigger);
    expect(screen.getByRole("dialog", { name: "Answer contents" })).toBeInTheDocument();
    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByRole("dialog", { name: "Answer contents" })).not.toBeInTheDocument();
    expect(trigger).toHaveFocus();
  });

  it("jumps within the transcript container without scrolling the window", () => {
    const { container } = render(
      <div className="transcript">
        <MarkdownMessage idPrefix="answer-2" content={"## One\n\n### Two\n\n## Three\n\n### Four"} />
      </div>,
    );
    const transcript = container.querySelector<HTMLElement>(".transcript")!;
    const target = screen.getByRole("heading", { name: "Three" });
    const scrollTo = vi.fn();
    Object.defineProperty(transcript, "scrollTop", { configurable: true, value: 200, writable: true });
    Object.defineProperty(transcript, "scrollTo", { configurable: true, value: scrollTo });
    transcript.getBoundingClientRect = () => ({ top: 50, bottom: 650, left: 0, right: 800, width: 800, height: 600, x: 0, y: 50, toJSON: () => ({}) });
    target.getBoundingClientRect = () => ({ top: 350, bottom: 380, left: 0, right: 700, width: 700, height: 30, x: 0, y: 350, toJSON: () => ({}) });

    fireEvent.click(screen.getByRole("button", { name: /Contents/ }));
    fireEvent.click(screen.getByRole("button", { name: "Three" }));

    expect(scrollTo).toHaveBeenCalledWith({ top: 480, behavior: "smooth" });
    expect(window.scrollY).toBe(0);
  });
});
