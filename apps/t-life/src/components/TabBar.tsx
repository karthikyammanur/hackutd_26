import type { ComponentType } from "react";
import { BagIcon, GiftIcon, GridIcon, HomeIcon, PersonIcon, SearchIcon } from "./icons";

export type Tab = "home" | "shop" | "benefits" | "services" | "account";

const TABS: { id: Tab; label: string; Icon: ComponentType<{ size?: number; strokeWidth?: number }> }[] = [
  { id: "home", label: "Home", Icon: HomeIcon },
  { id: "shop", label: "Shop", Icon: BagIcon },
  { id: "benefits", label: "Benefits", Icon: GiftIcon },
  { id: "services", label: "Services", Icon: GridIcon },
  { id: "account", label: "Account", Icon: PersonIcon },
];

export function TabBar({
  active,
  onSelect,
  onAsk,
}: {
  active: string;
  onSelect: (tab: Tab) => void;
  onAsk: () => void;
}) {
  return (
    <nav
      aria-label="Main"
      className="column-fixed bottom-0 z-20 flex items-center border-t border-line bg-white pb-[env(safe-area-inset-bottom)] pr-1.5"
    >
      {TABS.map(({ id, label, Icon }) => {
        const selected = active === id;
        return (
          <button
            key={id}
            type="button"
            onClick={() => onSelect(id)}
            aria-current={selected ? "page" : undefined}
            className={`flex h-[60px] min-w-0 flex-1 flex-col items-center justify-center gap-0.5 text-[11px] ${
              selected ? "font-semibold text-magenta" : "font-normal text-muted"
            }`}
          >
            <Icon size={24} strokeWidth={selected ? 2 : 1.6} />
            {label}
          </button>
        );
      })}
      <button
        type="button"
        onClick={onAsk}
        aria-label="Ask or search"
        className="ml-0.5 flex size-11 shrink-0 items-center justify-center rounded-full bg-page text-ink"
      >
        <SearchIcon size={22} />
      </button>
    </nav>
  );
}
