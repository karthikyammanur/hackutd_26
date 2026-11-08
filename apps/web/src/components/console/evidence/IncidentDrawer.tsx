import { useEffect, useRef } from "react";
import { createPortal } from "react-dom";
import { useEvidence } from "@/hooks/useEvidence";
import { formatBucket, formatHour, label, risk, TIER_COLORS } from "@/lib/evidence/labels";
import { parseIncident } from "@/lib/evidence/parse";
import { familyLabel, flagLabel, humanize } from "@/lib/simulate/labels";
import { StatGrid, Tag } from "../ui";

function money(value: boolean | null): string {
  if (value === null) return "Unknown";
  return value ? "Yes" : "No";
}

export function IncidentDrawer({ id, onClose }: { id: string; onClose: () => void }) {
  const { settled: incident, error, loading } = useEvidence(`/incidents/${encodeURIComponent(id)}`, parseIncident);
  const panel = useRef<HTMLDivElement>(null);
  const close = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    const opener = document.activeElement as HTMLElement | null;
    close.current?.focus();
    return () => opener?.focus();
  }, []);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
      if (event.key !== "Tab" || !panel.current) return;
      const items = panel.current.querySelectorAll<HTMLElement>("button, a[href], summary, [tabindex='0']");
      if (!items.length) return;
      const firstItem = items[0];
      const lastItem = items[items.length - 1];
      if (event.shiftKey && document.activeElement === firstItem) {
        event.preventDefault();
        lastItem.focus();
      } else if (!event.shiftKey && document.activeElement === lastItem) {
        event.preventDefault();
        firstItem.focus();
      }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  return createPortal(
    <div className="fixed inset-0 z-50 flex justify-end">
      <button type="button" aria-label="Close incident" tabIndex={-1} onClick={onClose} className="absolute inset-0 cursor-default bg-black/25" />
      <div
        ref={panel}
        role="dialog"
        aria-modal="true"
        aria-label="Incident evidence packet"
        className="relative h-full w-full max-w-[520px] animate-rise overflow-y-auto bg-card p-5 shadow-soft sm:p-7"
      >
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <p className="text-[13px] text-ink-2">Evidence packet</p>
            <h2 className="text-lg font-semibold tracking-[-0.015em]">{incident ? label(incident.method) : "Incident"}</h2>
          </div>
          <button ref={close} type="button" onClick={onClose} className="rounded-full bg-sunk px-3 py-1.5 font-medium">
            Close
          </button>
        </div>

        <p className="mt-3 rounded-xl bg-sunk px-3.5 py-2.5 text-[13px] font-medium">No transcript, audio or personal data is stored.</p>

        {loading && <p className="mt-6 text-ink-2">Loading the packet</p>}
        {error && <p className="mt-6 text-mag-deep">This packet is unavailable: {error}</p>}

        {incident && (
          <div className="animate-rise">
            <div className="mt-4 flex flex-wrap gap-1.5">
              {incident.source === "sandbox_synthetic" && <Tag hot>Synthetic test data</Tag>}
              {incident.tier && <Tag>{humanize(incident.tier)}</Tag>}
              {incident.channel && <Tag>{humanize(incident.channel)}</Tag>}
            </div>

            <StatGrid
              items={[
                ["Occurred", formatHour(incident.occurredHour)],
                ["Family", incident.family ? familyLabel(incident.family) : "Unavailable"],
                ["Peak risk", risk(incident.maxRisk)],
                ["Predicted method", label(incident.predictedMethod)],
                ["First alert", formatBucket(incident.firstAlertBucketS)],
                ["Call length", formatBucket(incident.durationBucketS)],
                ["Money moved before alert", money(incident.moneyMovedBeforeAlert)],
                ["Test outcome", label(incident.outcome)],
                ["Model", incident.model ?? "Unavailable"],
                ["Repeat-source group", incident.callerCluster ? incident.callerCluster.slice(0, 12) : "None"],
              ]}
            />

            <h3 className="mt-6 font-semibold">Summary</h3>
            <p className="mt-1 text-ink-2">{incident.summary ?? "No summary was generated for this incident."}</p>
            <p className="mt-1 text-[12.5px] text-ink-3">Written from the indicators below, never from call content.</p>

            <h3 className="mt-6 font-semibold">Risk timeline</h3>
            {incident.timeline.length ? (
              <ol className="mt-2 space-y-2">
                {incident.timeline.map((step) => (
                  <li key={step.seq} className="grid grid-cols-[42px_84px_minmax(0,1fr)_38px] items-center gap-2 text-[13px]">
                    <span className="text-ink-2">{formatBucket(step.tBucketS)}</span>
                    <span className="flex items-center gap-1.5">
                      <i aria-hidden="true" className="size-2.5 flex-none rounded-[3px]" style={{ background: TIER_COLORS[step.tier ?? ""] ?? "#a8a8a8" }} />
                      {label(step.tier)}
                    </span>
                    <span className="block h-2 rounded-[3px] bg-sunk">
                      <i
                        className="block h-full rounded-[3px] transition-[width] duration-500 ease-slide"
                        style={{ width: `${(step.risk ?? 0) * 100}%`, background: TIER_COLORS[step.tier ?? ""] ?? "#a8a8a8" }}
                      />
                    </span>
                    <span className="text-right font-medium">{risk(step.risk)}</span>
                  </li>
                ))}
              </ol>
            ) : (
              <p className="mt-1 text-[13px] text-ink-3">No timeline was recorded for this incident.</p>
            )}

            <h3 className="mt-6 font-semibold">Signals fired</h3>
            {incident.signals.length ? (
              <ul className="mt-2 space-y-2">
                {[...incident.signals]
                  .sort((a, b) => (b.strength ?? 0) - (a.strength ?? 0))
                  .map((signal) => (
                    <li key={signal.signal} className="text-[13px]">
                      <div className="flex justify-between gap-3">
                        <span className="min-w-0">{flagLabel(signal.signal)}</span>
                        <span className="font-medium">{risk(signal.strength)}</span>
                      </div>
                      <div className="mt-1 h-1.5 rounded-[3px] bg-sunk">
                        <i className="block h-full rounded-[3px] bg-mag" style={{ width: `${(signal.strength ?? 0) * 100}%` }} />
                      </div>
                    </li>
                  ))}
              </ul>
            ) : (
              <p className="mt-1 text-[13px] text-ink-3">No signals were recorded for this incident.</p>
            )}
          </div>
        )}
      </div>
    </div>,
    document.body,
  );
}
