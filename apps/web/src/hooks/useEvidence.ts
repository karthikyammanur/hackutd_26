import { useEffect, useState } from "react";
import { evidenceApi } from "@/lib/evidence/api";

interface Loaded<T> {
  path: string;
  data: T | null;
  error: string | null;
}

/** Fetches a path. `data` keeps the last good result during a reload, so charts animate rather than blink. */
export function useEvidence<T>(path: string | null, parse: (value: unknown) => T) {
  const [state, setState] = useState<Loaded<T> | null>(null);

  useEffect(() => {
    if (path === null) return;
    const controller = new AbortController();
    evidenceApi(path, controller.signal).then(
      (value) => setState({ path, data: parse(value), error: null }),
      (error: unknown) => {
        if (!controller.signal.aborted) setState({ path, data: null, error: error instanceof Error ? error.message : "Request failed" });
      },
    );
    return () => controller.abort();
  }, [path, parse]);

  const current = state?.path === path ? state : null;
  return { data: state?.data ?? null, error: current?.error ?? null, loading: path !== null && !current, settled: current?.data ?? null };
}
