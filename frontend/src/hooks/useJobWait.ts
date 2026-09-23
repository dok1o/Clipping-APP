// useJobWait: poll a Job until it reaches a terminal status (succeeded/failed/cancelled).
import { useCallback, useEffect, useRef, useState } from "react";
import { api, type Job } from "../api";

export function useJobWait() {
  const [job, setJob] = useState<Job | null>(null);
  const [error, setError] = useState<unknown>(null);
  const timer = useRef<number | null>(null);

  const stop = useCallback(() => {
    if (timer.current !== null) {
      window.clearInterval(timer.current);
      timer.current = null;
    }
  }, []);

  const wait = useCallback(
    (jobId: string) => {
      stop();
      setJob(null);
      setError(null);
      const poll = () => {
        api
          .getJob(jobId)
          .then((current) => {
            setJob(current);
            if (["succeeded", "failed", "cancelled"].includes(current.status)) {
              stop();
            }
          })
          .catch((e) => {
            setError(e);
            stop();
          });
      };
      poll();
      timer.current = window.setInterval(poll, 1500);
    },
    [stop],
  );

  useEffect(() => stop, [stop]);

  const running = job !== null && !["succeeded", "failed", "cancelled"].includes(job.status);
  return { job, error, running, wait, reset: () => setJob(null) };
}
