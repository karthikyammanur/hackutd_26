import { useState } from "react";
import type { RescoreRequest } from "@/lib/simulate/api";
import { PanelTitle, SideCard } from "../ui";
import { Lever } from "./RunControls";

const DEFAULTS: RescoreRequest = { dangerous_threshold: 0.5, uncertain_threshold: 0.2, require_hard_flag: false };

export function RescoreLevers({
  enabled,
  applied,
  error,
  onChange,
  onReset,
}: {
  enabled: boolean;
  applied: boolean;
  error: string | null;
  onChange: (request: RescoreRequest) => void;
  onReset: () => void;
}) {
  const [values, setValues] = useState(DEFAULTS);

  const update = (next: RescoreRequest) => {
    setValues(next);
    onChange(next);
  };
  const setDangerous = (value: number) =>
    update({ ...values, dangerous_threshold: value, uncertain_threshold: Math.min(values.uncertain_threshold, value) });
  const setUncertain = (value: number) =>
    update({ ...values, uncertain_threshold: value, dangerous_threshold: Math.max(values.dangerous_threshold, value) });

  return (
    <SideCard>
      <PanelTitle>Tune this run</PanelTitle>
      <p className="mt-1 text-[13px] text-ink-2">
        {enabled ? "Rescores saved frames without calling any model. Thresholds apply to each case's peak probability." : "Available when the run finishes."}
      </p>
      <fieldset disabled={!enabled} className="disabled:opacity-55">
        <Lever label="Dangerous at" value={values.dangerous_threshold.toFixed(2)}>
          <input className="mt-1 w-full accent-mag" type="range" min={0} max={1} step={0.01} value={values.dangerous_threshold} onChange={(e) => setDangerous(Number(e.target.value))} />
        </Lever>
        <Lever label="Uncertain at" value={values.uncertain_threshold.toFixed(2)}>
          <input className="mt-1 w-full accent-mag" type="range" min={0} max={1} step={0.01} value={values.uncertain_threshold} onChange={(e) => setUncertain(Number(e.target.value))} />
        </Lever>
        <label className="mt-3.5 flex items-center gap-2 text-[13px] text-ink-2">
          <input type="checkbox" className="size-4 accent-mag" checked={values.require_hard_flag} onChange={(e) => update({ ...values, require_hard_flag: e.target.checked })} />
          Require a hard red flag for dangerous
        </label>
      </fieldset>
      {applied && (
        <button
          onClick={() => {
            setValues(DEFAULTS);
            onReset();
          }}
          className="mt-3.5 text-[13px] font-medium text-mag-deep underline"
        >
          Back to the original scores
        </button>
      )}
      {error && (
        <p role="alert" className="mt-2.5 text-[13px] font-medium text-mag-deep">
          {error}
        </p>
      )}
    </SideCard>
  );
}
