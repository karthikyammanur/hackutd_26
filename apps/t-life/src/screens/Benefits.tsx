import { useState, type ComponentType } from "react";
import { CupArt, SliceArt, SuitcaseArt, TicketArt } from "../components/art";
import { BookmarkIcon } from "../components/icons";
import { SectionTitle, TabPage } from "../components/ui";

type Art = ComponentType<{ className?: string }>;

const CATEGORIES: Record<string, { hero: string; perks: { title: string; note: string; Art: Art }[] }> = {
  Tuesdays: {
    hero: "TUES DAYS",
    perks: [
      { title: "Coffee on us", note: "New this week", Art: CupArt },
      { title: "A free slice", note: "This Tuesday only", Art: SliceArt },
    ],
  },
  Travel: {
    hero: "TRAV EL",
    perks: [{ title: "Weekend stay savings", note: "Sample travel offer", Art: SuitcaseArt }],
  },
  Dining: {
    hero: "DIN ING",
    perks: [{ title: "Lunch for less", note: "Sample dining offer", Art: SliceArt }],
  },
  Entertainment: {
    hero: "SHOW TIME",
    perks: [{ title: "Movie night", note: "Sample ticket offer", Art: TicketArt }],
  },
};

export function Benefits() {
  const names = Object.keys(CATEGORIES);
  const [active, setActive] = useState(names[0]);
  const category = CATEGORIES[active];
  const Lead = category.perks[0].Art;
  return (
    <TabPage>
      <div className="on-dark relative overflow-hidden bg-[linear-gradient(180deg,var(--color-plum)_0%,#c0006a_55%,var(--color-magenta)_78%,#ffffff_100%)] text-white">
        <header className="flex items-center justify-between px-5 pb-3 pt-[var(--top-clear)]">
          <h1 className="text-[18px] font-medium">Benefits</h1>
          <BookmarkIcon />
        </header>
        <div className="scroller flex gap-1.5 overflow-x-auto px-5" role="group" aria-label="Benefit categories">
          {names.map((name) => (
            <button
              key={name}
              type="button"
              aria-pressed={name === active}
              onClick={() => setActive(name)}
              className={`min-h-11 shrink-0 rounded-full px-3.5 text-[14px] ${
                name === active ? "bg-white font-medium text-ink" : "text-white"
              }`}
            >
              {name}
            </button>
          ))}
        </div>
        <div className="relative mt-3 h-[290px]">
          <div
            aria-hidden="true"
            className="absolute inset-x-0 top-1 select-none px-4 text-[136px] font-bold uppercase leading-[0.88] tracking-[-0.03em] text-white/[0.16]"
          >
            {category.hero.split(" ").map((line) => (
              <div key={line}>{line}</div>
            ))}
          </div>
          <div className="absolute left-[56%] top-16 flex size-[176px] -translate-x-1/2 items-center justify-center rounded-lg bg-magenta shadow-[0_10px_30px_rgb(0_0_0/0.28)]">
            <Lead className="size-[132px]" />
          </div>
        </div>
      </div>
      <section className="mt-3 px-5">
        <SectionTitle>Your perks</SectionTitle>
        <ul className="mt-3 flex flex-col gap-3">
          {category.perks.map(({ title, note, Art }) => (
            <li key={title} className="flex items-center justify-between rounded-xl bg-magenta p-4 text-white">
              <span>
                <span className="block text-[13px]">{note}</span>
                <span className="block text-[18px] font-semibold">{title}</span>
              </span>
              <Art className="size-16" />
            </li>
          ))}
        </ul>
      </section>
    </TabPage>
  );
}
