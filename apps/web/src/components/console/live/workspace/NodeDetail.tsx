import { PIPELINE_NODES, type ActivityState, type CallTrace, type NodeId, type NodeKind } from "@/lib/console/call-model";
import { formatClock } from "@/lib/console/format";
import { Card, Tag } from "../../ui";

const STATE_LABEL: Record<ActivityState, string> = { idle: "Waiting", active: "Working now", done: "Finished" };

const KIND_LABEL: Record<NodeKind, string> = {
  simulated: "Simulated for the demo",
  agent: "Agent",
  model: "Model",
  device: "Phone line",
  memory: "Temporary memory",
  output: "Reaches the customer",
  knowledge: "Knowledge",
};

export function NodeDetail({ node, trace, onClose }: { node: NodeId; trace: CallTrace; onClose: () => void }) {
  const info = PIPELINE_NODES.find((candidate) => candidate.id === node);
  if (!info) return null;
  const { state, status } = trace.nodes[node];
  const history = trace.past.filter((beat) => beat.status[node] !== undefined);

  return (
    <Card className="animate-rise mt-4 p-[22px]">
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <h3 className="flex flex-wrap items-center gap-2.5 text-[17px] font-semibold tracking-[-0.012em]">
            {info.name}
            <Tag hot={state === "active"}>{STATE_LABEL[state]}</Tag>
          </h3>
          <p className="mt-1 text-ink-2">{info.role}</p>
        </div>
        <button type="button" onClick={onClose} className="text-[13px] font-medium text-ink-2 hover:text-ink">
          Close
        </button>
      </div>

      <dl className="mt-4 grid grid-cols-2 gap-x-6 gap-y-1 sm:grid-cols-[180px_minmax(0,1fr)]">
        <div>
          <dt className="text-[13px] text-ink-2">Kind</dt>
          <dd className="mt-px font-medium">{KIND_LABEL[info.kind]}</dd>
        </div>
        <div>
          <dt className="text-[13px] text-ink-2">Status</dt>
          <dd className="mt-px font-medium">{status}</dd>
        </div>
      </dl>

      {history.length > 0 && (
        <ol className="mt-4 border-t border-line pt-3">
          {history.map((beat) => (
            <li key={beat.t} className="flex justify-between gap-4 py-1">
              <span>{beat.status[node]}</span>
              <span className="flex-none text-ink-3 tabular-nums">{formatClock(beat.t)}</span>
            </li>
          ))}
        </ol>
      )}

      {node === "callback" && (
        <p className="mt-3 text-[12.5px] text-ink-2">The urgent callback phones the customer. It never calls emergency services.</p>
      )}
    </Card>
  );
}
