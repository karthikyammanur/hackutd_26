import { useCallback, useEffect, useMemo, useRef, useState, type RefObject } from "react";
import { traceAt, type Scenario } from "@/lib/console/call-model";
import { SCENARIOS } from "@/lib/console/scenarios";
import { FINAL_FRAME, frameAt, REPLAY_DURATION_S, type ReplayFrame } from "@/lib/home/replay";

/** Call seconds per real second in the hero. */
const CALL_RATE = 10;
/** Call seconds to rest on a finished call before the next one. */
const END_HOLD = 14;
const HERO_TICK_MS = 80;
const REPLAY_TICK_MS = 120;
const REPLAY_START_DELAY_MS = 350;

const prefersReducedMotion = () => window.matchMedia("(prefers-reduced-motion: reduce)").matches;

/** The moment a call is most dangerous, shown as a still when motion is reduced. */
function peakBeat(scenario: Scenario): number {
  const top = Math.max(...scenario.beats.map((beat) => beat.danger));
  return scenario.beats.find((beat) => beat.danger === top)?.t ?? 0;
}

export function useInView<T extends Element>(): [RefObject<T | null>, boolean] {
  const ref = useRef<T>(null);
  const [inView, setInView] = useState(false);

  useEffect(() => {
    const element = ref.current;
    if (!element) return;
    const observer = new IntersectionObserver(([entry]) => setInView(entry.isIntersecting), { threshold: 0.2 });
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  return [ref, inView];
}

/** Plays the scripted calls in turn. Only the moment changes the trace, so the figure re-renders on beats. */
export function useHeroCall(visible: boolean) {
  const [state, setState] = useState(() => {
    const reduced = prefersReducedMotion();
    return { index: 0, t: reduced ? peakBeat(SCENARIOS[0]) : 0, playing: !reduced };
  });

  useEffect(() => {
    if (!visible || !state.playing) return;
    let last = performance.now();
    const timer = window.setInterval(() => {
      const now = performance.now();
      const delta = ((now - last) / 1000) * CALL_RATE;
      last = now;
      setState((current) => {
        const t = current.t + delta;
        return t < SCENARIOS[current.index].duration + END_HOLD
          ? { ...current, t }
          : { ...current, index: (current.index + 1) % SCENARIOS.length, t: 0 };
      });
    }, HERO_TICK_MS);
    return () => window.clearInterval(timer);
  }, [visible, state.playing]);

  const select = useCallback((index: number) => {
    const reduced = prefersReducedMotion();
    setState({ index, t: reduced ? peakBeat(SCENARIOS[index]) : 0, playing: !reduced });
  }, []);

  const toggle = useCallback(() => setState((current) => ({ ...current, playing: !current.playing })), []);

  const scenario = SCENARIOS[state.index];
  const beatT = scenario.beats.filter((beat) => beat.t <= state.t).at(-1)?.t ?? 0;
  const trace = useMemo(() => traceAt(scenario, beatT), [scenario, beatT]);

  return {
    index: state.index,
    playing: state.playing,
    progress: Math.min(1, state.t / scenario.duration),
    trace,
    select,
    toggle,
  };
}

/** Rests on the finished run, plays once when first seen, and replays on request. */
export function useRunReplay(visible: boolean) {
  const [frame, setFrame] = useState<ReplayFrame>(FINAL_FRAME);
  const [playId, setPlayId] = useState(0);
  const [playing, setPlaying] = useState(false);
  const timer = useRef(0);
  const played = useRef(false);

  const play = useCallback(() => {
    played.current = true;
    window.clearInterval(timer.current);
    const startedAt = performance.now();
    setFrame(frameAt(0));
    setPlayId((id) => id + 1);
    setPlaying(true);
    timer.current = window.setInterval(() => {
      const elapsed = (performance.now() - startedAt) / 1000;
      setFrame(frameAt(elapsed));
      if (elapsed >= REPLAY_DURATION_S) {
        window.clearInterval(timer.current);
        setPlaying(false);
      }
    }, REPLAY_TICK_MS);
  }, []);

  useEffect(() => () => window.clearInterval(timer.current), []);

  useEffect(() => {
    if (!visible || played.current || prefersReducedMotion()) return;
    const start = window.setTimeout(play, REPLAY_START_DELAY_MS);
    return () => window.clearTimeout(start);
  }, [visible, play]);

  return { frame, playId, playing, play };
}
