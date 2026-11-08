import { TIERS, type Tier } from "@/lib/console/call-model";

/** Four rising bars, filled up to the tier, so the tier never depends on color alone. */
export function TierGlyph({ tier }: { tier: Tier }) {
  return (
    <svg width="20" height="15" viewBox="0 0 20 15" aria-hidden="true" className="flex-none">
      {TIERS.map((name, index) => {
        const height = 5 + index * 3.3;
        return (
          <rect
            key={name}
            x={index * 5.25}
            y={15 - height}
            width="3.75"
            height={height}
            rx="1"
            fill={index <= tier ? "var(--color-mag)" : "var(--color-wire)"}
          />
        );
      })}
    </svg>
  );
}
