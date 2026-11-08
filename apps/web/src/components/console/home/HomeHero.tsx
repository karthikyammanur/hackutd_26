import { useCallback, useMemo, useState } from "react";
import { useHeroCall, useInView } from "@/hooks/useHomeMotion";
import { PIPELINE_NODES, type CallTrace, type NodeId } from "@/lib/console/call-model";
import { SCENARIOS } from "@/lib/console/scenarios";
import { PauseIcon, PlayIcon } from "../icons";
import { PipelineGraph } from "../live/pipeline/PipelineGraph";
import { Tag } from "../ui";

const SHORT_NAMES: Record<string, string> = {
  "code-request": "Fake bank asks for a code",
  "ordinary-call": "Ordinary call",
  "friendly-stranger": "Friendly stranger",
  "id-disclosed": "ID number shared",
};

const ALERT_ACTIONS = ["Call my bank", "Ask my trusted contact", "Continue"];

function CustomerView({ trace }: { trace: CallTrace }) {
  const notice = trace.notices.at(-1);
  const urgent = notice?.channel === "urgent-callback";
  const alert = urgent || (notice?.timing === "during-call" && trace.tier === 3);

  if (!notice) {
    return (
      <div key="quiet" className="animate-rise rounded-[20px] bg-card p-5 shadow-soft">
        <p className="text-[19px] leading-[1.25] font-semibold tracking-[-0.018em]">Nothing on the customer's screen</p>
        <p className="mt-1.5 text-[14.5px] text-ink-2">Safe Signal stays quiet unless something looks wrong.</p>
      </div>
    );
  }

  return (
    <div
      key={notice.title}
      className={`animate-rise rounded-[20px] p-5 ${alert ? "bg-alert text-white shadow-[0_14px_32px_rgba(226,0,116,0.26)]" : "bg-card shadow-soft"}`}
    >
      <p className="text-[19px] leading-[1.25] font-semibold tracking-[-0.018em]">{notice.title}</p>
      <p className={`mt-1.5 text-[14.5px] ${alert ? "text-[#FFE7F3]" : "text-ink-2"}`}>{notice.body}</p>
      {alert && !urgent && (
        <ul className="mt-3.5 flex flex-wrap gap-2 text-[13px] font-semibold" aria-label="Choices on the alert">
          {ALERT_ACTIONS.map((action, index) => (
            <li key={action} className={`rounded-full px-3 py-1.5 ${index === 0 ? "bg-white text-ink" : "border border-white/70"}`}>
              {action}
            </li>
          ))}
        </ul>
      )}
      {urgent && <p className="mt-3 text-[13px] text-[#FFD3E9]">Safe Signal phones the customer, never emergency services.</p>}
      {!alert && <p className="mt-3 text-[13px] text-ink-3">{notice.timing === "after-call" ? "In T-Life, after the call" : "In T-Life, during the call"}</p>}
    </div>
  );
}

export function HomeHero({ active }: { active: boolean }) {
  const [figureRef, inView] = useInView<HTMLDivElement>();
  const call = useHeroCall(active && inView);
  const [selected, setSelected] = useState<NodeId | null>(null);
  const { trace } = call;

  const toggleNode = useCallback((node: NodeId) => setSelected((current) => (current === node ? null : node)), []);
  const graph = useMemo(() => <PipelineGraph trace={trace} selected={selected} onSelect={toggleNode} />, [trace, selected, toggleNode]);
  const node = PIPELINE_NODES.find((item) => item.id === selected);

  return (
    <section className="grid grid-cols-[minmax(0,1fr)] items-start gap-x-12 gap-y-8 min-[1180px]:grid-cols-[minmax(320px,392px)_minmax(0,1fr)]">
      <div className="pt-2 min-[1180px]:pt-7">
        <h2 className="text-[clamp(40px,4.3vw,58px)] leading-[1.03] font-semibold tracking-[-0.038em] text-balance">Protection that stays on the line.</h2>
        <p className="mt-5 max-w-[56ch] text-[17px] leading-[1.45] text-ink-2">
          T-Mobile labels known scam calls before they ring. Safe Signal covers the calls with no label, including the ones customers dial, and warns them while there's still time to act. It never hangs up for them.
        </p>
        <div className="mt-6 flex flex-wrap gap-2.5">
          <a href="#live" className="grid h-11 place-items-center rounded-full bg-mag px-5 text-[15px] font-semibold text-white hover:bg-mag-deep">
            Watch live agents
          </a>
          <a href="#simulate" className="grid h-11 place-items-center rounded-full border border-line bg-white px-5 text-[15px] font-medium hover:bg-sunk">
            Run a simulation
          </a>
        </div>
        <div className="mt-9 max-w-[440px]">
          <p className="mb-2 text-[13px] font-medium text-ink-2">What the customer sees</p>
          <div className="min-[1180px]:min-h-[186px]">
            <CustomerView trace={trace} />
          </div>
        </div>
      </div>

      <div className="min-w-0">
        <div ref={figureRef} className="overflow-x-auto">
          <div className="min-w-[640px]">{graph}</div>
        </div>

        <div className="mt-3 flex min-h-11 flex-wrap items-center gap-x-3 gap-y-1.5">
          {node ? (
            <p className="min-w-0 flex-1 basis-60">
              <b className="font-semibold">{node.name}.</b> <span className="text-ink-2">{node.role}.</span>
            </p>
          ) : (
            <p className="min-w-0 flex-1 basis-60 text-ink-2">
              <b className="font-semibold text-ink">{trace.now.marker}.</b> {trace.now.detail}. Select any part to see what it does.
            </p>
          )}
          <Tag>Simulated call</Tag>
        </div>

        <div className="mt-3 flex items-stretch gap-2">
          <button
            type="button"
            onClick={call.toggle}
            aria-label={call.playing ? "Pause the demo call" : "Play the demo call"}
            className="grid h-11 w-11 flex-none place-items-center self-start rounded-xl border border-line bg-white hover:bg-sunk sm:h-auto sm:self-stretch"
          >
            {call.playing ? <PauseIcon /> : <PlayIcon />}
          </button>
          <div role="group" aria-label="Demo calls" className="grid min-w-0 flex-1 grid-cols-2 gap-2 sm:grid-cols-4">
            {SCENARIOS.map((scenario, index) => {
              const current = index === call.index;
              return (
                <button
                  key={scenario.id}
                  type="button"
                  aria-pressed={current}
                  onClick={() => call.select(index)}
                  className={`relative overflow-hidden rounded-xl px-3 py-2.5 text-left text-[13px] leading-[1.2] font-medium ${current ? "bg-card text-ink shadow-soft" : "text-ink-2 hover:bg-sunk"}`}
                >
                  {current && <i aria-hidden="true" className="absolute top-0 left-0 h-[3px] bg-mag" style={{ width: `${call.progress * 100}%` }} />}
                  {SHORT_NAMES[scenario.id] ?? scenario.name}
                </button>
              );
            })}
          </div>
        </div>
      </div>
    </section>
  );
}
