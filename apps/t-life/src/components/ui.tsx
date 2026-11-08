import type { ComponentType, ReactNode } from "react";
import { BackIcon } from "./icons";

export function TabHeader({ title, actions }: { title: string; actions?: ReactNode }) {
  return (
    <header className="flex items-center justify-between px-5 pb-3 pt-[var(--top-clear)]">
      <h1 className="text-[18px] font-medium">{title}</h1>
      {actions && <div className="flex gap-3.5 text-ink">{actions}</div>}
    </header>
  );
}

export function PushedHeader({ title, onBack }: { title: string; onBack: () => void }) {
  return (
    <header className="relative flex items-center justify-center px-3 pb-2 pt-[var(--top-clear)]">
      <button
        type="button"
        onClick={onBack}
        aria-label="Back"
        className="absolute bottom-1 left-2 flex size-11 items-center justify-center rounded-lg"
      >
        <BackIcon size={22} />
      </button>
      <h1 className="py-2 text-[18px] font-semibold">{title}</h1>
    </header>
  );
}

export function SectionTitle({ children }: { children: ReactNode }) {
  return <h2 className="text-[18px] font-semibold">{children}</h2>;
}

/** Bottom padding clears the tab bar and the demo control. */
export function TabPage({ children, tone = "bg-white" }: { children: ReactNode; tone?: string }) {
  return <main className={`min-h-dvh pb-[calc(env(safe-area-inset-bottom)+132px)] ${tone}`}>{children}</main>;
}

export function ShortcutRow({ items }: { items: { label: string; Icon: ComponentType<{ size?: number }> }[] }) {
  return (
    <ul className="scroller -mx-5 mt-5 flex gap-3 overflow-x-auto px-5">
      {items.map(({ label, Icon }) => (
        <li
          key={label}
          className="flex h-[92px] w-[104px] shrink-0 flex-col justify-between rounded-xl border border-line bg-white p-3 text-[13px]"
        >
          <Icon size={24} />
          {label}
        </li>
      ))}
    </ul>
  );
}

export function StatusChip({ children, tone = "gray" }: { children: ReactNode; tone?: "gray" | "green" }) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded px-2 py-1 text-[12px] font-medium ${
        tone === "green" ? "bg-ok-soft text-ok" : "bg-page text-ink"
      }`}
    >
      <span aria-hidden="true" className="size-2 rounded-full bg-ok" />
      {children}
    </span>
  );
}
