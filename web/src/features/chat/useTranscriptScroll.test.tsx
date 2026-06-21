// @vitest-environment jsdom

import { act, cleanup, fireEvent, render } from "@testing-library/react";
import { RefObject, useEffect, useRef } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useTranscriptScroll } from "./useTranscriptScroll";

type Controls = ReturnType<typeof useTranscriptScroll<HTMLDivElement>>;

function setScrollMetrics(element: HTMLDivElement, values: { scrollHeight: number; clientHeight: number; scrollTop: number }) {
  Object.defineProperty(element, "scrollHeight", { configurable: true, value: values.scrollHeight });
  Object.defineProperty(element, "clientHeight", { configurable: true, value: values.clientHeight });
  element.scrollTop = values.scrollTop;
}

function Harness({
  version,
  onReady,
}: {
  version: string;
  onReady: (controls: Controls, ref: RefObject<HTMLDivElement | null>) => void;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const controls = useTranscriptScroll(ref, version);
  useEffect(() => onReady(controls, ref), [controls, onReady]);
  return <div data-testid="transcript" ref={ref} />;
}

describe("useTranscriptScroll", () => {
  beforeEach(() => {
    vi.stubGlobal("requestAnimationFrame", (callback: FrameRequestCallback) => {
      callback(0);
      return 0;
    });
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it("does not pull the reader back to the bottom after they scroll up", () => {
    let controls: Controls | undefined;
    const onReady = vi.fn((next: Controls) => { controls = next; });
    const { getByTestId, rerender } = render(<Harness version="1" onReady={onReady} />);
    const transcript = getByTestId("transcript") as HTMLDivElement;
    const scrollTo = vi.fn((options?: ScrollToOptions | number) => {
      if (typeof options === "object") transcript.scrollTop = Number(options.top);
    });
    Object.defineProperty(transcript, "scrollTo", { configurable: true, value: scrollTo });

    setScrollMetrics(transcript, { scrollHeight: 1000, clientHeight: 100, scrollTop: 300 });
    fireEvent.scroll(transcript);
    rerender(<Harness version="2" onReady={onReady} />);

    expect(scrollTo).not.toHaveBeenCalled();
    expect(controls?.isFollowing).toBe(false);
    expect(controls?.unreadCount).toBe(1);
  });

  it("uses an immediate container scroll while following new content", () => {
    const onReady = vi.fn();
    const { getByTestId, rerender } = render(<Harness version="1" onReady={onReady} />);
    const transcript = getByTestId("transcript") as HTMLDivElement;
    const scrollTo = vi.fn();
    Object.defineProperty(transcript, "scrollTo", { configurable: true, value: scrollTo });
    setScrollMetrics(transcript, { scrollHeight: 1000, clientHeight: 100, scrollTop: 900 });

    rerender(<Harness version="2" onReady={onReady} />);

    expect(scrollTo).toHaveBeenCalledWith({ top: 1000, behavior: "auto" });
  });

  it("restores following when the user jumps to the latest update", () => {
    let controls: Controls | undefined;
    const onReady = vi.fn((next: Controls) => { controls = next; });
    const { getByTestId, rerender } = render(<Harness version="1" onReady={onReady} />);
    const transcript = getByTestId("transcript") as HTMLDivElement;
    Object.defineProperty(transcript, "scrollTo", {
      configurable: true,
      value: vi.fn((options?: ScrollToOptions | number) => {
        if (typeof options === "object") transcript.scrollTop = Number(options.top);
      }),
    });

    setScrollMetrics(transcript, { scrollHeight: 1000, clientHeight: 100, scrollTop: 200 });
    fireEvent.scroll(transcript);
    rerender(<Harness version="2" onReady={onReady} />);

    act(() => controls?.followLatest("auto"));

    expect(transcript.scrollTo).toHaveBeenCalledWith({ top: 1000, behavior: "auto" });
    expect(controls?.isFollowing).toBe(true);
  });
});
