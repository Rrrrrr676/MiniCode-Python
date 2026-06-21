import { RefObject, useCallback, useEffect, useRef, useState } from "react";

// A small bottom tolerance avoids disabling follow mode on sub-pixel layout shifts.
const FOLLOW_THRESHOLD_PX = 80;

function prefersReducedMotion() {
  return window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false;
}

function distanceFromBottom(element: HTMLElement) {
  return element.scrollHeight - element.scrollTop - element.clientHeight;
}

export function useTranscriptScroll<T extends HTMLElement>(
  ref: RefObject<T | null>,
  contentVersion: unknown,
) {
  const [isFollowing, setIsFollowing] = useState(true);
  const [unreadCount, setUnreadCount] = useState(0);
  const isFollowingRef = useRef(true);
  const isSettlingRef = useRef(false);
  const lastScrollTopRef = useRef(0);
  const seenVersionRef = useRef(contentVersion);

  const scrollToBottom = useCallback((behavior: ScrollBehavior = "auto") => {
    const element = ref.current;
    if (!element) return;
    element.scrollTo({
      top: element.scrollHeight,
      behavior: prefersReducedMotion() ? "auto" : behavior,
    });
  }, [ref]);

  const followLatest = useCallback((behavior: ScrollBehavior = "smooth") => {
    isFollowingRef.current = true;
    setIsFollowing(true);
    setUnreadCount(0);
    requestAnimationFrame(() => scrollToBottom(behavior));
  }, [scrollToBottom]);

  useEffect(() => {
    const element = ref.current;
    if (!element) return undefined;
    const scrollElement = element;
    lastScrollTopRef.current = scrollElement.scrollTop;

    function onScroll() {
      const nextFollowing = distanceFromBottom(scrollElement) <= FOLLOW_THRESHOLD_PX;
      const movedUp = scrollElement.scrollTop < lastScrollTopRef.current - 2;
      lastScrollTopRef.current = scrollElement.scrollTop;
      if (isSettlingRef.current && !movedUp) {
        if (nextFollowing) setUnreadCount(0);
        return;
      }
      if (movedUp) isSettlingRef.current = false;
      isFollowingRef.current = nextFollowing;
      setIsFollowing(nextFollowing);
      if (nextFollowing) setUnreadCount(0);
    }

    scrollElement.addEventListener("scroll", onScroll, { passive: true });
    onScroll();
    return () => scrollElement.removeEventListener("scroll", onScroll);
  }, [ref]);

  useEffect(() => {
    if (Object.is(seenVersionRef.current, contentVersion)) return;
    seenVersionRef.current = contentVersion;

    if (isFollowingRef.current) {
      // Streaming updates use an immediate container scroll so intermediate
      // smooth-scroll events cannot be mistaken for the user moving upward.
      // A few frames also absorb content-visibility's deferred height measurement.
      let frame = 0;
      let attempts = 0;
      let previousHeight = -1;
      let stableFrames = 0;
      isSettlingRef.current = true;
      const settleAtBottom = () => {
        if (!isFollowingRef.current) return;
        scrollToBottom("auto");
        const element = ref.current;
        attempts += 1;
        if (element && element.scrollHeight === previousHeight && distanceFromBottom(element) <= FOLLOW_THRESHOLD_PX) {
          stableFrames += 1;
        } else {
          stableFrames = 0;
        }
        previousHeight = element?.scrollHeight ?? previousHeight;
        if (stableFrames < 2 && attempts < 20) {
          frame = requestAnimationFrame(settleAtBottom);
        } else {
          isSettlingRef.current = false;
        }
      };
      frame = requestAnimationFrame(settleAtBottom);
      return () => {
        cancelAnimationFrame(frame);
        isSettlingRef.current = false;
      };
    }

    setUnreadCount((count) => count + 1);
    return undefined;
  }, [contentVersion, scrollToBottom]);

  return {
    isFollowing,
    unreadCount,
    followLatest,
  };
}
