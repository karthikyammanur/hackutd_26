import {
  createContext,
  useContext,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
  type MouseEvent,
  type ReactNode,
} from "react";

interface TooltipContent {
  primary: string;
  secondary?: string;
}

interface TooltipState extends TooltipContent {
  x: number;
  y: number;
}

interface TooltipApi {
  show: (event: MouseEvent, content: TooltipContent) => void;
  hide: () => void;
}

const TooltipContext = createContext<TooltipApi | null>(null);

export function useTooltip(): TooltipApi {
  const api = useContext(TooltipContext);
  if (!api) throw new Error("useTooltip must be used inside TooltipProvider");
  return api;
}

/** One shared cursor tooltip for every chart. */
export function TooltipProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<TooltipState | null>(null);
  const element = useRef<HTMLDivElement>(null);

  // Position after render, once the tooltip's real size is known.
  useLayoutEffect(() => {
    if (!state || !element.current) return;
    const { width, height } = element.current.getBoundingClientRect();
    element.current.style.left = `${Math.min(window.innerWidth - width - 12, state.x + 14)}px`;
    element.current.style.top = `${Math.max(8, state.y - height - 12)}px`;
  }, [state]);

  const api = useMemo<TooltipApi>(
    () => ({
      show: (event, content) => setState({ x: event.clientX, y: event.clientY, ...content }),
      hide: () => setState(null),
    }),
    [],
  );

  return (
    <TooltipContext.Provider value={api}>
      {children}
      {state && (
        <div
          ref={element}
          role="tooltip"
          className="pointer-events-none fixed z-20 max-w-[260px] rounded-md bg-black px-2.5 py-[7px] text-[13px] leading-[1.35] text-white"
        >
          {state.primary}
          {state.secondary && <span className="block text-[#C9C9C9]">{state.secondary}</span>}
        </div>
      )}
    </TooltipContext.Provider>
  );
}
