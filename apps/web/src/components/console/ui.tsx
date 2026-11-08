import type { ReactNode } from "react";
import { Icon, type IconName } from "./icons";

export type Tint = "pink" | "sand" | "sage" | "blue" | "lilac" | "grey";

const TINTS: Record<Tint, string> = {
  pink: "bg-[#F4E1EA] text-[#A64F79]",
  sand: "bg-[#F0E7D6] text-[#94743A]",
  sage: "bg-[#E2EADB] text-[#5C7A48]",
  blue: "bg-[#DFE7F2] text-[#4B6E9E]",
  lilac: "bg-[#E7E2F2] text-[#6A5A9C]",
  grey: "bg-[#E8E8E8] text-[#555555]",
};

export function Tile({ icon, tint }: { icon: IconName; tint: Tint }) {
  return (
    <span className={`grid size-8 flex-none place-items-center rounded-[9px] ${TINTS[tint]}`}>
      <Icon name={icon} />
    </span>
  );
}

export function Tag({ hot = false, children }: { hot?: boolean; children: ReactNode }) {
  return (
    <span
      className={`inline-block rounded-full px-2 py-px text-xs font-medium whitespace-nowrap ${
        hot ? "bg-mag-wash text-mag-deep" : "bg-sunk text-ink-2"
      }`}
    >
      {children}
    </span>
  );
}

export function Card({ className = "", children }: { className?: string; children: ReactNode }) {
  return <div className={`rounded-[18px] bg-card shadow-soft ${className}`}>{children}</div>;
}

export function SideCard({ className = "", children }: { className?: string; children: ReactNode }) {
  return <Card className={`mt-5 p-[22px] ${className}`}>{children}</Card>;
}

export function PanelTitle({ children }: { children: ReactNode }) {
  return <h3 className="text-[17px] font-semibold tracking-[-0.012em]">{children}</h3>;
}

export function SectionTitle({ children }: { children: ReactNode }) {
  return <h2 className="text-[17px] font-semibold tracking-[-0.012em]">{children}</h2>;
}

export function Columns({ children }: { children: ReactNode }) {
  return (
    <div className="grid grid-cols-[minmax(0,1fr)] gap-12 min-[1241px]:grid-cols-[minmax(0,1fr)_340px]">{children}</div>
  );
}

export function StatGrid({ items }: { items: [string, string | number][] }) {
  return (
    <dl className="mt-[18px] grid grid-cols-2 gap-x-4 gap-y-3.5">
      {items.map(([label, value]) => (
        <div key={label}>
          <dt className="text-[13px] text-ink-2">{label}</dt>
          <dd className="mt-px font-medium">{value}</dd>
        </div>
      ))}
    </dl>
  );
}
