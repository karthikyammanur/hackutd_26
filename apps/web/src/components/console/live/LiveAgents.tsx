import { useCallSessions } from "@/hooks/useCallSessions";
import { traceAt } from "@/lib/console/call-model";
import { IDLE_SCENARIO } from "@/lib/console/scenarios";
import { CallWorkspace, type WorkspaceView } from "./workspace/CallWorkspace";
import { CommandBar } from "./workspace/CommandBar";
import { SessionRoster } from "./workspace/SessionRoster";

const IDLE_TRACE = traceAt(IDLE_SCENARIO, 0);

export function LiveAgents() {
  const calls = useCallSessions();
  const open = calls.sessions.find((session) => session.id === calls.openId) ?? null;

  let view: WorkspaceView;
  let viewKey: string;
  if (open) {
    view = { mode: "tracing", trace: traceAt(open.scenario, open.t), extent: traceAt(open.scenario, open.furthest), sessionId: open.id, isTest: open.kind === "test", mask: calls.openMask };
    viewKey = `call-${open.id}`;
  } else if (calls.receipt) {
    view = { mode: "erased", receipt: calls.receipt, trace: traceAt(calls.receipt.scenario, calls.receipt.t), extent: traceAt(calls.receipt.scenario, calls.receipt.heldSeconds) };
    viewKey = `call-${calls.receipt.sessionId}`;
  } else {
    view = { mode: "idle", trace: IDLE_TRACE, extent: IDLE_TRACE };
    viewKey = "idle";
  }

  const openId = open?.id ?? null;

  return (
    <div>
      <CommandBar count={calls.sessions.length} tlife={calls.tlife} onSearch={calls.openByNumber} onPlace={calls.placeTestCall} />
      <SessionRoster sessions={calls.sessions} openId={calls.openId} erased={calls.receipt} onOpen={calls.openTestSession} />
      <CallWorkspace
        key={viewKey}
        view={view}
        onClose={calls.closeView}
        onReviewSeek={calls.seekReview}
        deliveries={calls.deliveries}
        demo={{
          playing: calls.playing,
          speed: calls.speed,
          onToggle: calls.togglePlaying,
          onSpeed: calls.setSpeed,
          onSkip: () => {
            if (openId) calls.skipToAfterCall(openId);
          },
          onSeek: (t) => {
            if (openId) calls.seek(openId, t);
          },
        }}
      />
    </div>
  );
}
