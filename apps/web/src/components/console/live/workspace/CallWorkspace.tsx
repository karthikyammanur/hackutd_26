import { useState } from "react";
import { deliveryKey, type DeletionReceipt as Receipt, type NoticeDelivery } from "@/hooks/useCallSessions";
import type { CallTrace, NodeId } from "@/lib/console/call-model";
import { Card, Tag, Tile } from "../../ui";
import { CallStats } from "../danger/CallStats";
import { DangerTimeline } from "../danger/DangerTimeline";
import { PipelineGraph } from "../pipeline/PipelineGraph";
import { describeCall } from "./copy";
import { CustomerReach } from "./CustomerReach";
import { DeletionReceipt } from "./DeletionReceipt";
import { DemoControls } from "./DemoControls";
import { MarkerList } from "./MarkerList";
import { NodeDetail } from "./NodeDetail";

/** `trace` is the moment under the play head. `extent` is the furthest the call has reached. */
export type WorkspaceView = { trace: CallTrace; extent: CallTrace } & (
  | { mode: "idle" }
  | { mode: "tracing"; sessionId: string; isTest: boolean; mask: string | null }
  | { mode: "erased"; receipt: Receipt }
);

interface DemoPace {
  playing: boolean;
  speed: number;
  onToggle: () => void;
  onSpeed: (speed: number) => void;
  onSkip: () => void;
  onSeek: (t: number) => void;
}

interface WorkspaceProps {
  view: WorkspaceView;
  demo: DemoPace;
  onClose: () => void;
  onReviewSeek: (t: number) => void;
  deliveries: Record<string, NoticeDelivery>;
}

export function CallWorkspace({ view, demo, onClose, onReviewSeek, deliveries }: WorkspaceProps) {
  const [selected, setSelected] = useState<NodeId | null>(null);
  const { trace, extent } = view;
  const tracing = view.mode === "tracing" ? view : null;
  const erased = view.mode === "erased" ? view : null;

  function toggleNode(node: NodeId) {
    setSelected((current) => (current === node ? null : node));
  }

  const summary =
    view.mode === "idle"
      ? { title: "No call open", detail: "Place a test call, or search a full number to trace one call.", hot: false }
      : erased
        ? {
            title: "This call has been erased",
            detail: `Review how it went. It's gone the moment you move on.`,
            hot: false,
          }
        : describeCall(trace);

  const onLiveLines = tracing !== null && (trace.phase === "connecting" || trace.phase === "live");
  const sessionId = tracing?.sessionId ?? erased?.receipt.sessionId ?? "";
  const onSeek = erased ? onReviewSeek : tracing?.isTest ? demo.onSeek : null;

  return (
    <div className="mt-7">
      <div className="grid grid-cols-[minmax(0,1fr)] items-start gap-6 min-[1100px]:grid-cols-[minmax(0,1fr)_340px] min-[1100px]:gap-10">
        <div className="min-w-0">
          <header>
            {view.mode !== "idle" && (
              <div className="flex flex-wrap items-center gap-x-2.5 gap-y-2 font-semibold">
                <Tile icon="call" tint="pink" />
                Session {tracing ? tracing.sessionId : erased?.receipt.sessionId}
                {tracing?.mask && <span className="font-normal text-ink-2">Number ending in {tracing.mask}</span>}
                {tracing?.isTest && <Tag>Test call</Tag>}
                {tracing && (
                  <button type="button" onClick={onClose} className="text-[13px] font-medium text-ink-2 hover:text-ink">
                    Close
                  </button>
                )}
                {tracing?.isTest && (
                  <span className="ml-auto">
                    <DemoControls
                      playing={demo.playing}
                      speed={demo.speed}
                      canSkip={onLiveLines}
                      onToggle={demo.onToggle}
                      onSpeed={demo.onSpeed}
                      onSkip={demo.onSkip}
                    />
                  </span>
                )}
              </div>
            )}
            <div className="mt-3.5 text-[44px] leading-[1.1] font-semibold tracking-[-0.03em]">{summary.title}</div>
            <div className={`mt-1 text-[15.5px] font-medium ${summary.hot ? "text-mag" : "text-ink-2"}`}>{summary.detail}</div>
          </header>

          <section className="mt-6" aria-label="Pipeline">
            <PipelineGraph trace={trace} selected={selected} onSelect={toggleNode} />
          </section>
        </div>

        <aside className="grid min-w-0 gap-4">
          <CustomerReach trace={trace} deliveryAt={(beatT) => deliveries[deliveryKey(sessionId, beatT)]} />
          {erased && <DeletionReceipt receipt={erased.receipt} onClose={onClose} />}
          {selected && <NodeDetail node={selected} trace={trace} onClose={() => setSelected(null)} />}
        </aside>
      </div>

      {view.mode !== "idle" && (
        <>
          <section className="mt-10">
            <Card className="p-6">
              <DangerTimeline trace={trace} extent={extent} onSeek={onSeek} />
              <div className="mt-4">
                <CallStats trace={trace} />
              </div>
            </Card>
          </section>
          <div className="mt-10">
            <MarkerList trace={trace} extent={extent} onSeek={onSeek} />
          </div>
        </>
      )}
    </div>
  );
}
