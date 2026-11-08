import { useEffect, useRef } from "react";

/** Moves focus into a full-screen state and puts it back when the state closes. */
export function useTakeoverFocus<T extends HTMLElement>() {
  const headingRef = useRef<T>(null);
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    headingRef.current?.focus();
    return () => previous?.focus?.();
  }, []);
  return headingRef;
}
