import { useCallback, useEffect, useRef, useState } from "react";
import { api, type RescoreRequest } from "@/lib/simulate/api";
import {
  activeSteps,
  mergeDecisions,
  parseLessons,
  parseLive,
  parseMarkers,
  parseMethods,
  parseModels,
  TERMINAL,
  type Decision,
  type Lessons,
  type LiveState,
  type Marker,
  type MethodRow,
  type ModelRow,
} from "@/lib/simulate/parse";

const POLL_MS = 1000;
const RESCORE_DEBOUNCE_MS = 250;

export interface Rescored {
  byMethod: MethodRow[] | null;
  byModel: ModelRow[] | null;
}

interface Monitor {
  live: LiveState | null;
  seen: Decision[];
  active: string[];
  error: string | null;
}

const message = (error: unknown) => (error instanceof Error ? error.message : "Request failed");

/** Follows one run. Mount with `key={runId}` so a new run starts from empty state. */
export function useRunMonitor(runId: string | null, onFinished: () => void) {
  const [monitor, setMonitor] = useState<Monitor>({ live: null, seen: [], active: [], error: null });
  const [markers, setMarkers] = useState<Marker[] | null>(null);
  const [lessons, setLessons] = useState<Lessons | null>(null);
  const [rescored, setRescored] = useState<Rescored | null>(null);
  const [rescoreError, setRescoreError] = useState<string | null>(null);
  const finished = useRef(onFinished);
  const rescoreTimer = useRef<ReturnType<typeof setTimeout>>(undefined);
  const rescoreAbort = useRef<AbortController>(undefined);

  useEffect(() => {
    finished.current = onFinished;
  }, [onFinished]);

  useEffect(() => {
    const controller = new AbortController();
    const { signal } = controller;

    async function loadResults() {
      const [markerResult, lessonResult] = await Promise.allSettled([
        api(`/runs/${runId}/markers.json`, { signal }),
        api("/lessons", { signal }),
      ]);
      if (signal.aborted) return;
      setMarkers(markerResult.status === "fulfilled" ? parseMarkers(markerResult.value) : []);
      setLessons(lessonResult.status === "fulfilled" ? parseLessons(lessonResult.value) : null);
    }

    if (!runId) {
      api("/lessons", { signal }).then(
        (value) => setLessons(parseLessons(value)),
        () => undefined,
      );
      return () => controller.abort();
    }

    let timer: ReturnType<typeof setTimeout>;
    async function poll() {
      let done = false;
      try {
        const next = parseLive(await api(`/runs/${runId}/live`, { signal }));
        setMonitor((current) => ({
          live: next,
          seen: mergeDecisions(current.seen, next.recent),
          active: activeSteps(current.live, next),
          error: null,
        }));
        done = next.status !== null && TERMINAL.has(next.status);
      } catch (error) {
        if (signal.aborted) return;
        setMonitor((current) => ({ ...current, active: [], error: message(error) }));
      }
      if (signal.aborted) return;
      if (done) {
        await loadResults();
        if (!signal.aborted) finished.current();
      } else {
        timer = setTimeout(poll, POLL_MS);
      }
    }
    poll();

    return () => {
      controller.abort();
      clearTimeout(timer);
    };
  }, [runId]);

  useEffect(
    () => () => {
      clearTimeout(rescoreTimer.current);
      rescoreAbort.current?.abort();
    },
    [],
  );

  const rescore = useCallback(
    (request: RescoreRequest) => {
      clearTimeout(rescoreTimer.current);
      rescoreTimer.current = setTimeout(async () => {
        rescoreAbort.current?.abort();
        const controller = new AbortController();
        rescoreAbort.current = controller;
        try {
          const raw = (await api(`/runs/${runId}/rescore`, { method: "POST", body: request, signal: controller.signal })) as {
            by_method?: unknown;
            by_model?: unknown;
          } | null;
          setRescored({ byMethod: parseMethods(raw?.by_method), byModel: parseModels(raw?.by_model) });
          setRescoreError(null);
        } catch (error) {
          if (!controller.signal.aborted) setRescoreError(message(error));
        }
      }, RESCORE_DEBOUNCE_MS);
    },
    [runId],
  );

  const resetRescore = useCallback(() => {
    clearTimeout(rescoreTimer.current);
    rescoreAbort.current?.abort();
    setRescored(null);
    setRescoreError(null);
  }, []);

  return { ...monitor, markers, lessons, rescored, rescoreError, rescore, resetRescore };
}
