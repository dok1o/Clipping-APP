// usePolling: interval refetch with pause when the tab is hidden (no wasted requests).
import { useCallback, useEffect, useRef } from "react";

export function usePolling(fn: () => void, intervalMs: number, enabled = true) {
  const fnRef = useRef(fn);
  fnRef.current = fn;

  const run = useCallback(() => {
    if (document.visibilityState === "visible") {
      fnRef.current();
    }
  }, []);

  useEffect(() => {
    if (!enabled) return;
    run(); // immediate first fetch
    const timer = window.setInterval(run, intervalMs);
    document.addEventListener("visibilitychange", run);
    return () => {
      window.clearInterval(timer);
      document.removeEventListener("visibilitychange", run);
    };
  }, [run, intervalMs, enabled]);
}
