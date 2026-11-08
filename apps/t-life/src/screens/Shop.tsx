import { PhoneArt } from "../components/art";
import { AddPersonIcon, CartIcon, DeviceIcon, GridIcon } from "../components/icons";
import { SectionTitle, ShortcutRow, TabHeader, TabPage } from "../components/ui";

const CATEGORIES = ["Phones", "Accessories", "Tablets", "Watches"];
const COLORS = ["#6b7ec9", "#e5484d", "#3a403d"];

export function Shop() {
  return (
    <TabPage>
      <TabHeader title="Shop" actions={<CartIcon />} />
      <div className="px-5">
        <ShortcutRow
          items={[
            { label: "Upgrade", Icon: DeviceIcon },
            { label: "Add a line", Icon: AddPersonIcon },
            { label: "Bring device", Icon: GridIcon },
          ]}
        />
        <div className="mt-8">
          <SectionTitle>Browse by category</SectionTitle>
        </div>
        <ul className="scroller -mx-5 mt-3 flex gap-2.5 overflow-x-auto px-5">
          {CATEGORIES.map((category) => (
            <li key={category} className="shrink-0 rounded-full border border-line px-4 py-2.5 text-[14px]">
              {category}
            </li>
          ))}
        </ul>
        <article className="mt-7 flex gap-4 rounded-xl bg-white p-4 shadow-[0_2px_12px_rgb(0_0_0/0.12)]">
          <PhoneArt className="h-[132px] w-[96px] shrink-0" />
          <div className="min-w-0">
            <p className="text-[13px] text-muted">Sample brand</p>
            <h2 className="text-[18px] font-medium">Sample phone 5</h2>
            <div aria-hidden="true" className="mt-2 flex gap-2">
              {COLORS.map((color) => (
                <span key={color} className="size-5 rounded-full" style={{ background: color }} />
              ))}
            </div>
            <p className="mt-3 border-t border-line pt-2 text-[14px] font-medium">Starting at $XX.XX/month</p>
            <p className="mt-0.5 text-[13px] text-muted">Example pricing for the demo</p>
          </div>
        </article>
      </div>
    </TabPage>
  );
}
